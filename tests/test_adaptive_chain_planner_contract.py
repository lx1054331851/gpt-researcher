import asyncio
import json
from types import SimpleNamespace

from gpt_researcher.skills import research_planner
from gpt_researcher.skills.research_planner import (
    assess_outline_chain_coverage,
    generate_outline,
)


def _cfg_for_chain() -> SimpleNamespace:
    return SimpleNamespace(
        strategic_llm_model="test-model",
        strategic_llm_provider="test-provider",
        llm_kwargs={},
        language="english",
        adaptive_coverage_enhancer_enabled=False,
        adaptive_coverage_min_ratio=0.75,
        adaptive_coverage_revise_max_rounds=1,
        adaptive_chain_enforcer_enabled=True,
        adaptive_chain_min_ratio=0.90,
        adaptive_chain_patch_max_rounds=1,
        adaptive_chain_profile_mode="dual",
        adaptive_chain_industry_profile="auto",
    )


def _sparse_chain_outline(query: str) -> dict:
    return {
        "query": query,
        "objective": f"Analyze {query}",
        "scope": "Focus on macro and brand baseline.",
        "workstreams": [
            {
                "id": "ws-1",
                "title": "Industry and brand baseline",
                "intent": "Only cover industry trend and brand baseline",
                "deliverable": "Baseline memo",
            }
        ],
        "evidence_requirements": ["Use credible sources"],
        "deliverables": ["One recommendation"],
        "risk_controls": ["Mark uncertainty"],
        "must_answer_questions": [f"What should we do for {query}?"],
        "constraints": ["Stay decision-oriented"],
        "sections": [
            {
                "id": "foundation-1",
                "title": "Industry Context",
                "intent": "Industry baseline and macro context",
                "key_questions": ["What is the macro context?"],
                "stage": "foundation",
                "priority": 0.9,
                "required": True,
            },
            {
                "id": "evidence-1",
                "title": "Brand Baseline",
                "intent": "Brand positioning and current baseline",
                "key_questions": ["What is the brand baseline?"],
                "stage": "evidence",
                "priority": 0.8,
                "required": True,
            },
            {
                "id": "judgement-1",
                "title": "Decision",
                "intent": "High-level next step",
                "key_questions": ["What should be done next?"],
                "stage": "judgement",
                "priority": 0.7,
                "required": True,
            },
        ],
    }


def _full_chain_outline(query: str) -> dict:
    return {
        "query": query,
        "objective": f"Analyze {query}",
        "scope": "Cover industry, brand, demand, material, technology, and execution.",
        "workstreams": [
            {
                "id": "ws-1",
                "title": "Industry trajectory",
                "intent": "Apparel industry outlook and trajectory",
                "deliverable": "Industry baseline",
            },
            {
                "id": "ws-2",
                "title": "Brand strategy baseline",
                "intent": "Brand/group product baseline and strategy",
                "deliverable": "Brand baseline",
            },
            {
                "id": "ws-3",
                "title": "Demand signals",
                "intent": "Consumer demand and stakeholder signals",
                "deliverable": "Demand map",
            },
            {
                "id": "ws-4",
                "title": "Material constraints",
                "intent": "Fiber and raw material upstream constraints",
                "deliverable": "Material constraint matrix",
            },
            {
                "id": "ws-5",
                "title": "Technology pathway",
                "intent": "Fabric/process technology routes",
                "deliverable": "Tech route comparison",
            },
            {
                "id": "ws-6",
                "title": "Execution rollout",
                "intent": "Pilot milestones and execution roadmap",
                "deliverable": "Execution plan",
            },
        ],
        "evidence_requirements": ["Use verified references"],
        "deliverables": ["Decision-ready recommendation"],
        "risk_controls": ["Mark unresolved gaps"],
        "must_answer_questions": [f"What should be done for {query}?"],
        "constraints": ["Keep chain complete"],
        "sections": [
            {
                "id": "foundation-1",
                "title": "Industry and Brand Baseline",
                "intent": "Industry context and brand baseline",
                "key_questions": ["What is changing in the apparel industry and brand baseline?"],
                "stage": "foundation",
                "priority": 0.9,
                "required": True,
            },
            {
                "id": "evidence-1",
                "title": "Demand, Material, and Technology",
                "intent": "Demand signals, material constraints, and technology pathways",
                "key_questions": ["How do demand, material, and technology interact?"],
                "stage": "evidence",
                "priority": 0.8,
                "required": True,
            },
            {
                "id": "judgement-1",
                "title": "Execution Roadmap",
                "intent": "Execution rollout and decision actions",
                "key_questions": ["What is the rollout plan and go/no-go gate?"],
                "stage": "judgement",
                "priority": 0.7,
                "required": True,
            },
        ],
    }


def test_generate_outline_prompt_includes_chain_constraints(monkeypatch):
    captured = {"prompt": ""}
    cfg = _cfg_for_chain()
    query = "2027 shirt fabric strategy for UNIQLO supplier"

    async def fake_create_chat_completion(**kwargs):
        captured["prompt"] = kwargs["messages"][-1]["content"]
        return json.dumps(_full_chain_outline(query))

    monkeypatch.setattr(research_planner, "create_chat_completion", fake_create_chat_completion)

    outline, _ = asyncio.run(
        generate_outline(
            query=query,
            user_requirements="decision oriented",
            language="english",
            report_style="strategic_report",
            source_policy="medium_tier",
            cfg=cfg,
        )
    )
    prompt_text = captured["prompt"].lower()
    assert outline.query == query
    assert "coverage chain to preserve explicit end-to-end logic" in prompt_text
    assert "industry -> brand/entity -> demand -> materials/inputs -> technology/process -> execution" in prompt_text
    assert "apparel industry context and external trajectory" in prompt_text


def test_generate_outline_revises_once_when_chain_is_missing(monkeypatch):
    cfg = _cfg_for_chain()
    query = "2027 shirt fabric strategy for UNIQLO supplier"
    calls = {"count": 0}

    async def fake_create_chat_completion(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return json.dumps(_sparse_chain_outline(query))
        return json.dumps(_full_chain_outline(query))

    monkeypatch.setattr(research_planner, "create_chat_completion", fake_create_chat_completion)

    outline, _ = asyncio.run(
        generate_outline(
            query=query,
            user_requirements="decision oriented",
            language="english",
            report_style="strategic_report",
            source_policy="medium_tier",
            cfg=cfg,
        )
    )
    chain_cov = assess_outline_chain_coverage(outline)
    assert calls["count"] == 2
    assert chain_cov["ratio"] >= 0.90
