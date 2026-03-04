import asyncio
from types import SimpleNamespace

from gpt_researcher.orchestration.task_graph import TaskNode, TaskStage
from gpt_researcher.skills import adaptive_deep_research
from gpt_researcher.skills.adaptive_deep_research import AdaptiveDeepResearchSkill


def _researcher_for_frontier():
    cfg = SimpleNamespace(
        strategic_llm_model="test-model",
        strategic_llm_provider="test-provider",
        smart_llm_model="test-model",
        smart_llm_provider="test-provider",
        llm_kwargs={},
        deep_research_breadth=6,
        deep_research_concurrency=2,
        adaptive_max_queries_per_round=6,
        adaptive_frontier_query_ratio=0.35,
        adaptive_exploration_profile="high_recall",
    )
    return SimpleNamespace(
        cfg=cfg,
        websocket=None,
        headers={},
        query_domains=[],
        retrievers=[],
        query="2027 shirt fabric roadmap",
        visited_urls=set(),
        research_sources=[],
        scraper_manager=None,
        add_research_sources=lambda sources: None,
        context="",
        research_trace={},
    )


def test_query_matrix_enforces_frontier_queries(monkeypatch):
    skill = AdaptiveDeepResearchSkill(_researcher_for_frontier())

    async def fake_create_chat_completion(**kwargs):
        return """[
          "[core] uniqlo shirt fabric baseline 2027",
          "[core] uniqlo shirt material cost and capacity",
          "[core] uniqlo shirt compliance and regulation",
          "[core] uniqlo shirt implementation roadmap"
        ]"""

    monkeypatch.setattr(adaptive_deep_research, "create_chat_completion", fake_create_chat_completion)
    node = TaskNode(
        node_id="evidence_1",
        title="Evidence",
        description="evidence node",
        stage=TaskStage.EVIDENCE,
        uncertainty=0.4,
    )

    queries = asyncio.run(skill._generate_query_matrix(node, 1))
    assert queries
    frontier_count = sum(
        1 for query in queries
        if skill._query_track_map.get(skill._normalize_query_signature(query)) == "frontier"
    )
    assert frontier_count >= 2
    assert skill.diagnostics["frontier_query_count"] >= frontier_count


def test_force_frontier_round_uses_frontier_fallback(monkeypatch):
    skill = AdaptiveDeepResearchSkill(_researcher_for_frontier())

    async def fake_create_chat_completion(**kwargs):
        raise RuntimeError("force fallback")

    monkeypatch.setattr(adaptive_deep_research, "create_chat_completion", fake_create_chat_completion)
    node = TaskNode(
        node_id="evidence_2",
        title="Technology",
        description="technology node",
        stage=TaskStage.EVIDENCE,
        uncertainty=0.6,
    )

    queries = asyncio.run(skill._generate_query_matrix(node, 2, force_frontier=True))
    assert queries
    frontier_count = sum(
        1 for query in queries
        if skill._query_track_map.get(skill._normalize_query_signature(query)) == "frontier"
    )
    assert frontier_count >= 1
