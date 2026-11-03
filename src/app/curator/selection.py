"""Pick the resources shown for one roadmap node (spec 11.5) and replace on feedback (11.6).

Pure functions over :class:`~app.vetting.ScoredResource`: the caller stores the
:class:`Curation` (it is plain JSON) and replays each user's "not helpful"
answers with :func:`replace`, so a replacement never needs a new search.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.retrieval import tokenize_vi
from app.vetting import THRESHOLD, ScoredResource

__all__ = [
    "LAMBDA",
    "MAX_PER_DOMAIN",
    "TOP_K",
    "Curation",
    "Similarity",
    "curate",
    "lexical_similarity",
    "replace",
]

TOP_K = 5
LAMBDA = 0.7  # MMR: weight of quality against novelty
MAX_PER_DOMAIN = 2
DURATION_SLACK = 1.5  # shown resources may add up to 1.5 x the node's estimate
MIN_SOURCES = 2  # fewer than this and the node is "insufficient" (curate or abstain)
FORMAT_NAMES = {"reading": "bài đọc", "video": "video", "exercise": "bài tập"}

Similarity = Callable[[ScoredResource, ScoredResource], float]


def lexical_similarity(a: ScoredResource, b: ScoredResource) -> float:
    """Cosine similarity of word counts over title and opening text.

    shortcut: lexical, not the embeddings spec 11.5 names; pass an embedding
    ``similarity`` once app.llm has an embedding client within quota.
    """
    left = Counter(tokenize_vi(f"{a.title} {a.excerpt}"))
    right = Counter(tokenize_vi(f"{b.title} {b.excerpt}"))
    dot = sum(count * right[word] for word, count in left.items())
    norm = math.sqrt(sum(c * c for c in left.values()) * sum(c * c for c in right.values()))
    return dot / norm if norm else 0.0


@dataclass(frozen=True)
class Curation:
    status: str  # ready | insufficient
    resources: list[ScoredResource]  # shown, teacher pins first
    reserve: list[ScoredResource] = field(default_factory=list)  # replacements, best first
    gaps: list[str] = field(default_factory=list)  # why the set is short, in Vietnamese
    budget_minutes: float | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Curation:
        """Rebuild a curation stored with ``dataclasses.asdict``."""
        return cls(
            status=data["status"],
            resources=[ScoredResource(**row) for row in data["resources"]],
            reserve=[ScoredResource(**row) for row in data.get("reserve", [])],
            gaps=list(data.get("gaps", [])),
            budget_minutes=data.get("budget_minutes"),
        )


def _select(
    chosen: list[ScoredResource],
    pool: list[ScoredResource],
    slots: int,
    budget: float | None,
    lam: float,
    similarity: Similarity,
) -> tuple[list[ScoredResource], list[ScoredResource]]:
    """Greedy MMR under the domain, format and duration rules; returns (chosen, rest)."""
    chosen, pool = list(chosen), list(pool)
    for filled in range(slots):
        used = sum(resource.minutes or 0 for resource in chosen)
        # Teacher pins never count towards the domain limit.
        per_domain = Counter(resource.domain for resource in chosen if not resource.pinned)
        allowed = [
            resource
            for resource in pool
            if per_domain[resource.domain] < MAX_PER_DOMAIN
            and (budget is None or resource.minutes is None or used + resource.minutes <= budget)
        ]
        if not allowed:
            break
        # Keep the last slots for formats still missing from the set, when there are any.
        missing = {r.format for r in allowed} - {r.format for r in chosen}
        if len(missing) >= slots - filled:
            allowed = [resource for resource in allowed if resource.format in missing]
        best = max(
            allowed,
            key=lambda r: lam * r.score
            - (1 - lam) * max((similarity(r, other) for other in chosen), default=0.0),
        )
        chosen.append(best)
        pool.remove(best)
    return chosen, pool


def _finish(
    shown: list[ScoredResource], reserve: list[ScoredResource], budget: float | None
) -> Curation:
    gaps = []
    if len(shown) < MIN_SOURCES:
        gaps.append(
            f"Chưa tìm được đủ nguồn đạt chất lượng: cần ít nhất {MIN_SOURCES}, "
            f"mới có {len(shown)}."
        )
    present = {resource.format for resource in shown}
    gaps += [f"Chưa có {name} đạt ngưỡng." for fmt, name in FORMAT_NAMES.items()
             if fmt not in present]
    status = "ready" if len(shown) >= MIN_SOURCES else "insufficient"
    return Curation(status, shown, reserve, gaps, budget)


def curate(
    scored: Iterable[ScoredResource],
    *,
    pinned: Iterable[ScoredResource] = (),
    est_minutes: int | None = None,
    top_k: int = TOP_K,
    threshold: float = THRESHOLD,
    lam: float = LAMBDA,
    similarity: Similarity = lexical_similarity,
) -> Curation:
    """The shown set for one node: never filled up with resources below ``threshold``.

    A resource is eligible only with a grounded ``evidence_quote``, so every shown
    reason is backed by text the page really contains.
    """
    pins = list(pinned)
    pinned_urls = {resource.url for resource in pins}
    eligible = sorted(
        (
            resource
            for resource in scored
            if resource.url not in pinned_urls
            and resource.score >= threshold
            and resource.evidence_quote
        ),
        key=lambda resource: resource.score,
        reverse=True,
    )
    budget = est_minutes * DURATION_SLACK if est_minutes else None
    shown, reserve = _select(
        pins, eligible, max(0, top_k - len(pins)), budget, lam, similarity
    )
    return _finish(shown, reserve, budget)


def replace(
    curation: Curation,
    url: str,
    *,
    lam: float = LAMBDA,
    similarity: Similarity = lexical_similarity,
) -> Curation:
    """Drop the shown resource at ``url`` ("not helpful") and bring up the next reserve.

    Raises ``KeyError`` when ``url`` is not shown.
    """
    shown = [resource for resource in curation.resources if resource.url != url]
    if len(shown) == len(curation.resources):
        raise KeyError(url)
    shown, reserve = _select(
        shown, curation.reserve, 1, curation.budget_minutes, lam, similarity
    )
    return _finish(shown, reserve, curation.budget_minutes)
