import asyncio
import json
import os
import re
import time
import uuid
import shutil
import traceback
from typing import Awaitable, Dict, List, Any
from fastapi.responses import JSONResponse, FileResponse
from gpt_researcher.document.document import DocumentLoader
from gpt_researcher import GPTResearcher
from utils import write_md_to_pdf, write_md_to_word, write_text_to_md
from pathlib import Path
from datetime import datetime
from fastapi import HTTPException, WebSocketDisconnect
import logging
import hashlib

from .multi_agent_runner import run_multi_agent_task
from gpt_researcher.orchestration.outline_schema import (
    ReportBlueprint,
    ResearchOutline,
    build_blueprint_from_outline,
)
from gpt_researcher.skills.research_planner import (
    generate_outline,
    normalize_blueprint_payload,
    normalize_outline_payload,
    revise_outline,
    validate_outline,
)

# Import chat agent
try:
    import sys
    backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    from chat.chat import ChatAgentWithMemory
except ImportError:
    ChatAgentWithMemory = None

logger = logging.getLogger(__name__)

ALLOWED_REPORT_STYLES = {"strategic_report", "consulting_brief"}
ALLOWED_SOURCE_POLICIES = {"strict_tier", "medium_tier", "broad_collect"}


def _is_ws_closed_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        isinstance(exc, WebSocketDisconnect)
        or "cannot call \"send\" once a close message has been sent" in message
        or "connection closed" in message
        or "clientdisconnected" in message
        or "websocketdisconnect" in message
    )


async def _safe_websocket_send_json(websocket, data: Dict[str, Any], *, context: str = "") -> bool:
    try:
        await websocket.send_json(data)
        return True
    except Exception as e:
        if _is_ws_closed_error(e):
            if not getattr(websocket, "_gptr_disconnected_logged", False):
                logger.info(
                    "WebSocket disconnected while sending JSON%s: %s",
                    f" ({context})" if context else "",
                    e,
                )
                try:
                    setattr(websocket, "_gptr_disconnected_logged", True)
                except Exception:
                    pass
        else:
            logger.error(
                "WebSocket JSON send failed%s: %s\n%s",
                f" ({context})" if context else "",
                e,
                traceback.format_exc(),
            )
        return False


async def _safe_websocket_send_text(websocket, data: str, *, context: str = "") -> bool:
    try:
        await websocket.send_text(data)
        return True
    except Exception as e:
        if _is_ws_closed_error(e):
            if not getattr(websocket, "_gptr_disconnected_logged", False):
                logger.info(
                    "WebSocket disconnected while sending text%s: %s",
                    f" ({context})" if context else "",
                    e,
                )
                try:
                    setattr(websocket, "_gptr_disconnected_logged", True)
                except Exception:
                    pass
        else:
            logger.error(
                "WebSocket text send failed%s: %s\n%s",
                f" ({context})" if context else "",
                e,
                traceback.format_exc(),
            )
        return False

class CustomLogsHandler:
    """Custom handler to capture streaming logs from the research process"""
    def __init__(self, websocket, task: str):
        self.logs = []
        self.websocket = websocket
        sanitized_filename = sanitize_filename(f"task_{int(time.time())}_{task}")
        self.log_file = os.path.join("outputs", f"{sanitized_filename}.json")
        self.timestamp = datetime.now().isoformat()
        self._ws_available = True
        # Initialize log file with metadata
        os.makedirs("outputs", exist_ok=True)
        with open(self.log_file, 'w') as f:
            json.dump({
                "timestamp": self.timestamp,
                "events": [],
                "content": {
                    "query": "",
                    "sources": [],
                    "context": [],
                    "report": "",
                    "costs": 0.0
                }
            }, f, indent=2)

    async def send_json(self, data: Dict[str, Any]) -> None:
        """Store log data and send to websocket"""
        # Send to websocket for real-time display
        if self.websocket and self._ws_available:
            sent = await _safe_websocket_send_json(self.websocket, data, context="CustomLogsHandler")
            if not sent:
                self._ws_available = False
            
        # Read current log file
        with open(self.log_file, 'r') as f:
            log_data = json.load(f)
            
        # Update appropriate section based on data type
        if data.get('type') == 'logs':
            log_data['events'].append({
                "timestamp": datetime.now().isoformat(),
                "type": "event",
                "data": data
            })
        else:
            # Update content section for other types of data
            log_data['content'].update(data)
            
        # Save updated log file
        with open(self.log_file, 'w') as f:
            json.dump(log_data, f, indent=2)


