"""Two-stage research planner for adaptive deep research."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import json_repair

from ..config import Config
from ..llm_provider.generic.base import ReasoningEfforts
from ..orchestration.coverage_lenses import (
    assess_chain_coverage,
    assess_text_coverage,
    coverage_chain_prompt_block,
    coverage_lens_prompt_block,
    resolve_chain_steps,
)
from ..orchestration.outline_schema import (
    ResearchOutline,
    ReportBlueprint,
    build_blueprint_from_outline,
    validate_research_outline,
)
from ..utils.llm import create_chat_completion

logger = logging.getLogger(__name__)


def _outline_text_segments(outline: ResearchOutline) -> list[str]:
    segments: list[str] = [
        outline.objective or "",
        outline.scope or "",
        " ".join(outline.constraints or []),
        " ".join(outline.evidence_requirements or []),
        " ".join(outline.deliverables or []),
        " ".join(outline.risk_controls or []),
    ]
    for workstream in outline.workstreams or []:
        if not isinstance(workstream, dict):
            continue
        segments.append(
            " ".join(
                [
                    str(workstream.get("title") or ""),
                    str(workstream.get("intent") or ""),
                    str(workstream.get("deliverable") or ""),
                ]
            ).strip()
        )
    for section in outline.sections or []:
        segments.append(
            " ".join(
                [
                    str(section.title or ""),
                    str(section.intent or ""),
                    " ".join(section.key_questions or []),
                ]
            ).strip()
        )
    return [item for item in segments if item]


def assess_outline_coverage(outline: ResearchOutline) -> dict[str, Any]:
    return assess_text_coverage(_outline_text_segments(outline))


def assess_outline_chain_coverage(
    outline: ResearchOutline,
    chain_steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return assess_chain_coverage(_outline_text_segments(outline), chain_steps=chain_steps)


def _fallback_outline(query: str, user_requirements: str | None = None) -> ResearchOutline:
    objective = f"Deliver decision-ready research for: {query}"
    if user_requirements:
        objective = f"{objective}. Additional requirements: {user_requirements}"
    return ResearchOutline.from_dict(
        {
            "outline_id": uuid.uuid4().hex,
            "query": query,
            "objective": objective,
            "scope": f"Focus on objective, evidence-grounded analysis and executable decisions for {query}.",
            "workstreams": [
                {
                    "id": "ws-1-brand-strategy-sustainability",
                    "title": "品牌战略与可持续承诺调研",
                    "intent": "梳理品牌定位、承诺与公开披露的一致性。",
                    "deliverable": "战略承诺一致性结论与差距清单",
                },
                {
                    "id": "ws-2-fabric-trend-2027",
                    "title": "2027 面料趋势调研",
                    "intent": "识别趋势方向、应用成熟度与商业价值。",
                    "deliverable": "趋势优先级矩阵",
                },
                {
                    "id": "ws-3-functional-tech-upgrade",
                    "title": "功能性技术升级调研",
                    "intent": "评估功能技术升级路径与验证指标。",
                    "deliverable": "技术升级路线图",
                },
                {
                    "id": "ws-4-green-material-low-carbon",
                    "title": "环保材料与低碳工艺调研",
                    "intent": "分析绿色材料与低碳工艺的减排潜力及成本。",
                    "deliverable": "材料工艺权衡清单",
                },
                {
                    "id": "ws-5-competition-consumer-feedback",
                    "title": "竞品与消费者反馈调研",
                    "intent": "对比竞品策略并提炼用户反馈信号。",
                    "deliverable": "竞品与用户洞察摘要",
                },
                {
                    "id": "ws-6-synthesis-recommendation-output",
                    "title": "综合评估与方案输出",
                    "intent": "形成闭环建议与分阶段行动方案。",
                    "deliverable": "可执行建议包（优先级/风险/里程碑）",
                },
            ],
            "evidence_requirements": [
                "关键结论至少一条 T1/T2 证据锚点。",
                "存在冲突时必须跨来源交叉验证。",
            ],
            "deliverables": [
                "面向决策者的具体建议输出（含优先级）。",
                "实施路线图与风险控制建议。",
            ],
            "risk_controls": [
                "显式标注证据冲突与未验证项。",
                "低质量来源不得单独支撑关键结论。",
            ],
            "must_answer_questions": [
                f"针对 {query}，最可执行的建议是什么？",
            ],
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
    report_style: str | None = None,
    source_policy: str | None = None,
    cfg: Config | None = None,
) -> tuple[ResearchOutline, ReportBlueprint]:
    """Generate initial outline and blueprint draft."""
    config = cfg or Config()
    requirements = (user_requirements or "").strip()
    language_hint = language or config.language or "english"
    coverage_lenses_block = coverage_lens_prompt_block()
    chain_steps = resolve_chain_steps(
        profile_mode=str(getattr(config, "adaptive_chain_profile_mode", "generic") or "generic"),
        industry_profile=str(getattr(config, "adaptive_chain_industry_profile", "auto") or "auto"),
        query=query,
    )
    coverage_chain_block = coverage_chain_prompt_block(chain_steps)

    prompt = f"""
