"""Planner: places study work into availability (spec 6.1). No HTTP, SQL or LLM."""

from app.planner.diff import PlanDiff, diff
from app.planner.engine import (
    Plan,
    PlanLimits,
    PlannedSession,
    Planner,
    Shortfall,
    WorkItem,
    build_plan,
)
from app.planner.intervals import (
    Interval,
    intersect,
    merge,
    minutes,
    split_days,
    subtract,
)

__all__ = [
    "Interval",
    "Plan",
    "PlanDiff",
    "PlanLimits",
    "PlannedSession",
    "Planner",
    "Shortfall",
    "WorkItem",
    "build_plan",
    "diff",
    "intersect",
    "merge",
    "minutes",
    "split_days",
    "subtract",
]
