import asyncio
from types import SimpleNamespace

from gpt_researcher.actions import report_generation
from gpt_researcher.utils.enum import Tone


def _cfg() -> SimpleNamespace:
    return SimpleNamespace(
        smart_llm_model="test-model",
        smart_llm_provider="test-provider",
        smart_token_limit=1200,
        llm_kwargs={},
        report_format="APA",
        total_words=900,
        language="english",
        report_completion_guard_enabled=True,
        report_completion_max_attempts=0,
        report_completion_require_marker=False,
        report_sectional_fallback_enabled=False,
        report_sectional_preflight_enabled=False,
        adaptive_coverage_enhancer_enabled=False,
        adaptive_chain_enforcer_enabled=True,
        adaptive_chain_min_ratio=0.90,
        adaptive_chain_require_explicit_sections=True,
        adaptive_chain_patch_max_rounds=1,
        adaptive_chain_profile_mode="generic",
        adaptive_chain_industry_profile="auto",
        adaptive_reference_url_min_ratio=0.80,
    )


def test_generate_report_patches_missing_explicit_chain_sections(monkeypatch):
    calls = {"total": 0, "patch_called": 0}

    async def fake_create_chat_completion(**kwargs):
        calls["total"] += 1
        prompt = kwargs["messages"][-1]["content"]
        if "ADAPTIVE_ARTIFACT_PATCH_TASK" in prompt:
            calls["patch_called"] += 1
            return """
## Industry
Industry macro baseline and trend signals. ([I](https://example.com/i))
## Brand
Brand strategy and current baseline. ([B](https://example.com/b))
## Demand
Consumer demand and stakeholder requirements. ([D](https://example.com/d))
## Material
Raw material and upstream constraints. ([M](https://example.com/m))
## Technology
Technology/process pathways and tradeoffs. ([T](https://example.com/t))
## Execution
Execution roadmap and rollout milestones. ([E](https://example.com/e))
Chain Map: 行业→品牌→需求→材料→技术→落地
"""

        return """
# Report
## Findings
Industry macro trend is shifting. Brand strategy baseline is changing.
Consumer demand requires comfort and durability.
Raw material and upstream supply constraints remain tight.
Technology/process options are maturing, and execution roadmap is needed.

## Coverage Check
- Covered lenses: baseline, options, demand, economics, risk, roadmap.
- Gap Notes: competition benchmark needs more proof with next-round evidence.

## Decision Sheet
| Option | Expected Value | Feasibility | Main Risk | First Experiment | Go/No-Go Signal |
|---|---|---|---|---|---|
| A | High | Medium | Cost | Pilot line | Defect rate < 2% |

## Conclusion
Use staged rollout with material-risk gates.

## References
- [S1](https://example.com/s1)
- [S2](https://example.com/s2)
"""

    monkeypatch.setattr(report_generation, "create_chat_completion", fake_create_chat_completion)

    metadata = {}
    report = asyncio.run(
        report_generation.generate_report(
            query="2027 shirt fabric development strategy",
            context="test context",
            agent_role_prompt="You are a test analyst.",
            report_type="adaptive_deep",
            tone=Tone.Objective,
            report_source="web",
            websocket=None,
            cfg=_cfg(),
            generation_metadata_callback=metadata.update,
        )
    )

    assert "## Industry" in report
    assert "## Execution" in report
    assert "Chain Map: 行业→品牌→需求→材料→技术→落地" in report
    assert metadata["adaptive_artifact_patch_applied"] is True
    assert metadata["explicit_chain_sections_ok"] is True
    assert metadata["chain_section_order_ok"] is True
    assert metadata["chain_patch_reason"] == "missing_artifacts_or_explicit_chain_sections"
    assert metadata["reference_url_ratio"] >= 0.80
    assert calls["patch_called"] == 1
