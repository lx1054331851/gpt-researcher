import asyncio
from types import SimpleNamespace

from gpt_researcher.config import Config
from gpt_researcher.orchestration.task_graph import TaskNode, TaskStage
from gpt_researcher.prompts import PromptFamily
from gpt_researcher.skills import adaptive_deep_research
from gpt_researcher.skills.adaptive_deep_research import AdaptiveDeepResearchSkill


def _dummy_researcher():
    return SimpleNamespace(
        cfg=SimpleNamespace(
            strategic_llm_model="test-model",
            strategic_llm_provider="test-provider",
            smart_llm_model="test-model",
            smart_llm_provider="test-provider",
            llm_kwargs={},
            deep_research_breadth=3,
            deep_research_concurrency=2,
            adaptive_coverage_profile="high_coverage",
        ),
        websocket=None,
        headers={},
        query_domains=[],
        retrievers=[],
        query="test prompt contract",
        visited_urls=set(),
        research_sources=[],
        scraper_manager=None,
        add_research_sources=lambda sources: None,
        context="",
        research_trace={},
    )


def test_adaptive_report_prompt_mentions_coverage_and_gap_notes():
    prompt_family = PromptFamily(Config())
    prompt = prompt_family.generate_adaptive_deep_research_prompt(
        question="How should a supplier plan 2027 product strategy?",
        context="evidence package",
        report_source="web",
        language="english",
    )
    lowered = prompt.lower()
    assert "coverage lenses" in lowered
    assert "coverage check" in lowered
    assert "gap notes" in lowered
    assert "single lens" in lowered or "single dimension" in lowered
    assert "decision sheet" in lowered
    assert "macro context" in lowered and "execution roadmap" in lowered
    assert "include explicit section headers" in lowered or "explicit chain sections" in lowered
    assert "chain map: 行业→品牌→需求→材料→技术→落地" in prompt
    assert "frontier radar" in lowered
    assert "evidence maturity (t1/t2/t3)" in lowered
    assert "execution track" in lowered and "frontier track" in lowered
    assert "reference hygiene rules" in lowered


def test_query_matrix_prompt_uses_cross_intent_sampling(monkeypatch):
    researcher = _dummy_researcher()
    skill = AdaptiveDeepResearchSkill(researcher)
    captured = {"prompt": ""}

    async def fake_create_chat_completion(**kwargs):
        captured["prompt"] = kwargs["messages"][-1]["content"]
        return '["query a", "query b"]'

    monkeypatch.setattr(adaptive_deep_research, "create_chat_completion", fake_create_chat_completion)
    node = TaskNode(
        node_id="evidence_1",
        title="Evidence coverage node",
        description="Collect broad decision evidence",
        stage=TaskStage.EVIDENCE,
        uncertainty=0.6,
    )
    queries = asyncio.run(skill._generate_query_matrix(node, 1))
    assert len(queries) == 2
    text = captured["prompt"].lower()
    assert "overall research objective" in text
    assert "counter-evidence" in text
    assert "economics and operational feasibility" in text
    assert "implementation examples and roadmap signals" in text
    assert "currently uncovered chain steps" in text
    assert "must cover at least" in text


def test_dimension_planning_prompt_requires_orthogonal_coverage(monkeypatch):
    researcher = _dummy_researcher()
    skill = AdaptiveDeepResearchSkill(researcher)
    captured = {"prompt": ""}

    async def fake_create_chat_completion(**kwargs):
        captured["prompt"] = kwargs["messages"][-1]["content"]
        return '["Scope", "Baseline", "Options", "Stakeholders", "Economics", "Risk", "Competition", "Roadmap"]'

    monkeypatch.setattr(adaptive_deep_research, "create_chat_completion", fake_create_chat_completion)
    dimensions = asyncio.run(skill._plan_dimensions("cross-domain planning"))
    assert len(dimensions) >= 6
    text = captured["prompt"].lower()
    assert "orthogonal" in text
    assert "coverage lenses" in text
    assert "avoid single-angle plans" in text
