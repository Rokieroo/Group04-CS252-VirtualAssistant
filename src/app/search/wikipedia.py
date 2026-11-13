"""Wikipedia external search provider (Issue #157, ADR 004).

Queries MediaWiki Action API for Vietnamese (vi) and English (en) Wikipedia.
All text is licensed under CC BY-SA 4.0.
"""

from __future__ import annotations

import html
import logging
import re
import time
from typing import Any
from urllib.parse import quote

import httpx

from app.search.base import Candidate, SearchProvider

log = logging.getLogger("app.search.wikipedia")

DEFAULT_MAX_RESULTS = 5
DEFAULT_TIMEOUT = 10.0
MAX_RETRIES = 2
RETRY_DELAY = 0.5

_TAG_RE = re.compile(r"<[^>]+>")


def _plain_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", text)).strip()


def _error_code(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.TransportError):
        return "network"
    return type(exc).__name__


class WikipediaSearch(SearchProvider):
    """External provider for Wikipedia articles in Vietnamese and English."""

    name = "wikipedia"
    cost_per_call = 0.0

    def __init__(
        self,
        endpoint_template: str | None = None,
        *,
        client: Any | None = None,
        max_results: int = DEFAULT_MAX_RESULTS,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.endpoint_template = endpoint_template or "https://{lang}.wikipedia.org/w/api.php"
        self.client = client
        self.max_results = max(1, max_results)
        self.timeout = timeout
        self.last_error: str | None = None

    def _endpoint(self, lang: str) -> str:
        clean_lang = "vi" if lang.casefold().startswith("vi") else "en"
        return self.endpoint_template.format(lang=clean_lang)

    def search(
        self,
        query: str,
        *,
        lang: str = "vi",
        kind: str | None = None,
        safe: bool = True,
    ) -> list[Candidate]:
        if not query.strip():
            return []

        clean_lang = "vi" if lang.casefold().startswith("vi") else "en"
        endpoint = self._endpoint(clean_lang)

        params: dict[str, Any] = {
            "action": "query",
            "list": "search",
            "srsearch": query.strip(),
            "format": "json",
            "utf8": "1",
            "srlimit": self.max_results,
        }
        headers = {
            "User-Agent": "Pathly/1.0 (https://github.com/Rokieroo/Group04-CS252-VirtualAssistant; mailto:team@pathly.app)",
            "Accept": "application/json",
        }

        response = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                if self.client is not None:
                    response = self.client.get(endpoint, params=params, headers=headers)
                else:
                    response = httpx.get(
                        endpoint, params=params, headers=headers, timeout=self.timeout
                    )
                response.raise_for_status()
                self.last_error = None
                break
            except Exception as exc:  # noqa: BLE001 - network/json errors degrade gracefully
                self.last_error = _error_code(exc)
                if attempt < MAX_RETRIES and isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
                    time.sleep(RETRY_DELAY)
                    continue
                log.warning("provider=wikipedia failed error=%s", self.last_error)
                return []

        if response is None:
            return []

        try:
            payload = response.json()
            return self._candidates(payload, lang=clean_lang, kind=kind)
        except Exception as exc:  # noqa: BLE001 - bad JSON degrades gracefully
            self.last_error = _error_code(exc)
            log.warning("provider=wikipedia bad json error=%s", self.last_error)
            return []

    def _candidates(
        self, payload: Any, *, lang: str, kind: str | None
    ) -> list[Candidate]:
        if not isinstance(payload, dict):
            return []
        query_data = payload.get("query") or {}
        search_results = query_data.get("search")
        if not isinstance(search_results, list):
            return []

        candidates: list[Candidate] = []
        seen: set[str] = set()

        for item in search_results:
            if not isinstance(item, dict):
                continue

            raw_title = item.get("title")
            title = _plain_text(raw_title)
            if not title:
                continue

            wiki_slug = quote(title.replace(" ", "_"), safe="/:")
            url = f"https://{lang}.wikipedia.org/wiki/{wiki_slug}"
            if url in seen:
                continue

            snippet = _plain_text(item.get("snippet"))

            seen.add(url)
            candidates.append(
                Candidate(
                    url=url,
                    title=title,
                    provider="wikipedia",
                    kind=kind or "article",
                    lang=lang,
                    snippet=snippet[:300],
                    license="CC-BY-SA-4.0",
                    institution="Wikimedia Foundation",
                )
            )
            if len(candidates) >= self.max_results:
                break

        return candidates


WikipediaProvider = WikipediaSearch

__all__ = ["WikipediaProvider", "WikipediaSearch"]
