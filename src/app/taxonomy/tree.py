"""The subject tree (issue #99): field -> subject -> topic, read from YAML.

``data/catalog/subjects.yaml`` is the source of truth; this module only parses and
validates it, so a typo fails loudly at load instead of silently never matching.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "catalog" / "subjects.yaml"
DEPTHS = ("field", "subject", "topic")
LEARNER_LEVELS = frozenset({"k12", "undergrad", "grad"})
# Course.level says "university"; catalog courses say undergrad or grad.
_UNIVERSITY = frozenset({"undergrad", "grad"})
_SEGMENT = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_KEYS = {
    "field": {"slug", "name", "name_vi", "ref", "levels", "departments", "subjects"},
    "subject": {"slug", "name", "name_vi", "ref", "keywords", "course_codes", "departments",
                "topics"},
    "topic": {"slug", "name", "name_vi", "ref", "keywords"},
}
_CHILDREN = {"field": "subjects", "subject": "topics"}


class TaxonomyError(ValueError):
    """The YAML breaks a rule of the tree; the message names the entry."""


@dataclass(frozen=True)
class Subject:
    """One entry of the tree; ``depth`` is field, subject or topic."""

    slug: str
    name: str
    name_vi: str
    depth: str
    parent: str | None = None
    ref: str = ""
    keywords: tuple[str, ...] = ()
    course_codes: tuple[str, ...] = ()
    departments: tuple[str, ...] = ()
    levels: frozenset[str] = frozenset()  # fields only: the learner levels served

    @property
    def field(self) -> str:
        return self.slug.split(".", 1)[0]


class Taxonomy:
    def __init__(self, subjects: list[Subject]):
        self._by_slug = {subject.slug: subject for subject in subjects}

    def __getitem__(self, slug: str) -> Subject:
        return self._by_slug[slug]

    def __contains__(self, slug: object) -> bool:
        return slug in self._by_slug

    def __iter__(self) -> Iterator[Subject]:
        return iter(self._by_slug.values())

    def __len__(self) -> int:
        return len(self._by_slug)

    def ancestors(self, slug: str) -> tuple[str, ...]:
        """Parent first, field last."""
        found = []
        parent = self[slug].parent
        while parent is not None:
            found.append(parent)
            parent = self[parent].parent
        return tuple(found)

    def fields_for(self, level: str) -> frozenset[str]:
        """Fields serving a learner level; "university" or an unknown level means
        undergrad or grad, so school subjects never label university material."""
        wanted = frozenset({level}) if level in LEARNER_LEVELS else _UNIVERSITY
        return frozenset(
            subject.slug for subject in self if subject.depth == "field" and subject.levels & wanted
        )

    @classmethod
    def from_dict(cls, data: dict) -> Taxonomy:
        subjects: list[Subject] = []
        for raw in _list(data, "fields", "the file"):
            _parse(raw, "field", None, subjects)
        slugs = [subject.slug for subject in subjects]
        duplicates = sorted({slug for slug in slugs if slugs.count(slug) > 1})
        if duplicates:
            raise TaxonomyError(f"duplicate slugs: {duplicates}")
        return cls(subjects)


@lru_cache(maxsize=4)
def load_taxonomy(path: Path = DEFAULT_PATH) -> Taxonomy:
    """Parsed once per process and path; restart to pick up edits."""
    return Taxonomy.from_dict(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})


def _parse(raw: object, depth: str, parent: str | None, out: list[Subject]) -> None:
    if not isinstance(raw, dict):
        raise TaxonomyError(f"a {depth} under {parent or 'the root'} must be a mapping")
    slug = str(raw.get("slug") or "")
    where = slug or f"a {depth} under {parent or 'the root'}"
    unknown = sorted(set(raw) - _KEYS[depth])
    if unknown:
        raise TaxonomyError(f"{where}: unknown keys {unknown}")
    prefix, _, segment = slug.rpartition(".")
    if (prefix or None) != parent or not _SEGMENT.fullmatch(segment):
        expected = f"{parent}.<segment>" if parent else "<segment>"
        raise TaxonomyError(f"{where}: slug must be {expected} in lowercase-kebab")
    for key in ("name", "name_vi"):
        if not str(raw.get(key) or "").strip():
            raise TaxonomyError(f"{slug}: {key} is required")
    levels = frozenset(_strings(raw, "levels", slug))
    if depth == "field" and (not levels or levels - LEARNER_LEVELS):
        raise TaxonomyError(
            f"{slug}: levels must be a non-empty subset of {sorted(LEARNER_LEVELS)}")
    codes = _strings(raw, "course_codes", slug)
    for code in codes:
        try:
            re.compile(code)
        except re.error as exc:
            raise TaxonomyError(f"{slug}: bad course code pattern {code!r}: {exc}") from None
    out.append(Subject(
        slug=slug,
        name=str(raw["name"]).strip(),
        name_vi=str(raw["name_vi"]).strip(),
        depth=depth,
        parent=parent,
        ref=str(raw.get("ref") or ""),
        keywords=_strings(raw, "keywords", slug),
        course_codes=codes,
        departments=_strings(raw, "departments", slug),
        levels=levels,
    ))
    child = _CHILDREN.get(depth)
    if child:
        for item in _list(raw, child, slug, required=False):
            _parse(item, DEPTHS[DEPTHS.index(depth) + 1], slug, out)


def _list(raw: dict, key: str, where: str, *, required: bool = True) -> list:
    value = raw.get(key)
    if value is None and not required:
        return []
    if not isinstance(value, list):
        raise TaxonomyError(f"{where}: {key} must be a list")
    return value


def _strings(raw: dict, key: str, where: str) -> tuple[str, ...]:
    values = _list(raw, key, where, required=False)
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise TaxonomyError(f"{where}: {key} must be a list of non-empty strings")
    return tuple(value.strip() for value in values)
