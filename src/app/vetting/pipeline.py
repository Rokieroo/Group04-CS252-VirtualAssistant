"""Vet the candidates of one roadmap node: fetch, filter, judge, score (spec 11.3-11.4, 11.8).

Only a URL a search provider returned *and* the fetcher loaded can come out of
:func:`vet` (verify or drop); everything else is reported in ``dropped`` with a
reason code.  Fetches run in parallel; LLM calls run one by one, cheapest-first,
within the per-node budget.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlsplit

from app.llm import LLMClient
from app.retrieval import score_against
from app.search import Candidate, canonical_url
from app.vetting import score
from app.vetting.document import Document, read_document
from app.vetting.fetch import FetchResult, SafeFetcher
from app.vetting.filters import Deduper, Learner, content_failure, fetch_failure
from app.vetting.judge import judge
from app.vetting.policy import DomainTier, default_policy

__all__ = ["Node", "ScoredResource", "Vetting", "resource_format", "vet"]

MAX_FETCH = 25
MAX_JUDGE = 12
ENOUGH = 5  # stop judging once this many resources reach STRONG
STRONG = 0.8
FETCH_WORKERS = 8
EXCERPT_CHARS = 1000
_EXERCISE = re.compile(
    r"\b(?:exercises?|practice|problem\s+sets?|worked\s+examples?|quiz|"
    r"bài\s+tập|luyện\s+tập|lời\s+giải)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Node:
    """The roadmap node being served: course data only, so results can be shared."""

    title: str
    outcomes: tuple[str, ...] = ()
    est_minutes: int | None = None
    fast_moving: bool = True  # IT-like subject whose material ages (freshness)


@dataclass(frozen=True)
class ScoredResource:
    """A verified, scored resource; plain values so it stores as JSON."""

    url: str
    title: str
    provider: str
    format: str  # reading | video | exercise
    lang: str
    domain: str
    is_free: bool
    minutes: int | None
    score: float
    breakdown: dict[str, float]
    reason: str
    evidence_quote: str
    content_hash: str
    excerpt: str  # opening text, so the curator can compare resources without refetching
    pinned: bool = False

    @classmethod
    def pinned_by_teacher(cls, candidate: Candidate) -> ScoredResource:
        """A teacher's pin is shown as is: never fetched for scoring, never re-ranked."""
        return cls(
            url=candidate.url,
            title=candidate.title,
            provider=candidate.provider,
            format=resource_format(candidate),
            lang=candidate.lang,
            domain=_domain(candidate.url),
            is_free=True,
            minutes=None,
            score=1.0,
            breakdown={},
            reason="Giáo viên đã ghim nguồn này",
            evidence_quote="",
            content_hash="",
            excerpt=candidate.snippet,
            pinned=True,
        )


@dataclass(frozen=True)
class Vetting:
    resources: list[ScoredResource]  # best first
    dropped: list[tuple[str, str]] = field(default_factory=list)  # (url, reason)


@dataclass(frozen=True)
class _Page:
    candidate: Candidate
    fetched: FetchResult
    document: Document | None
    failure: str | None


def resource_format(candidate: Candidate) -> str:
    """Which slot of the reading / video / exercise mix a resource fills (spec 11.5)."""
    kind = candidate.kind.casefold()
    if kind == "video":
        return "video"
    if kind in {"exercise", "quiz"} or _EXERCISE.search(f"{candidate.title} {candidate.snippet}"):
        return "exercise"
    return "reading"


