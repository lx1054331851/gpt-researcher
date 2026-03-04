"""Schema helpers for editable research outlines and report blueprints."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from .task_graph import TaskStage

OutlineStage = Literal["foundation", "evidence", "judgement"]


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", str(value or "").strip())
    text = text.strip("-").lower()
    return text or f"section-{uuid.uuid4().hex[:8]}"


def _coerce_stage(value: str | None) -> OutlineStage:
    raw = str(value or "").strip().lower()
    if raw in {"foundation", "evidence", "judgement"}:
        return raw  # type: ignore[return-value]
    if raw in {"judgment", "decision", "recommendation", "conclusion"}:
        return "judgement"
    if raw in {"background", "overview", "definition"}:
        return "foundation"
    return "evidence"


@dataclass
class OutlineSection:
    id: str
    title: str
    intent: str
    key_questions: list[str] = field(default_factory=list)
    stage: OutlineStage = "evidence"
    priority: float = 0.5
    required: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int) -> "OutlineSection":
        title = str(data.get("title") or "").strip()
        section_id = str(data.get("id") or "").strip() or _slugify(title or f"section-{index}")
        intent = str(data.get("intent") or title).strip() or title or f"Section {index}"
        key_questions = [str(item).strip() for item in (data.get("key_questions") or []) if str(item).strip()]
        if not key_questions and title:
            key_questions = [f"What is the most important evidence for {title}?"]
        try:
            priority = float(data.get("priority", 0.5))
        except (TypeError, ValueError):
            priority = 0.5
        priority = max(0.0, min(1.0, priority))
        required = bool(data.get("required", True))
        return cls(
            id=section_id,
            title=title or f"Section {index}",
            intent=intent,
            key_questions=key_questions,
            stage=_coerce_stage(data.get("stage")),
            priority=priority,
            required=required,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "intent": self.intent,
            "key_questions": self.key_questions,
            "stage": self.stage,
            "priority": self.priority,
            "required": self.required,
        }


@dataclass
class ResearchOutline:
    outline_id: str
    query: str
    objective: str
    audience: str | None = None
    constraints: list[str] = field(default_factory=list)
    sections: list[OutlineSection] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any], query_hint: str | None = None) -> "ResearchOutline":
        outline_id = str(data.get("outline_id") or "").strip() or uuid.uuid4().hex
        query = str(data.get("query") or query_hint or "").strip()
        objective = str(data.get("objective") or query or "").strip() or "Deliver decision-ready research findings."
        audience = str(data.get("audience") or "").strip() or None
        constraints = [str(item).strip() for item in (data.get("constraints") or []) if str(item).strip()]
        raw_sections = data.get("sections") or []
        sections = [OutlineSection.from_dict(item, idx + 1) for idx, item in enumerate(raw_sections) if isinstance(item, dict)]

        if not sections:
            base = query or "the topic"
            sections = [
                OutlineSection(
                    id="foundation-1",
                    title="Context and Definitions",
                    intent=f"Define the problem and context for {base}.",
                    key_questions=[f"What baseline context is required to evaluate {base}?"],
                    stage="foundation",
                    priority=0.9,
                    required=True,
                ),
                OutlineSection(
                    id="evidence-1",
                    title="Evidence and Comparative Findings",
                    intent=f"Gather measurable evidence and competing approaches for {base}.",
                    key_questions=[f"What evidence is strongest for {base}?", "Where do sources disagree?"],
                    stage="evidence",
                    priority=0.8,
                    required=True,
                ),
                OutlineSection(
                    id="judgement-1",
                    title="Decision and Recommendations",
                    intent=f"Provide clear recommendations for {base}.",
                    key_questions=["What action should be taken next and why?"],
                    stage="judgement",
                    priority=0.7,
                    required=True,
                ),
            ]

        return cls(
            outline_id=outline_id,
            query=query,
            objective=objective,
            audience=audience,
            constraints=constraints,
            sections=sections,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "outline_id": self.outline_id,
            "query": self.query,
            "objective": self.objective,
            "audience": self.audience,
            "constraints": self.constraints,
            "sections": [section.to_dict() for section in self.sections],
        }


@dataclass
class SectionSpec:
    id: str
    title: str
    purpose: str
    stage: OutlineStage
    required_evidence_types: list[str] = field(default_factory=list)
    min_citations: int = 1
    must_include: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any], fallback_title: str = "") -> "SectionSpec":
        title = str(data.get("title") or fallback_title or "").strip() or "Section"
        section_id = str(data.get("id") or "").strip() or _slugify(title)
        stage = _coerce_stage(str(data.get("stage") or "evidence"))
        required_types = [str(item).strip() for item in (data.get("required_evidence_types") or []) if str(item).strip()]
        if not required_types:
            required_types = ["quantitative", "primary_source"] if stage == "evidence" else ["cross_source"]
        min_citations = int(data.get("min_citations", 1) or 1)
        min_citations = max(0, min_citations)
        must_include = [str(item).strip() for item in (data.get("must_include") or []) if str(item).strip()]
        purpose = str(data.get("purpose") or data.get("intent") or title).strip() or title
        return cls(
            id=section_id,
            title=title,
            purpose=purpose,
            stage=stage,
            required_evidence_types=required_types,
            min_citations=min_citations,
            must_include=must_include,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "purpose": self.purpose,
            "stage": self.stage,
            "required_evidence_types": self.required_evidence_types,
            "min_citations": self.min_citations,
            "must_include": self.must_include,
        }


@dataclass
class ReportBlueprint:
    section_order: list[str]
    section_specs: list[SectionSpec]
    narrative_strategy: str = "pyramid"
    citation_policy: dict[str, Any] = field(default_factory=dict)
    output_constraints: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any], outline: ResearchOutline | None = None) -> "ReportBlueprint":
        section_specs_raw = data.get("section_specs") or []
        specs = [SectionSpec.from_dict(item) for item in section_specs_raw if isinstance(item, dict)]

        if not specs and outline:
            specs = [
                SectionSpec(
                    id=section.id,
                    title=section.title,
                    purpose=section.intent,
                    stage=section.stage,
                    required_evidence_types=["quantitative", "primary_source"] if section.stage == "evidence" else ["cross_source"],
                    min_citations=2 if section.stage == "evidence" else 1,
                    must_include=["conflict_status"] if section.stage == "judgement" else [],
                )
                for section in outline.sections
            ]

        section_order = [str(item).strip() for item in (data.get("section_order") or []) if str(item).strip()]
        if not section_order:
            section_order = [spec.id for spec in specs]

        return cls(
            section_order=section_order,
            section_specs=specs,
            narrative_strategy=str(data.get("narrative_strategy") or "pyramid"),
            citation_policy=data.get("citation_policy") or {
                "core_claim_min_tier": "T2",
                "require_source_tier": True,
                "core_claim_min_anchors": 1,
            },
            output_constraints=[str(item).strip() for item in (data.get("output_constraints") or []) if str(item).strip()],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_order": self.section_order,
            "section_specs": [spec.to_dict() for spec in self.section_specs],
            "narrative_strategy": self.narrative_strategy,
            "citation_policy": self.citation_policy,
            "output_constraints": self.output_constraints,
        }


def outline_stage_to_task_stage(stage: OutlineStage) -> TaskStage:
    if stage == "foundation":
        return TaskStage.FOUNDATION
    if stage == "judgement":
        return TaskStage.JUDGEMENT
    return TaskStage.EVIDENCE


def validate_research_outline(outline: ResearchOutline) -> tuple[bool, list[str]]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    stage_set: set[str] = set()

    for section in outline.sections:
        if not section.title.strip():
            errors.append(f"section_title_empty:{section.id}")
        normalized_id = section.id.strip().lower()
        normalized_title = section.title.strip().lower()
        if normalized_id in seen_ids:
            errors.append(f"section_id_duplicated:{section.id}")
        seen_ids.add(normalized_id)
        if normalized_title in seen_titles:
            errors.append(f"section_title_duplicated:{section.title}")
        seen_titles.add(normalized_title)
        stage_set.add(section.stage)

    required_stages = {"foundation", "evidence", "judgement"}
    missing = sorted(required_stages - stage_set)
    if missing:
        errors.append(f"missing_stages:{','.join(missing)}")

    return len(errors) == 0, errors


def build_blueprint_from_outline(
    outline: ResearchOutline,
    *,
    output_constraints: list[str] | None = None,
    citation_policy: dict[str, Any] | None = None,
) -> ReportBlueprint:
    section_specs: list[SectionSpec] = []
    section_order: list[str] = []
    for section in outline.sections:
        min_citations = 2 if section.stage == "evidence" else 1
        required_types = ["quantitative", "primary_source"] if section.stage == "evidence" else ["cross_source"]
        must_include = []
        if section.stage == "judgement":
            must_include.extend(["decision_recommendation", "risk_tradeoff"])
        section_specs.append(
            SectionSpec(
                id=section.id,
                title=section.title,
                purpose=section.intent,
                stage=section.stage,
                required_evidence_types=required_types,
                min_citations=min_citations,
                must_include=must_include,
            )
        )
        section_order.append(section.id)

    default_constraints = ["must_include_decision_recommendations", "must_include_risk_list", "must_include_comparison_table"]
    return ReportBlueprint(
        section_order=section_order,
        section_specs=section_specs,
        narrative_strategy="pyramid",
        citation_policy=citation_policy or {
            "core_claim_min_tier": "T2",
            "require_source_tier": True,
            "core_claim_min_anchors": 1,
        },
        output_constraints=output_constraints or default_constraints,
    )

