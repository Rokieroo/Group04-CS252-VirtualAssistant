"""Study-time estimation for roadmap nodes (spec 10.2).

Every course gets ``credits * 120`` minutes of self-study per week. The weekly pool
is split across that week's topics by difficulty (1-3) and Bloom level; a topic in
the week immediately before a milestone receives an extra 20% for review.

The allocation is integer-based: each week's base allocations add up exactly to the
weekly pool. The review bonus is added on top, so a review week intentionally costs
more than the normal weekly budget.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from app.roadmap.graph import node_key

MINUTES_PER_CREDIT = 120
REVIEW_BONUS = 0.20

DIFFICULTY_WEIGHT = {1: 1.0, 2: 1.25, 3: 1.5}
BLOOM_WEIGHT = {
    "remember": 0.8,
    "understand": 1.0,
    "apply": 1.25,
    "analyze": 1.4,
    "evaluate": 1.55,
    "create": 1.7,
}


def _value(node: Any, key: str, default: Any = None) -> Any:
    if isinstance(node, dict):
        return node.get(key, default)
    return getattr(node, key, default)


def _kind(node: Any) -> str:
    return str(_value(node, "kind", None) or _value(node, "type", "topic") or "topic")


def _week(node: Any) -> int:
    try:
        val = _value(node, "week", None) or _value(node, "due_week", None) or 1
        return max(1, int(val))
    except (TypeError, ValueError):
        return 1


def _difficulty(node: Any) -> int:
    try:
        return min(3, max(1, int(_value(node, "difficulty", 1) or 1)))
    except (TypeError, ValueError):
        return 1


def _bloom(node: Any) -> str:
    value = str(_value(node, "bloom_level", "understand") or "understand").lower()
    return value if value in BLOOM_WEIGHT else "understand"


def weekly_minutes(credits: float) -> int:
    """The standard weekly self-study budget for a course."""
    return max(0, round(float(credits) * MINUTES_PER_CREDIT))


def node_weight(node: Any) -> float:
    """Relative share of a week's pool: harder topics and higher Bloom cost more."""
    return DIFFICULTY_WEIGHT[_difficulty(node)] * BLOOM_WEIGHT[_bloom(node)]


def review_weeks(milestones: Iterable[Any]) -> set[int]:
    """Weeks immediately before a milestone; these get the 20% review bonus."""
    weeks = set()
    for milestone in milestones:
        week = _week(milestone)
        if week > 1:
            weeks.add(week - 1)
    return weeks


def _split_pool(nodes: list[Any], pool: int) -> list[int]:
    """Split ``pool`` by node weight, preserving the exact total with largest remainders."""
    weights = [node_weight(node) for node in nodes]
    total_weight = sum(weights) or float(len(nodes) or 1)
    if not weights:
        return []
    if not sum(weights):
        weights = [1.0] * len(nodes)
        total_weight = float(len(nodes))
    raw = [pool * weight / total_weight for weight in weights]
    shares = [int(value) for value in raw]
    remainder = pool - sum(shares)
    order = sorted(
        range(len(nodes)),
        key=lambda index: (raw[index] - shares[index], -index),
        reverse=True,
    )
    for index in order[:remainder]:
        shares[index] += 1
    return shares


def allocate_durations(
    nodes: Iterable[Any],
    credits: float | None = None,
    *,
    weekly_budget: int | None = None,
    milestones: Iterable[Any] | None = None,
    review_bonus: float = REVIEW_BONUS,
) -> dict[str, int]:
    """Allocate minutes to every node, keyed by node id/slug.

    The pool is ``weekly_budget`` when given, otherwise ``credits * 120``. Only
    ``topic`` nodes consume the pool; milestones keep an explicit duration or 0.
    Topics in a week immediately before a milestone get their base share multiplied
    by ``1 + review_bonus``.
    """
    rows = list(nodes)
    pool = (
        max(0, int(weekly_budget))
        if weekly_budget is not None
        else weekly_minutes(credits or 0)
    )
    topics: dict[int, list[Any]] = {}
    result: dict[str, int] = {}
    for node in rows:
        key = node_key(node)
        if _kind(node) == "milestone":
            result[key] = max(0, int(_value(node, "duration_minutes", 0) or 0))
        else:
            topics.setdefault(_week(node), []).append(node)

    for week in sorted(topics):
        group = topics[week]
        for node, minutes in zip(group, _split_pool(group, pool), strict=True):
            result[node_key(node)] = minutes

    bonus_weeks = review_weeks(milestones or [])
    for week in sorted(bonus_weeks & set(topics)):
        for node in topics[week]:
            key = node_key(node)
            result[key] = round(result[key] * (1 + review_bonus))
    return result


def estimate_durations(
    nodes: Iterable[Any],
    credits: float | None = None,
    *,
    weekly_budget: int | None = None,
    milestones: Iterable[Any] | None = None,
    review_bonus: float = REVIEW_BONUS,
) -> list[Any]:
    """Return the same node shapes with ``duration_minutes`` filled in."""
    rows = list(nodes)
    durations = allocate_durations(
        rows,
        credits,
        weekly_budget=weekly_budget,
        milestones=milestones,
        review_bonus=review_bonus,
    )
    result = []
    for node in rows:
        minutes = durations[node_key(node)]
        if isinstance(node, dict):
            result.append({**node, "duration_minutes": minutes})
        elif hasattr(node, "__dataclass_fields__"):
            result.append(replace(node, duration_minutes=minutes))
        else:
            result.append(minutes)
    return result


# Readable aliases for callers that use the wording from the specification.
calculate_durations = allocate_durations
calculate_duration = allocate_durations
