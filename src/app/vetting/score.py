"""The quality score: seven criteria in [0, 1] and their weights (spec 11.4)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from types import MappingProxyType

from app.vetting.policy import DomainTier

__all__ = [
    "THRESHOLD",
    "WEIGHTS",
    "accessibility",
    "authority",
    "community",
    "freshness",
    "total",
]

WEIGHTS: Mapping[str, float] = MappingProxyType(
    {
        "relevance": 0.30,
        "authority": 0.20,
        "level_fit": 0.15,
        "pedagogy": 0.10,
        "freshness": 0.10,
        "accessibility": 0.10,
        "community": 0.05,
    }
)
THRESHOLD = 0.65  # only resources at or above this are shown (curate or abstain)

_AUTHORITY = {DomainTier.TIER1: 1.0, DomainTier.TIER2: 0.7, DomainTier.OTHER: 0.4}
UNKNOWN = 0.5  # a criterion we cannot measure neither helps nor hurts much
FAST_SHELF_LIFE = 5  # years before IT material starts to age
MIN_RATINGS = 10


def authority(tier: DomainTier) -> float:
    return _AUTHORITY.get(tier, 0.0)


def freshness(published: date | None, today: date, *, fast_moving: bool) -> float:
    """IT material ages after 5 years; maths and physics barely age at all."""
    if published is None:
        return UNKNOWN
    years = max(0.0, (today - published).days / 365.25)
    if fast_moving:
        return max(0.2, 1.0 - 0.15 * max(0.0, years - FAST_SHELF_LIFE))
    return max(0.8, 1.0 - 0.01 * years)


def accessibility(*, free: bool, transcript: bool, minutes: int | None) -> float:
    """Free without login, readable text or captions, and at most an hour long."""
    length = UNKNOWN if minutes is None else float(minutes <= 60)
    return 0.4 * free + 0.3 * transcript + 0.3 * length


def community(helpful: int, total: int) -> float:
    """Share of "helpful" votes, smoothed towards 0.5 (Bayes, prior of 10 votes)."""
    if total < MIN_RATINGS:
        return UNKNOWN
    return (helpful + UNKNOWN * MIN_RATINGS) / (total + MIN_RATINGS)


def total(breakdown: Mapping[str, float]) -> float:
    return round(sum(weight * breakdown[name] for name, weight in WEIGHTS.items()), 4)
