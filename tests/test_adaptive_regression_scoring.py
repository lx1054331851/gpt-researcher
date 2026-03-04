from __future__ import annotations

import re
from pathlib import Path

from gpt_researcher.actions.report_generation import (
    _calculate_reference_url_ratio,
    _check_explicit_chain_sections,
    evaluate_goal_alignment,
)
from gpt_researcher.orchestration.coverage_lenses import assess_chain_coverage, resolve_chain_steps


def _extract_topic(report: str) -> str:
    for line in report.splitlines():
        text = line.strip()
        if text.startswith("# "):
            return text[2:].strip()
    for line in report.splitlines():
        text = line.strip()
        if text.startswith("## "):
            return text[3:].strip()
    return "research topic"


def _tokenize_topic(topic: str) -> list[str]:
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_-]{2,}", topic)
    return [t.lower() for t in tokens[:8]]


def _score_topic_fit(report: str, topic: str) -> float:
    tokens = _tokenize_topic(topic)
    if not tokens:
        return 5.0
    lower = report.lower()
    hits = sum(1 for token in tokens if token in lower)
    return round(min(10.0, 3.0 + 7.0 * (hits / len(tokens))), 2)


def _score_goal_completion(report: str) -> float:
    lower = report.lower()
    has_conclusion = any(h in lower for h in ["## 结论", "## conclusion", "## recommendations"])
    action_tokens = (
        "建议", "行动", "路线图", "优先级", "recommend", "action", "roadmap", "priority",
    )
    action_hits = sum(1 for token in action_tokens if token in lower)
    base = 4.0 + min(4.0, action_hits * 0.6)
    if has_conclusion:
        base += 2.0
    return round(min(10.0, base), 2)


def _score_structure_flow(report: str) -> float:
    h2_count = sum(1 for line in report.splitlines() if line.strip().startswith("## "))
    paragraph_count = sum(1 for line in report.splitlines() if line.strip() and not line.strip().startswith("#"))
    score = 3.0 + min(4.0, h2_count * 0.7) + min(3.0, paragraph_count / 30.0)
    return round(min(10.0, score), 2)


def _score_evidence_quality(report: str) -> float:
    citations = len(re.findall(r"\[[^\]]+\]\((https?://[^\s)]+)\)", report))
    numbers = len(re.findall(r"\b\d+(?:\.\d+)?%?\b", report))
    score = 2.5 + min(4.5, citations * 0.25) + min(3.0, numbers * 0.05)
    return round(min(10.0, score), 2)


def _score_report(report: str) -> dict[str, float]:
    topic = _extract_topic(report)
    return {
        "贴题度": _score_topic_fit(report, topic),
        "目标达成": _score_goal_completion(report),
        "结构流畅度": _score_structure_flow(report),
        "证据质量": _score_evidence_quality(report),
    }


def _score_chain_alignment(report: str) -> dict[str, float | bool]:
    topic = _extract_topic(report)
    chain_steps = resolve_chain_steps(profile_mode="dual", industry_profile="auto", query=topic)
    chain_cov = assess_chain_coverage([report], chain_steps=chain_steps)
    section_check = _check_explicit_chain_sections(report)
    goal_ok, _issues = evaluate_goal_alignment(report, topic)
    return {
        "chain_coverage_ratio": float(chain_cov.get("ratio", 0.0)),
        "explicit_chain_sections_ok": bool(section_check.get("explicit_ok")),
        "reference_url_ratio": float(_calculate_reference_url_ratio(report)),
        "goal_alignment_ok": bool(goal_ok),
    }


def test_regression_compare_scores_for_sample_reports():
    current_report_path = Path("outputs/task_1772591891_584a607d8a.md")
    gemini_report_path = Path("data/gemini_final_report.md")

    if not current_report_path.exists() or not gemini_report_path.exists():
        # Keep the test non-blocking in environments without these artifacts.
        assert True
        return

    current_scores = _score_report(current_report_path.read_text(encoding="utf-8", errors="ignore"))
    gemini_scores = _score_report(gemini_report_path.read_text(encoding="utf-8", errors="ignore"))

    print("Current report scores:", current_scores)
    print("Gemini report scores:", gemini_scores)

    for label in ["贴题度", "目标达成", "结构流畅度", "证据质量"]:
        assert label in current_scores
        assert label in gemini_scores
        assert 0.0 <= current_scores[label] <= 10.0
        assert 0.0 <= gemini_scores[label] <= 10.0


def test_regression_compare_chain_metrics_for_sample_reports():
    current_report_path = Path("outputs/task_1772591891_584a607d8a.md")
    gemini_report_path = Path("data/gemini_final_report.md")

    if not current_report_path.exists() or not gemini_report_path.exists():
        assert True
        return

    current_metrics = _score_chain_alignment(current_report_path.read_text(encoding="utf-8", errors="ignore"))
    gemini_metrics = _score_chain_alignment(gemini_report_path.read_text(encoding="utf-8", errors="ignore"))

    print("Current chain metrics:", current_metrics)
    print("Gemini chain metrics:", gemini_metrics)

    for key in ["chain_coverage_ratio", "reference_url_ratio"]:
        assert 0.0 <= float(current_metrics[key]) <= 1.0
        assert 0.0 <= float(gemini_metrics[key]) <= 1.0
    for key in ["explicit_chain_sections_ok", "goal_alignment_ok"]:
        assert isinstance(current_metrics[key], bool)
        assert isinstance(gemini_metrics[key], bool)
