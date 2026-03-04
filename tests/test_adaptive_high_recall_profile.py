from types import SimpleNamespace

from gpt_researcher.orchestration.task_graph import TaskNode, TaskStage
from gpt_researcher.skills.adaptive_deep_research import AdaptiveDeepResearchSkill


def _researcher_with_high_recall():
    cfg = SimpleNamespace(
        deep_research_breadth=3,
        deep_research_concurrency=2,
        adaptive_max_rounds_per_node=2,
        adaptive_max_queries_per_round=3,
        adaptive_max_sources_per_query=5,
        tavily_advanced_enabled=False,
        tavily_search_depth_default="basic",
        adaptive_exploration_profile="high_recall",
        adaptive_frontier_query_ratio=0.35,
        adaptive_min_unique_domains=25,
        adaptive_min_unique_urls=45,
        strategic_llm_model="test-model",
        strategic_llm_provider="test-provider",
        smart_llm_model="test-model",
        smart_llm_provider="test-provider",
        llm_kwargs={},
    )
    return SimpleNamespace(
        cfg=cfg,
        websocket=None,
        headers={},
        query_domains=[],
        retrievers=[],
        query="2027 shirt fabric strategy",
        visited_urls=set(),
        research_sources=[],
        scraper_manager=None,
        add_research_sources=lambda sources: None,
        context="",
        research_trace={},
    )


def test_high_recall_profile_expands_round_and_query_budgets():
    skill = AdaptiveDeepResearchSkill(_researcher_with_high_recall())
    assert skill.exploration_profile == "high_recall"
    assert skill.max_queries_per_round >= 6
    assert skill.max_rounds_per_node >= 3
    assert skill.max_sources_per_query >= 8
    assert skill.breadth >= 6


def test_high_recall_profile_uses_advanced_search_depth_for_foundation_and_evidence():
    skill = AdaptiveDeepResearchSkill(_researcher_with_high_recall())
    foundation_node = TaskNode(
        node_id="foundation_1",
        title="Foundation",
        description="Scope",
        stage=TaskStage.FOUNDATION,
        uncertainty=0.2,
    )
    evidence_node = TaskNode(
        node_id="evidence_1",
        title="Evidence",
        description="Evidence",
        stage=TaskStage.EVIDENCE,
        uncertainty=0.2,
    )
    judgement_node = TaskNode(
        node_id="judgement_1",
        title="Judgement",
        description="Judgement",
        stage=TaskStage.JUDGEMENT,
        uncertainty=0.2,
    )

    assert skill._resolve_search_depth(foundation_node, has_conflict=False) == "advanced"
    assert skill._resolve_search_depth(evidence_node, has_conflict=False) == "advanced"
    assert skill._resolve_search_depth(judgement_node, has_conflict=False) in {"basic", "advanced"}
