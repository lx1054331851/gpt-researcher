import asyncio
from types import SimpleNamespace

from gpt_researcher.actions import report_generation
from gpt_researcher.config import Config
from gpt_researcher.prompts import PromptFamily, get_prompt_by_report_type, report_type_mapping
from gpt_researcher.utils.enum import ReportType
from gpt_researcher.utils.enum import Tone


def test_evaluate_report_completeness_detects_trailing_header():
    partial_report = """# Title
## Executive Summary
Some summary text.
### 4"""
    complete, missing = report_generation.evaluate_report_completeness(
        partial_report,
        require_sections=True,
        require_marker=True,
    )
    assert not complete
    assert "trailing_header_without_content" in missing


def test_prompt_routing_deep_and_adaptive_are_decoupled():
    assert report_type_mapping[ReportType.DeepResearch.value] == "generate_deep_research_prompt"
    assert report_type_mapping[ReportType.AdaptiveDeepResearch.value] == "generate_adaptive_deep_research_prompt"

    prompt_family = PromptFamily(Config())
    deep_prompt = get_prompt_by_report_type(ReportType.DeepResearch.value, prompt_family)
    adaptive_prompt = get_prompt_by_report_type(ReportType.AdaptiveDeepResearch.value, prompt_family)

    assert deep_prompt.__name__ == "generate_deep_research_prompt"
    assert adaptive_prompt.__name__ == "generate_adaptive_deep_research_prompt"


def test_generate_report_auto_continuation(monkeypatch):
    async def fake_create_chat_completion(**kwargs):
        messages = kwargs["messages"]
        content = messages[-1]["content"]
        callback = kwargs.get("finish_reason_callback")

        if "Continue the existing report" in content:
            if callback:
                callback("stop")
            return """## 结论
关键结论已补全。

## 参考文献
- [Source](https://example.com/source)
<!-- REPORT_COMPLETE -->"""

        if callback:
            callback("length")
        return """# 测试报告
## 摘要
这是被截断的输出。
### 4"""

    monkeypatch.setattr(report_generation, "create_chat_completion", fake_create_chat_completion)

    cfg = SimpleNamespace(
        smart_llm_model="test-model",
        smart_llm_provider="test-provider",
        smart_token_limit=1200,
        llm_kwargs={},
        report_format="APA",
        total_words=1200,
        language="chinese",
        report_completion_guard_enabled=True,
        report_completion_max_attempts=2,
        report_completion_require_marker=True,
        report_sectional_preflight_enabled=False,
    )

    metadata = {}
    report = asyncio.run(
        report_generation.generate_report(
            query="test query",
            context="test context",
            agent_role_prompt="You are a test analyst.",
            report_type="adaptive_deep",
            tone=Tone.Objective,
            report_source="web",
            websocket=None,
            cfg=cfg,
            custom_prompt="Write a concise report.",
            generation_metadata_callback=metadata.update,
        )
    )

    assert "## 结论" in report
    assert "## 参考文献" in report
    assert "<!-- REPORT_COMPLETE -->" not in report
    assert metadata["continuation_attempts"] == 1
    assert metadata["final_complete"] is True
    assert "length" in metadata["finish_reasons"]


def test_extract_section_titles_from_outline():
    outline = """
## 执行摘要
## 关键发现
### 次级标题（应忽略）
## 风险与不确定性
"""
    titles = report_generation.extract_section_titles_from_outline(outline, max_sections=5)
    assert titles == ["执行摘要", "关键发现", "风险与不确定性"]


def test_generate_report_uses_sectional_fallback(monkeypatch):
    async def fake_create_chat_completion(**kwargs):
        messages = kwargs["messages"]
        content = messages[-1]["content"]
        callback = kwargs.get("finish_reason_callback")
        if callback:
            callback("length")

        if "SECTIONAL_OUTLINE_TASK" in content:
            return "## 执行摘要\n## 关键发现\n## 结论"
        if "SECTIONAL_SECTION_TASK" in content:
            if "Section Title: 执行摘要" in content:
                return "## 执行摘要\n摘要内容。([S1](https://example.com/s1))"
            if "Section Title: 关键发现" in content:
                return "## 关键发现\n关键发现内容。([S2](https://example.com/s2))"
            if "Section Title: 结论" in content:
                return "## 结论\n结论内容。([S3](https://example.com/s3))"
        if "SECTIONAL_REFERENCES_TASK" in content:
            return "## 参考文献\n- [S1](https://example.com/s1)\n- [S2](https://example.com/s2)\n- [S3](https://example.com/s3)"

        # Initial generation + continuation remain incomplete.
        return "# 报告\n## 摘要\n不完整输出。\n### 4"

    monkeypatch.setattr(report_generation, "create_chat_completion", fake_create_chat_completion)

    cfg = SimpleNamespace(
        smart_llm_model="test-model",
        smart_llm_provider="test-provider",
        smart_token_limit=1200,
        llm_kwargs={},
        report_format="APA",
        total_words=1200,
        language="chinese",
        report_completion_guard_enabled=True,
        report_completion_max_attempts=1,
        report_completion_require_marker=True,
        report_sectional_fallback_enabled=True,
        report_sectional_max_sections=4,
        report_sectional_context_chars=8000,
        report_sectional_preflight_enabled=False,
    )

    metadata = {}
    report = asyncio.run(
        report_generation.generate_report(
            query="test query",
            context="test context",
            agent_role_prompt="You are a test analyst.",
            report_type="adaptive_deep",
            tone=Tone.Objective,
            report_source="web",
            websocket=None,
            cfg=cfg,
            custom_prompt="Write a concise report.",
            generation_metadata_callback=metadata.update,
        )
    )

    assert "## 执行摘要" in report
    assert "## 关键发现" in report
    assert "## 结论" in report
    assert "## 参考文献" in report
    assert metadata["used_sectional_fallback"] is True
    assert metadata["sectional_fallback"]["assembled_sections"] >= 3


