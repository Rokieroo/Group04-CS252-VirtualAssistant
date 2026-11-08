"""OpenStax books through the CMS API (ADR 004: ``method: api``).

The license is read per book: OpenStax publishes under more than one license,
and a book that names none, or one we do not know, waits for review instead of
being given a default. Chapters sit under ``/apps/archive``, which
``robots.txt`` forbids, so a book is one record without units.
"""

import html
import json
import re
from collections.abc import Collection, Iterator
from datetime import datetime

import httpx

from app.catalog.connectors.base import (
    CatalogRecord,
    ConnectorError,
    Fetcher,
    relevant,
    wanted,
)
from app.catalog.sources import Provider

PAGE_SIZE = 50
MAX_PAGES = 20  # 1000 books; the API reported 129 on 2026-11-05
LICENSES = {
    ("Creative Commons Attribution License", "4.0"): "CC-BY-4.0",
    ("Creative Commons Attribution-NonCommercial-ShareAlike License", "4.0"): "CC-BY-NC-SA-4.0",
}


def _text(value: str | None) -> str:
    """Plain text of an HTML fragment."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value or "")).split())


def book(provider: Provider, item: dict, source: str) -> CatalogRecord | None:
    """A live book as a record; retired, deprecated and unlisted books are skipped."""
    meta = item.get("meta") or {}
    if item.get("book_state") != "live" or not meta.get("html_url"):
        return None
    license_id = LICENSES.get((item.get("license_name"), item.get("license_version")))
    areas = [
        s.get("subject_category") or s.get("subject_name") or ""
        for s in [*(item.get("book_categories") or []), *(item.get("book_subjects") or [])]
    ]
    title = str(item.get("title") or "")
    return CatalogRecord(
        provider=provider.id,
        external_id=str(item["id"]),
        title=title,
        url=meta["html_url"],
        license=license_id if license_id in provider.licenses else None,
        level="k12" if "high school" in title.casefold() else "undergrad",
        language=meta.get("locale") or "en",
        format="book",
        department=" · ".join(dict.fromkeys(a for a in areas if a)),
        description=_text(item.get("description")),
        fetched_from=source,
    )


class OpenStaxConnector:
    name = "openstax"

    def __init__(self, provider: Provider, fetcher: Fetcher):
        self.provider = provider
        self.fetcher = fetcher

    def fetch(
        self, subjects: Collection[str], since: datetime | None = None
    ) -> Iterator[CatalogRecord]:
        """``since`` is ignored: the API reports no change date, and a license may change."""
        asked = wanted(subjects)
        base = httpx.URL(self.provider.endpoint)
        for page in range(MAX_PAGES):
            url = str(base.copy_merge_params({"limit": PAGE_SIZE, "offset": page * PAGE_SIZE}))
            result = self.fetcher.fetch(url)
            if not result.ok:
                raise ConnectorError(f"api_{result.error or result.paywall or result.status}")
            try:
                data = json.loads(result.text)
                items, total = data["items"], int(data["meta"]["total_count"])
            except (ValueError, KeyError, TypeError) as exc:
                raise ConnectorError("bad_api_response") from exc
            for item in items:
                record = book(self.provider, item, url)
                if record and relevant(record, asked):
                    yield record
            if not items or (page + 1) * PAGE_SIZE >= total:
                return
