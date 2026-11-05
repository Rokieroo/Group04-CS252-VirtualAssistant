"""MIT OpenCourseWare through its sitemaps (ADR 004: ``method: sitemap``).

The sitemap index lists one sitemap per course; the course slug already names
the course, so courses are matched against the wanted subjects before any
course page is requested. A matched course costs two requests: its page (title,
department, level, description) and its sitemap (the section pages, as units).
"""

import html
import logging
import re
from collections.abc import Collection, Iterator
from dataclasses import replace
from datetime import datetime
from xml.etree import ElementTree

from app.catalog.connectors.base import (
    CatalogRecord,
    ConnectorError,
    Fetcher,
    UnitRecord,
    relevant,
    wanted,
)
from app.catalog.sources import Provider

log = logging.getLogger(__name__)

_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_COURSE = re.compile(r"^(https://ocw\.mit\.edu/courses/([a-z0-9-]+)/)sitemap\.xml$")
_TERM = re.compile(r"-(?:spring|fall|summer|winter|january-iap|iap)-(\d{4})$")
_DETAIL = re.compile(r'class="course-number-term-detail">([^<]+)<')
_OG_TITLE = re.compile(r'<meta property="og:title" content="([^"]+)"')
_DESCRIPTION = re.compile(r'<meta name="description" content="([^"]*)"')
# Course logistics and file dumps, not study material.
_NOT_UNITS = {"syllabus", "calendar", "instructor-insights", "download", "related-resources"}


def _locations(body: bytes) -> list[str]:
    # The standard parser expands no external entities, and the body is capped at 5 MB.
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as exc:
        raise ConnectorError("bad_sitemap") from exc
    return [node.text.strip() for node in root.iter(_NS + "loc") if node.text]


def _sentence(slug: str) -> str:
    words = slug.replace("-", " ").strip()
    return words[:1].upper() + words[1:]


def draft(provider: Provider, course_url: str, slug: str) -> CatalogRecord | None:
    """What the slug alone says: "6-0002-introduction-to-...-fall-2016"."""
    tokens = slug.split("-")
    prefix = 3 if tokens[0] == "res" else 2
    if len(tokens) <= prefix:
        return None
    if tokens[0] == "res":
        code = f"RES.{tokens[1]}-{tokens[2]}".upper()
    else:
        code = f"{tokens[0]}.{tokens[1]}".upper()
    rest = "-".join(tokens[prefix:])
    term = _TERM.search(rest)
    return CatalogRecord(
        provider=provider.id,
        external_id=slug,
        title=_sentence(rest[: term.start()] if term else rest),
        url=course_url,
        license=provider.licenses[0],
        code=code,
        year=int(term.group(1)) if term else None,
        fetched_from=course_url + "sitemap.xml",
    )


def from_page(record: CatalogRecord, page: str) -> CatalogRecord:
    """Refine a draft with the course page's own title, department and level."""
    changes = {}
    if found := _OG_TITLE.search(page):
        parts = [html.unescape(p).strip() for p in found.group(1).split(" | ")]
        changes["title"] = parts[0] or record.title
        if len(parts) > 2:
            changes["department"] = parts[1]
    if found := _DETAIL.search(page):
        detail = html.unescape(found.group(1))
        changes["code"] = detail.split(" | ")[0].strip() or record.code
        if "Graduate" in detail and "Undergraduate" not in detail:
            changes["level"] = "grad"
    if found := _DESCRIPTION.search(page):
        changes["description"] = html.unescape(found.group(1)).strip()
    return replace(record, **changes)


def units(course_url: str, locations: list[str]) -> tuple[UnitRecord, ...]:
    """Section pages ("pages/readings/", "video_galleries/lecture-videos/")."""
    found = {}
    for location in locations:
        path = location.removeprefix(course_url)
        match = re.fullmatch(r"(pages|video_galleries)/([a-z0-9-]+)/", path)
        if match and match.group(2) not in _NOT_UNITS:
            fmt = "video" if match.group(1) == "video_galleries" else "article"
            found[location] = (_sentence(match.group(2)), fmt)
    # Sorted by URL: sitemap order is not stable, and positions key the unit rows.
    return tuple(
        UnitRecord(position, title, url, fmt)
        for position, (url, (title, fmt)) in enumerate(sorted(found.items()), start=1)
    )


class MitOcwConnector:
    name = "mit_ocw"

    def __init__(self, provider: Provider, fetcher: Fetcher):
        self.provider = provider
        self.fetcher = fetcher

    def fetch(
        self, subjects: Collection[str], since: datetime | None = None
    ) -> Iterator[CatalogRecord]:
        """``since`` is ignored: OCW sitemaps carry no ``lastmod``."""
        asked = wanted(subjects)
        index = self.fetcher.fetch(self.provider.endpoint)
        if not index.ok:
            raise ConnectorError(f"index_{index.error or index.paywall or index.status}")
        for location in _locations(index.body):
            match = _COURSE.match(location)
            record = match and draft(self.provider, match.group(1), match.group(2))
            if record and relevant(record, asked):
                yield self._course(record)

    def _course(self, record: CatalogRecord) -> CatalogRecord:
        page = self.fetcher.fetch(record.url)
        if page.ok:
            record = replace(from_page(record, page.text), fetched_from=record.url)
        else:
            log.warning("mit_ocw course_page_failed reason=%s", page.error or page.status)
        sitemap = self.fetcher.fetch(record.url + "sitemap.xml")
        if not sitemap.ok:
            log.warning("mit_ocw course_sitemap_failed reason=%s", sitemap.error or sitemap.status)
            return record
        try:
            return replace(record, units=units(record.url, _locations(sitemap.body)))
        except ConnectorError:
            log.warning("mit_ocw course_sitemap_unreadable")
            return record
