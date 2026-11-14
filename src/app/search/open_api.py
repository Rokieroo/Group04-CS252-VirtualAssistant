"""The base for keyless open APIs registered in ADR 004 (#157)."""

from __future__ import annotations

import logging
import time
from abc import abstractmethod
from collections.abc import Iterable
from typing import Any

import httpx

from app.catalog.sources import Provider, Sources, load_sources
from app.search.base import Candidate, SearchProvider
from app.search.http import error_code, transient

log = logging.getLogger("app.search.open_api")

DEFAULT_MAX_RESULTS = 5
DEFAULT_TIMEOUT = 10.0
SNIPPET_CHARS = 300  # ADR 004 section 5: metadata, a link and at most 300 characters
# Wikimedia's User-Agent policy asks for a way to reach the operator.
USER_AGENT = "Pathly/0.1 (+https://github.com/Rokieroo/Group04-CS252-VirtualAssistant)"


class OpenApiSearch(SearchProvider):
    """A keyless JSON API whose terms and licenses are a row of ``catalog_sources.yaml``.

    The row is the authority: a provider whose terms forbid automated access cannot
    be built, and a candidate is returned only with a URL and one of the row's
    licenses, so changing what may be shown stays a reviewed data change.
    Transient failures are retried; every failure ends as ``[]`` and ``last_error``.
    """

    kinds: frozenset[str] = frozenset()  # the formats this provider returns
    publisher = ""
    retries = 2
    backoff = 0.5  # seconds, doubled per retry

    def __init__(
        self,
        *,
        client: Any | None = None,
        max_results: int = DEFAULT_MAX_RESULTS,
        timeout: float = DEFAULT_TIMEOUT,
        sources: Sources | None = None,
    ):
        row = (sources or load_sources()).providers[self.name]
        if not row.automated or row.method != "api":
            raise ValueError(f"not_automatable_{row.id}")  # ADR 004 section 9
        self.registry: Provider = row
        self.client = client
        self.max_results = max(1, max_results)
        self.timeout = timeout
        self.last_error: str | None = None

    @abstractmethod
    def request(self, query: str, lang: str) -> tuple[str, dict[str, Any]]:
        """The URL and query parameters for one search."""

    @abstractmethod
    def candidates(self, payload: Any, lang: str) -> Iterable[Candidate]:
        """Candidates read from one response; may raise on a malformed payload."""

    def search(
        self,
        query: str,
        *,
        lang: str = "vi",
        kind: str | None = None,
        safe: bool = True,
    ) -> list[Candidate]:
        wanted = kind.casefold() if kind else None
        if not query.strip() or (wanted and wanted not in self.kinds):
            return []
        self.last_error = None
        try:
            found = list(self.candidates(self._get(*self.request(query.strip(), lang)), lang))
        except Exception as exc:  # noqa: BLE001 - network/quota/bad JSON never break search
            self.last_error = error_code(exc)
            log.warning("provider=%s failed error=%s", self.name, self.last_error)
            return []
        results: list[Candidate] = []
        seen: set[str] = set()
        for candidate in found:
            if (
                not candidate.url.startswith("https://")
                or not candidate.title
                or candidate.license not in self.registry.licenses
                or candidate.url in seen
            ):
                continue  # issue #157: no result without a URL or a registered license
            seen.add(candidate.url)
            candidate.snippet = candidate.snippet[:SNIPPET_CHARS]
            results.append(candidate)
        return results[: self.max_results]

    def _get(self, url: str, params: dict[str, Any]) -> Any:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        # httpx replaces a URL's query with `params`; merge to keep a registry endpoint's filters.
        target = str(httpx.URL(url).copy_merge_params(params))
        for attempt in range(self.retries + 1):
            try:
                if self.client is not None:
                    response = self.client.get(target, headers=headers)
                else:
                    response = httpx.get(target, headers=headers, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                if attempt == self.retries or not transient(exc):
                    raise
                time.sleep(self.backoff * 2**attempt)
        raise AssertionError("unreachable")


__all__ = ["DEFAULT_MAX_RESULTS", "DEFAULT_TIMEOUT", "SNIPPET_CHARS", "USER_AGENT", "OpenApiSearch"]
