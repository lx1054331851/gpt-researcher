"""Task graph primitives for adaptive deep research."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class TaskStage(str, Enum):
    FOUNDATION = "foundation"
    EVIDENCE = "evidence"
    JUDGEMENT = "judgement"


@dataclass
class TaskNode:
    node_id: str
    title: str
    description: str
    stage: TaskStage
    dependencies: list[str] = field(default_factory=list)
    priority: float = 0.5
    uncertainty: float = 0.5
    status: TaskStatus = TaskStatus.PENDING
    branch_type: str = "main"
    parent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["stage"] = self.stage.value
        data["status"] = self.status.value
        return data


class TaskGraph:
    """Simple DAG manager for research task scheduling."""

    def __init__(self) -> None:
        self.nodes: dict[str, TaskNode] = {}
        self._branch_counter = 0

    def add_node(self, node: TaskNode) -> None:
        self.nodes[node.node_id] = node

    def get_node(self, node_id: str) -> TaskNode | None:
        return self.nodes.get(node_id)

    def mark_status(self, node_id: str, status: TaskStatus) -> None:
        if node_id in self.nodes:
            self.nodes[node_id].status = status

    def add_branch_node(
        self,
        parent_node_id: str,
        title: str,
        description: str,
        priority: float = 0.8,
        uncertainty: float = 0.8,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        if parent_node_id not in self.nodes:
            return None

        self._branch_counter += 1
        branch_id = f"rabbit_{self._branch_counter}"
        self.add_node(
            TaskNode(
                node_id=branch_id,
                title=title,
                description=description,
                stage=TaskStage.EVIDENCE,
                dependencies=[parent_node_id],
                priority=priority,
                uncertainty=uncertainty,
                branch_type="rabbit_hole",
                parent_id=parent_node_id,
                metadata=metadata or {},
            )
        )
        return branch_id

    def get_ready_nodes(self, limit: int | None = None) -> list[TaskNode]:
        ready: list[TaskNode] = []
        for node in self.nodes.values():
            if node.status != TaskStatus.PENDING:
                continue
            if all(
                dep in self.nodes and self.nodes[dep].status == TaskStatus.COMPLETED
                for dep in node.dependencies
            ):
                ready.append(node)

        ready.sort(key=lambda n: (n.priority, n.uncertainty), reverse=True)
        if limit is not None:
            return ready[:limit]
        return ready

    def has_pending(self) -> bool:
        return any(n.status == TaskStatus.PENDING for n in self.nodes.values())

    def export_state(self) -> dict[str, Any]:
        dependencies: list[dict[str, str]] = []
        for node in self.nodes.values():
            for dep in node.dependencies:
                dependencies.append(
                    {
                        "from": dep,
                        "to": node.node_id,
                    }
                )
        return {
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "dependencies": dependencies,
        }


def _classify_stage(dimension: str) -> TaskStage:
    value = dimension.lower()
    foundation_keywords = {"definition", "background", "context", "history", "overview"}
    judgement_keywords = {"recommend", "decision", "strategy", "conclusion", "risk", "forecast"}

    if any(k in value for k in foundation_keywords):
        return TaskStage.FOUNDATION
    if any(k in value for k in judgement_keywords):
        return TaskStage.JUDGEMENT
    return TaskStage.EVIDENCE


def build_default_task_graph(query: str, dimensions: list[str]) -> TaskGraph:
    """
    Build a 3-stage DAG:
    foundation -> evidence -> judgement.
    """
    graph = TaskGraph()
    if not dimensions:
        dimensions = [
            f"Background and definitions for {query}",
            f"Current state and key data for {query}",
            f"Competing views and controversies about {query}",
            f"Practical implications and risks of {query}",
            f"Forward-looking trends for {query}",
            f"Decision framework and recommendations for {query}",
        ]

    staged: dict[TaskStage, list[str]] = {
        TaskStage.FOUNDATION: [],
        TaskStage.EVIDENCE: [],
        TaskStage.JUDGEMENT: [],
    }
    for dim in dimensions:
        staged[_classify_stage(dim)].append(dim)

    if not staged[TaskStage.FOUNDATION]:
        staged[TaskStage.FOUNDATION].append(f"Background and definitions for {query}")
    if not staged[TaskStage.EVIDENCE]:
        staged[TaskStage.EVIDENCE].append(f"Evidence and current state for {query}")
    if not staged[TaskStage.JUDGEMENT]:
        staged[TaskStage.JUDGEMENT].append(f"Recommendations and implications for {query}")

    foundation_ids: list[str] = []
    evidence_ids: list[str] = []

    for idx, dim in enumerate(staged[TaskStage.FOUNDATION], start=1):
        node_id = f"foundation_{idx}"
        graph.add_node(
            TaskNode(
                node_id=node_id,
                title=dim,
                description=dim,
                stage=TaskStage.FOUNDATION,
                priority=0.9,
                uncertainty=0.45,
            )
        )
        foundation_ids.append(node_id)

    for idx, dim in enumerate(staged[TaskStage.EVIDENCE], start=1):
        node_id = f"evidence_{idx}"
        graph.add_node(
            TaskNode(
                node_id=node_id,
                title=dim,
                description=dim,
                stage=TaskStage.EVIDENCE,
                dependencies=foundation_ids.copy(),
                priority=0.8,
                uncertainty=0.7,
            )
        )
        evidence_ids.append(node_id)

    judgement_dependencies = evidence_ids or foundation_ids
    for idx, dim in enumerate(staged[TaskStage.JUDGEMENT], start=1):
        node_id = f"judgement_{idx}"
        graph.add_node(
            TaskNode(
                node_id=node_id,
                title=dim,
                description=dim,
                stage=TaskStage.JUDGEMENT,
                dependencies=judgement_dependencies.copy(),
                priority=0.7,
                uncertainty=0.8,
            )
        )

    return graph


def build_task_graph_from_outline(outline: dict[str, Any]) -> TaskGraph:
    """Build a DAG directly from a locked outline structure."""
    graph = TaskGraph()
    sections = outline.get("sections") or []
    if not isinstance(sections, list):
        return graph

    stage_to_ids: dict[TaskStage, list[str]] = {
        TaskStage.FOUNDATION: [],
        TaskStage.EVIDENCE: [],
        TaskStage.JUDGEMENT: [],
    }

    for idx, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            continue
        raw_stage = str(section.get("stage") or "").lower().strip()
        if raw_stage in {"foundation"}:
            stage = TaskStage.FOUNDATION
        elif raw_stage in {"judgement", "judgment", "decision", "recommendation"}:
            stage = TaskStage.JUDGEMENT
        else:
            stage = TaskStage.EVIDENCE

        node_id = str(section.get("id") or "").strip() or f"{stage.value}_{idx}"
        title = str(section.get("title") or "").strip() or f"Section {idx}"
        description = str(section.get("intent") or section.get("description") or title).strip()
        try:
            priority = float(section.get("priority", 0.5))
        except (TypeError, ValueError):
            priority = 0.5
        priority = max(0.0, min(1.0, priority))

        dependencies = []
        if stage == TaskStage.EVIDENCE:
            dependencies = stage_to_ids[TaskStage.FOUNDATION].copy()
        elif stage == TaskStage.JUDGEMENT:
            dependencies = (
                stage_to_ids[TaskStage.EVIDENCE].copy()
                if stage_to_ids[TaskStage.EVIDENCE]
                else stage_to_ids[TaskStage.FOUNDATION].copy()
            )

        graph.add_node(
            TaskNode(
                node_id=node_id,
                title=title,
                description=description,
                stage=stage,
                dependencies=dependencies,
                priority=priority,
                uncertainty=0.65 if stage == TaskStage.EVIDENCE else 0.5,
                metadata={"outline_required": bool(section.get("required", True))},
            )
        )
        stage_to_ids[stage].append(node_id)

    return graph
