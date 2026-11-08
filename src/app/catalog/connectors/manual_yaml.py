"""Hand-added sources from reviewed YAML files (ADR 004: ``method: manual``).

Open Yale Courses has no sitemap, and some sources (Khan Academy, Coursera) may
not be fetched by any program: an admin lists them by hand, and they then go
through the same upsert and verification as connector output. Each file holds
``resources:``, a list of entries::

    - title: Use case diagram
      url: https://en.wikipedia.org/wiki/Use_case_diagram
      license: CC-BY-SA-4.0          # an id of catalog_sources.yaml, required
      kind: article                  # course | book | video | article
      lang: en
      level: undergrad               # k12 | undergrad | grad
      subjects: [ct.use-cases]       # taxonomy ids a reviewer checked, optional
      tags: [use case diagram]       # free text the tagger reads, optional
      is_free: true                  # default; false if only a preview is free (ADR 004 s7)
      units: [{title: ..., url: ..., kind: video}]   # optional

The provider is the registry provider that owns the URL's domain, else
``manual``; an entry's ``provider`` field is the internal catalog's label and is
not read here.
"""

import logging
from collections.abc import Collection, Iterator
from datetime import datetime
from pathlib import Path

import yaml

from app.catalog.connectors.base import (
    MANUAL,
    CatalogRecord,
    ConnectorError,
    UnitRecord,
    relevant,
    wanted,
)
from app.catalog.sources import Sources
from app.search.service import canonical_url

log = logging.getLogger(__name__)


def _list(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value or [] if v]


def entry(item: dict, sources: Sources, source: str) -> CatalogRecord | None:
    title, url = str(item.get("title") or "").strip(), str(item.get("url") or "").strip()
    if not title or not url:
        return None
    owner = sources.provider_of(url)
    year = item.get("year")
    return CatalogRecord(
        provider=owner.id if owner and owner.use == "source" else MANUAL,
        external_id=canonical_url(url),
        title=title,
        url=url,
        license=item.get("license"),
        level=str(item.get("level") or "undergrad"),
        language=str(item.get("lang") or "en"),
        format=str(item.get("kind") or "article"),
        code=item.get("code"),
        year=year if isinstance(year, int) else None,
        department=str(item.get("course") or ""),
        description=str(item.get("snippet") or ""),
        keywords=tuple(_list(item.get("tags"))),
        is_free=item.get("is_free", True),
        subjects=tuple(_list(item.get("subjects"))),
        units=tuple(
            UnitRecord(position, str(u["title"]), str(u["url"]), str(u.get("kind") or "article"))
            for position, u in enumerate(item.get("units") or [], start=1)
            if isinstance(u, dict) and u.get("title") and u.get("url")
        ),
        fetched_from=source,
    )


class ManualYamlConnector:
    def __init__(self, paths: list[Path], sources: Sources, *, name: str = "manual_yaml"):
        self.paths = paths
        self.sources = sources
        self.name = name

    def records(self) -> Iterator[CatalogRecord]:
        for path in self.paths:
            try:
                document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError) as exc:
                raise ConnectorError("unreadable_file") from exc
            items = document.get("resources") if isinstance(document, dict) else None
            for item in items or []:
                record = entry(item, self.sources, path.name) if isinstance(item, dict) else None
                if record is None:
                    log.warning("%s skipped_entry file=%s", self.name, path.name)
                    continue
                yield record

    def fetch(
        self, subjects: Collection[str], since: datetime | None = None
    ) -> Iterator[CatalogRecord]:
        """``since`` is ignored: entries carry no dates and the files are small."""
        asked = wanted(subjects)
        return (record for record in self.records() if relevant(record, asked))
