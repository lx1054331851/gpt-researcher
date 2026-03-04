"""Conflict detection helpers for claim-level evidence."""

from __future__ import annotations

from dataclasses import dataclass
import itertools
import re


POSITIVE_CUES = {
    "increase",
    "increased",
    "growth",
    "higher",
    "improved",
    "benefit",
    "supports",
    "up",
    "rise",
}
NEGATIVE_CUES = {
    "decrease",
    "decreased",
    "decline",
    "lower",
    "worse",
    "risk",
    "opposes",
    "down",
    "drop",
}


@dataclass
class ConflictRecord:
    claim_a: str
    claim_b: str
    reason: str
    status: str = "unresolved"

    def to_dict(self) -> dict:
        return {
            "claim_a": self.claim_a,
            "claim_b": self.claim_b,
            "reason": self.reason,
            "status": self.status,
        }


def _tokenize(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", value.lower()))


def _polarity(value: str) -> int:
    tokens = _tokenize(value)
    pos = len(tokens & POSITIVE_CUES)
    neg = len(tokens & NEGATIVE_CUES)
    if pos > neg:
        return 1
    if neg > pos:
        return -1
    return 0


def detect_conflicts(claims: list[str]) -> list[ConflictRecord]:
    records: list[ConflictRecord] = []
    normalized = [c for c in claims if c and c.strip()]
    for left, right in itertools.combinations(normalized, 2):
        left_tokens = _tokenize(left)
        right_tokens = _tokenize(right)
        shared = left_tokens & right_tokens
        if len(shared) < 3:
            continue
        if _polarity(left) * _polarity(right) == -1:
            records.append(
                ConflictRecord(
                    claim_a=left,
                    claim_b=right,
                    reason="Opposite directional signals on overlapping topic.",
                )
            )
    return records


def build_resolution_queries(conflict: ConflictRecord, base_query: str) -> list[str]:
    return [
        f"{base_query} third-party verification for: {conflict.claim_a}",
        f"{base_query} independent evidence contradicting or confirming: {conflict.claim_b}",
        f"{base_query} methodology comparison and source of disagreement",
    ]
