"""One external web-search API adapter (spec 11.2).

The default endpoint is Serper (a small JSON API that works well for
Vietnamese and English queries).  Set ``WEB_SEARCH_API_URL`` to a compatible
endpoint if the team chooses another vendor; response parsing also accepts the
common Brave, Google Custom Search, and Tavily shapes.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.search.base import Candidate, SearchProvider
from app.search.http import error_code, plain_text

log = logging.getLogger("app.search.web")

DEFAULT_WEB_SEARCH_URL = "https://google.serper.dev/search"
DEFAULT_MAX_RESULTS = 5
DEFAULT_TIMEOUT = 10.0


class WebSearch(SearchProvider):
    """General web results; failures are recorded and degrade to ``[]``."""

    name = "web"
    # shortcut: Serper list price ($50 per 50k queries, Nov 2026); update with the vendor.
    cost_per_call = 0.001

    def __init__(
        self,
        api_key: str | None = None,
        *,
        endpoint: str | None = None,
        client: Any | None = None,
        max_results: int = DEFAULT_MAX_RESULTS,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.api_key = api_key
        self.endpoint = (
            endpoint
            or os.getenv("WEB_SEARCH_API_URL")
            or os.getenv("SERPER_API_URL")
            or DEFAULT_WEB_SEARCH_URL
        )
        self.client = client
        self.max_results = max(1, max_results)
        self.timeout = timeout
        self.last_error: str | None = None

    def _key(self) -> str:
        if self.api_key:
            return self.api_key
        for name in (
            "WEB_SEARCH_API_KEY",
            "SERPER_API_KEY",
            "BRAVE_SEARCH_API_KEY",
            "TAVILY_API_KEY",
        ):
            value = os.getenv(name, "").strip()
            if value:
                return value
        return ""

    def search(
        self,
        query: str,
        *,
        lang: str = "vi",
        kind: str | None = None,
        safe: bool = True,
    ) -> list[Candidate]:
        if kind and kind.casefold() == "video":
            return []
        if not query.strip():
            return []
        api_key = self._key()
        if not api_key:
            self.last_error = "missing_api_key"
            log.warning("provider=web skipped: missing WEB_SEARCH_API_KEY")
            return []
        try:
            response = self._request(
                api_key,
                {
                    "q": query,
                    "num": self.max_results,
                    "hl": lang,
                    "safe": "active" if safe else "off",
                },
            )
            response.raise_for_status()
            payload = response.json()
            self.last_error = None
            return self._candidates(payload, lang=lang, kind=kind)
        except Exception as exc:  # noqa: BLE001 - network/key/quota/bad JSON never break search
            self.last_error = error_code(exc)
            log.warning("provider=web failed error=%s", self.last_error)
            return []

    def _request(self, api_key: str, body: dict[str, Any]) -> Any:
        host = urlsplit(self.endpoint).netloc.casefold()
        headers = {"Content-Type": "application/json"}
        if "tavily.com" in host:
            headers["Authorization"] = f"Bearer {api_key}"
        elif "brave" in host:
            headers["X-Subscription-Token"] = api_key
        else:
            # Serper and Serper-compatible endpoints.
            headers["X-API-KEY"] = api_key
        if self.client is not None:
            return self.client.post(self.endpoint, json=body, headers=headers)
        return httpx.post(self.endpoint, json=body, headers=headers, timeout=self.timeout)

    def _items(self, payload: Any) -> list[Any]:
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        for key in ("organic", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        web = payload.get("web")
        if isinstance(web, dict) and isinstance(web.get("results"), list):
            return web["results"]
        return []

    def _candidates(
        self, payload: Any, *, lang: str, kind: str | None
    ) -> list[Candidate]:
        candidates: list[Candidate] = []
        seen: set[str] = set()
        for item in self._items(payload):
            if not isinstance(item, dict):
                continue
            url = plain_text(item.get("link") or item.get("url") or item.get("href"))
            title = plain_text(item.get("title") or item.get("name"))
            if not url or not title or url in seen:
                continue
            seen.add(url)
            candidates.append(
                Candidate(
                    url=url,
                    title=title,
                    provider="web",
                    kind=kind or "article",
                    lang=lang,
                    snippet=plain_text(
                        item.get("snippet")
                        or item.get("description")
                        or item.get("content")
                    ),
                )
            )
            if len(candidates) >= self.max_results:
                break
        return candidates


WebSearchProvider = WebSearch
WebProvider = WebSearch

__all__ = ["DEFAULT_WEB_SEARCH_URL", "WebProvider", "WebSearch", "WebSearchProvider"]
