"""Saliency scoring for unexpected discoveries."""

from __future__ import annotations

import re


def _tokenize(value: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]{3,}", value.lower())
    return set(tokens)


def _lexical_overlap(a: str, b: str) -> float:
    ta = _tokenize(a)
    tb = _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _domain_credibility(url: str | None) -> float:
    if not url:
        return 0.55
    value = url.lower()
    if any(s in value for s in [".gov", ".edu"]):
        return 0.95
    if any(s in value for s in [".org", "nature.com", "science.org", "who.int", "oecd.org"]):
        return 0.85
    if any(s in value for s in [".com", ".io", ".ai"]):
        return 0.65
    return 0.55


STOPWORDS = {
    "and",
    "the",
    "for",
    "with",
    "that",
    "this",
    "from",
    "new",
    "show",
    "shows",
    "study",
    "studies",
    "impact",
}


class SaliencyDetector:
    """Scores whether a finding is significant enough to trigger re-planning."""

    def __init__(self, threshold: float):
        self.threshold = threshold

    def score(
        self,
        research_goal: str,
        finding: str,
        known_claims: set[str],
        source_url: str | None = None,
    ) -> float:
        relevance = _lexical_overlap(research_goal, finding)
        novelty = 0.0 if finding.lower().strip() in known_claims else 1.0
        credibility = _domain_credibility(source_url)

        # Bonus for shared high-signal terms to avoid under-scoring semantically
        # close findings with low lexical Jaccard (e.g., healthcare vs hospital).
        goal_tokens = _tokenize(research_goal) - STOPWORDS
        finding_tokens = _tokenize(finding) - STOPWORDS
        shared_signal = len(goal_tokens & finding_tokens)
        signal_bonus = min(0.20, 0.06 * shared_signal)

        return 0.40 * relevance + 0.35 * novelty + 0.25 * credibility + signal_bonus

    def is_salient(
        self,
        research_goal: str,
        finding: str,
        known_claims: set[str],
        source_url: str | None = None,
    ) -> tuple[bool, float]:
        score = self.score(research_goal, finding, known_claims, source_url)
        return score >= self.threshold, score