class Researcher:
    def __init__(self, query: str, report_type: str = "research_report"):
        self.query = query
        self.report_type = report_type
        # Generate unique ID for this research task
        self.research_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(query)}"
        # Initialize logs handler with research ID
        self.logs_handler = CustomLogsHandler(None, self.research_id)
        self.researcher = GPTResearcher(
            query=query,
            report_type=report_type,
            websocket=self.logs_handler
        )

    async def research(self) -> dict:
        """Conduct research and return paths to generated files"""
        await self.researcher.conduct_research()
        report = await self.researcher.write_report()
        
        # Generate the files
        sanitized_filename = sanitize_filename(f"task_{int(time.time())}_{self.query}")
        file_paths = await generate_report_files(report, sanitized_filename)
        
        # Get the JSON log path that was created by CustomLogsHandler
        json_relative_path = os.path.relpath(self.logs_handler.log_file)
        
        return {
            "output": {
                **file_paths,  # Include PDF, DOCX, and MD paths
                "json": json_relative_path
            }
        }

def sanitize_filename(filename: str) -> str:
    # Split into components
    prefix, timestamp, *task_parts = filename.split('_')
    task = '_'.join(task_parts)
    task_hash = hashlib.md5(task.encode('utf-8', errors='ignore')).hexdigest()[:10]
            
    # Reassemble and clean the filename
    sanitized = f"{prefix}_{timestamp}_{task_hash}"
    return re.sub(r"[^\w\s-]", "", sanitized).strip()


def _parse_command_payload(data: str, command: str) -> dict[str, Any]:
    prefix = f"{command} "
    if not data.strip().startswith(prefix):
        raise ValueError(f"Invalid command payload for '{command}'")
    payload_raw = data.strip()[len(prefix):].strip()
    if not payload_raw:
        return {}
    return json.loads(payload_raw)


def _serialize_outline_payload(
    outline: ResearchOutline,
    blueprint: ReportBlueprint,
    *,
    message_type: str,
    report_style: str = "strategic_report",
    source_policy: str = "medium_tier",
) -> dict[str, Any]:
    return {
        "type": message_type,
        "content": message_type,
        "outline_id": outline.outline_id,
        "outline": outline.to_dict(),
        "report_blueprint": blueprint.to_dict(),
        "report_style": report_style,
        "source_policy": source_policy,
        "output": {
            "outline_id": outline.outline_id,
            "outline": outline.to_dict(),
            "report_blueprint": blueprint.to_dict(),
            "report_style": report_style,
            "source_policy": source_policy,
        },
    }


def _normalize_report_style(raw_value: Any) -> str:
    value = str(raw_value or "strategic_report").strip().lower()
    return value if value in ALLOWED_REPORT_STYLES else "strategic_report"


def _normalize_source_policy(raw_value: Any) -> str:
    value = str(raw_value or "medium_tier").strip().lower()
    return value if value in ALLOWED_SOURCE_POLICIES else "medium_tier"


def _extract_query_keywords(query: str) -> list[str]:
    raw_tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_-]{2,}", str(query or ""))
    stopwords = {
        "what", "when", "where", "which", "who", "why", "how", "the", "and", "for", "with",
        "from", "that", "this", "are", "was", "were", "will", "into", "about", "research",
        "report", "analysis", "deep", "adaptive",
        "什么", "如何", "哪些", "以及", "关于", "研究", "报告", "分析",
    }
    deduped: list[str] = []
    seen: set[str] = set()
    for token in raw_tokens:
        key = token.strip().lower()
        if not key or key in stopwords:
            continue
        if key in seen:
            continue
        seen.add(key)
        deduped.append(token.strip())
    return deduped[:12]


def _outline_text_for_alignment(outline: ResearchOutline) -> str:
    parts: list[str] = []
    parts.extend([outline.query, outline.objective, getattr(outline, "scope", "")])
    for ws in getattr(outline, "workstreams", []) or []:
        if isinstance(ws, dict):
            parts.extend(
                [
                    str(ws.get("title") or ""),
                    str(ws.get("intent") or ""),
                    str(ws.get("deliverable") or ""),
                ]
            )
        else:
            parts.append(str(ws))
    return " ".join(parts).lower()


