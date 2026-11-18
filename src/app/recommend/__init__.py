"""One recommendation list per roadmap node (#155, spec 11.4-11.8).

The database answers first: the learner's own material, then verified catalog
sources (#102). External pages are asked for only while the database holds fewer
than ``ENOUGH`` strong sources, and they arrive already vetted (fetched, filtered
and judged, spec 11.3-11.4). This module never searches, fetches or calls a model,
so the API, the search job and the benchmark share one pure function.

Final score = spec 11.4 score x learner fit x feedback adjustment; the curator's
MMR then picks a set that mixes formats under the domain limit (spec 11.5).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from urllib.parse import urlsplit

from app.catalog.matching import stem
from app.catalog.taxonomy import cosine, encode, normalize
from app.curator import select_shown
from app.curator.selection import FORMAT_NAMES
from app.search import canonical_url
from app.vetting import THRESHOLD, Learner, Node, ScoredResource

__all__ = [
    "ENOUGH",
    "NO_FEEDBACK",
    "STRONG",
    "VERIFICATION",
    "Feedback",
    "Recommendation",
    "needs_external",
    "recommend",
]

# What a learner may rely on for each kind; an external page is never "verified".
VERIFICATION = {"user_material": "private", "catalog": "verified", "external": "unverified"}
STRONG = 0.8  # spec 11.8: a source this good counts towards stopping the search
ENOUGH = 3  # strong database sources that make an external search unnecessary
OTHER_LANGUAGE = 0.9  # fit of a page in an allowed language other than the learner's first
SIMILAR_PENALTY = 0.3  # share of score lost by a copy of a source the learner found unhelpful
_FILLER = {"and", "the", "for", "with", "from", "into", "cua", "va", "cac", "trong"}


@dataclass(frozen=True)
class Recommendation:
    """One source shown for a node, with the facts that justify it."""

    kind: str  # user_material | catalog | external
    source_id: str  # Source.id, Resource.id, or the canonical URL of an external page
    title: str
    url: str | None
    format: str  # reading | video | exercise
    score: float
    reason: str

    @property
    def verification_status(self) -> str:
        return VERIFICATION[self.kind]


@dataclass(frozen=True)
class Feedback:
    """What this learner said about earlier recommendations (spec 11.6)."""

    rejected: frozenset[str] = frozenset()  # source ids marked not helpful on this node
    unhelpful_titles: tuple[str, ...] = ()  # every source the learner found unhelpful


NO_FEEDBACK = Feedback()


@dataclass(frozen=True)
class _Candidate:
    kind: str
    source_id: str
    resource: ScoredResource  # its ``url`` is the identity the curator dedupes on
    pages: tuple[int, ...] = ()
    origin: str = ""  # institution or host, as the learner would recognise it


def needs_external(database: Sequence[Mapping]) -> bool:
    """Spec 11.8: search outside only while fewer than ``ENOUGH`` catalog sources are strong.

    The learner's own material does not count: it is private, and the node still
    needs public sources for what that material leaves out.
    """
    strong = [r for r in database if r["kind"] != "user_material" and r["score"] >= STRONG]
    return len(strong) < ENOUGH


def recommend(
    node: Node,
    learner: Learner,
    *,
    database: Sequence[Mapping],
    external: Callable[[], Iterable[ScoredResource]],
    feedback: Feedback = NO_FEEDBACK,
    limit: int = 5,
) -> list[Recommendation]:
    """Up to ``limit`` recommendations for ``node``, the learner's own material first.

    ``database`` is the node's ``sources`` from ``node_sources`` (#102); ``external``
    returns vetted pages and is called only when ``needs_external(database)``.
    """
    own = [
        _own(row) for row in database
        if row["kind"] == "user_material" and row["id"] not in feedback.rejected
    ]
    catalog = [_catalog(row) for row in database if row["kind"] != "user_material"]
    known = {c.resource.url for c in catalog}
    found = [
        _external(page) for page in (external() if needs_external(database) else ())
        if canonical_url(page.url) not in known  # the verified copy wins
    ]
    unhelpful = [encode(title) for title in feedback.unhelpful_titles]
    eligible = {}
    for candidate in catalog + found:
        if candidate.source_id in feedback.rejected:
            continue
        resource = candidate.resource
        # The 0.65 bar is on quality (spec 11.4); fit and feedback only reorder what passed.
        # A vetted page also needs its grounded quote; a catalog source was verified by #101.
        if resource.score < THRESHOLD or not (candidate.kind == "catalog" or resource.evidence_quote):
            continue
        score = resource.score * _fit(resource.lang, learner) * _feedback(resource.title, unhelpful)
        eligible[resource.url] = replace(candidate, resource=replace(resource, score=score))
    chosen = select_shown(
        (c.resource for c in eligible.values()),
        pinned=[c.resource for c in own],
        est_minutes=node.est_minutes,
        top_k=limit,
    )
    by_url = {c.resource.url: c for c in own} | eligible
    return [_recommendation(node, by_url[r.url]) for r in chosen.resources]


def _own(row: Mapping) -> _Candidate:
    resource = _resource(row, url=f"material:{row['id']}", pinned=True)
    return _Candidate("user_material", row["id"], resource, tuple(row.get("pages") or ()))


def _catalog(row: Mapping) -> _Candidate:
    url = canonical_url(row["url"]) or row["url"]
    origin = row.get("institution") or _host(url)
    return _Candidate("catalog", row["id"], _resource(row, url=url), origin=origin)


def _resource(row: Mapping, *, url: str, pinned: bool = False) -> ScoredResource:
    return ScoredResource(
        url=url,
        title=row["title"],
        provider=row.get("provider") or "",
        format=_slot(row.get("format")),
        lang=row.get("lang") or "",
        domain="" if pinned else _host(url),
        is_free=True,
        minutes=row.get("duration_min"),
        score=float(row["score"]),
        breakdown={},
        reason=row.get("reason") or "",
        evidence_quote="",
        content_hash="",
        excerpt="",
        pinned=pinned,
    )


def _external(page: ScoredResource) -> _Candidate:
    url = canonical_url(page.url) or page.url
    return _Candidate("external", url, replace(page, url=url), origin=page.domain or _host(url))


def _slot(fmt: str | None) -> str:
    """The reading / video / exercise slot of a catalog format (spec 11.5)."""
    return fmt if fmt in ("video", "exercise") else "reading"


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


def _fit(lang: str, learner: Learner) -> float:
    """Pages in the learner's first language fit best; other allowed ones a little less.

    Level and language are already hard filters upstream (the catalog's audience
    match, vetting's language rule and judged ``level_fit``), so only preference is left.
    """
    return 1.0 if not lang or not learner.langs or lang == learner.langs[0] else OTHER_LANGUAGE


def _feedback(title: str, unhelpful: list[list[float]]) -> float:
    """Lower sources that resemble what this learner found unhelpful (spec 11.6)."""
    if not unhelpful:
        return 1.0
    vector = encode(title)
    likeness = max(max(cosine(vector, other), 0.0) for other in unhelpful)
    return 1 - SIMILAR_PENALTY * likeness


def _recommendation(node: Node, candidate: _Candidate) -> Recommendation:
    resource = candidate.resource
    return Recommendation(
        kind=candidate.kind,
        source_id=candidate.source_id,
        title=resource.title,
        url=None if candidate.kind == "user_material" else resource.url,
        format=resource.format,
        score=round(resource.score, 3),
        reason=_reason(node.title, candidate),
    )


def _reason(node_title: str, candidate: _Candidate) -> str:
    """Facts only: what matches the node, where it comes from, its format and length."""
    resource = candidate.resource
    parts = []
    shared = _shared_words(node_title, resource.title)
    if shared:
        parts.append("Khớp " + ", ".join(f"“{word}”" for word in shared[:3]))
    if candidate.kind == "user_material":
        parts.append("Tài liệu của bạn")
        if candidate.pages:
            pages = ", ".join(str(p) for p in candidate.pages[:3])
            parts.append(f"trang {pages}{'…' if len(candidate.pages) > 3 else ''}")
        return " · ".join(parts)
    parts.append(candidate.origin)
    length = f" {resource.minutes} phút" if resource.minutes else ""
    parts.append(FORMAT_NAMES[resource.format] + length)
    parts.append("đã xác minh" if candidate.kind == "catalog" else "chưa xác minh")
    return " · ".join(part for part in parts if part)


def _shared_words(node_title: str, title: str) -> list[str]:
    """Words of the node title that the source title also uses (plurals folded)."""
    stems = {stem(word) for word in normalize(title).split()}
    words = []
    for word in normalize(node_title).split():
        if len(word) >= 3 and word not in _FILLER and stem(word) in stems and word not in words:
            words.append(word)
    return words