You are planning a deep-research workflow.
Return JSON only, no markdown.

Task: "{query}"
Language: {language_hint}
Additional requirements: {requirements or "None"}
Report style: {report_style or "strategic_report"}
Source policy: {source_policy or "medium_tier"}

Coverage lenses to maximize breadth (avoid single-dimension planning):
{coverage_lenses_block}

Coverage chain to preserve explicit end-to-end logic:
{coverage_chain_block}

JSON schema:
{{
  "objective": "string",
  "scope": "string",
  "workstreams": [
    {{
      "id": "short-kebab-id",
      "title": "string",
      "intent": "string",
      "deliverable": "string"
    }}
  ],
  "evidence_requirements": ["string"],
  "deliverables": ["string"],
  "risk_controls": ["string"],
  "must_answer_questions": ["string"],
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
- Keep 4-8 sections but include complete editable planning fields (scope/workstreams/evidence_requirements/deliverables/risk_controls/must_answer_questions).
- Must include at least one section for each stage: foundation/evidence/judgement.
- Keep titles specific and decision-oriented.
- Workstreams should follow a practical execution chain and be directly related to the query.
- Sections/workstreams should jointly cover as many coverage lenses as possible.
- Sections/workstreams should explicitly map to the chain:
  industry -> brand/entity -> demand -> materials/inputs -> technology/process -> execution.
- Keep dimensions orthogonal; avoid repeating near-identical themes.
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

    coverage_enhancer_enabled = bool(getattr(config, "adaptive_coverage_enhancer_enabled", False))
    coverage_min_ratio = max(0.0, min(1.0, float(getattr(config, "adaptive_coverage_min_ratio", 0.75))))
    coverage_revise_rounds = max(0, int(getattr(config, "adaptive_coverage_revise_max_rounds", 1)))
    chain_enforcer_enabled = bool(getattr(config, "adaptive_chain_enforcer_enabled", True))
    chain_min_ratio = max(0.0, min(1.0, float(getattr(config, "adaptive_chain_min_ratio", 0.90))))
    chain_patch_rounds = max(0, int(getattr(config, "adaptive_chain_patch_max_rounds", 1)))

    if coverage_enhancer_enabled:
        coverage = assess_outline_coverage(outline)
        attempts = 0
        while coverage["ratio"] < coverage_min_ratio and attempts < coverage_revise_rounds:
            missing_labels = coverage.get("missing_labels") or []
            revise_instruction = (
                "Improve outline coverage by filling missing analysis lenses while keeping sections decision-oriented. "
                f"Missing lenses: {', '.join(missing_labels) if missing_labels else 'none'}."
            )
            revised_outline, _ = await revise_outline(
                outline=outline,
                instruction=revise_instruction,
                language=language,
                report_style=report_style,
                source_policy=source_policy,
                cfg=config,
            )
            outline = revised_outline
            coverage = assess_outline_coverage(outline)
            attempts += 1

        if coverage["ratio"] < coverage_min_ratio:
            outline.constraints = list(outline.constraints or [])
            outline.constraints.append(
                "Coverage gap retained after auto-revision. Missing lenses: "
                + ", ".join(coverage.get("missing_labels") or [])
            )

    if chain_enforcer_enabled:
        chain_coverage = assess_outline_chain_coverage(outline, chain_steps=chain_steps)
        attempts = 0
        while (
            (chain_coverage.get("ratio", 0.0) < chain_min_ratio or bool(chain_coverage.get("missing_ids")))
            and attempts < chain_patch_rounds
        ):
            missing_chain = chain_coverage.get("missing_labels") or []
            revise_instruction = (
                "Improve outline chain completeness. Explicitly cover the chain "
                "(industry -> brand/entity -> demand -> materials/inputs -> technology/process -> execution). "
                f"Missing chain steps: {', '.join(missing_chain) if missing_chain else 'none'}."
            )
            revised_outline, _ = await revise_outline(
                outline=outline,
                instruction=revise_instruction,
                language=language,
                report_style=report_style,
                source_policy=source_policy,
                cfg=config,
            )
            outline = revised_outline
            chain_coverage = assess_outline_chain_coverage(outline, chain_steps=chain_steps)
            attempts += 1

        if chain_coverage.get("ratio", 0.0) < chain_min_ratio or bool(chain_coverage.get("missing_ids")):
            outline.constraints = list(outline.constraints or [])
            outline.constraints.append(
                "Chain coverage gap retained after auto-revision. Missing chain steps: "
                + ", ".join(chain_coverage.get("missing_labels") or [])
            )

    blueprint = build_blueprint_from_outline(outline)
    return outline, blueprint


async def revise_outline(
    outline: ResearchOutline,
    instruction: str,
    language: str | None = None,
    report_style: str | None = None,
    source_policy: str | None = None,
    cfg: Config | None = None,
) -> tuple[ResearchOutline, ReportBlueprint]:
    """Rewrite an existing outline while preserving schema integrity."""
    config = cfg or Config()
    rewrite_instruction = (instruction or "").strip()
    if not rewrite_instruction:
        blueprint = build_blueprint_from_outline(outline)
        return outline, blueprint

    language_hint = language or config.language or "english"
    coverage_lenses_block = coverage_lens_prompt_block()
    chain_steps = resolve_chain_steps(
        profile_mode=str(getattr(config, "adaptive_chain_profile_mode", "generic") or "generic"),
        industry_profile=str(getattr(config, "adaptive_chain_industry_profile", "auto") or "auto"),
        query=outline.query,
    )
    coverage_chain_block = coverage_chain_prompt_block(chain_steps)
    prompt = f"""
Rewrite the following research outline according to the instruction.
Return JSON only.

Instruction: {rewrite_instruction}
Language: {language_hint}
Report style: {report_style or "strategic_report"}
Source policy: {source_policy or "medium_tier"}
Coverage lenses to preserve breadth:
{coverage_lenses_block}
Coverage chain to preserve end-to-end logic:
{coverage_chain_block}

Current outline JSON:
{outline.to_dict()}

Output schema:
{{
  "objective": "string",
  "scope": "string",
  "workstreams": [
    {{
      "id": "short-kebab-id",
      "title": "string",
      "intent": "string",
      "deliverable": "string"
    }}
  ],
  "evidence_requirements": ["string"],
  "deliverables": ["string"],
  "risk_controls": ["string"],
  "must_answer_questions": ["string"],
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
- Keep workstreams non-empty and aligned with the query objective.
- Keep sections/workstreams broadly covering the coverage lenses instead of collapsing into one angle.
- Keep explicit chain coverage:
  industry -> brand/entity -> demand -> materials/inputs -> technology/process -> execution.
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
