import asyncio
import json
from types import SimpleNamespace

from gpt_researcher.skills import research_planner
from gpt_researcher.skills.research_planner import assess_outline_coverage, generate_outline


def _test_cfg():
    return SimpleNamespace(
        strategic_llm_model="test-model",
        strategic_llm_provider="test-provider",
        llm_kwargs={},
        language="english",
        adaptive_coverage_enhancer_enabled=True,
        adaptive_coverage_min_ratio=0.75,
        adaptive_coverage_revise_max_rounds=1,
    )


def _sparse_outline_payload(query: str) -> dict:
    return {
        "query": query,
        "objective": f"Analyze {query}",
        "scope": "Technical architecture focus only.",
        "workstreams": [
            {"id": "ws-1", "title": "Tech architecture", "intent": "Model and infra only", "deliverable": "Tech memo"}
        ],
        "sections": [
            {
                "id": "foundation-1",
                "title": "Technical framing",
                "intent": "Architecture and model details",
                "key_questions": ["What architecture should we use?"],
                "stage": "foundation",
                "priority": 0.9,
                "required": True,
            },
            {
                "id": "evidence-1",
                "title": "Technical evidence",
                "intent": "Benchmark and model scores",
                "key_questions": ["Which model scores better?"],
                "stage": "evidence",
                "priority": 0.8,
                "required": True,
            },
            {
                "id": "judgement-1",
                "title": "Technical judgement",
                "intent": "Recommend technical stack",
                "key_questions": ["Which stack should we choose?"],
                "stage": "judgement",
                "priority": 0.7,
                "required": True,
            },
        ],
    }


def _broad_outline_payload(query: str) -> dict:
    return {
        "query": query,
        "objective": f"Decision-ready plan for {query}",
        "scope": "Scope constraints, baseline, options, economics, risk, benchmark, and roadmap.",
        "workstreams": [
            {"id": "ws-1", "title": "Stakeholder demand", "intent": "User/buyer demand mapping", "deliverable": "Demand matrix"},
            {"id": "ws-2", "title": "Economics and feasibility", "intent": "Cost/capacity/timeline feasibility", "deliverable": "Feasibility model"},
            {"id": "ws-3", "title": "Risk and compliance", "intent": "Regulatory and uncertainty analysis", "deliverable": "Risk register"},
        ],
        "sections": [
            {
                "id": "foundation-1",
                "title": "Scope and Baseline",
                "intent": "Frame constraints and baseline evidence",
                "key_questions": ["What is in scope and current baseline?"],
                "stage": "foundation",
                "priority": 0.9,
                "required": True,
            },
            {
                "id": "evidence-1",
                "title": "Options, Economics, and Benchmarks",
                "intent": "Compare options with economics and competitor benchmarks",
                "key_questions": ["Which option wins on tradeoffs?"],
                "stage": "evidence",
                "priority": 0.8,
                "required": True,
            },
            {
                "id": "judgement-1",
                "title": "Risk-managed Roadmap",
                "intent": "Priorities, risks, actions, and implementation roadmap",
                "key_questions": ["What should be done next and when?"],
                "stage": "judgement",
                "priority": 0.7,
                "required": True,
            },
        ],
    }


def test_generate_outline_revises_when_coverage_is_low(monkeypatch):
    query = "enterprise AI rollout strategy"
    calls = {"count": 0}

    async def fake_create_chat_completion(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return json.dumps(_sparse_outline_payload(query))
        return json.dumps(_broad_outline_payload(query))

    monkeypatch.setattr(research_planner, "create_chat_completion", fake_create_chat_completion)
    outline, _blueprint = asyncio.run(
        generate_outline(
            query=query,
            user_requirements="keep it practical",
            language="english",
            report_style="strategic_report",
            source_policy="medium_tier",
            cfg=_test_cfg(),
        )
    )
    coverage = assess_outline_coverage(outline)
    assert calls["count"] == 2
    assert coverage["ratio"] >= 0.75


def test_generate_outline_marks_gap_if_still_insufficient(monkeypatch):
    query = "enterprise AI rollout strategy"
    calls = {"count": 0}

    async def fake_create_chat_completion(**kwargs):
        calls["count"] += 1
        return json.dumps(_sparse_outline_payload(query))

    monkeypatch.setattr(research_planner, "create_chat_completion", fake_create_chat_completion)
    outline, _blueprint = asyncio.run(
        generate_outline(
            query=query,
            user_requirements="keep it practical",
            language="english",
            report_style="strategic_report",
            source_policy="medium_tier",
            cfg=_test_cfg(),
        )
    )
    coverage = assess_outline_coverage(outline)
    assert calls["count"] == 2
    assert coverage["ratio"] < 0.75
    assert any("Coverage gap retained" in item for item in (outline.constraints or []))