def _contains_recommendation_deliverable(outline: ResearchOutline) -> bool:
    deliverables = [str(item).strip().lower() for item in (getattr(outline, "deliverables", []) or []) if str(item).strip()]
    if not deliverables:
        return False
    recommendation_tokens = (
        "recommend", "recommendation", "action", "roadmap", "strategy", "proposal", "plan",
        "建议", "行动", "路线图", "策略", "方案", "落地", "优先级",
    )
    return any(any(token in item for token in recommendation_tokens) for item in deliverables)


def _validate_outline_for_execution(outline: ResearchOutline, query: str) -> list[str]:
    errors: list[str] = []

    stage_set = {section.stage for section in outline.sections}
    missing_stages = [stage for stage in ("foundation", "evidence", "judgement") if stage not in stage_set]
    if missing_stages:
        errors.append(f"Missing required section stages: {', '.join(missing_stages)}")

    workstreams = getattr(outline, "workstreams", []) or []
    if not workstreams:
        errors.append("workstreams must not be empty.")
    else:
        keywords = _extract_query_keywords(query or outline.query)
        if keywords:
            plan_text = _outline_text_for_alignment(outline)
            matched = [kw for kw in keywords if kw.lower() in plan_text]
            if not matched:
                errors.append("workstreams do not appear aligned with query keywords.")

    if not _contains_recommendation_deliverable(outline):
        errors.append("deliverables must include concrete recommendation output.")

    return errors


async def handle_start_command(
    websocket,
    data: str,
    manager,
    *,
    start_payload: dict[str, Any] | None = None,
    research_outline: dict[str, Any] | None = None,
    report_blueprint: dict[str, Any] | None = None,
    outline_locked: bool = False,
    user_requirements: str | None = None,
):
    json_data = start_payload if start_payload is not None else _parse_command_payload(data, "start")
    (
        task,
        report_type,
        source_urls,
        document_urls,
        tone,
        language,
        headers,
        report_source,
        query_domains,
        mcp_enabled,
        mcp_strategy,
        mcp_configs,
        word_fonts,
        report_style,
        source_policy,
    ) = extract_command_data(json_data)

    if not task or not report_type:
        print("Error: Missing task or report_type")
        return

    # Create logs handler with websocket and task
    logs_handler = CustomLogsHandler(websocket, task)
    # Initialize log content with query
    await logs_handler.send_json({
        "query": task,
        "sources": [],
        "context": [],
        "report": ""
    })

    sanitized_filename = sanitize_filename(f"task_{int(time.time())}_{task}")

    report = await manager.start_streaming(
        task,
        report_type,
        report_source,
        source_urls,
        document_urls,
        tone,
        websocket,
        headers,
        query_domains,
        language,
        mcp_enabled,
        mcp_strategy,
        mcp_configs,
        research_outline=research_outline,
        report_blueprint=report_blueprint,
        outline_locked=outline_locked,
        user_requirements=user_requirements,
        report_style=report_style,
        source_policy=source_policy,
    )
    report = str(report)
    file_paths = await generate_report_files(report, sanitized_filename, word_fonts=word_fonts)
    # Add JSON log path to file_paths
    file_paths["json"] = os.path.relpath(logs_handler.log_file)
    await send_file_paths(websocket, file_paths)


async def handle_start_plan_command(
    websocket,
    data: str,
    manager,
    outline_session: dict[str, dict[str, Any]],
):
    payload = _parse_command_payload(data, "start_plan")
    task = str(payload.get("task") or "").strip()
    report_type = str(payload.get("report_type") or "").strip()
    user_requirements = str(payload.get("user_requirements") or "").strip() or None
    language = payload.get("language")
    report_style = _normalize_report_style(payload.get("report_style"))
    source_policy = _normalize_source_policy(payload.get("source_policy"))

    if not task:
        await _safe_websocket_send_json(
            websocket,
            {"type": "error", "content": "error", "output": "Missing task in start_plan command."},
            context="start-plan/missing-task",
        )
        return

    if report_type and report_type != "adaptive_deep":
        await _safe_websocket_send_json(
            websocket,
            {
                "type": "logs",
                "content": "warning",
                "output": "start_plan is designed for adaptive_deep. Falling back to direct execution for this report_type.",
            },
            context="start-plan/non-adaptive-warning",
        )
        await handle_start_command(websocket, data, manager, start_payload=payload)
        return

    outline, blueprint = await generate_outline(
        query=task,
        user_requirements=user_requirements,
        language=language,
        report_style=report_style,
        source_policy=source_policy,
    )

    if not outline.outline_id:
        outline.outline_id = uuid.uuid4().hex

    payload["report_style"] = report_style
    payload["source_policy"] = source_policy
    outline_session[outline.outline_id] = {
        "outline": outline.to_dict(),
        "report_blueprint": blueprint.to_dict(),
        "start_payload": payload,
        "user_requirements": user_requirements,
        "language": language,
        "report_style": report_style,
        "source_policy": source_policy,
    }

    await _safe_websocket_send_json(
        websocket,
        _serialize_outline_payload(
            outline,
            blueprint,
            message_type="outline_draft",
            report_style=report_style,
            source_policy=source_policy,
        ),
        context="start-plan/outline-draft",
    )


