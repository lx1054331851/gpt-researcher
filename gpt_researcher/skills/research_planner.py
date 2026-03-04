"""Two-stage research planner for adaptive deep research."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import json_repair

from ..config import Config
from ..llm_provider.generic.base import ReasoningEfforts
from ..orchestration.outline_schema import (
    ResearchOutline,
    ReportBlueprint,
    build_blueprint_from_outline,
    validate_research_outline,
)
from ..utils.llm import create_chat_completion

logger = logging.getLogger(__name__)


def _fallback_outline(query: str, user_requirements: str | None = None) -> ResearchOutline:
    objective = f"Deliver decision-ready research for: {query}"
    if user_requirements:
        objective = f"{objective}. Additional requirements: {user_requirements}"
    return ResearchOutline.from_dict(
        {
            "outline_id": uuid.uuid4().hex,
            "query": query,
            "objective": objective,
            "constraints": [
                "Focus on verifiable evidence.",
                "Mark unresolved conflicts explicitly.",
            ],
            "sections": [
                {
                    "id": "foundation-1",
                    "title": "Problem Framing and Scope",
                    "intent": "Define goals, scope, and evaluation dimensions.",
                    "key_questions": ["What is in scope and what is out of scope?"],
                    "stage": "foundation",
                    "priority": 0.9,
                    "required": True,
                },
                {
                    "id": "evidence-1",
                    "title": "Evidence and Technical Paths",
                    "intent": "Collect comparative evidence for major technical routes.",
                    "key_questions": ["What route has strongest evidence?", "Where do claims conflict?"],
                    "stage": "evidence",
                    "priority": 0.8,
                    "required": True,
                },
                {
                    "id": "judgement-1",
                    "title": "Decision Guidance",
                    "intent": "Provide decision recommendations and implementation priorities.",
                    "key_questions": ["What should be done now versus later?"],
                    "stage": "judgement",
                    "priority": 0.7,
                    "required": True,
                },
            ],
        },
        query_hint=query,
    )


def validate_outline(outline: ResearchOutline) -> tuple[bool, list[str]]:
    return validate_research_outline(outline)


async def generate_outline(
    query: str,
    user_requirements: str | None = None,
    language: str | None = None,
    cfg: Config | None = None,
) -> tuple[ResearchOutline, ReportBlueprint]:
    """Generate initial outline and blueprint draft."""
    config = cfg or Config()
    requirements = (user_requirements or "").strip()
    language_hint = language or config.language or "english"

    prompt = f"""
You are planning a deep-research workflow.
Return JSON only, no markdown.

Task: "{query}"
Language: {language_hint}
Additional requirements: {requirements or "None"}

JSON schema:
{{
  "objective": "string",
  "audience": "string or null",
  "constraints": ["string"],
  "sections": [
    {{
      "id": "short-kebab-id",
      "title": "string",
      "intent": "string",
      "key_questions": ["string"],
      "stage": "foundation|evidence|judgement",
      "priority": 0.0-1.0,
      "required": true
    }}
  ]
}}

Constraints:
- 4-8 sections total.
- Must include at least one section for each stage: foundation/evidence/judgement.
- Keep titles specific and decision-oriented.
"""

    outline: ResearchOutline | None = None
    try:
        response = await asyncio.wait_for(
            create_chat_completion(
                model=config.strategic_llm_model,
                llm_provider=config.strategic_llm_provider,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                reasoning_effort=ReasoningEfforts.Medium.value,
                llm_kwargs=config.llm_kwargs,
            ),
            timeout=30,
        )
        parsed = json_repair.loads(response)
        if isinstance(parsed, dict):
            parsed["outline_id"] = parsed.get("outline_id") or uuid.uuid4().hex
            parsed["query"] = parsed.get("query") or query
            outline = ResearchOutline.from_dict(parsed, query_hint=query)
    except Exception as exc:
        logger.warning("generate_outline fallback triggered: %s", exc)

    if outline is None:
        outline = _fallback_outline(query, user_requirements=requirements)

    valid, errors = validate_outline(outline)
    if not valid:
        logger.warning("Generated outline failed validation, applying fallback. errors=%s", errors)
        outline = _fallback_outline(query, user_requirements=requirements)

    blueprint = build_blueprint_from_outline(outline)
    return outline, blueprint


async def revise_outline(
    outline: ResearchOutline,
    instruction: str,
    language: str | None = None,
    cfg: Config | None = None,
) -> tuple[ResearchOutline, ReportBlueprint]:
    """Rewrite an existing outline while preserving schema integrity."""
    config = cfg or Config()
    rewrite_instruction = (instruction or "").strip()
    if not rewrite_instruction:
        blueprint = build_blueprint_from_outline(outline)
        return outline, blueprint

    language_hint = language or config.language or "english"
    prompt = f"""
Rewrite the following research outline according to the instruction.
Return JSON only.

Instruction: {rewrite_instruction}
Language: {language_hint}

Current outline JSON:
{outline.to_dict()}

Output schema:
{{
  "objective": "string",
  "audience": "string or null",
  "constraints": ["string"],
  "sections": [
    {{
      "id": "short-kebab-id",
      "title": "string",
      "intent": "string",
      "key_questions": ["string"],
      "stage": "foundation|evidence|judgement",
      "priority": 0.0-1.0,
      "required": true
    }}
  ]
}}

Hard constraints:
- Preserve all required fields for each section.
- Must include foundation/evidence/judgement stages.
- Keep section count between 3 and 10.
"""

    revised_outline: ResearchOutline | None = None
    try:
        response = await asyncio.wait_for(
            create_chat_completion(
                model=config.strategic_llm_model,
                llm_provider=config.strategic_llm_provider,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                reasoning_effort=ReasoningEfforts.Medium.value,
                llm_kwargs=config.llm_kwargs,
            ),
            timeout=30,
        )
        parsed = json_repair.loads(response)
        if isinstance(parsed, dict):
            parsed["outline_id"] = outline.outline_id
            parsed["query"] = outline.query
            revised_outline = ResearchOutline.from_dict(parsed, query_hint=outline.query)
    except Exception as exc:
        logger.warning("revise_outline fallback triggered: %s", exc)

    if revised_outline is None:
        revised_data = outline.to_dict()
        revised_data["constraints"] = list(revised_data.get("constraints") or [])
        revised_data["constraints"].append(f"User revision request: {rewrite_instruction}")
        revised_outline = ResearchOutline.from_dict(revised_data, query_hint=outline.query)

    valid, errors = validate_outline(revised_outline)
    if not valid:
        logger.warning("Revised outline failed validation, keeping original. errors=%s", errors)
        revised_outline = outline

    blueprint = build_blueprint_from_outline(revised_outline)
    return revised_outline, blueprint


def normalize_outline_payload(payload: dict[str, Any], query_hint: str | None = None) -> ResearchOutline:
    return ResearchOutline.from_dict(payload, query_hint=query_hint)


def normalize_blueprint_payload(payload: dict[str, Any], outline: ResearchOutline | None = None) -> ReportBlueprint:
    return ReportBlueprint.from_dict(payload, outline=outline)