def test_generate_report_sectional_preflight(monkeypatch):
    async def fake_create_chat_completion(**kwargs):
        messages = kwargs["messages"]
        content = messages[-1]["content"]
        callback = kwargs.get("finish_reason_callback")
        if callback:
            callback("stop")

        if "SECTIONAL_OUTLINE_TASK" in content:
            return "## 执行摘要\n## 结论"
        if "SECTIONAL_SECTION_TASK" in content:
            if "Section Title: 执行摘要" in content:
                return "## 执行摘要\n预判分节内容。([S1](https://example.com/s1))"
            return "## 结论\n预判分节结论。([S2](https://example.com/s2))"
        if "SECTIONAL_REFERENCES_TASK" in content:
            return "## 参考文献\n- [S1](https://example.com/s1)\n- [S2](https://example.com/s2)"

        raise AssertionError("Preflight test should not call full-report generation path")

    monkeypatch.setattr(report_generation, "create_chat_completion", fake_create_chat_completion)

    cfg = SimpleNamespace(
        smart_llm_model="test-model",
        smart_llm_provider="test-provider",
        smart_token_limit=1200,
        llm_kwargs={},
        report_format="APA",
        total_words=1200,
        language="chinese",
        report_completion_guard_enabled=True,
        report_completion_max_attempts=1,
        report_completion_require_marker=True,
        report_sectional_fallback_enabled=True,
        report_sectional_preflight_enabled=True,
        report_sectional_preflight_min_context_chars=1,
        report_sectional_max_sections=4,
        report_sectional_context_chars=8000,
    )

    metadata = {}
    report = asyncio.run(
        report_generation.generate_report(
            query="test query",
            context="x" * 200,
            agent_role_prompt="You are a test analyst.",
            report_type="adaptive_deep",
            tone=Tone.Objective,
            report_source="web",
            websocket=None,
            cfg=cfg,
            custom_prompt="Write a concise report.",
            generation_metadata_callback=metadata.update,
        )
    )

    assert "## 执行摘要" in report
    assert "## 结论" in report
    assert "## 参考文献" in report
    assert metadata["used_sectional_preflight"] is True
    assert metadata["continuation_attempts"] == 0


def test_generate_report_blueprint_mode(monkeypatch):
    async def fake_create_chat_completion(**kwargs):
        content = kwargs["messages"][-1]["content"]
        callback = kwargs.get("finish_reason_callback")
        if callback:
            callback("stop")

        if "BLUEPRINT_SECTION_TASK" in content and "Section Title: Executive Summary" in content:
            return "## Executive Summary\nSummary with citation [S1](https://example.com/s1)."
        if "BLUEPRINT_SECTION_TASK" in content and "Section Title: Evidence" in content:
            return "## Evidence\nEvidence details [S2](https://example.com/s2)."
        if "BLUEPRINT_SECTION_TASK" in content and "Section Title: Recommendation" in content:
            return "## Recommendation\nRecommendation details [S3](https://example.com/s3)."
        if "generate a concise and clear conclusion section" in content.lower():
            return "## Conclusion\nFinal conclusion."

        return "## Section\nFallback body."

    monkeypatch.setattr(report_generation, "create_chat_completion", fake_create_chat_completion)

    cfg = SimpleNamespace(
        smart_llm_model="test-model",
        smart_llm_provider="test-provider",
        strategic_llm_model="test-model",
        strategic_llm_provider="test-provider",
        smart_token_limit=1200,
        llm_kwargs={},
        report_format="APA",
        total_words=1200,
        language="english",
        report_completion_guard_enabled=True,
        report_completion_max_attempts=1,
        report_completion_require_marker=True,
        report_sectional_fallback_enabled=True,
        report_sectional_preflight_enabled=False,
    )

    blueprint = {
        "section_order": ["s1", "s2", "s3"],
        "section_specs": [
            {"id": "s1", "title": "Executive Summary", "purpose": "Summarize key findings", "stage": "foundation", "required_evidence_types": ["cross_source"], "min_citations": 1},
            {"id": "s2", "title": "Evidence", "purpose": "Provide evidence", "stage": "evidence", "required_evidence_types": ["quantitative"], "min_citations": 1},
            {"id": "s3", "title": "Recommendation", "purpose": "Provide decision guidance", "stage": "judgement", "required_evidence_types": ["cross_source"], "min_citations": 1},
        ],
    }

    metadata = {}
    report = asyncio.run(
        report_generation.generate_report(
            query="test query",
            context="test context",
            agent_role_prompt="You are a test analyst.",
            report_type="adaptive_deep",
            tone=Tone.Objective,
            report_source="web",
            websocket=None,
            cfg=cfg,
            report_blueprint=blueprint,
            user_requirements="focus on decision support",
            generation_metadata_callback=metadata.update,
        )
    )

    assert "## Executive Summary" in report
    assert "## Evidence" in report
    assert "## Recommendation" in report
    assert metadata["used_blueprint_mode"] is True
    assert metadata["blueprint_coverage_ok"] is True