async def handle_revise_plan_command(
    websocket,
    data: str,
    outline_session: dict[str, dict[str, Any]],
):
    payload = _parse_command_payload(data, "revise_plan")
    outline_id = str(payload.get("outline_id") or "").strip()
    mode = str(payload.get("mode") or "").strip() or "ai_rewrite"

    if not outline_id or outline_id not in outline_session:
        await _safe_websocket_send_json(
            websocket,
            {"type": "error", "content": "error", "output": "Unknown outline_id. Please generate a plan first."},
            context="revise-plan/outline-not-found",
        )
        return

    state = outline_session[outline_id]
    current_outline = normalize_outline_payload(state.get("outline") or {}, query_hint=(state.get("start_payload") or {}).get("task"))
    current_blueprint = normalize_blueprint_payload(state.get("report_blueprint") or {}, outline=current_outline)
    language = payload.get("language") or state.get("language")
    report_style = _normalize_report_style(payload.get("report_style") or state.get("report_style"))
    source_policy = _normalize_source_policy(payload.get("source_policy") or state.get("source_policy"))

    if mode == "manual_replace":
        manual_outline = payload.get("manual_outline")
        if not isinstance(manual_outline, dict):
            await _safe_websocket_send_json(
                websocket,
                {"type": "error", "content": "error", "output": "manual_replace mode requires a full manual_outline object."},
                context="revise-plan/manual-outline-missing",
            )
            return
        revised_outline = normalize_outline_payload(
            {
                **manual_outline,
                "outline_id": outline_id,
                "query": current_outline.query,
            },
            query_hint=current_outline.query,
        )
        blueprint_payload = payload.get("report_blueprint")
        if isinstance(blueprint_payload, dict):
            revised_blueprint = normalize_blueprint_payload(blueprint_payload, outline=revised_outline)
        else:
            revised_blueprint = build_blueprint_from_outline(revised_outline)
    else:
        instruction = str(payload.get("instruction") or "").strip()
        revised_outline, revised_blueprint = await revise_outline(
            outline=current_outline,
            instruction=instruction,
            language=language,
            report_style=report_style,
            source_policy=source_policy,
        )
        revised_outline.outline_id = outline_id
        if isinstance(payload.get("report_blueprint"), dict):
            revised_blueprint = normalize_blueprint_payload(payload["report_blueprint"], outline=revised_outline)
        elif not revised_blueprint:
            revised_blueprint = current_blueprint

    valid, errors = validate_outline(revised_outline)
    if not valid:
        await _safe_websocket_send_json(
            websocket,
            {"type": "error", "content": "error", "output": f"Outline validation failed: {', '.join(errors)}"},
            context="revise-plan/validation-failed",
        )
        return

    state["outline"] = revised_outline.to_dict()
    state["report_blueprint"] = revised_blueprint.to_dict()
    state["language"] = language
    state["report_style"] = report_style
    state["source_policy"] = source_policy

    await _safe_websocket_send_json(
        websocket,
        _serialize_outline_payload(
            revised_outline,
            revised_blueprint,
            message_type="outline_updated",
            report_style=report_style,
            source_policy=source_policy,
        ),
        context="revise-plan/outline-updated",
    )


