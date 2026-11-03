"""YouTube Data API v3 provider (spec 11.2)."""

from __future__ import annotations

import html
import logging
import os
import re
from typing import Any

import httpx

from app.search.base import Candidate, SearchProvider

log = logging.getLogger("app.search.youtube")

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
DEFAULT_MAX_RESULTS = 5
DEFAULT_TIMEOUT = 10.0
_TAG_RE = re.compile(r"<[^>]+>")


def _plain_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", text)).strip()


def _error_code(exc: Exception) -> str:
    """A short, secret-free error label for logs and ``search_runs``."""

    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.TransportError):
        return "network"
    return type(exc).__name__


class YouTubeSearch(SearchProvider):
    """Find lecture videos cheaply; every failure becomes an empty result."""

    name = "youtube"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: Any | None = None,
        max_results: int = DEFAULT_MAX_RESULTS,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.api_key = api_key
        self.client = client
        self.max_results = max(1, max_results)
        self.timeout = timeout
        self.last_error: str | None = None

    def _key(self) -> str:
        if self.api_key:
            return self.api_key
        for name in ("YOUTUBE_API_KEY", "YOUTUBE_DATA_API_KEY", "GOOGLE_API_KEY"):
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
        if kind and kind.casefold() != "video":
            return []
        if not query.strip():
            return []
        api_key = self._key()
        if not api_key:
            self.last_error = "missing_api_key"
            log.warning("provider=youtube skipped: missing YOUTUBE_API_KEY")
            return []
        try:
            response = self._request(
                {
                    "key": api_key,
                    "part": "snippet",
                    "q": query,
                    "type": "video",
                    "maxResults": self.max_results,
                    "relevanceLanguage": lang,
                    "safeSearch": "strict" if safe else "moderate",
                }
            )
            response.raise_for_status()
            payload = response.json()
            self.last_error = None
            return self._candidates(payload, lang=lang)
        except Exception as exc:  # noqa: BLE001 - network/key/quota/bad JSON never break search
            self.last_error = _error_code(exc)
            log.warning("provider=youtube failed error=%s", self.last_error)
            return []

    def _request(self, params: dict[str, Any]) -> Any:
        if self.client is not None:
            return self.client.get(YOUTUBE_SEARCH_URL, params=params)
        return httpx.get(YOUTUBE_SEARCH_URL, params=params, timeout=self.timeout)

    def _candidates(self, payload: Any, *, lang: str) -> list[Candidate]:
        if not isinstance(payload, dict):
            return []
        items = payload.get("items", [])
        if not isinstance(items, list):
            return []
        candidates: list[Candidate] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            video_id = (item.get("id") or {}).get("videoId")
            snippet = item.get("snippet") or {}
            if not video_id or not isinstance(snippet, dict):
                continue
            title = _plain_text(snippet.get("title"))
            if not title:
                continue
            candidates.append(
                Candidate(
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    title=title,
                    provider="youtube",
                    kind="video",
                    lang=lang,
                    snippet=_plain_text(snippet.get("description")),
                )
            )
            if len(candidates) >= self.max_results:
                break
        return candidates


YouTubeProvider = YouTubeSearch

__all__ = ["YOUTUBE_SEARCH_URL", "YouTubeProvider", "YouTubeSearch"]
