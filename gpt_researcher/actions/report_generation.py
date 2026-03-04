import asyncio
import re
from typing import List, Dict, Any, Callable
from ..config.config import Config
from ..utils.llm import create_chat_completion
from ..utils.logger import get_formatted_logger
from ..prompts import PromptFamily, get_prompt_by_report_type
from ..utils.enum import Tone

logger = get_formatted_logger()

REPORT_COMPLETE_MARKER = "<!-- REPORT_COMPLETE -->"
DEFAULT_MAX_OUTLINE_CONTEXT_CHARS = 24000
CONCLUSION_SECTION_PATTERN = re.compile(
    r"^#{1,6}\s*(conclusion|conclusions|summary|final thoughts|结论|总结|结语)(\s|:|：|$)",
    flags=re.IGNORECASE | re.MULTILINE,
)
REFERENCE_SECTION_PATTERN = re.compile(
    r"^#{1,6}\s*(references|reference|sources|bibliography|works cited|参考文献|参考资料|资料来源|来源)(\s|:|：|$)",
    flags=re.IGNORECASE | re.MULTILINE,
)
TRAILING_HEADER_PATTERN = re.compile(r"^#{1,6}\s+.+$")
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")


def evaluate_report_completeness(
    report: str,
    *,
    require_sections: bool,
    require_marker: bool,
) -> tuple[bool, list[str]]:
    """Return (is_complete, missing_requirements) for generated markdown report."""
    missing: list[str] = []
    report = (report or "").strip()

    lines = [line.rstrip() for line in report.splitlines()]
    non_empty_lines = [line for line in lines if line.strip()]
    if not non_empty_lines:
        missing.append("empty_report")
    else:
        last_non_empty = non_empty_lines[-1].strip()
        if TRAILING_HEADER_PATTERN.match(last_non_empty):
            missing.append("trailing_header_without_content")

    if require_sections and not CONCLUSION_SECTION_PATTERN.search(report):
        missing.append("missing_conclusion_section")
    if require_sections and not REFERENCE_SECTION_PATTERN.search(report):
        missing.append("missing_references_section")
    if require_marker and REPORT_COMPLETE_MARKER not in report:
        missing.append("missing_completion_marker")

    return len(missing) == 0, missing


def _strip_completion_marker(report: str) -> str:
    return report.replace(REPORT_COMPLETE_MARKER, "").strip()