def _domain(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


def _read(candidate: Candidate, fetcher: SafeFetcher, learner: Learner) -> _Page:
    fetched = fetcher.fetch(candidate.url)
    failure = fetch_failure(fetched, learner)
    if failure:
        return _Page(candidate, fetched, None, failure)
    document = read_document(candidate, fetched)
    return _Page(candidate, fetched, document, content_failure(document, learner))


def _fetch_all(
    candidates: list[Candidate], fetcher: SafeFetcher | None, learner: Learner
) -> list[_Page]:
    owned = fetcher is None
    fetcher = fetcher or SafeFetcher()
    try:
        with ThreadPoolExecutor(FETCH_WORKERS) as pool:
            return list(pool.map(lambda candidate: _read(candidate, fetcher, learner), candidates))
    finally:
        if owned:
            fetcher.close()


def vet(
    candidates: Iterable[Candidate],
    node: Node,
    learner: Learner | None = None,
    *,
    llm: LLMClient,
    fetcher: SafeFetcher | None = None,
    ratings: Mapping[str, tuple[int, int]] | None = None,
    today: date | None = None,
) -> Vetting:
    """Score the candidates of ``node`` for ``learner``.

    ``ratings`` maps a resource URL to ``(helpful, total)`` votes; ``fetcher``
    is shared by batch callers so ``robots.txt`` answers stay cached.
    """
    learner = learner or Learner()
    today = today or date.today()
    ratings = ratings or {}
    dropped: list[tuple[str, str]] = []

    requested, unique = Deduper(), []
    for candidate in candidates:
        if requested.seen(canonical_url(candidate.url)):
            dropped.append((candidate.url, "duplicate"))
        else:
            unique.append(candidate)
    dropped += [(candidate.url, "budget") for candidate in unique[MAX_FETCH:]]

    # After redirects, two URLs can land on one page, or two pages carry one body.
    loaded, pages = Deduper(), []
    for page in _fetch_all(unique[:MAX_FETCH], fetcher, learner):
        if page.failure:
            dropped.append((page.candidate.url, page.failure))
        elif loaded.seen(canonical_url(page.fetched.final_url), page.fetched.content_hash):
            dropped.append((page.candidate.url, "duplicate"))
        else:
            pages.append(page)
    if not pages:
        return Vetting([], dropped)

    policy = fetcher.policy if fetcher else default_policy()
    goal = " ".join((node.title, *node.outcomes))
    lexical = score_against(goal, [page.document.text for page in pages])
    tiers = [policy.tier(page.fetched.final_url) for page in pages]
    # Judge the likeliest pages first, so the budget and the early stop cost the least.
    order = sorted(
        range(len(pages)), key=lambda i: lexical[i] + score.authority(tiers[i]), reverse=True
    )

    resources: list[ScoredResource] = []
    for position, i in enumerate(order):
        page = pages[i]
        if position >= MAX_JUDGE or sum(r.score >= STRONG for r in resources) >= ENOUGH:
            dropped.append((page.candidate.url, "budget"))
            continue
        resource = _score(page, node, learner, llm, lexical[i], tiers[i], ratings, today)
        resources.append(resource)
    resources.sort(key=lambda resource: resource.score, reverse=True)
    return Vetting(resources, dropped)


def _score(
    page: _Page,
    node: Node,
    learner: Learner,
    llm: LLMClient,
    lexical: float,
    tier: DomainTier,
    ratings: Mapping[str, tuple[int, int]],
    today: date,
) -> ScoredResource:
    document, fetched, candidate = page.document, page.fetched, page.candidate
    verdict = judge(
        llm, document.text, title=node.title, outcomes=node.outcomes, level=learner.level
    )
    url = fetched.final_url or candidate.url
    is_free = fetched.paywall is None
    breakdown = {
        # Spec 11.4: an ungrounded quote zeroes relevance, lexical half included.
        "relevance": (verdict.relevance + lexical) / 2 if verdict.evidence_quote else 0.0,
        "authority": score.authority(tier),
        "level_fit": verdict.level_fit,
        "pedagogy": verdict.pedagogy,
        "freshness": score.freshness(document.published, today, fast_moving=node.fast_moving),
        "accessibility": score.accessibility(
            free=is_free, transcript=document.transcript, minutes=document.minutes
        ),
        "community": score.community(*ratings.get(url, (0, 0))),
    }
    return ScoredResource(
        url=url,
        title=candidate.title,
        provider=candidate.provider,
        format=resource_format(candidate),
        lang=document.lang,
        domain=_domain(url),
        is_free=is_free,
        minutes=document.minutes,
        score=score.total(breakdown),
        breakdown={name: round(value, 4) for name, value in breakdown.items()},
        reason=verdict.reason,
        evidence_quote=verdict.evidence_quote,
        content_hash=fetched.content_hash,
        excerpt=document.text[:EXCERPT_CHARS],
    )
