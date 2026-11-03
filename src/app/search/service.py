"""Query generation, provider orchestration, and ``search_runs`` logging."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit, urlunsplit
from uuid import uuid4

from sqlalchemy import text

from app.search.base import Candidate, SearchProvider
from app.search.catalog import CatalogSearch
from app.search.pii_filter import filter_pii
from app.search.web import WebSearch
from app.search.youtube import YouTubeSearch

log = logging.getLogger("app.search.service")

MIN_QUERIES = 3
MAX_QUERIES = 5
DEFAULT_MAX_RESULTS = 10


@dataclass(frozen=True)
class SearchRunRecord:
    """One row destined for ``search_runs`` (already PII-filtered)."""

    query: str
    provider: str
    status: str
    results_count: int
    error: str | None = None


SearchRunRecorder = Callable[[SearchRunRecord], None]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def generate_queries(
    topic: str,
    course: str = "",
    *,
    clo: str = "",
    count: int = MAX_QUERIES,
) -> list[str]:
    """Generate 3-5 diverse queries (spec 11.1).

    Every result has passed through :func:`filter_pii`.  The fixed templates
    are the fallback when no LLM is available, so search never depends on an
    LLM call succeeding.
    """

    topic = _clean(topic)
    course = _clean(course)
    clo = _clean(clo)
    if not topic and not course:
        return []
    if not topic:
        topic = course
        course = ""

    wanted = max(MIN_QUERIES, min(MAX_QUERIES, int(count)))
    subject = " ".join(part for part in (topic, course) if part)
    clo_part = f" {clo}" if clo else ""

    # Keep the Vietnamese and English queries separate, and make the format
    # request explicit: "filetype:pdf" and "video" are visible to providers.
    templates = [
        f"{subject} bài giảng",
        f"{subject}{clo_part} lecture notes filetype:pdf",
        f"{subject}{clo_part} tutorial video",
        f"{subject} bài tập có lời giải",
        f"{topic}{clo_part} worked examples",
    ]

    queries: list[str] = []
    seen: set[str] = set()
    for template in templates:
        query = _clean(filter_pii(template))[:240].strip()
        key = query.casefold()
        if query and key not in seen:
            seen.add(key)
            queries.append(query)
        if len(queries) >= wanted:
            break
    return queries


def _canonical_url(url: str) -> str:
    """Deduplicate by URL without changing what the user will open."""

    value = (url or "").strip()
    if not value:
        return ""
    parts = urlsplit(value)
    netloc = parts.netloc.casefold()
    path = parts.path.rstrip("/")
    if netloc in {"youtu.be", "www.youtu.be"} and path:
        return f"https://www.youtube.com/watch?v={path.lstrip('/')}"
    if netloc in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        video_id = parse_qs(parts.query).get("v", [""])[0]
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
    return urlunsplit((parts.scheme.casefold(), netloc, path, parts.query, ""))


def record_search_run(
    session: Any,
    *,
    user_id: str,
    query: str,
    provider: str,
    status: str,
    results_count: int,
) -> None:
    """Append one PII-filtered row to ``search_runs`` using the existing schema.

    The app layer deliberately does not import the backend ORM (ADR 003), so
    this uses the shared SQLAlchemy session and a small SQL statement.
    """

    session.execute(
        text(
            "INSERT INTO search_runs "
            "(id, user_id, query, provider, status, results_count) "
            "VALUES (:id, :user_id, :query, :provider, :status, :results_count)"
        ),
        {
            "id": str(uuid4()),
            "user_id": user_id,
            "query": filter_pii(query),
            "provider": provider,
            "status": status,
            "results_count": results_count,
        },
    )


class SearchService:
    """Run catalog first, then external providers, tolerating every failure."""

    def __init__(
        self,
        providers: Sequence[SearchProvider] | None = None,
        *,
        max_results: int = DEFAULT_MAX_RESULTS,
        session: Any | None = None,
        user_id: str | None = None,
    ):
        self.providers = list(
            providers
            if providers is not None
            else [CatalogSearch(), YouTubeSearch(), WebSearch()]
        )
        self.max_results = max(1, max_results)
        self.session = session
        self.user_id = user_id
        self.last_queries: list[str] = []
        self.last_errors: dict[str, str] = {}
        self.last_runs: list[SearchRunRecord] = []
        self.last_candidates: list[Candidate] = []
        self.last_record_error: str | None = None

    def search(
        self,
        topic: str = "",
        course: str = "",
        *,
        query: str | None = None,
        clo: str = "",
        lang: str = "vi",
        kind: str | None = None,
        safe: bool = True,
        count: int = MAX_QUERIES,
        queries: Sequence[str] | None = None,
        user_id: str | None = None,
        session: Any | None = None,
        record_run: SearchRunRecorder | None = None,
    ) -> list[Candidate]:
        """Return deduplicated candidates, catalog results first.

        Passing ``session`` and ``user_id`` persists one ``search_runs`` row per
        query/provider call.  A recording failure is logged but never loses
        search results.
        """

        record_session = session if session is not None else self.session
        record_user = user_id if user_id is not None else self.user_id
        if query is not None:
            topic = query
        raw_queries = list(queries) if queries is not None else generate_queries(
            topic, course, clo=clo, count=count
        )
        self.last_queries = []
        self.last_errors = {}
        self.last_runs = []
        self.last_record_error = None
        for raw in raw_queries:
            filtered = _clean(filter_pii(str(raw)))[:240].strip()
            if filtered and filtered not in self.last_queries:
                self.last_queries.append(filtered)
        if not self.last_queries:
            self.last_candidates = []
            return []

        # Catalog is quota-free and must be first, even if a caller supplied
        # providers in another order.
        providers = sorted(
            self.providers,
            key=lambda provider: getattr(provider, "name", "").casefold() != "catalog",
        )
        collected: list[Candidate] = []
        seen_urls: set[str] = set()

        for provider in providers:
            provider_name = getattr(provider, "name", "") or type(provider).__name__
            for search_query in self.last_queries:
                status = "empty"
                error: str | None = None
                results: list[Candidate] = []
                if hasattr(provider, "last_error"):
                    provider.last_error = None
                try:
                    raw_results = provider.search(
                        search_query, lang=lang, kind=kind, safe=safe
                    )
                    if not isinstance(raw_results, list):
                        raise TypeError("provider returned a non-list")
                    results = raw_results
                    error = getattr(provider, "last_error", None)
                    status = "error" if error else ("ok" if results else "empty")
                except Exception as exc:  # noqa: BLE001 - one provider must not break search
                    error = type(exc).__name__
                    status = "error"
                    self.last_errors[provider_name] = error
                    log.warning(
                        "provider=%s query failed error=%s", provider_name, error
                    )

                run = SearchRunRecord(
                    query=search_query,
                    provider=provider_name,
                    status=status,
                    results_count=len(results),
                    error=error,
                )
                self.last_runs.append(run)
                self._persist(
                    run,
                    user_id=record_user,
                    session=record_session,
                    callback=record_run,
                )

                if error:
                    self.last_errors[provider_name] = error
                for candidate in results:
                    url = _canonical_url(candidate.url)
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    collected.append(candidate)

        self.last_candidates = collected[: self.max_results]
        return self.last_candidates

    def _persist(
        self,
        run: SearchRunRecord,
        *,
        user_id: str | None,
        session: Any | None,
        callback: SearchRunRecorder | None,
    ) -> None:
        try:
            if callback is not None:
                callback(run)
            elif session is not None and user_id:
                record_search_run(
                    session,
                    user_id=user_id,
                    query=run.query,
                    provider=run.provider,
                    status=run.status,
                    results_count=run.results_count,
                )
        except Exception as exc:  # noqa: BLE001 - logging must never lose search results
            self.last_record_error = type(exc).__name__
            log.warning("search_runs recording failed error=%s", self.last_record_error)


def search(
    topic: str = "",
    course: str = "",
    *,
    query: str | None = None,
    clo: str = "",
    lang: str = "vi",
    kind: str | None = None,
    safe: bool = True,
    count: int = MAX_QUERIES,
    queries: Sequence[str] | None = None,
    providers: Sequence[SearchProvider] | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    user_id: str | None = None,
    session: Any | None = None,
    record_run: SearchRunRecorder | None = None,
) -> list[Candidate]:
    """Convenience wrapper around :class:`SearchService`."""

    service = SearchService(providers=providers, max_results=max_results)
    return service.search(
        topic,
        course,
        query=query,
        clo=clo,
        lang=lang,
        kind=kind,
        safe=safe,
        count=count,
        queries=queries,
        user_id=user_id,
        session=session,
        record_run=record_run,
    )


__all__ = [
    "DEFAULT_MAX_RESULTS",
    "MAX_QUERIES",
    "MIN_QUERIES",
    "SearchRunRecord",
    "SearchRunRecorder",
    "SearchService",
    "generate_queries",
    "record_search_run",
    "search",
]