async def handle_execute_plan_command(
    websocket,
    data: str,
    manager,
    outline_session: dict[str, dict[str, Any]],
):
    payload = _parse_command_payload(data, "execute_plan")
    outline_id = str(payload.get("outline_id") or "").strip()
    if not outline_id or outline_id not in outline_session:
        await _safe_websocket_send_json(
            websocket,
            {"type": "error", "content": "error", "output": "Unknown outline_id. Please start_plan first."},
            context="execute-plan/outline-not-found",
        )
        return

    state = outline_session[outline_id]
    start_payload = dict(state.get("start_payload") or {})
    start_payload.update({k: v for k, v in payload.items() if k in {
        "task",
        "report_type",
        "source_urls",
        "document_urls",
        "tone",
        "language",
        "headers",
        "report_source",
        "query_domains",
        "mcp_enabled",
        "mcp_strategy",
        "mcp_configs",
        "word_fonts",
        "report_style",
        "source_policy",
    }})
    start_payload["report_style"] = _normalize_report_style(
        start_payload.get("report_style") or state.get("report_style")
    )
    start_payload["source_policy"] = _normalize_source_policy(
        start_payload.get("source_policy") or state.get("source_policy")
    )

    approved_outline_payload = payload.get("approved_outline")
    if isinstance(approved_outline_payload, dict):
        final_outline = normalize_outline_payload(
            {
                **approved_outline_payload,
                "outline_id": outline_id,
                "query": start_payload.get("task") or approved_outline_payload.get("query"),
            },
            query_hint=start_payload.get("task"),
        )
    else:
        final_outline = normalize_outline_payload(state.get("outline") or {}, query_hint=start_payload.get("task"))

    blueprint_payload = payload.get("report_blueprint")
    if isinstance(blueprint_payload, dict):
        final_blueprint = normalize_blueprint_payload(blueprint_payload, outline=final_outline)
    else:
        final_blueprint = normalize_blueprint_payload(state.get("report_blueprint") or {}, outline=final_outline)

    valid, errors = validate_outline(final_outline)
    execution_errors = _validate_outline_for_execution(final_outline, str(start_payload.get("task") or final_outline.query))
    if (not valid) or execution_errors:
        merged_errors = list(errors)
        merged_errors.extend(execution_errors)
        await _safe_websocket_send_json(
            websocket,
            {
                "type": "outline_validation_error",
                "content": "outline_validation_error",
                "output": f"Outline validation failed: {', '.join(merged_errors)}",
                "errors": merged_errors,
            },
            context="execute-plan/validation-failed",
        )
        return

    state["outline"] = final_outline.to_dict()
    state["report_blueprint"] = final_blueprint.to_dict()
    state["start_payload"] = start_payload
    state["user_requirements"] = payload.get("user_requirements") or state.get("user_requirements")
    state["report_style"] = start_payload.get("report_style")
    state["source_policy"] = start_payload.get("source_policy")

    await handle_start_command(
        websocket,
        "",
        manager,
        start_payload=start_payload,
        research_outline=final_outline.to_dict(),
        report_blueprint=final_blueprint.to_dict(),
        outline_locked=True,
        user_requirements=state.get("user_requirements"),
    )


async def handle_human_feedback(data: str):
    feedback_data = json.loads(data[14:])  # Remove "human_feedback" prefix
    print(f"Received human feedback: {feedback_data}")
    # TODO: Add logic to forward the feedback to the appropriate agent or update the research state


async def handle_chat_command(websocket, data: str):
    """Handle chat command from WebSocket."""
    try:
        # Parse chat data - format is "chat {json_data}"
        json_str = data[5:].strip()  # Remove "chat " prefix
        chat_data = json.loads(json_str)
        
        message = chat_data.get("message", "")
        report = chat_data.get("report", "")
        messages = chat_data.get("messages", [])
        
        # If only message is provided, convert to messages format
        if message and not messages:
            messages = [{"role": "user", "content": message}]
        
        if not messages:
            await _safe_websocket_send_json(websocket, {
                "type": "chat",
                "content": "No message provided.",
                "role": "assistant"
            }, context="chat/no-message")
            return
        
        # Check if ChatAgentWithMemory is available
        if ChatAgentWithMemory is None:
            await _safe_websocket_send_json(websocket, {
                "type": "chat",
                "content": "Chat functionality is not available. Please check the server configuration.",
                "role": "assistant"
            }, context="chat/unavailable")
            return
        
        # Create chat agent with the report context
        chat_agent = ChatAgentWithMemory(
            report=report,
            config_path="default",
            headers=None
        )
        
        # Process the chat
        response_content, tool_calls_metadata = await chat_agent.chat(messages, websocket)
        
        # Send response back via WebSocket
        await _safe_websocket_send_json(websocket, {
            "type": "chat",
            "content": response_content,
            "role": "assistant",
            "metadata": {
                "tool_calls": tool_calls_metadata
            } if tool_calls_metadata else None
        }, context="chat/response")
        
        logger.info(f"Chat response sent successfully")
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse chat data: {e}")
        await _safe_websocket_send_json(websocket, {
            "type": "chat",
            "content": f"Error: Invalid message format - {str(e)}",
            "role": "assistant"
        }, context="chat/json-decode-error")
    except Exception as e:
        logger.error(f"Error handling chat command: {e}\n{traceback.format_exc()}")
        await _safe_websocket_send_json(websocket, {
            "type": "chat",
            "content": f"Error processing your message: {str(e)}",
            "role": "assistant"
        }, context="chat/unhandled-error")

