"""Adaptive orchestration primitives for deep research workflows."""

from .budget import BranchBudgetManager
from .conflict_solver import ConflictRecord, detect_conflicts, build_resolution_queries
from .entropy import EntropyTracker, LoopMetrics
from .outline_schema import (
    OutlineSection,
    ReportBlueprint,
    ResearchOutline,
    SectionSpec,
    build_blueprint_from_outline,
    outline_stage_to_task_stage,
    validate_research_outline,
)
from .saliency import SaliencyDetector
from .task_graph import TaskGraph, TaskNode, TaskStage, TaskStatus, build_default_task_graph, build_task_graph_from_outline
from .trace import ResearchTrace

__all__ = [
    "OutlineSection",
    "BranchBudgetManager",
    "ConflictRecord",
    "EntropyTracker",
    "LoopMetrics",
    "ReportBlueprint",
    "ResearchTrace",
    "ResearchOutline",
    "SaliencyDetector",
    "SectionSpec",
    "TaskGraph",
    "TaskNode",
    "TaskStage",
    "TaskStatus",
    "build_blueprint_from_outline",
    "build_default_task_graph",
    "build_task_graph_from_outline",
    "outline_stage_to_task_stage",
    "build_resolution_queries",
    "detect_conflicts",
    "validate_research_outline",
]
