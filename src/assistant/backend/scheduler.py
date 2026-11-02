"""Deprecated: moved to app.planner (ADR 003). Re-exported so old imports keep working."""

from app.planner import (
    Interval,
    WorkItem,
    build_plan,
    intersect,
    merge,
    minutes,
    split_days,
    subtract,
)

__all__ = [
    "Interval",
    "WorkItem",
    "build_plan",
    "intersect",
    "merge",
    "minutes",
    "split_days",
    "subtract",
]