async def generate_report_files(report: str, filename: str, word_fonts: List[str] | None = None) -> Dict[str, str]:
    pdf_path = await write_md_to_pdf(report, filename)
    docx_path = await write_md_to_word(report, filename, word_fonts=word_fonts)
    md_path = await write_text_to_md(report, filename)
    return {"pdf": pdf_path, "docx": docx_path, "md": md_path}


async def send_file_paths(websocket, file_paths: Dict[str, str]):
    await _safe_websocket_send_json(
        websocket,
        {"type": "path", "output": file_paths},
        context="send-file-paths",
    )


def get_config_dict(
    langchain_api_key: str, openai_api_key: str, tavily_api_key: str,
    google_api_key: str, google_cx_key: str, bing_api_key: str,
    searchapi_api_key: str, serpapi_api_key: str, serper_api_key: str, searx_url: str
) -> Dict[str, str]:
    return {
        "LANGCHAIN_API_KEY": langchain_api_key or os.getenv("LANGCHAIN_API_KEY", ""),
        "OPENAI_API_KEY": openai_api_key or os.getenv("OPENAI_API_KEY", ""),
        "TAVILY_API_KEY": tavily_api_key or os.getenv("TAVILY_API_KEY", ""),
        "GOOGLE_API_KEY": google_api_key or os.getenv("GOOGLE_API_KEY", ""),
        "GOOGLE_CX_KEY": google_cx_key or os.getenv("GOOGLE_CX_KEY", ""),
        "BING_API_KEY": bing_api_key or os.getenv("BING_API_KEY", ""),
        "SEARCHAPI_API_KEY": searchapi_api_key or os.getenv("SEARCHAPI_API_KEY", ""),
        "SERPAPI_API_KEY": serpapi_api_key or os.getenv("SERPAPI_API_KEY", ""),
        "SERPER_API_KEY": serper_api_key or os.getenv("SERPER_API_KEY", ""),
        "SEARX_URL": searx_url or os.getenv("SEARX_URL", ""),
        "LANGCHAIN_TRACING_V2": os.getenv("LANGCHAIN_TRACING_V2", "true"),
        "DOC_PATH": os.getenv("DOC_PATH", "./my-docs"),
        "RETRIEVER": os.getenv("RETRIEVER", ""),
        "EMBEDDING_MODEL": os.getenv("OPENAI_EMBEDDING_MODEL", "")
    }


def update_environment_variables(config: Dict[str, str]):
    for key, value in config.items():
        os.environ[key] = value


async def handle_file_upload(file, DOC_PATH: str) -> Dict[str, str]:
    file_path = os.path.join(DOC_PATH, os.path.basename(file.filename))
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    print(f"File uploaded to {file_path}")

    document_loader = DocumentLoader(DOC_PATH)
    await document_loader.load()

    return {"filename": file.filename, "path": file_path}


async def handle_file_deletion(filename: str, DOC_PATH: str) -> JSONResponse:
    file_path = os.path.join(DOC_PATH, os.path.basename(filename))
    if os.path.exists(file_path):
        os.remove(file_path)
        print(f"File deleted: {file_path}")
        return JSONResponse(content={"message": "File deleted successfully"})
    else:
        print(f"File not found: {file_path}")
        return JSONResponse(status_code=404, content={"message": "File not found"})


async def execute_multi_agents(manager) -> Any:
    websocket = manager.active_connections[0] if manager.active_connections else None
    if websocket:
        report = await run_multi_agent_task("Is AI in a hype cycle?", websocket, stream_output)
        return {"report": report}
    else:
        return JSONResponse(status_code=400, content={"message": "No active WebSocket connection"})


