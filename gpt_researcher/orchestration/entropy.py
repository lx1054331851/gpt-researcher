"""Information gain and saturation metrics."""

from __future__ import annotations

from dataclasses import dataclass
import re


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _normalize_claims(claims: list[str]) -> set[str]:
    return {_normalize(c) for c in claims if c and c.strip()}


@dataclass
class LoopMetrics:
    novelty_score: float
    redundancy_score: float
    entropy_gain: float
    saturated: bool


class EntropyTracker:
    """Tracks novelty/redundancy and stop conditions per node."""

    def __init__(self, min_gain: float, patience: int = 2):
        self.min_gain = min_gain
        self.patience = patience
        self._low_gain_streak: dict[str, int] = {}

    def evaluate(
        self,
        node_id: str,
        new_claims: list[str],
        known_claims: set[str],
    ) -> LoopMetrics:
        normalized_new = _normalize_claims(new_claims)
        if not normalized_new:
            novelty = 0.0
            redundancy = 1.0
        else:
            unique_new = normalized_new - known_claims
            novelty = len(unique_new) / len(normalized_new)
            redundancy = 1.0 - novelty

        entropy_gain = novelty - redundancy
        if entropy_gain < self.min_gain:
            self._low_gain_streak[node_id] = self._low_gain_streak.get(node_id, 0) + 1
        else:
            self._low_gain_streak[node_id] = 0

        saturated = self._low_gain_streak.get(node_id, 0) >= self.patience
        return LoopMetrics(
            novelty_score=novelty,
            redundancy_score=redundancy,
            entropy_gain=entropy_gain,
            saturated=saturated,
        )
