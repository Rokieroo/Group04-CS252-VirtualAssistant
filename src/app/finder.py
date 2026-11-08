"""The resource finder for one roadmap node: search, vet, curate (spec 11), and what it cost.

Each part keeps its one job; this module only runs them in order and measures the
run, so the caller can log it (``resource_searches`` and ``search_runs``).
"""
from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.curator import Curation, curate
from app.llm import LLMClient, MeteredLLM
from app.search import SearchRunRecord, SearchService
from app.vetting import Learner, Node, SafeFetcher, ScoredResource, vet

__all__ = ["Found", "SearchStats", "find_resources"]


@dataclass(frozen=True)
class SearchStats:
    """What one resource search did and spent (issue #69)."""

    queries: int
    candidates: int
    vetted: int  # verified and scored
    kept: int  # shown to the learner
    llm_calls: int
    llm_cost_usd: float
    search_cost_usd: float
    duration_ms: int
    runs: tuple[SearchRunRecord, ...] = ()  # one per provider call, with its latency


@dataclass(frozen=True)
class Found:
    curation: Curation
    stats: SearchStats


def find_resources(
    node: Node,
    learner: Learner,
    *,
    course: str = "",
    search: SearchService,
    llm: LLMClient,
    fetcher: SafeFetcher | None = None,
    pinned: Iterable[ScoredResource] = (),
    ratings: Mapping[str, tuple[int, int]] | None = None,
) -> Found:
    """Find, verify and pick the resources of ``node``; never raises for a provider's sake."""
    started = time.perf_counter()
    meter = MeteredLLM(llm)
    candidates = search.search(
        node.title,
        course,
        clo=node.outcomes[0] if node.outcomes else "",
        lang=learner.langs[0] if learner.langs else "vi",
    )
    vetting = vet(candidates, node, learner, llm=meter, fetcher=fetcher, ratings=ratings)
    curation = curate(vetting.resources, pinned=pinned, est_minutes=node.est_minutes)
    stats = SearchStats(
        queries=len(search.last_queries),
        candidates=len(candidates),
        vetted=len(vetting.resources),
        kept=len(curation.resources),
        llm_calls=meter.calls,
        llm_cost_usd=meter.cost_usd,
        search_cost_usd=sum(run.cost_usd for run in search.last_runs),
        duration_ms=round((time.perf_counter() - started) * 1000),
        runs=tuple(search.last_runs),
    )
    return Found(curation, stats)
