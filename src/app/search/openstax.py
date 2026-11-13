"""OpenStax external search provider (Issue #157, ADR 004).

Queries OpenStax books CMS API and extracts open-access textbooks.
Reads license per book (CC BY 4.0 or CC BY-NC-SA 4.0); unlicenced books are dropped.
"""

from __future__ import annotations

import html
import logging
import re
import time
from typing import Any

import httpx

from app.search.base import Candidate, SearchProvider

log = logging.getLogger("app.search.openstax")

DEFAULT_OPENSTAX_ENDPOINT = "https://openstax.org/apps/cms/api/v2/pages/"
DEFAULT_MAX_RESULTS = 5
DEFAULT_TIMEOUT = 10.0
MAX_RETRIES = 2
RETRY_DELAY = 0.5

_TAG_RE = re.compile(r"<[^>]+>")

OPENSTAX_LICENSES: dict[tuple[str, str], str] = {
    ("Creative Commons Attribution License", "4.0"): "CC-BY-4.0",
    ("Creative Commons Attribution-NonCommercial-ShareAlike License", "4.0"): "CC-BY-NC-SA-4.0",
    ("Creative Commons Attribution", "4.0"): "CC-BY-4.0",
    ("Creative Commons Attribution-NonCommercial-ShareAlike", "4.0"): "CC-BY-NC-SA-4.0",
}


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


def _normalize_license(name: Any, version: Any) -> str | None:
    if not name:
        return None
    key = (str(name).strip(), str(version or "").strip())
    if key in OPENSTAX_LICENSES:
        return OPENSTAX_LICENSES[key]
    raw = f"{name} {version or ''}".casefold()
    if "noncommercial" in raw or "nc" in raw:
        return "CC-BY-NC-SA-4.0"
    if "attribution" in raw or "cc-by" in raw:
        return "CC-BY-4.0"
    return None


class OpenStaxSearch(SearchProvider):
    """External search provider for OpenStax books and courseware."""

    name = "openstax"
    cost_per_call = 0.0

    def __init__(
        self,
        endpoint: str | None = None,
        *,
        client: Any | None = None,
        max_results: int = DEFAULT_MAX_RESULTS,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.endpoint = endpoint or DEFAULT_OPENSTAX_ENDPOINT
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
            "type": "books.Book",
            "search": query.strip(),
            "fields": "title,license_name,license_version,book_state,description,book_subjects,book_categories",
            "limit": self.max_results,
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
                log.warning("provider=openstax failed error=%s", self.last_error)
                return []

        if response is None:
            return []

        try:
            payload = response.json()
            return self._candidates(payload, lang=lang, kind=kind)
        except Exception as exc:  # noqa: BLE001 - bad JSON degrades gracefully
            self.last_error = _error_code(exc)
            log.warning("provider=openstax bad json error=%s", self.last_error)
            return []

    def _candidates(
        self, payload: Any, *, lang: str, kind: str | None
    ) -> list[Candidate]:
        if not isinstance(payload, dict):
            return []
        items = payload.get("items")
        if not isinstance(items, list):
            return []

        candidates: list[Candidate] = []
        seen: set[str] = set()

        for item in items:
            if not isinstance(item, dict):
                continue

            # Skip non-live or deprecated books
            if item.get("book_state") and item.get("book_state") != "live":
                continue

            meta = item.get("meta") or {}
            url = _plain_text(meta.get("html_url") or item.get("html_url"))
            if not url or url in seen:
                continue

            title = _plain_text(item.get("title"))
            if not title:
                continue

            # License check: must be recognized, else dropped
            license_id = _normalize_license(item.get("license_name"), item.get("license_version"))
            if not license_id:
                continue

            snippet = _plain_text(item.get("description"))

            book_locale = meta.get("locale") or lang
            candidate_kind = kind or "book"

            seen.add(url)
            candidates.append(
                Candidate(
                    url=url,
                    title=title,
                    provider="openstax",
                    kind=candidate_kind,
                    lang=book_locale,
                    snippet=snippet[:300],
                    license=license_id,
                    institution="OpenStax (Rice University)",
                )
            )
            if len(candidates) >= self.max_results:
                break

        return candidates


OpenStaxProvider = OpenStaxSearch

__all__ = ["DEFAULT_OPENSTAX_ENDPOINT", "OpenStaxProvider", "OpenStaxSearch"]
