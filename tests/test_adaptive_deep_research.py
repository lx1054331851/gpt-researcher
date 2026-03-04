import asyncio
from types import SimpleNamespace

from gpt_researcher.orchestration.task_graph import (
    TaskNode,
    TaskStage,
    TaskStatus,
    build_default_task_graph,
)
from gpt_researcher.skills.adaptive_deep_research import AdaptiveDeepResearchSkill


class DummyRetriever:
    def __init__(self, query, headers=None, query_domains=None):
        self.query = query
        self.headers = headers or {}
        self.query_domains = query_domains or []

    def search(self, max_results=5):
        return [
            {
                "href": "https://example.com/source",
                "title": "Example Source",
                "body": "AI adoption improves productivity with measurable gains.",
                "raw_content": "AI adoption improves productivity with measurable gains in enterprise workflows.",
            }
        ][:max_results]


class DummyScraperManager:
    async def browse_urls(self, urls):
        return []


def make_dummy_researcher():
    cfg = SimpleNamespace(
        deep_research_breadth=2,
        deep_research_concurrency=2,
        adaptive_min_depth=1,
        adaptive_max_depth=3,
        adaptive_quality_threshold=7.5,
        entropy_min_gain=0.08,
        saliency_threshold=0.72,
        tavily_search_depth_default="basic",
        tavily_advanced_enabled=True,
        rabbit_hole_max_queries_per_branch=2,
        rabbit_hole_max_branches=1,
        max_search_results_per_query=5,
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
        retrievers=[DummyRetriever],
        query="How does AI affect productivity?",
        visited_urls=set(),
        research_sources=[],
        scraper_manager=DummyScraperManager(),
        add_research_sources=lambda sources: None,
        context="",
        research_trace={},
    )


def test_adaptive_deep_research_run_with_mocked_planning(monkeypatch):
    researcher = make_dummy_researcher()
    skill = AdaptiveDeepResearchSkill(researcher)

    async def fake_plan_dimensions(query: str):
        return [
            "Background and definitions",
            "Current state and data",
            "Recommendations and implications",
        ]

    async def fake_query_matrix(node, round_index: int):
        return [f"{node.title} query {round_index}"]

    async def fake_extract_claims(query: str, context: str, urls: list[str]):
        return [("AI improves productivity in many organizations.", "https://example.com/source")]

    monkeypatch.setattr(skill, "_plan_dimensions", fake_plan_dimensions)
    monkeypatch.setattr(skill, "_generate_query_matrix", fake_query_matrix)
    monkeypatch.setattr(skill, "_extract_claims", fake_extract_claims)

    context = asyncio.run(skill.run())

    assert "Evidence Log" in context
    assert researcher.research_trace
    assert "planner" in researcher.research_trace
    assert "loop_metrics" in researcher.research_trace
    assert "citations" in researcher.research_trace
    assert "diagnostics" in researcher.research_trace
    assert researcher.visited_urls


def test_search_depth_switching():
    researcher = make_dummy_researcher()
    skill = AdaptiveDeepResearchSkill(researcher)
    node = TaskNode(
        node_id="evidence_1",
        title="Current evidence",
        description="Current evidence",
        stage=TaskStage.EVIDENCE,
        uncertainty=0.8,
    )

    assert skill._resolve_search_depth(node, has_conflict=False) == "advanced"
    assert skill._resolve_search_depth(node, has_conflict=True) == "advanced"

    node.uncertainty = 0.2
    assert skill._resolve_search_depth(node, has_conflict=False) == "basic"

    skill.tavily_advanced_enabled = False
    assert skill._resolve_search_depth(node, has_conflict=True) == "basic"


def test_source_quality_filter_prioritizes_and_limits_domains():
    researcher = make_dummy_researcher()
    skill = AdaptiveDeepResearchSkill(researcher)
    skill.max_sources_per_query = 3
    skill.max_sources_per_domain = 1
    skill.min_source_quality_score = 0.0
    skill.high_quality_domains = {"www.vfc.com", "www.sec.gov"}
    skill.low_quality_domains = {"www.accio.com"}

    results = [
        {"href": "https://www.accio.com/a", "title": "shopping guide", "body": "affiliate links"},
        {"href": "https://www.vfc.com/investors/a", "title": "earnings transcript", "body": "revenue gross margin guidance"},
        {"href": "https://www.vfc.com/investors/b", "title": "press release", "body": "revenue"},
        {"href": "https://www.sec.gov/ixviewer/xyz", "title": "10-k filing", "body": "operating margin"},
        {"href": "https://example.org/report", "title": "industry overview", "body": "revenue trends"},
    ]

    selected = skill._rank_and_filter_search_results(results)
    assert len(selected) <= 3
    selected_domains = [skill._domain_from_url(item["href"]) for item in selected]
    # Low-quality source should be filtered out.
    assert "www.accio.com" not in selected_domains
    # Domain cap should keep only one vfc.com result.
    assert selected_domains.count("www.vfc.com") <= 1
    hq_domains = {"www.vfc.com", "www.sec.gov"}
    assert sum(1 for domain in selected_domains if domain in hq_domains) >= 2


