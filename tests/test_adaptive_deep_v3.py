import asyncio
import json
from types import SimpleNamespace

from backend.server import server_utils
from gpt_researcher.orchestration.outline_schema import (
    ResearchOutline,
    build_blueprint_from_outline,
    validate_research_outline,
)
from gpt_researcher.orchestration.task_graph import build_task_graph_from_outline
from gpt_researcher.skills.adaptive_deep_research import AdaptiveDeepResearchSkill


class FakeWebSocket:
    def __init__(self):
        self.json_messages = []
        self.text_messages = []

    async def send_json(self, payload):
        self.json_messages.append(payload)

    async def send_text(self, payload):
        self.text_messages.append(payload)


def _make_outline(query: str = "adaptive deep testing") -> ResearchOutline:
    return ResearchOutline.from_dict(
        {
            "outline_id": "outline_test",
            "query": query,
            "objective": "Validate two-stage execution",
            "sections": [
                {
                    "id": "foundation-1",
                    "title": "Context",
                    "intent": "Define scope and baseline assumptions",
                    "key_questions": ["What is the scope?"],
                    "stage": "foundation",
                    "priority": 0.9,
                    "required": True,
                },
                {
                    "id": "evidence-1",
                    "title": "Evidence",
                    "intent": "Collect measurable evidence",
                    "key_questions": ["What evidence is strongest?"],
                    "stage": "evidence",
                    "priority": 0.8,
                    "required": True,
                },
                {
                    "id": "judgement-1",
                    "title": "Decision",
                    "intent": "Provide recommendations",
                    "key_questions": ["What should be done next?"],
                    "stage": "judgement",
                    "priority": 0.7,
                    "required": True,
                },
            ],
        }
    )


def test_outline_schema_validation_detects_missing_stages():
    invalid_outline = ResearchOutline.from_dict(
        {
            "outline_id": "invalid",
            "query": "test",
            "objective": "invalid test",
            "sections": [
                {
                    "id": "s1",
                    "title": "Only evidence",
                    "intent": "Evidence only",
                    "key_questions": ["q1"],
                    "stage": "evidence",
                    "priority": 0.6,
                    "required": True,
                }
            ],
        }
    )
    valid, errors = validate_research_outline(invalid_outline)
    assert not valid
    assert any("missing_stages" in err for err in errors)


def test_locked_outline_builds_expected_dag_dependencies():
    outline = _make_outline()
    graph = build_task_graph_from_outline(outline.to_dict())
    exported = graph.export_state()

    node_by_id = {node["node_id"]: node for node in exported["nodes"]}
    assert "foundation-1" in node_by_id
    assert "evidence-1" in node_by_id
    assert "judgement-1" in node_by_id
    assert node_by_id["evidence-1"]["dependencies"] == ["foundation-1"]
    assert node_by_id["judgement-1"]["dependencies"] == ["evidence-1"]


def test_adaptive_deep_uses_locked_outline_without_free_planning(monkeypatch):
    outline = _make_outline()
    blueprint = build_blueprint_from_outline(outline)
    researcher = SimpleNamespace(
        cfg=SimpleNamespace(),
        websocket=None,
        headers={},
        query_domains=[],
        retrievers=[],
        query=outline.query,
        visited_urls=set(),
        research_sources=[],
        scraper_manager=None,
        add_research_sources=lambda sources: None,
        context="",
        research_trace={},
        research_outline=outline.to_dict(),
        report_blueprint=blueprint.to_dict(),
        user_requirements="",
    )
    skill = AdaptiveDeepResearchSkill(researcher)

    async def should_not_be_called(_query):
        raise AssertionError("_plan_dimensions should not run when locked outline is present")

    async def fake_process_node(node, depth_count, progress, graph, on_progress=None, deadline_ts=None):
        return "completed"

    monkeypatch.setattr(skill, "_plan_dimensions", should_not_be_called)
    monkeypatch.setattr(skill, "_process_node", fake_process_node)

    result = asyncio.run(skill.run())
    assert "Evidence Log" in result
    assert researcher.research_trace.get("outline", {}).get("outline_id") == "outline_test"
    assert researcher.research_trace.get("blueprint", {}).get("section_order")


