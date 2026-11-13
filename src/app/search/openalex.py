"""OpenAlex external search provider (Issue #157, ADR 004).

Queries OpenAlex works API filtered to Open Access (is_oa:true).
Extracts license, institution/publisher, and metadata.
"""

from __future__ import annotations

import html
import logging
import re
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.search.base import Candidate, SearchProvider

log = logging.getLogger("app.search.openalex")

DEFAULT_OPENALEX_ENDPOINT = "https://api.openalex.org/works"
DEFAULT_MAX_RESULTS = 5
DEFAULT_TIMEOUT = 10.0
MAX_RETRIES = 2
RETRY_DELAY = 0.5

_TAG_RE = re.compile(r"<[^>]+>")

OPENALEX_LICENSES: dict[str, str] = {
    "cc-by": "CC-BY-4.0",
    "cc-by-4.0": "CC-BY-4.0",
    "cc-by-nc-sa": "CC-BY-NC-SA-4.0",
    "cc-by-nc-sa-4.0": "CC-BY-NC-SA-4.0",
    "cc-by-sa": "CC-BY-SA-4.0",
    "cc-by-sa-4.0": "CC-BY-SA-4.0",
    "cc-by-nc": "CC-BY-NC-4.0",
    "cc-by-nc-4.0": "CC-BY-NC-4.0",
    "cc0": "CC0-1.0",
    "public-domain": "CC0-1.0",
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


def _normalize_license(raw: Any) -> str | None:
    if not raw:
        return None
    val = str(raw).strip().lower()
    if val in OPENALEX_LICENSES:
        return OPENALEX_LICENSES[val]
    # Check prefixes
    for prefix, target in OPENALEX_LICENSES.items():
        if val.startswith(prefix):
            return target
    if val.startswith("cc"):
        return val.upper()
    return None


def _reconstruct_abstract(inverted: Any) -> str:
    if not isinstance(inverted, dict):
        return ""
    try:
        positions: dict[int, str] = {}
        for word, idxs in inverted.items():
            if isinstance(idxs, list):
                for idx in idxs:
                    if isinstance(idx, int):
                        positions[idx] = word
        return " ".join(positions[k] for k in sorted(positions.keys()))
    except (TypeError, ValueError, KeyError):
        return ""


class OpenAlexSearch(SearchProvider):
    """External provider for open-access papers and books from OpenAlex."""

    name = "openalex"
    cost_per_call = 0.0

    def __init__(
        self,
        endpoint: str | None = None,
        *,
        client: Any | None = None,
        max_results: int = DEFAULT_MAX_RESULTS,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.endpoint = endpoint or DEFAULT_OPENALEX_ENDPOINT
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
            "search": query.strip(),
            "filter": "is_oa:true",
            "per_page": self.max_results,
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
                log.warning("provider=openalex failed error=%s", self.last_error)
                return []

        if response is None:
            return []

        try:
            payload = response.json()
            return self._candidates(payload, lang=lang, kind=kind)
        except Exception as exc:  # noqa: BLE001 - bad JSON degrades gracefully
            self.last_error = _error_code(exc)
            log.warning("provider=openalex bad json error=%s", self.last_error)
            return []

    def _candidates(
        self, payload: Any, *, lang: str, kind: str | None
    ) -> list[Candidate]:
        if not isinstance(payload, dict):
            return []
        results = payload.get("results")
        if not isinstance(results, list):
            return []

        candidates: list[Candidate] = []
        seen: set[str] = set()

        for item in results:
            if not isinstance(item, dict):
                continue

            primary_loc = item.get("primary_location") or {}
            best_oa = item.get("best_oa_location") or {}

            # URL extraction
            url = (
                item.get("doi")
                or primary_loc.get("landing_page_url")
                or primary_loc.get("pdf_url")
                or best_oa.get("landing_page_url")
                or best_oa.get("pdf_url")
                or item.get("id")
            )
            url = _plain_text(url)
            if not url or url in seen:
                continue
            parsed = urlsplit(url)
            if not parsed.scheme or not parsed.netloc:
                continue

            # Title
            title = _plain_text(item.get("title") or item.get("display_name"))
            if not title:
                continue

            # License: must be clearly identified, otherwise skipped
            raw_license = (
                primary_loc.get("license")
                or best_oa.get("license")
                or item.get("open_access", {}).get("oa_status")
            )
            license_id = _normalize_license(raw_license)
            if not license_id:
                # Issue #157: Nguồn không rõ giấy phép bị loại
                continue

            # Institution / Publisher
            source = primary_loc.get("source") or best_oa.get("source") or {}
            institution = source.get("host_organization_name") or source.get("display_name") or ""
            if not institution:
                authorships = item.get("authorships") or []
                if authorships and isinstance(authorships, list):
                    insts = authorships[0].get("institutions") or []
                    if insts and isinstance(insts, list):
                        institution = insts[0].get("display_name") or ""
            institution = _plain_text(institution)

            # Snippet
            snippet = _plain_text(_reconstruct_abstract(item.get("abstract_inverted_index")))
            if not snippet:
                concepts = item.get("concepts") or []
                if isinstance(concepts, list):
                    concept_names = [c.get("display_name") for c in concepts if isinstance(c, dict) and c.get("display_name")]
                    if concept_names:
                        snippet = f"Topics: {', '.join(concept_names[:5])}"

            work_type = str(item.get("type") or "").casefold()
            candidate_kind = kind or ("book" if "book" in work_type else "article")
            work_lang = str(item.get("language") or lang)

            seen.add(url)
            candidates.append(
                Candidate(
                    url=url,
                    title=title,
                    provider="openalex",
                    kind=candidate_kind,
                    lang=work_lang,
                    snippet=snippet[:300],
                    license=license_id,
                    institution=institution,
                )
            )
            if len(candidates) >= self.max_results:
                break

        return candidates


OpenAlexProvider = OpenAlexSearch

__all__ = ["DEFAULT_OPENALEX_ENDPOINT", "OpenAlexProvider", "OpenAlexSearch"]
