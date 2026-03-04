from gpt_researcher.config import Config
from gpt_researcher.prompts import PromptFamily


def test_adaptive_prompt_requires_frontier_radar_contract():
    prompt = PromptFamily(Config()).generate_adaptive_deep_research_prompt(
        question="What should be the 2027 shirt fabric roadmap?",
        context="adaptive evidence package",
        report_source="web",
        language="english",
    )
    lowered = prompt.lower()
    assert "frontier radar" in lowered
    assert "evidence maturity (t1/t2/t3)" in lowered
    assert "2027 landing window (near/mid/far)" in lowered
    assert "key blocker (cost/capacity/compliance)" in lowered
    assert "next experiment" in lowered
    assert "execution track" in lowered
    assert "frontier track" in lowered