def test_claim_ledger_and_citation_coverage_metrics():
    researcher = SimpleNamespace(
        cfg=SimpleNamespace(),
        websocket=None,
        headers={},
        query_domains=[],
        retrievers=[],
        query="claim-ledger test",
        visited_urls=set(),
        research_sources=[],
        scraper_manager=None,
        add_research_sources=lambda sources: None,
        context="",
        research_trace={},
    )
    skill = AdaptiveDeepResearchSkill(researcher)
    skill.claim_to_anchors = {
        "Claim A": [{"url": "https://www.sec.gov/ixviewer/a", "source_tier": "T1"}],
        "Claim B": [{"url": "https://example.com/blog/b", "source_tier": "T3"}],
    }
    skill.research_journal["contradictions"] = ["Claim A <-> Claim B"]

    ledger = skill._build_claim_ledger()
    coverage = skill._compute_citation_coverage()

    assert len(ledger) == 2
    assert any(item["source_tier"] == "T1" for item in ledger)
    assert coverage["core_claims_total"] == 2
    assert coverage["core_claims_with_anchor"] == 2
    assert coverage["coverage_ratio"] == 1.0


def test_websocket_two_stage_plan_flow(monkeypatch):
    outline = _make_outline()
    blueprint = build_blueprint_from_outline(outline)
    ws = FakeWebSocket()
    manager = SimpleNamespace()
    outline_session = {}

    async def fake_generate_outline(
        query,
        user_requirements=None,
        language=None,
        report_style=None,
        source_policy=None,
        cfg=None,
    ):
        return outline, blueprint

    async def fake_revise_outline(
        outline_obj,
        instruction,
        language=None,
        report_style=None,
        source_policy=None,
        cfg=None,
    ):
        revised = ResearchOutline.from_dict(
            {
                **outline_obj.to_dict(),
                "objective": f"{outline_obj.objective} | revised",
            }
        )
        return revised, build_blueprint_from_outline(revised)

    captured_execute = {}

    async def fake_handle_start_command(websocket, data, manager_obj, **kwargs):
        captured_execute.update(kwargs)
        await websocket.send_json({"type": "path", "output": {"md": "outputs/test.md"}})

    monkeypatch.setattr(server_utils, "generate_outline", fake_generate_outline)
    monkeypatch.setattr(server_utils, "revise_outline", fake_revise_outline)
    monkeypatch.setattr(server_utils, "handle_start_command", fake_handle_start_command)

    start_payload = {
        "task": "test two-stage",
        "report_type": "adaptive_deep",
        "report_source": "web",
        "tone": "Objective",
        "language": "english",
        "report_style": "consulting_brief",
        "source_policy": "medium_tier",
        "query_domains": [],
        "mcp_enabled": False,
        "mcp_strategy": "fast",
        "mcp_configs": [],
    }
    asyncio.run(
        server_utils.handle_start_plan_command(
            ws,
            f"start_plan {json.dumps(start_payload)}",
            manager,
            outline_session,
        )
    )
    assert ws.json_messages[-1]["type"] == "outline_draft"
    assert ws.json_messages[-1]["report_style"] == "consulting_brief"
    assert ws.json_messages[-1]["source_policy"] == "medium_tier"
    outline_id = ws.json_messages[-1]["outline_id"]

    revise_payload = {"outline_id": outline_id, "mode": "ai_rewrite", "instruction": "make it concise"}
    asyncio.run(
        server_utils.handle_revise_plan_command(
            ws,
            f"revise_plan {json.dumps(revise_payload)}",
            outline_session,
        )
    )
    assert ws.json_messages[-1]["type"] == "outline_updated"

    execute_payload = {"outline_id": outline_id}
    asyncio.run(
        server_utils.handle_execute_plan_command(
            ws,
            f"execute_plan {json.dumps(execute_payload)}",
            manager,
            outline_session,
        )
    )
    assert captured_execute.get("outline_locked") is True
    assert captured_execute.get("research_outline", {}).get("outline_id") == outline_id
    assert "report_blueprint" in captured_execute
    assert captured_execute.get("start_payload", {}).get("report_style") == "consulting_brief"


