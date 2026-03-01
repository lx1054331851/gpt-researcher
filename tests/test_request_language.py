import os
import sys
import types
import asyncio

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Keep unit tests isolated from optional runtime dependencies.
markdown_stub = types.ModuleType("markdown")
markdown_stub.markdown = lambda *_args, **_kwargs: ""
sys.modules.setdefault("markdown", markdown_stub)

mistune_stub = types.ModuleType("mistune")
mistune_stub.html = lambda *_args, **_kwargs: ""
sys.modules.setdefault("mistune", mistune_stub)

sys.modules.setdefault("json5", types.ModuleType("json5"))

from backend.server.server_utils import extract_command_data
from backend.server import websocket_manager as ws_manager


def test_extract_command_data_includes_language():
    payload = {
        "task": "test task",
        "report_type": "research_report",
        "report_source": "web",
        "tone": "Objective",
        "language": "chinese",
        "query_domains": ["example.com"],
    }

    result = extract_command_data(payload)

    assert len(result) == 12
    assert result[0] == "test task"
    assert result[1] == "research_report"
    assert result[5] == "chinese"


class _DummyConfig:
    def __init__(self, _config_path=None):
        self.language = "english"
        self.prompt_family = "default"
        self.embedding_provider = "dummy"
        self.embedding_model = "dummy"
        self.embedding_kwargs = {}

    def set_verbose(self, _verbose: bool):
        return None


class _DummyComponent:
    def __init__(self, *_args, **_kwargs):
        pass


class _DummyImageGenerator(_DummyComponent):
    pass


def test_gpt_researcher_instance_language_override(monkeypatch):
    import gpt_researcher.agent as agent_mod

    monkeypatch.setattr(agent_mod, "Config", _DummyConfig)
    monkeypatch.setattr(agent_mod, "get_prompt_family", lambda *_args, **_kwargs: "default")
    monkeypatch.setattr(agent_mod, "get_retrievers", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(agent_mod, "Memory", _DummyComponent)
    monkeypatch.setattr(agent_mod, "ResearchConductor", _DummyComponent)
    monkeypatch.setattr(agent_mod, "ReportGenerator", _DummyComponent)
    monkeypatch.setattr(agent_mod, "ContextManager", _DummyComponent)
    monkeypatch.setattr(agent_mod, "BrowserManager", _DummyComponent)
    monkeypatch.setattr(agent_mod, "SourceCurator", _DummyComponent)
    monkeypatch.setattr(agent_mod, "ImageGenerator", _DummyImageGenerator)

    researcher = agent_mod.GPTResearcher(query="test", language="chinese")
    assert researcher.cfg.language == "chinese"

    default_researcher = agent_mod.GPTResearcher(query="test")
    assert default_researcher.cfg.language == "english"


class _DummyLogsHandler:
    def __init__(self, *_args, **_kwargs):
        pass

    async def send_json(self, _data):
        return None


@pytest.mark.parametrize(
    "report_type,builder_name",
    [
        ("research_report", "basic"),
        ("detailed_report", "detailed"),
    ],
)
def test_run_agent_passes_language_to_report_builders(monkeypatch, report_type, builder_name):
    captured = {}

    class _BaseDummyReport:
        def __init__(self, **kwargs):
            captured["language"] = kwargs.get("language")
            captured["builder"] = builder_name

        async def run(self):
            return "ok"

    monkeypatch.setattr(ws_manager, "CustomLogsHandler", _DummyLogsHandler)

    if builder_name == "basic":
        monkeypatch.setattr(ws_manager, "BasicReport", _BaseDummyReport)
    else:
        monkeypatch.setattr(ws_manager, "DetailedReport", _BaseDummyReport)

    result = asyncio.run(
        ws_manager.run_agent(
            task="task",
            report_type=report_type,
            report_source="web",
            source_urls=[],
            document_urls=[],
            tone="Objective",
            websocket=object(),
            stream_output=lambda *_args, **_kwargs: None,
            language="chinese",
        )
    )

    assert result == "ok"
    assert captured["language"] == "chinese"


def test_run_agent_passes_language_to_multi_agents(monkeypatch):
    captured = {}

    async def _fake_run_research_task(**kwargs):
        captured["language"] = kwargs.get("language")
        return {"report": "multi"}

    monkeypatch.setattr(ws_manager, "CustomLogsHandler", _DummyLogsHandler)
    monkeypatch.setattr(ws_manager, "run_research_task", _fake_run_research_task)

    result = asyncio.run(
        ws_manager.run_agent(
            task="task",
            report_type="multi_agents",
            report_source="web",
            source_urls=[],
            document_urls=[],
            tone="Objective",
            websocket=object(),
            stream_output=lambda *_args, **_kwargs: None,
            language="chinese",
        )
    )

    assert result == "multi"
    assert captured["language"] == "chinese"