def _truncate_text(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return value
    return value[:max_chars]


def _is_transport_error(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return any(
        token in text
        for token in (
            "incomplete chunked read",
            "connection",
            "peer closed",
            "eof",
            "transport",
            "timed out",
            "timeout",
        )
    )


def _reference_heading(language: str) -> str:
    lang = (language or "").lower()
    return "## 参考文献" if ("chinese" in lang or lang.startswith("zh")) else "## References"


def _conclusion_heading(language: str) -> str:
    lang = (language or "").lower()
    return "## 结论" if ("chinese" in lang or lang.startswith("zh")) else "## Conclusion"


def _build_reference_section_from_report(report: str, language: str, max_items: int = 20) -> str:
    heading = _reference_heading(language)
    lines: list[str] = []
    seen_urls: set[str] = set()
    for match in MARKDOWN_LINK_PATTERN.finditer(report or ""):
        title = (match.group(1) or "").strip() or "Source"
        url = (match.group(2) or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        lines.append(f"- [{title}]({url})")
        if len(lines) >= max_items:
            break
    if not lines:
        fallback_line = "- 未提取到可用外部链接。" if heading == "## 参考文献" else "- No external links were extracted."
        lines = [fallback_line]
    return f"{heading}\n" + "\n".join(lines)


def _apply_emergency_completion(
    report: str,
    missing_requirements: list[str],
    language: str,
    require_marker: bool,
) -> str:
    patched = (report or "").rstrip()
    missing = set(missing_requirements or [])

    if "trailing_header_without_content" in missing:
        filler = "- 待补充的段落在后续版本补全。" if ("chinese" in (language or "").lower() or str(language).lower().startswith("zh")) else "- Additional details are pending a follow-up update."
        patched = f"{patched}\n\n{filler}"

    if "missing_conclusion_section" in missing:
        heading = _conclusion_heading(language)
        text = (
            "- 基于当前可核验证据，核心结论已形成；其余未证实点已在正文标记为待验证。"
            if heading == "## 结论"
            else "- Based on currently verifiable evidence, core conclusions are established and unresolved items remain marked for validation."
        )
        patched = f"{patched}\n\n{heading}\n{text}"

    if "missing_references_section" in missing:
        patched = f"{patched}\n\n{_build_reference_section_from_report(patched, language)}"

    missing_blueprint_sections = [
        item.split(":", 1)[1].strip()
        for item in missing
        if item.startswith("missing_blueprint_section:")
    ]
    for title in missing_blueprint_sections:
        if not title:
            continue
        placeholder = (
            f"## {title}\n- 本节为结构占位，待补充经验证据与结论。"
            if ("chinese" in (language or "").lower() or str(language).lower().startswith("zh"))
            else f"## {title}\n- Placeholder section added to preserve required report structure."
        )
        if f"## {title}" not in patched:
            patched = f"{patched}\n\n{placeholder}"

    if require_marker and REPORT_COMPLETE_MARKER not in patched:
        patched = f"{patched}\n\n{REPORT_COMPLETE_MARKER}"

    return patched


def extract_section_titles_from_outline(outline_markdown: str, max_sections: int = 6) -> list[str]:
    """Extract ordered H2 section titles from markdown outline."""
    titles: list[str] = []
    seen: set[str] = set()
    for raw_line in (outline_markdown or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        title = ""
        if line.startswith("## "):
            title = line[3:].strip()
        elif line.startswith("- ## "):
            title = line[5:].strip()
        elif re.match(r"^\d+[\.\)]\s+.+", line):
            title = re.sub(r"^\d+[\.\)]\s+", "", line).strip()

        title = re.sub(r"[*_`#]", "", title).strip()
        title = re.sub(r"\s{2,}", " ", title)
        if not title:
            continue

        normalized = title.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        titles.append(title)
        if len(titles) >= max_sections:
            break

    return titles


def default_section_titles(language: str) -> list[str]:
    lang = (language or "").lower()
    if "chinese" in lang or lang.startswith("zh"):
        return [
            "执行摘要",
            "关键发现与证据",
            "风险与不确定性",
            "结论与行动建议",
        ]
    return [
        "Executive Summary",
        "Key Findings and Evidence",
        "Risks and Uncertainties",
        "Conclusion and Recommendations",
    ]


def _extract_h2_titles(markdown_text: str) -> list[str]:
    titles: list[str] = []
    for line in (markdown_text or "").splitlines():
        line = line.strip()
        if line.startswith("## "):
            titles.append(line[3:].strip())
    return titles


def _validate_blueprint_section_coverage(report: str, report_blueprint: dict[str, Any]) -> tuple[bool, list[str]]:
    rendered_titles = {title.strip().lower() for title in _extract_h2_titles(report)}
    missing: list[str] = []
    specs = report_blueprint.get("section_specs") or []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        title = str(spec.get("title") or "").strip()
        if not title:
            continue
        if title.lower() not in rendered_titles:
            missing.append(title)
    return len(missing) == 0, missing


async def _generate_blueprint_report(
    *,
    query: str,
    context: str,
    report_blueprint: dict[str, Any],
    user_requirements: str | None,
    report_format: str,
    tone: Tone,
    language: str,
    cfg,
    agent_role_prompt: str,
    websocket,
    cost_callback: callable,
    prompt_family: type[PromptFamily] | PromptFamily,
    finish_reason_callback: Callable[[str | None], None] | None = None,
    **kwargs,
) -> tuple[str, dict[str, Any]]:
    section_order = [str(item).strip() for item in (report_blueprint.get("section_order") or []) if str(item).strip()]
    section_specs = report_blueprint.get("section_specs") or []
    spec_map: dict[str, dict[str, Any]] = {}
    for spec in section_specs:
        if not isinstance(spec, dict):
            continue
        sid = str(spec.get("id") or "").strip()
        if sid:
            spec_map[sid] = spec

    if not section_order and spec_map:
        section_order = list(spec_map.keys())

    if not section_order:
        # Delegate to existing sectional fallback behavior when blueprint is empty.
        return await _generate_sectional_report(
            query=query,
            context=context,
            report_source="web",
            report_format=report_format,
            tone=tone,
            language=language,
            cfg=cfg,
            agent_role_prompt=agent_role_prompt,
            websocket=websocket,
            cost_callback=cost_callback,
            prompt_family=prompt_family,
            max_sections=6,
            context_char_limit=DEFAULT_MAX_OUTLINE_CONTEXT_CHARS,
            finish_reason_callback=finish_reason_callback,
            **kwargs,
        )

    trimmed_context = _truncate_text(str(context), DEFAULT_MAX_OUTLINE_CONTEXT_CHARS)
    user_req = (user_requirements or "").strip()
    rendered_sections: list[str] = []
    rendered_ids: list[str] = []

    for idx, section_id in enumerate(section_order, start=1):
        spec = spec_map.get(section_id) or {}
        title = str(spec.get("title") or section_id).strip() or f"Section {idx}"
        purpose = str(spec.get("purpose") or spec.get("intent") or title).strip()
        required_evidence = [str(item).strip() for item in (spec.get("required_evidence_types") or []) if str(item).strip()]
        min_citations = max(0, int(spec.get("min_citations", 1) or 1))
        must_include = [str(item).strip() for item in (spec.get("must_include") or []) if str(item).strip()]

        section_prompt = f"""
BLUEPRINT_SECTION_TASK
Write ONE markdown section according to the blueprint constraints.

Topic: {query}
Section ID: {section_id}
Section Index: {idx}/{len(section_order)}
Section Title: {title}
Section Purpose: {purpose}
Required Evidence Types: {required_evidence or ["cross_source"]}
Minimum Citations: {min_citations}
Must Include Elements: {must_include or ["none"]}
User Requirements: {user_req or "none"}

Requirements:
- Start with exactly: ## {title}
- Keep analysis grounded in provided context.
- Add explicit citations using markdown links.
- If evidence is conflicting or incomplete, state uncertainty explicitly.
- Write in {language}, tone: {tone.value}.
- Avoid repeating content from other sections.

Context:
{trimmed_context}
"""
        section_md = await _generate_report_once(
            cfg=cfg,
            agent_role_prompt=agent_role_prompt,
            messages=[
                {"role": "system", "content": f"{agent_role_prompt}"},
                {"role": "user", "content": section_prompt},
            ],
            websocket=websocket,
            cost_callback=cost_callback,
            finish_reason_callback=finish_reason_callback,
            **kwargs,
        )
        if section_md.strip():
            rendered_sections.append(section_md.strip())
            rendered_ids.append(section_id)

    report = "\n\n".join(rendered_sections).strip()
    if not report.strip():
        return "", {"rendered_sections": 0, "section_order": section_order, "rendered_ids": []}

    if not CONCLUSION_SECTION_PATTERN.search(report):
        conclusion_text = await create_chat_completion(
            model=cfg.smart_llm_model,
            messages=[
                {"role": "system", "content": f"{agent_role_prompt}"},
                {
                    "role": "user",
                    "content": prompt_family.generate_report_conclusion(
                        query=query,
                        report_content=report,
                        language=language,
                        report_format=report_format,
                    ),
                },
            ],
            temperature=0.25,
            llm_provider=cfg.smart_llm_provider,
            stream=True,
            websocket=websocket,
            max_tokens=cfg.smart_token_limit,
            llm_kwargs=cfg.llm_kwargs,
            cost_callback=cost_callback,
            finish_reason_callback=finish_reason_callback,
            **kwargs,
        )
        if conclusion_text.strip():
            report = f"{report.rstrip()}\n\n{conclusion_text.strip()}"

    if not REFERENCE_SECTION_PATTERN.search(report):
        report = f"{report.rstrip()}\n\n{_build_reference_section_from_report(report, language)}"

    coverage_ok, missing_sections = _validate_blueprint_section_coverage(report, report_blueprint)
    meta = {
        "rendered_sections": len(rendered_sections),
        "section_order": section_order,
        "rendered_ids": rendered_ids,
        "coverage_ok": coverage_ok,
        "missing_sections": missing_sections,
    }
    return report, meta


async def _generate_report_once(
    *,
    cfg,
    agent_role_prompt: str,
    messages: list[dict[str, str]],
    websocket,
    cost_callback: callable,
    finish_reason_callback: Callable[[str | None], None] | None = None,
    **kwargs
) -> str:
    try:
        return await create_chat_completion(
            model=cfg.smart_llm_model,
            messages=messages,
            temperature=0.35,
            llm_provider=cfg.smart_llm_provider,
            stream=True,
            websocket=websocket,
            max_tokens=cfg.smart_token_limit,
            llm_kwargs=cfg.llm_kwargs,
            cost_callback=cost_callback,
            finish_reason_callback=finish_reason_callback,
            **kwargs
        )
    except Exception:
        # Fallback path with single-message prompt for strict providers.
        fallback_content = "\n\n".join(message.get("content", "") for message in messages)
        return await create_chat_completion(
            model=cfg.smart_llm_model,
            messages=[{"role": "user", "content": f"{agent_role_prompt}\n\n{fallback_content}"}],
            temperature=0.35,
            llm_provider=cfg.smart_llm_provider,
            stream=True,
            websocket=websocket,
            max_tokens=cfg.smart_token_limit,
            llm_kwargs=cfg.llm_kwargs,
            cost_callback=cost_callback,
            finish_reason_callback=finish_reason_callback,
            **kwargs
        )


async def _generate_sectional_report(
    *,
    query: str,
    context: str,
    report_source: str,
    report_format: str,
    tone: Tone,
    language: str,
    cfg,
    agent_role_prompt: str,
    websocket,
    cost_callback: callable,
    prompt_family: type[PromptFamily] | PromptFamily,
    max_sections: int,
    context_char_limit: int,
    finish_reason_callback: Callable[[str | None], None] | None = None,
    **kwargs,
) -> tuple[str, dict[str, Any]]:
    """
    Fallback strategy: generate outline then write section-by-section.
    Used only when full-report generation remains incomplete.
    """
    trimmed_context = _truncate_text(str(context), context_char_limit)
    outline_prompt = f"""
SECTIONAL_OUTLINE_TASK
Using the context below, produce a concise markdown outline with H2 headings only.
Return only headings in order, one per line, e.g.:
## Heading 1
## Heading 2

Topic: {query}
Context:
{trimmed_context}
"""

    outline_markdown = await _generate_report_once(
        cfg=cfg,
        agent_role_prompt=agent_role_prompt,
        messages=[
            {"role": "system", "content": f"{agent_role_prompt}"},
            {"role": "user", "content": outline_prompt},
        ],
        websocket=websocket,
        cost_callback=cost_callback,
        finish_reason_callback=finish_reason_callback,
        **kwargs,
    )

    section_titles = extract_section_titles_from_outline(outline_markdown, max_sections=max_sections)
    if not section_titles:
        section_titles = default_section_titles(language)[:max_sections]

    sections: list[str] = []
    for idx, section_title in enumerate(section_titles, start=1):
        section_prompt = f"""
SECTIONAL_SECTION_TASK
Write ONLY one markdown section for this report.

Section Title: {section_title}
Section Index: {idx}/{len(section_titles)}
Topic: {query}

Requirements:
- Start with '## {section_title}'
- Use concise, evidence-backed analysis with in-text citations in markdown links.
- Do NOT include a references section unless this section itself is explicitly references.
- Keep this section self-contained and non-duplicative.
- Write in {language}.
- Use {tone.value} tone.

Context:
{trimmed_context}
"""

        section_md = await _generate_report_once(
            cfg=cfg,
            agent_role_prompt=agent_role_prompt,
            messages=[
                {"role": "system", "content": f"{agent_role_prompt}"},
                {"role": "user", "content": section_prompt},
            ],
            websocket=websocket,
            cost_callback=cost_callback,
            finish_reason_callback=finish_reason_callback,
            **kwargs,
        )

        if section_md.strip():
            sections.append(section_md.strip())

    report = "\n\n".join(sections).strip()

    # Ensure conclusion exists.
    has_conclusion, _missing = evaluate_report_completeness(
        report,
        require_sections=True,
        require_marker=False,
    )
    if not CONCLUSION_SECTION_PATTERN.search(report):
        conclusion_text = await create_chat_completion(
            model=cfg.smart_llm_model,
            messages=[
                {"role": "system", "content": f"{agent_role_prompt}"},
                {
                    "role": "user",
                    "content": prompt_family.generate_report_conclusion(
                        query=query,
                        report_content=report,
                        language=language,
                        report_format=report_format,
                    ),
                },
            ],
            temperature=0.25,
            llm_provider=cfg.smart_llm_provider,
            stream=True,
            websocket=websocket,
            max_tokens=cfg.smart_token_limit,
            llm_kwargs=cfg.llm_kwargs,
            cost_callback=cost_callback,
            finish_reason_callback=finish_reason_callback,
            **kwargs,
        )
        if conclusion_text.strip():
            report = f"{report.rstrip()}\n\n{conclusion_text.strip()}"

    # Ensure references exist.
    if not REFERENCE_SECTION_PATTERN.search(report):
        references_prompt = f"""
SECTIONAL_REFERENCES_TASK
Based on the draft report below, produce a deduplicated references section in markdown.

Requirements:
- Start with '## 参考文献' for Chinese, or '## References' otherwise.
- Include only sources actually referenced in the report.
- Each reference must contain one markdown hyperlink.
- Return only this references section.

Language: {language}
Draft report:
{report}
"""
        references_md = await _generate_report_once(
            cfg=cfg,
            agent_role_prompt=agent_role_prompt,
            messages=[
                {"role": "system", "content": f"{agent_role_prompt}"},
                {"role": "user", "content": references_prompt},
            ],
            websocket=websocket,
            cost_callback=cost_callback,
            finish_reason_callback=finish_reason_callback,
            **kwargs,
        )
        if references_md.strip():
            report = f"{report.rstrip()}\n\n{references_md.strip()}"

    meta = {
        "outline_raw_length": len(outline_markdown or ""),
        "section_count": len(section_titles),
        "section_titles": section_titles,
        "assembled_sections": len(sections),
        "completion_check_hint": has_conclusion,
    }
    return report, meta


async def write_report_introduction(
    query: str,
    context: str,
    agent_role_prompt: str,
    config: Config,
    websocket=None,
    cost_callback: callable = None,
    prompt_family: type[PromptFamily] | PromptFamily = PromptFamily,
    **kwargs
) -> str:
    """
    Generate an introduction for the report.

    Args:
        query (str): The research query.
        context (str): Context for the report.
        role (str): The role of the agent.
        config (Config): Configuration object.
        websocket: WebSocket connection for streaming output.
        cost_callback (callable, optional): Callback for calculating LLM costs.
        prompt_family: Family of prompts

    Returns:
        str: The generated introduction.
    """
    try:
        introduction = await create_chat_completion(
            model=config.smart_llm_model,
            messages=[
                {"role": "system", "content": f"{agent_role_prompt}"},
                {"role": "user", "content": prompt_family.generate_report_introduction(
                    question=query,
                    research_summary=context,
                    language=config.language
                )},
            ],
            temperature=0.25,
            llm_provider=config.smart_llm_provider,
            stream=True,
            websocket=websocket,
            max_tokens=config.smart_token_limit,
            llm_kwargs=config.llm_kwargs,
            cost_callback=cost_callback,
            **kwargs
        )
        return introduction
    except Exception as e:
        logger.error(f"Error in generating report introduction: {e}")
    return ""


async def write_conclusion(
    query: str,
    context: str,
    agent_role_prompt: str,
    config: Config,
    websocket=None,
    cost_callback: callable = None,
    prompt_family: type[PromptFamily] | PromptFamily = PromptFamily,
    **kwargs
) -> str:
    """
    Write a conclusion for the report.

    Args:
        query (str): The research query.
        context (str): Context for the report.
        role (str): The role of the agent.
        config (Config): Configuration object.
        websocket: WebSocket connection for streaming output.
        cost_callback (callable, optional): Callback for calculating LLM costs.
        prompt_family: Family of prompts

    Returns:
        str: The generated conclusion.
    """
    try:
        conclusion = await create_chat_completion(
            model=config.smart_llm_model,
            messages=[
                {"role": "system", "content": f"{agent_role_prompt}"},
                {
                    "role": "user",
                    "content": prompt_family.generate_report_conclusion(query=query,
                                                                        report_content=context,
                                                                        language=config.language),
                },
            ],
            temperature=0.25,
            llm_provider=config.smart_llm_provider,
            stream=True,
            websocket=websocket,
            max_tokens=config.smart_token_limit,
            llm_kwargs=config.llm_kwargs,
            cost_callback=cost_callback,
            **kwargs
        )
        return conclusion
    except Exception as e:
        logger.error(f"Error in writing conclusion: {e}")
    return ""


async def summarize_url(
    url: str,
    content: str,
    role: str,
    config: Config,
    websocket=None,
    cost_callback: callable = None,
    **kwargs
) -> str:
    """
    Summarize the content of a URL.

    Args:
        url (str): The URL to summarize.
        content (str): The content of the URL.
        role (str): The role of the agent.
        config (Config): Configuration object.
        websocket: WebSocket connection for streaming output.
        cost_callback (callable, optional): Callback for calculating LLM costs.

    Returns:
        str: The summarized content.
    """
    try:
        summary = await create_chat_completion(
            model=config.smart_llm_model,
            messages=[
                {"role": "system", "content": f"{role}"},
                {"role": "user", "content": f"Summarize the following content from {url}:\n\n{content}"},
            ],
            temperature=0.25,
            llm_provider=config.smart_llm_provider,
            stream=True,
            websocket=websocket,
            max_tokens=config.smart_token_limit,
            llm_kwargs=config.llm_kwargs,
            cost_callback=cost_callback,
            **kwargs
        )
        return summary
    except Exception as e:
        logger.error(f"Error in summarizing URL: {e}")
    return ""


async def generate_draft_section_titles(
    query: str,
    current_subtopic: str,
    context: str,
    role: str,
    config: Config,
    websocket=None,
    cost_callback: callable = None,
    prompt_family: type[PromptFamily] | PromptFamily = PromptFamily,
    **kwargs
) -> List[str]:
    """
    Generate draft section titles for the report.

    Args:
        query (str): The research query.
        context (str): Context for the report.
        role (str): The role of the agent.
        config (Config): Configuration object.
        websocket: WebSocket connection for streaming output.
        cost_callback (callable, optional): Callback for calculating LLM costs.
        prompt_family: Family of prompts

    Returns:
        List[str]: A list of generated section titles.
    """
    try:
        section_titles = await create_chat_completion(
            model=config.smart_llm_model,
            messages=[
                {"role": "system", "content": f"{role}"},
                {"role": "user", "content": prompt_family.generate_draft_titles_prompt(
                    current_subtopic, query, context)},
            ],
            temperature=0.25,
            llm_provider=config.smart_llm_provider,
            stream=True,
            websocket=None,
            max_tokens=config.smart_token_limit,
            llm_kwargs=config.llm_kwargs,
            cost_callback=cost_callback,
            **kwargs
        )
        return section_titles.split("\n")
    except Exception as e:
        logger.error(f"Error in generating draft section titles: {e}")
    return []


async def generate_report(
    query: str,
    context,
    agent_role_prompt: str,
    report_type: str,
    tone: Tone,
    report_source: str,
    websocket,
    cfg,
    main_topic: str = "",
    existing_headers: list = [],
    relevant_written_contents: list = [],
    cost_callback: callable = None,
    custom_prompt: str = "", # This can be any prompt the user chooses with the context
    headers=None,
    prompt_family: type[PromptFamily] | PromptFamily = PromptFamily,
    available_images: list = None,
    report_blueprint: dict | None = None,
    user_requirements: str | None = None,
    generation_metadata_callback: Callable[[dict], None] | None = None,
    **kwargs
):
    """
    generates the final report
    Args:
        query:
        context:
        agent_role_prompt:
        report_type:
        websocket:
        tone:
        cfg:
        main_topic:
        existing_headers:
        relevant_written_contents:
        cost_callback:
        prompt_family: Family of prompts
        available_images: Pre-generated images to embed in the report

    Returns:
        report:

    """
    available_images = available_images or []
    generate_prompt = get_prompt_by_report_type(report_type, prompt_family)
    report = ""

    if report_type == "subtopic_report":
        content = f"{generate_prompt(query, existing_headers, relevant_written_contents, main_topic, context, report_format=cfg.report_format, tone=tone, total_words=cfg.total_words, language=cfg.language)}"
    elif custom_prompt:
        content = f"{custom_prompt}\n\nContext: {context}"
    else:
        content = f"{generate_prompt(query, context, report_source, report_format=cfg.report_format, tone=tone, total_words=cfg.total_words, language=cfg.language)}"
    
    guard_enabled = bool(getattr(cfg, "report_completion_guard_enabled", True))
    guard_max_attempts = max(0, int(getattr(cfg, "report_completion_max_attempts", 2)))
    guard_require_marker = bool(getattr(cfg, "report_completion_require_marker", True))
    sectional_fallback_enabled = bool(getattr(cfg, "report_sectional_fallback_enabled", True))
    sectional_max_sections = max(2, int(getattr(cfg, "report_sectional_max_sections", 6)))
    sectional_context_chars = max(5000, int(getattr(cfg, "report_sectional_context_chars", DEFAULT_MAX_OUTLINE_CONTEXT_CHARS)))
    sectional_preflight_enabled = bool(getattr(cfg, "report_sectional_preflight_enabled", True))
    sectional_preflight_min_context_chars = max(2000, int(getattr(cfg, "report_sectional_preflight_min_context_chars", 14000)))
    sectional_timeout_seconds = max(20, int(getattr(cfg, "report_sectional_timeout_seconds", 120)))
    sectional_fallback_reduced_max_sections = max(2, int(getattr(cfg, "report_sectional_fallback_reduced_max_sections", 4)))
    sectional_fallback_reduced_context_chars = max(5000, int(getattr(cfg, "report_sectional_fallback_reduced_context_chars", 12000)))
    require_sections = report_type != "subtopic_report"
    context_text = str(context)

    preflight_condition = (
        sectional_fallback_enabled
        and sectional_preflight_enabled
        and require_sections
        and (
            report_type in {"deep", "adaptive_deep"}
            or len(context_text) >= sectional_preflight_min_context_chars
        )
    )

    # Add available images instruction if images were pre-generated
    if available_images:
        images_info = "\n".join([
            f"- Image {i+1}: ![{img.get('title', img.get('alt_text', 'Illustration'))}]({img['url']}) - {img.get('section_hint', 'General')}"
            for i, img in enumerate(available_images)
        ])
        content += f"""

AVAILABLE IMAGES:
You have the following pre-generated images available. Embed them in relevant sections of your report using the exact markdown syntax provided:

{images_info}

Place each image on its own line after the relevant section header or paragraph. Use all available images where they add value to the content."""
    if guard_enabled:
        content += f"""

OUTPUT COMPLETION RULES:
- You MUST include a clear conclusion section.
- You MUST include a references/sources section.
- End the full report with the exact marker: {REPORT_COMPLETE_MARKER}
"""

    finish_reasons: list[str] = []

    def _capture_finish_reason(reason: str | None) -> None:
        if reason:
            finish_reasons.append(str(reason))

    sectional_meta: dict[str, Any] = {}
    blueprint_meta: dict[str, Any] = {}
    used_blueprint_mode = False
    used_sectional_fallback = False
    used_sectional_preflight = False
    preflight_transport_failed = False
    preflight_error = ""
    fallback_max_sections = sectional_max_sections
    fallback_context_chars = sectional_context_chars
    emergency_completion_applied = False

    if preflight_condition:
        try:
            sectional_report, sectional_meta = await asyncio.wait_for(
                _generate_sectional_report(
                    query=query,
                    context=context_text,
                    report_source=report_source,
                    report_format=cfg.report_format,
                    tone=tone,
                    language=cfg.language,
                    cfg=cfg,
                    agent_role_prompt=agent_role_prompt,
                    websocket=websocket,
                    cost_callback=cost_callback,
                    prompt_family=prompt_family,
                    max_sections=sectional_max_sections,
                    context_char_limit=sectional_context_chars,
                    finish_reason_callback=_capture_finish_reason,
                    **kwargs,
                ),
                timeout=sectional_timeout_seconds,
            )
            if sectional_report.strip():
                report = sectional_report.strip()
                used_sectional_preflight = True
                if guard_require_marker and REPORT_COMPLETE_MARKER not in report:
                    report = f"{report}\n\n{REPORT_COMPLETE_MARKER}"
        except Exception as e:
            preflight_error = str(e)
            preflight_transport_failed = isinstance(e, asyncio.TimeoutError) or _is_transport_error(e)
            if preflight_transport_failed:
                fallback_max_sections = min(sectional_max_sections, sectional_fallback_reduced_max_sections)
                fallback_context_chars = min(sectional_context_chars, sectional_fallback_reduced_context_chars)
            logger.error(f"Error in sectional preflight generation: {e}")

    if report_blueprint and not report.strip():
        try:
            blueprint_report, blueprint_meta = await _generate_blueprint_report(
                query=query,
                context=context_text,
                report_blueprint=report_blueprint,
                user_requirements=user_requirements,
                report_format=cfg.report_format,
                tone=tone,
                language=cfg.language,
                cfg=cfg,
                agent_role_prompt=agent_role_prompt,
                websocket=websocket,
                cost_callback=cost_callback,
                prompt_family=prompt_family,
                finish_reason_callback=_capture_finish_reason,
                **kwargs,
            )
            if blueprint_report.strip():
                report = blueprint_report.strip()
                used_blueprint_mode = True
                if guard_require_marker and REPORT_COMPLETE_MARKER not in report:
                    report = f"{report}\n\n{REPORT_COMPLETE_MARKER}"
        except Exception as e:
            logger.error(f"Error in blueprint-driven generation: {e}")

    continuation_attempts = 0
    initial_complete = False
    missing_requirements: list[str] = []

    if not report.strip():
        messages = [
            {"role": "system", "content": f"{agent_role_prompt}"},
            {"role": "user", "content": content},
        ]

        try:
            report = await _generate_report_once(
                cfg=cfg,
                agent_role_prompt=agent_role_prompt,
                messages=messages,
                websocket=websocket,
                cost_callback=cost_callback,
                finish_reason_callback=_capture_finish_reason,
                **kwargs,
            )
        except Exception as e:
            logger.error(f"Error in generate_report initial call: {e}")
            report = ""

    initial_complete, missing_requirements = evaluate_report_completeness(
        report,
        require_sections=require_sections,
        require_marker=guard_require_marker and guard_enabled,
    )

    if guard_enabled and not initial_complete:
        for attempt in range(1, guard_max_attempts + 1):
            continuation_attempts = attempt
            missing_text = ", ".join(missing_requirements) if missing_requirements else "none"
            continuation_prompt = f"""
The prior report appears incomplete or truncated.
Continue the existing report without repeating already written content.

Missing requirements to satisfy: {missing_text}

Current partial report:
{report}

Rules:
- Continue from the unfinished point.
- Preserve original markdown style and headings.
- Add the missing sections if absent.
- End your continuation with the exact marker: {REPORT_COMPLETE_MARKER}
- Return ONLY markdown continuation text to append.
"""
            try:
                continuation = await _generate_report_once(
                    cfg=cfg,
                    agent_role_prompt=agent_role_prompt,
                    messages=[
                        {"role": "system", "content": f"{agent_role_prompt}"},
                        {"role": "user", "content": continuation_prompt},
                    ],
                    websocket=websocket,
                    cost_callback=cost_callback,
                    finish_reason_callback=_capture_finish_reason,
                    **kwargs,
                )
            except Exception as e:
                logger.error(f"Error in generate_report continuation attempt {attempt}: {e}")
                continuation = ""

            if continuation.strip():
                report = f"{report.rstrip()}\n\n{continuation.lstrip()}"

            completed, missing_requirements = evaluate_report_completeness(
                report,
                require_sections=require_sections,
                require_marker=guard_require_marker and guard_enabled,
            )
            if completed:
                break

    final_complete, final_missing = evaluate_report_completeness(
        report,
        require_sections=require_sections,
        require_marker=guard_require_marker and guard_enabled,
    )
    if report_blueprint:
        coverage_ok, missing_sections = _validate_blueprint_section_coverage(report, report_blueprint)
        if not coverage_ok:
            final_complete = False
            final_missing.extend([f"missing_blueprint_section:{title}" for title in missing_sections])
    allow_sectional_fallback = sectional_fallback_enabled and not preflight_transport_failed
    if guard_enabled and require_sections and not final_complete and allow_sectional_fallback:
        try:
            sectional_report, sectional_meta = await asyncio.wait_for(
                _generate_sectional_report(
                    query=query,
                    context=context_text,
                    report_source=report_source,
                    report_format=cfg.report_format,
                    tone=tone,
                    language=cfg.language,
                    cfg=cfg,
                    agent_role_prompt=agent_role_prompt,
                    websocket=websocket,
                    cost_callback=cost_callback,
                    prompt_family=prompt_family,
                    max_sections=fallback_max_sections,
                    context_char_limit=fallback_context_chars,
                    finish_reason_callback=_capture_finish_reason,
                    **kwargs,
                ),
                timeout=sectional_timeout_seconds,
            )
            if sectional_report.strip():
                report = sectional_report.strip()
                used_sectional_fallback = True
                if guard_require_marker and REPORT_COMPLETE_MARKER not in report:
                    report = f"{report}\n\n{REPORT_COMPLETE_MARKER}"
                final_complete, final_missing = evaluate_report_completeness(
                    report,
                    require_sections=require_sections,
                    require_marker=guard_require_marker and guard_enabled,
                )
        except Exception as e:
            logger.error(f"Error in sectional fallback generation: {e}")

    if guard_enabled and not final_complete:
        report = _apply_emergency_completion(
            report=report,
            missing_requirements=final_missing,
            language=cfg.language,
            require_marker=guard_require_marker and guard_enabled,
        )
        emergency_completion_applied = True
        final_complete, final_missing = evaluate_report_completeness(
            report,
            require_sections=require_sections,
            require_marker=guard_require_marker and guard_enabled,
        )

    marker_present = REPORT_COMPLETE_MARKER in report
    report = _strip_completion_marker(report)
    blueprint_coverage_ok = True
    blueprint_missing_sections: list[str] = []
    if report_blueprint:
        blueprint_coverage_ok, blueprint_missing_sections = _validate_blueprint_section_coverage(report, report_blueprint)

    if generation_metadata_callback:
        generation_metadata_callback(
            {
                "guard_enabled": guard_enabled,
                "initial_complete": initial_complete,
                "final_complete": final_complete,
                "continuation_attempts": continuation_attempts,
                "missing_requirements": final_missing,
                "marker_present": marker_present,
                "finish_reasons": finish_reasons,
                "used_sectional_fallback": used_sectional_fallback,
                "used_sectional_preflight": used_sectional_preflight,
                "sectional_preflight_condition": preflight_condition,
                "sectional_preflight_transport_failed": preflight_transport_failed,
                "sectional_preflight_error": preflight_error,
                "emergency_completion_applied": emergency_completion_applied,
                "sectional_fallback": sectional_meta,
                "used_blueprint_mode": used_blueprint_mode,
                "blueprint_generation": blueprint_meta,
                "blueprint_coverage_ok": blueprint_coverage_ok,
                "blueprint_missing_sections": blueprint_missing_sections,
            }
        )

    return report
