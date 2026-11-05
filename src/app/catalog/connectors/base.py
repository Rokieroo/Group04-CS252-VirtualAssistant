"""One interface for every catalog connector (#98, ADR 004).

A connector reads one provider and yields :class:`CatalogRecord` values for the
subjects a syllabus needs; it never touches the database. The backend's
``upsert_records`` stores them as ``pending`` resources for verification (#101).
"""

from collections.abc import Collection, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.catalog.sources import Sources
from app.catalog.taxonomy import subjects as taxonomy
from app.catalog.taxonomy import tag_resource
from app.vetting.fetch import FetchResult
from app.vetting.policy import DomainTier, default_policy

LEVELS = {"k12", "undergrad", "grad"}
MANUAL = "manual"  # provider of a hand-added source outside the registry


class ConnectorError(Exception):
    """A provider could not be read at all; ``reason`` is a short, log-safe code."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class UnitRecord:
    """A lecture page, chapter or video gallery inside a course."""

    position: int
    title: str
    url: str
    format: str = "article"


@dataclass(frozen=True)
class CatalogRecord:
    """A course or book: the metadata ADR 004 section 5 allows, plus provenance."""

    provider: str
    external_id: str
    title: str
    url: str
    license: str | None  # None: the provider names none, so it waits for review
    level: str = "undergrad"
    language: str = "en"
    format: str = "course"
    code: str | None = None
    year: int | None = None
    department: str = ""
    description: str = ""  # only feeds subject tags; never stored (ADR 004 section 5)
    keywords: tuple[str, ...] = ()  # topic phrases a curator assigned (YAML `tags`)
    is_free: bool | None = True
    subjects: tuple[str, ...] = ()  # a curator's labels; empty: tag automatically
    units: tuple[UnitRecord, ...] = ()
    fetched_from: str = ""  # the sitemap, API page or file the record came from
    updated_at: datetime | None = None  # set by providers that report changes

    def tag_fields(self) -> dict:
        """The fields the subject tagger reads (``taxonomy._fields``)."""
        return {
            "title": self.title,
            "code": self.code or "",
            "department": self.department,
            "description": " ".join([self.description, *self.keywords]).strip(),
        }


class Fetcher(Protocol):
    def fetch(self, url: str) -> FetchResult: ...


class CatalogConnector(Protocol):
    name: str  # stored as ``resources.source_connector``

    def fetch(
        self, subjects: Collection[str], since: datetime | None = None
    ) -> Iterator[CatalogRecord]:
        """Records about ``subjects``; ``since`` skips records unchanged after it.

        Connectors whose provider reports no change dates ignore ``since``: the
        upsert is idempotent, so re-reading costs requests, never rows.
        """
        ...


def wanted(subjects: Iterable[str]) -> frozenset[str]:
    """``subjects`` with their topics and their parents, the root field excepted.

    A course labelled "ct" serves a node that needs "ct.framing"; one labelled
    "computing" says too little to serve anything.
    """
    rows = {row["id"]: row for row in taxonomy()}
    asked = {s for s in subjects if s in rows}
    found = set(asked)
    grew = True
    while grew:
        below = {i for i, row in rows.items() if row.get("parent_id") in found}
        grew = not below <= found
        found |= below
    for subject in asked:
        parent = rows[subject].get("parent_id")
        while parent and rows[parent].get("depth", 1) > 1:
            found.add(parent)
            parent = rows[parent].get("parent_id")
    return frozenset(found)


def labels(record: CatalogRecord) -> set[str]:
    """The curator's labels, else what the tagger accepts from names and keywords.

    Selection ignores the description: a blurb names topics in passing (a nursing
    book "processes" data), so it would pull in books about other subjects. The
    stored tags still read it.
    """
    if record.subjects:
        return set(record.subjects)
    names = {**record.tag_fields(), "description": " ".join(record.keywords)}
    return {t.subject_id for t in tag_resource(names) if not t.needs_review}


def relevant(record: CatalogRecord, subjects: frozenset[str]) -> bool:
    """``subjects`` is the output of :func:`wanted`."""
    return bool(labels(record) & subjects)


def check_record(record: CatalogRecord, sources: Sources) -> str | None:
    """Why ``record`` may not enter the catalog, or None.

    Connector output is untrusted: a sitemap may list any host, and a hand-written
    file may name any license.
    """
    if not record.title.strip() or not record.external_id:
        return "missing_metadata"
    if record.level not in LEVELS:
        return "bad_level"
    known = {row["id"] for row in taxonomy()}
    if not set(record.subjects) <= known:
        return "unknown_subject"
    urls = [record.url, *(unit.url for unit in record.units)]
    policy = default_policy()
    for url in urls:
        if not url.startswith(("https://", "http://")):
            return "bad_url"
        if policy.tier(url) is DomainTier.BLOCKED or policy.is_paywalled(url):
            return "blocked_domain"
    provider = sources.providers.get(record.provider)
    if provider is None:
        if record.provider != MANUAL:
            return "unknown_provider"
        # Outside the registry only a named, known license may vouch for a source.
        return None if record.license in sources.licenses else "unknown_license"
    if provider.use != "source":
        return "not_a_source_provider"
    if not all(provider.owns(url) for url in urls):
        return "foreign_domain"
    if record.license is None:
        return None if len(provider.licenses) > 1 else "missing_license"
    return None if record.license in provider.licenses else "unknown_license"


@dataclass
class FakeConnector:
    """Serves fixed records, for tests and offline demos."""

    records: list[CatalogRecord] = field(default_factory=list)
    name: str = "fake"
    calls: list[tuple[frozenset[str], datetime | None]] = field(default_factory=list)

    def fetch(
        self, subjects: Collection[str], since: datetime | None = None
    ) -> Iterator[CatalogRecord]:
        asked = wanted(subjects)
        self.calls.append((asked, since))
        for record in self.records:
            fresh = since is None or record.updated_at is None or record.updated_at >= since
            if fresh and relevant(record, asked):
                yield record
