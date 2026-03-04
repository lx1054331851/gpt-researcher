"""Research trace model for adaptive deep research."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResearchTrace:
    planner: dict[str, Any] = field(default_factory=dict)
    loop_metrics: list[dict[str, Any]] = field(default_factory=list)
    replans: list[dict[str, Any]] = field(default_factory=list)
    budget: dict[str, Any] = field(default_factory=dict)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    citations: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    outline: dict[str, Any] = field(default_factory=dict)
    blueprint: dict[str, Any] = field(default_factory=dict)
    claim_ledger: list[dict[str, Any]] = field(default_factory=list)
    citation_coverage: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def set_planner(self, planner: dict[str, Any]) -> None:
        self.planner = planner

    def add_loop_metric(self, metric: dict[str, Any]) -> None:
        self.loop_metrics.append(metric)

    def add_replan(self, replan: dict[str, Any]) -> None:
        self.replans.append(replan)

    def set_budget(self, budget: dict[str, Any]) -> None:
        self.budget = budget

    def add_conflict(self, conflict: dict[str, Any]) -> None:
        self.conflicts.append(conflict)

    def add_citation(self, claim: str, anchor: dict[str, Any]) -> None:
        self.citations.setdefault(claim, []).append(anchor)

    def set_diagnostics(self, diagnostics: dict[str, Any]) -> None:
        self.diagnostics = diagnostics

    def set_outline(self, outline: dict[str, Any]) -> None:
        self.outline = outline

    def set_blueprint(self, blueprint: dict[str, Any]) -> None:
        self.blueprint = blueprint

    def set_claim_ledger(self, claim_ledger: list[dict[str, Any]]) -> None:
        self.claim_ledger = claim_ledger

    def set_citation_coverage(self, citation_coverage: dict[str, Any]) -> None:
        self.citation_coverage = citation_coverage

    def to_dict(self) -> dict[str, Any]:
        return {
            "planner": self.planner,
            "loop_metrics": self.loop_metrics,
            "replans": self.replans,
            "budget": self.budget,
            "conflicts": self.conflicts,
            "citations": self.citations,
            "outline": self.outline,
            "blueprint": self.blueprint,
            "claim_ledger": self.claim_ledger,
            "citation_coverage": self.citation_coverage,
            "diagnostics": self.diagnostics,
        }