def test_execute_plan_blocks_invalid_outline_and_returns_validation_error(monkeypatch):
    outline = _make_outline(query="AI datacenter strategy 2027")
    blueprint = build_blueprint_from_outline(outline)
    ws = FakeWebSocket()
    manager = SimpleNamespace()
    outline_session = {}

    async def fake_generate_outline(
        query,
        user_requirements=None,
        language=None,
        report_style=None,
        source_policy=None,
        cfg=None,
    ):
        return outline, blueprint

    started = {"called": False}

    async def fake_handle_start_command(websocket, data, manager_obj, **kwargs):
        started["called"] = True

    monkeypatch.setattr(server_utils, "generate_outline", fake_generate_outline)
    monkeypatch.setattr(server_utils, "handle_start_command", fake_handle_start_command)

    asyncio.run(
        server_utils.handle_start_plan_command(
            ws,
            "start_plan " + json.dumps(
                {
                    "task": "AI datacenter strategy 2027",
                    "report_type": "adaptive_deep",
                    "report_source": "web",
                    "tone": "Objective",
                }
            ),
            manager,
            outline_session,
        )
    )
    outline_id = ws.json_messages[-1]["outline_id"]

    invalid_outline = outline.to_dict()
    invalid_outline["workstreams"] = [
        {
            "id": "ws-x",
            "title": "Unrelated gardening stream",
            "intent": "Plant flowers",
            "deliverable": "Garden notes",
        }
    ]
    invalid_outline["deliverables"] = ["Background notes only"]

    asyncio.run(
        server_utils.handle_execute_plan_command(
            ws,
            "execute_plan " + json.dumps(
                {
                    "outline_id": outline_id,
                    "approved_outline": invalid_outline,
                }
            ),
            manager,
            outline_session,
        )
    )

    assert started["called"] is False
    assert ws.json_messages[-1]["type"] == "outline_validation_error"
    assert "deliverables" in ws.json_messages[-1]["output"].lower()


def test_adaptive_trace_diagnostics_include_coverage_fields(monkeypatch):
    researcher = SimpleNamespace(
        cfg=SimpleNamespace(
            adaptive_coverage_enhancer_enabled=True,
            adaptive_coverage_min_ratio=0.75,
            adaptive_coverage_profile="high_coverage",
        ),
        websocket=None,
        headers={},
        query_domains=[],
        retrievers=[],
        query="coverage diagnostics test",
        visited_urls=set(),
        research_sources=[],
        scraper_manager=None,
        add_research_sources=lambda sources: None,
        context="",
        research_trace={},
        research_outline=None,
        report_blueprint=None,
        user_requirements="",
    )
    skill = AdaptiveDeepResearchSkill(researcher)

    async def fake_plan_dimensions(_query):
        return [
            "Problem framing and scope constraints",
            "Current state and baseline evidence",
            "Option comparison and tradeoffs",
            "Stakeholder demand signals",
            "Economics and feasibility",
            "Risk and compliance uncertainty",
            "Competition benchmarks",
            "Roadmap priorities and actions",
        ]

    async def fake_process_node(node, depth_count, progress, graph, on_progress=None, deadline_ts=None):
        return "completed"

    monkeypatch.setattr(skill, "_plan_dimensions", fake_plan_dimensions)
    monkeypatch.setattr(skill, "_process_node", fake_process_node)

    asyncio.run(skill.run())
    diagnostics = researcher.research_trace.get("diagnostics", {})
    assert "coverage_ratio" in diagnostics
    assert "coverage_missing_lenses_count" in diagnostics
    assert "chain_coverage_ratio" in diagnostics
    assert "chain_missing_steps_count" in diagnostics
    assert "chain_missing_steps" in diagnostics
    assert "chain_step_query_coverage" in diagnostics
    assert isinstance(diagnostics["chain_step_query_coverage"], list)