async def handle_websocket_communication(websocket, manager):
    running_task: asyncio.Task | None = None
    outline_session: dict[str, dict[str, Any]] = {}

    def run_long_running_task(awaitable: Awaitable) -> asyncio.Task:
        async def safe_run():
            try:
                await awaitable
            except asyncio.CancelledError:
                logger.info("Task cancelled.")
                raise
            except Exception as e:
                logger.error(f"Error running task: {e}\n{traceback.format_exc()}")
                await _safe_websocket_send_json(
                    websocket,
                    {
                        "type": "logs",
                        "content": "error",
                        "output": f"Error: {e}",
                    },
                    context="task-error",
                )

        return asyncio.create_task(safe_run())

    try:
        while True:
            try:
                data = await websocket.receive_text()
                logger.info(f"Received WebSocket message: {data[:50]}..." if len(data) > 50 else data)
                
                if data == "ping":
                    sent = await _safe_websocket_send_text(websocket, "pong", context="ping")
                    if not sent:
                        break
                elif running_task and not running_task.done():
                    # discard any new request if a task is already running
                    logger.warning(
                        f"Received request while task is already running. Request data preview: {data[: min(20, len(data))]}..."
                    )
                    sent = await _safe_websocket_send_json(
                        websocket,
                        {
                            "type": "logs",
                            "content": "warning",
                            "output": "Task already running. Please wait.",
                        },
                        context="task-already-running",
                    )
                    if not sent:
                        break
                # Normalize command detection by checking startswith after stripping whitespace
                elif data.strip().startswith("start_plan"):
                    logger.info("Processing start_plan command")
                    running_task = run_long_running_task(
                        handle_start_plan_command(websocket, data, manager, outline_session)
                    )
                elif data.strip().startswith("revise_plan"):
                    logger.info("Processing revise_plan command")
                    running_task = run_long_running_task(
                        handle_revise_plan_command(websocket, data, outline_session)
                    )
                elif data.strip().startswith("execute_plan"):
                    logger.info("Processing execute_plan command")
                    running_task = run_long_running_task(
                        handle_execute_plan_command(websocket, data, manager, outline_session)
                    )
                elif data.strip().startswith("start"):
                    logger.info(f"Processing start command")
                    running_task = run_long_running_task(
                        handle_start_command(websocket, data, manager)
                    )
                elif data.strip().startswith("human_feedback"):
                    logger.info(f"Processing human_feedback command")
                    running_task = run_long_running_task(handle_human_feedback(data))
                elif data.strip().startswith("chat"):
                    logger.info(f"Processing chat command")
                    running_task = run_long_running_task(handle_chat_command(websocket, data))
                else:
                    error_msg = f"Error: Unknown command or not enough parameters provided. Received: '{data[:100]}...'" if len(data) > 100 else f"Error: Unknown command or not enough parameters provided. Received: '{data}'"
                    logger.error(error_msg)
                    print(error_msg)
                    sent = await _safe_websocket_send_json(websocket, {
                        "type": "error",
                        "content": "error",
                        "output": "Unknown command received by server"
                    }, context="unknown-command")
                    if not sent:
                        break
            except WebSocketDisconnect as e:
                logger.info(f"WebSocket disconnected during receive loop. code={e.code}, reason='{e.reason}'")
                break
            except Exception as e:
                if _is_ws_closed_error(e):
                    logger.info(f"WebSocket closed in communication loop: {e}")
                else:
                    logger.error(f"WebSocket error: {str(e)}\n{traceback.format_exc()}")
                    print(f"WebSocket error: {e}")
                break
    finally:
        if running_task and not running_task.done():
            running_task.cancel()
            try:
                await running_task
            except asyncio.CancelledError:
                pass

def extract_command_data(json_data: Dict) -> tuple:
    return (
        json_data.get("task"),
        json_data.get("report_type"),
        json_data.get("source_urls"),
        json_data.get("document_urls"),
        json_data.get("tone"),
        json_data.get("language"),
        json_data.get("headers", {}),
        json_data.get("report_source"),
        json_data.get("query_domains", []),
        json_data.get("mcp_enabled", False),
        json_data.get("mcp_strategy", "fast"),
        json_data.get("mcp_configs", []),
        json_data.get("word_fonts", []),
        _normalize_report_style(json_data.get("report_style")),
        _normalize_source_policy(json_data.get("source_policy")),
    )
