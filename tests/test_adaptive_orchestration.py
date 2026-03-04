from gpt_researcher.orchestration.budget import BranchBudgetManager
from gpt_researcher.orchestration.conflict_solver import detect_conflicts
from gpt_researcher.orchestration.entropy import EntropyTracker
from gpt_researcher.orchestration.saliency import SaliencyDetector
from gpt_researcher.orchestration.task_graph import TaskStatus, build_default_task_graph


def test_task_graph_dependency_order():
    graph = build_default_task_graph(
        "AI adoption",
        [
            "Background and definitions",
            "Current state data",
            "Recommendations and strategy",
        ],
    )

    ready = graph.get_ready_nodes()
    assert ready
    assert all(node.node_id.startswith("foundation_") for node in ready)

    for node in ready:
        graph.mark_status(node.node_id, TaskStatus.COMPLETED)

    ready_after_foundation = graph.get_ready_nodes()
    assert ready_after_foundation
    assert all(node.node_id.startswith("evidence_") for node in ready_after_foundation)

    exported = graph.export_state()
    assert "dependencies" in exported
    assert exported["dependencies"]
    assert any(dep["to"].startswith("evidence_") for dep in exported["dependencies"])


def test_entropy_tracker_saturation():
    tracker = EntropyTracker(min_gain=0.08, patience=2)
    known = {"already known fact"}

    first = tracker.evaluate("n1", ["new fact"], known)
    assert first.entropy_gain > 0
    assert not first.saturated

    second = tracker.evaluate("n1", ["already known fact"], known)
    assert second.entropy_gain < 0.08
    assert not second.saturated

    third = tracker.evaluate("n1", ["already known fact"], known)
    assert third.saturated


def test_saliency_and_branch_budget():
    detector = SaliencyDetector(threshold=0.6)
    is_salient, score = detector.is_salient(
        research_goal="AI impact on healthcare productivity",
        finding="New studies show AI improves hospital productivity by 20 percent",
        known_claims=set(),
        source_url="https://www.who.int/news",
    )
    assert is_salient
    assert score >= 0.6

    budget = BranchBudgetManager(max_branches=1, max_queries_per_branch=2)
    assert budget.register_branch("rabbit_1", "evidence_1")
    assert budget.can_consume_query("rabbit_1")
    assert budget.consume_query("rabbit_1")
    assert budget.consume_query("rabbit_1")
    assert not budget.can_consume_query("rabbit_1")
    assert budget.consume_query("foundation_1")  # main-line query is always counted
    assert budget.total_queries == 3
    assert not budget.consume_query("rabbit_unknown", is_branch=True)
    assert not budget.can_spawn_branch()


def test_conflict_detection():
    claims = [
        "Revenue increased in 2025 due to AI adoption in operations.",
        "Revenue decreased in 2025 due to AI adoption in operations.",
        "Customer retention remained stable during the same period.",
    ]
    conflicts = detect_conflicts(claims)
    assert conflicts
    assert conflicts[0].reason