def test_adaptive_trace_contains_diagnostics(monkeypatch):
    researcher = make_dummy_researcher()
    skill = AdaptiveDeepResearchSkill(researcher)

    async def fake_plan_dimensions(query: str):
        return [
            "Background and definitions",
            "Current state and data",
            "Recommendations and implications",
        ]

    async def fake_query_matrix(node, round_index: int):
        return [f"{node.title} query {round_index}"]

    async def fake_extract_claims(query: str, context: str, urls: list[str]):
        return [("AI improves productivity in many organizations.", "https://example.com/source")]

    monkeypatch.setattr(skill, "_plan_dimensions", fake_plan_dimensions)
    monkeypatch.setattr(skill, "_generate_query_matrix", fake_query_matrix)
    monkeypatch.setattr(skill, "_extract_claims", fake_extract_claims)

    asyncio.run(skill.run())
    trace = researcher.research_trace
    assert "diagnostics" in trace
    assert isinstance(trace["diagnostics"], dict)


def test_query_context_uses_search_cache(monkeypatch):
    researcher = make_dummy_researcher()
    skill = AdaptiveDeepResearchSkill(researcher)
    skill.cache_enabled = True
    call_count = {"n": 0}

    async def fake_get_search_results(query, retriever, query_domains=None, researcher=None):
        call_count["n"] += 1
        return [
            {
                "href": "https://example.com/source",
                "title": "Cached Source",
                "body": "Cached context body",
                "raw_content": "Cached context body raw",
            }
        ]

    monkeypatch.setattr(
        "gpt_researcher.skills.adaptive_deep_research.get_search_results",
        fake_get_search_results,
    )

    node = TaskNode(
        node_id="evidence_cache",
        title="Cache test node",
        description="Cache test node",
        stage=TaskStage.EVIDENCE,
        uncertainty=0.2,
    )
    asyncio.run(skill._collect_query_context(node, "same query"))
    asyncio.run(skill._collect_query_context(node, "same query"))
    assert call_count["n"] == 1


def test_node_termination_reason_is_recorded(monkeypatch):
    researcher = make_dummy_researcher()
    skill = AdaptiveDeepResearchSkill(researcher)
    skill.max_rounds_per_node = 1

    async def fake_plan_dimensions(query: str):
        return ["Background and definitions", "Current state data", "Recommendations and strategy"]

    async def fake_query_matrix(node, round_index: int):
        return []

    monkeypatch.setattr(skill, "_plan_dimensions", fake_plan_dimensions)
    monkeypatch.setattr(skill, "_generate_query_matrix", fake_query_matrix)

    asyncio.run(skill.run())
    planner_nodes = researcher.research_trace.get("planner", {}).get("nodes", [])
    assert planner_nodes
    assert any(node.get("metadata", {}).get("termination_reason") for node in planner_nodes)


def test_early_stop_requires_min_completed_nodes():
    researcher = make_dummy_researcher()
    skill = AdaptiveDeepResearchSkill(researcher)
    skill.min_completed_nodes_for_early_stop = 4

    graph = build_default_task_graph(
        "AI adoption",
        [
            "Background and definitions",
            "Current state data",
            "Current state data by geography",
            "Current state data by channel",
            "Recommendations and strategy",
        ],
    )
    assert not skill._can_early_stop(graph)

    # Complete one foundation + one evidence only: still not enough.
    graph.mark_status("foundation_1", TaskStatus.COMPLETED)
    graph.mark_status("evidence_1", TaskStatus.COMPLETED)
    assert not skill._can_early_stop(graph)

    # Complete additional evidence nodes to reach threshold.
    for node_id in ["evidence_2", "evidence_3"]:
        if graph.get_node(node_id):
            graph.mark_status(node_id, TaskStatus.COMPLETED)
    assert skill._can_early_stop(graph)
