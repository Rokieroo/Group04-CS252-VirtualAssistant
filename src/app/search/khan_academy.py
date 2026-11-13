"""Khan Academy external search provider (Issue #157, ADR 004).

Queries Khan Academy public search API and extracts videos, articles, and exercises.
All eligible resources are licensed under CC BY-NC-SA 4.0.
"""

from __future__ import annotations

import html
import logging
import re
import time
from typing import Any
from urllib.parse import urljoin

import httpx

from app.search.base import Candidate, SearchProvider

log = logging.getLogger("app.search.khan_academy")

DEFAULT_KHAN_ENDPOINT = "https://www.khanacademy.org/api/v1/search"
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


class KhanAcademySearch(SearchProvider):
    """External provider for Khan Academy videos, exercises, and articles."""

    name = "khan_academy"
    cost_per_call = 0.0

    def __init__(
        self,
        endpoint: str | None = None,
        *,
        client: Any | None = None,
        max_results: int = DEFAULT_MAX_RESULTS,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.endpoint = endpoint or DEFAULT_KHAN_ENDPOINT
        self.client = client
        self.max_results = max(1, max_results)
        self.timeout = timeout
        self.last_error: str | None = None

    def search(
        self,
        query: str,
        *,
        lang: str = "en",
        kind: str | None = None,
        safe: bool = True,
    ) -> list[Candidate]:
        if not query.strip():
            return []

        params: dict[str, Any] = {
            "query": query.strip(),
            "page": 0,
        }
        headers = {
            "User-Agent": "Pathly/1.0 (https://github.com/Rokieroo/Group04-CS252-VirtualAssistant; mailto:team@pathly.app)",
            "Accept": "application/json",
        }

        response = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                if self.client is not None:
                    response = self.client.get(self.endpoint, params=params, headers=headers)
                else:
                    response = httpx.get(
                        self.endpoint, params=params, headers=headers, timeout=self.timeout
                    )
                response.raise_for_status()
                self.last_error = None
                break
            except Exception as exc:  # noqa: BLE001 - network/json errors degrade gracefully
                self.last_error = _error_code(exc)
                if attempt < MAX_RETRIES and isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
                    time.sleep(RETRY_DELAY)
                    continue
                log.warning("provider=khan_academy failed error=%s", self.last_error)
                return []

        if response is None:
            return []

        try:
            payload = response.json()
            return self._candidates(payload, lang=lang, kind=kind)
        except Exception as exc:  # noqa: BLE001 - bad JSON degrades gracefully
            self.last_error = _error_code(exc)
            log.warning("provider=khan_academy bad json error=%s", self.last_error)
            return []

    def _candidates(
        self, payload: Any, *, lang: str, kind: str | None
    ) -> list[Candidate]:
        items: list[Any] = []
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            for k in ("items", "results", "data"):
                if isinstance(payload.get(k), list):
                    items = payload[k]
                    break

        candidates: list[Candidate] = []
        seen: set[str] = set()

        for item in items:
            if not isinstance(item, dict):
                continue

            raw_url = item.get("url") or item.get("ka_url") or item.get("relative_url")
            if not raw_url:
                continue
            url = _plain_text(raw_url)
            if not url.startswith("http"):
                url = urljoin("https://www.khanacademy.org", url)

            if url in seen:
                continue

            title = _plain_text(item.get("title") or item.get("translated_title"))
            if not title:
                continue

            snippet = _plain_text(
                item.get("description")
                or item.get("translated_description")
                or item.get("snippet")
            )

            item_kind = str(item.get("kind") or item.get("type") or "").casefold()
            candidate_kind = kind or ("video" if "video" in item_kind else ("exercise" if "exercise" in item_kind else "article"))

            seen.add(url)
            candidates.append(
                Candidate(
                    url=url,
                    title=title,
                    provider="khan_academy",
                    kind=candidate_kind,
                    lang=lang,
                    snippet=snippet[:300],
                    license="CC-BY-NC-SA-4.0",
                    institution="Khan Academy",
                )
            )
            if len(candidates) >= self.max_results:
                break

        return candidates


KhanAcademyProvider = KhanAcademySearch

__all__ = ["DEFAULT_KHAN_ENDPOINT", "KhanAcademyProvider", "KhanAcademySearch"]
