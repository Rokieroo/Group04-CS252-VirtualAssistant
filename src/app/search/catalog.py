"""Internal catalog provider (spec 11.2).

Catalog entries are curated resources (teacher-pinned material, OER, official
library links).  The catalog is always available and costs no quota, so it is
the first provider the search service asks and the fallback when external
providers fail.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.search.base import Candidate, SearchProvider

log = logging.getLogger("app.search.catalog")

DEFAULT_CATALOG_DIR = Path(__file__).resolve().parents[3] / "data" / "catalog"

# Query words that describe the search format rather than the topic.  They
# should not stop a catalog entry from matching the substantive query terms.
_STOPWORDS = {
    "a", "an", "and", "article", "bai", "ban", "cac", "cho", "co",
    "course", "cua", "dang", "duoc", "examples", "exercise", "exercises",
    "file", "filetype", "for", "giang", "giai", "hoc", "in", "lecture",
    "loi", "material", "materials", "mon", "notes", "of", "on", "pdf",
    "practice", "slide", "slides", "tai", "tap", "the", "tiet", "tren",
    "tutorial", "va", "ve", "video", "voi", "worked", "youtube",
}


@dataclass
class _Entry:
    candidate: Candidate
    search_text: str
    title_text: str
    tags: tuple[str, ...]


def _as_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [_as_text(item) for item in value if _as_text(item)]
    return [_as_text(value)] if _as_text(value) else []


def _normalize(text: str) -> str:
    """Case-, accent-, and punctuation-insensitive text used for matching."""

    folded = unicodedata.normalize("NFKD", text.casefold())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    folded = folded.replace("đ", "d")
    return re.sub(r"[^\w\s]", " ", folded)


def _entries_from_document(document: Any) -> list[dict[str, Any]]:
    if document is None:
        return []
    if isinstance(document, list):
        return [item for item in document if isinstance(item, dict)]
    if not isinstance(document, dict):
        return []
    if "url" in document and "title" in document:
        return [document]
    for key in ("resources", "items", "entries", "catalog", "results"):
        if isinstance(document.get(key), list):
            return [item for item in document[key] if isinstance(item, dict)]
    # Also accept a mapping keyed by a stable id whose values are resources.
    values = list(document.values())
    if values and all(isinstance(item, dict) for item in values):
        return values
    return []


class CatalogSearch(SearchProvider):
    """Search YAML files under ``data/catalog`` (or a supplied directory)."""

    name = "catalog"

    def __init__(
        self,
        directory: str | Path | None = None,
        *,
        catalog_dir: str | Path | None = None,
        max_results: int = 5,
        session=None,
        now=None,
    ):
        chosen = directory if directory is not None else catalog_dir
        self.directory = Path(chosen) if chosen is not None else DEFAULT_CATALOG_DIR
        self.max_results = max(1, max_results)
        self.last_error: str | None = None
        self.session = session
        self.now = now
        self._entries: list[_Entry] = []
        self._signature: tuple[tuple[str, int, int], ...] | None = None

    def _files(self) -> list[Path]:
        if not self.directory.exists():
            return []
        if self.directory.is_file():
            return [self.directory] if self.directory.suffix.lower() in {".yaml", ".yml"} else []
        return sorted(
            path
            for pattern in ("*.yaml", "*.yml")
            for path in self.directory.glob(pattern)
            if path.is_file()
        )

    def _read_entries(self, files: list[Path]) -> list[_Entry]:
        try:
            import yaml
        except ImportError:  # pragma: no cover - PyYAML is a declared dependency
            self.last_error = "missing_pyyaml"
            log.warning("provider=catalog unavailable: missing PyYAML")
            return []

        entries: list[_Entry] = []
        for path in files:
            try:
                document = yaml.safe_load(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001 - a bad hand-edited YAML file must not break search
                self.last_error = f"{path.name}: {type(exc).__name__}"
                log.warning("provider=catalog skipped file=%s error=%s", path.name,
                            type(exc).__name__)
                continue
            for item in _entries_from_document(document):
                candidate = self._candidate(item)
                if candidate is None:
                    continue
                tags = tuple(
                    _as_list(item.get("tags"))
                    + _as_list(item.get("topics"))
                    + _as_list(item.get("topic"))
                    + _as_list(item.get("keywords"))
                    + _as_list(item.get("course"))
                    + _as_list(item.get("courses"))
                )
                entries.append(
                    _Entry(
                        candidate=candidate,
                        search_text=_normalize(
                            " ".join(
                                [candidate.title, candidate.snippet, candidate.kind,
                                 candidate.lang, *tags]
                            )
                        ),
                        title_text=_normalize(candidate.title),
                        tags=tuple(_normalize(tag) for tag in tags if tag),
                    )
                )
        return entries

    @staticmethod
    def _candidate(item: dict[str, Any]) -> Candidate | None:
        url = _as_text(item.get("url") or item.get("link") or item.get("href"))
        title = _as_text(item.get("title") or item.get("name"))
        if not url or not title:
            return None
        return Candidate(
            url=url,
            title=title,
            provider=_as_text(item.get("provider")) or "catalog",
            kind=_as_text(item.get("kind") or item.get("type") or item.get("format"))
            or "article",
            lang=_as_text(item.get("lang") or item.get("language")) or "vi",
            snippet=_as_text(
                item.get("snippet")
                or item.get("description")
                or item.get("summary")
            ),
        )

    def _load(self) -> list[_Entry]:
        if self.session is not None:
            return self._database_entries()
        files = self._files()
        signature = tuple(
            (str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in files
        )
        if self._signature != signature:
            self._entries = self._read_entries(files)
            self._signature = signature
            if self._entries:
                self.last_error = None
        return self._entries

    def _database_entries(self):
        from datetime import UTC, datetime

        from sqlalchemy import text

        from app.catalog.verification import is_current, latest_results
        from app.vetting.policy import default_policy

        now = self.now or datetime.now(UTC)
        rows = self.session.execute(text("SELECT id,url,title,kind,lang,format FROM resources r "
            "WHERE verification_status='verified' AND canonical_url IS NOT NULL "
            "AND content_hash IS NOT NULL AND license IS NOT NULL AND failed_checks < 2 "
            "AND (http_status IS NULL OR http_status=200)" )).mappings()
        checks = latest_results(self.session.execute(text(
            "SELECT resource_id,check_name,result,checked_at FROM "
            "resource_verifications ORDER BY checked_at DESC,id DESC")))
        entries = []
        for row in rows:
            if not is_current(checks.get(row["id"], {}), now):
                continue
            if default_policy().tier(row["url"]).value == 0:
                continue
            candidate = Candidate(row["url"], row["title"], "catalog", row["format"] or row["kind"], row["lang"])
            entries.append(_Entry(candidate, _normalize(row["title"]), _normalize(row["title"]), ()))
        return entries

    def search(
        self,
        query: str,
        *,
        lang: str = "vi",
        kind: str | None = None,
        safe: bool = True,
    ) -> list[Candidate]:
        entries = self._load()
        if not entries:
            return []
        query_text = _normalize(query)
        query_tokens = [
            token
            for token in query_text.split()
            if len(token) > 1 and token not in _STOPWORDS and not token.isdigit()
        ]
        scored: list[tuple[int, int, _Entry]] = []
        for entry in entries:
            if kind and entry.candidate.kind.casefold() != kind.casefold():
                continue
            if not query_tokens:
                score = 1
            else:
                score = 0
                for token in query_tokens:
                    if token in entry.title_text.split():
                        score += 3
                    elif token in entry.search_text:
                        score += 1
                    elif token in entry.tags:
                        score += 2
                if query_text and query_text in entry.title_text:
                    score += 5
            if score > 0:
                scored.append((score, int(entry.candidate.lang != lang), entry))
        scored.sort(key=lambda row: (-row[0], row[1], row[2].candidate.title.casefold()))

        results: list[Candidate] = []
        seen: set[str] = set()
        for _score, _lang_mismatch, entry in scored:
            if entry.candidate.url in seen:
                continue
            seen.add(entry.candidate.url)
            results.append(entry.candidate)
            if len(results) >= self.max_results:
                break
        return results


# Friendly alias for callers that prefer the provider naming used elsewhere.
CatalogProvider = CatalogSearch

__all__ = ["DEFAULT_CATALOG_DIR", "CatalogProvider", "CatalogSearch"]
