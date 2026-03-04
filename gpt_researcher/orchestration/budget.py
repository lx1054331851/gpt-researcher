"""Budget gates for rabbit-hole exploration branches."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BranchBudget:
    branch_id: str
    parent_id: str | None
    max_queries: int
    used_queries: int = 0


class BranchBudgetManager:
    """Tracks and enforces per-branch and branch-count budgets."""

    def __init__(self, max_branches: int, max_queries_per_branch: int):
        self.max_branches = max_branches
        self.max_queries_per_branch = max_queries_per_branch
        self._branches: dict[str, BranchBudget] = {}
        self.total_queries = 0

    def can_spawn_branch(self) -> bool:
        return len(self._branches) < self.max_branches

    def register_branch(self, branch_id: str, parent_id: str | None = None) -> bool:
        if not self.can_spawn_branch():
            return False
        if branch_id in self._branches:
            return True
        self._branches[branch_id] = BranchBudget(
            branch_id=branch_id,
            parent_id=parent_id,
            max_queries=self.max_queries_per_branch,
        )
        return True

    def can_consume_query(self, branch_id: str, is_branch: bool = False) -> bool:
        budget = self._branches.get(branch_id)
        if budget is None:
            # Main-line nodes are unrestricted; rabbit-hole branches must be registered.
            return not is_branch
        return budget.used_queries < budget.max_queries

    def consume_query(self, branch_id: str, is_branch: bool = False) -> bool:
        if not self.can_consume_query(branch_id, is_branch=is_branch):
            return False

        budget = self._branches.get(branch_id)
        if budget is not None:
            budget.used_queries += 1
        self.total_queries += 1
        return True

    def export(self) -> dict:
        return {
            "max_branches": self.max_branches,
            "max_queries_per_branch": self.max_queries_per_branch,
            "total_queries": self.total_queries,
            "branches": [
                {
                    "branch_id": b.branch_id,
                    "parent_id": b.parent_id,
                    "used_queries": b.used_queries,
                    "max_queries": b.max_queries,
                    "exhausted": b.used_queries >= b.max_queries,
                }
                for b in self._branches.values()
            ],
        }
