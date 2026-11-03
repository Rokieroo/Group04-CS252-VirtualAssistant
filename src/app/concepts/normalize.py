"""Shared topic normalization (issue #50).

Slugs, comparison keys and duplicate merging used to live in ``extract.py``.
They now live here so the Week 1 page-window pipeline (``from_pages.py``) and
newer week-based topic inputs share the same Unicode-aware rules.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

SIMILAR_TITLE = 0.9


@dataclass
class TopicIn:
    """One topic proposed for a week, before normalization."""

    title: str
    week: int
    source_page: int | None = None
    summary: str = ""


def slugify(value: str) -> str:
    """Return an ASCII, lower-case URL slug for ``value``.

    Vietnamese diacritics are removed (``đ`` becomes ``d``) so the result is
    safe in URLs and stable across NFC/NFD input.
    """
    text = unicodedata.normalize("NFC", str(value or ""))
    ascii_text = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    ascii_text = ascii_text.encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:80].strip("-")


def normalize(title: str) -> str:
    """Normalize a title for fuzzy comparison, as space-separated words."""
    return slugify(title).replace("-", " ")


def _clean_title(value: str) -> str:
    """Keep the display title but collapse whitespace; compose Vietnamese text."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(value or ""))).strip()


def comparison_key(title: str) -> str:
    """Lower-case key for duplicate detection, without the 80-character slug limit.

    NFC is applied first so composed and decomposed Vietnamese spellings compare
    equal; diacritics and punctuation are then removed so ``"Solution  ladder "``,
    ``"solution ladder"`` and ``"Solution Ladder!"`` share one key.
    """
    text = unicodedata.normalize("NFC", str(title or ""))
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text.casefold())
    return " ".join(text.split())


def _unique_slug(base: str, used: set[str]) -> str:
    """Return ``base`` or ``base-2``, ``base-3``... so every slug is unique."""
    base = base or "topic"
    candidate = base
    number = 1
    while candidate in used:
        number += 1
        suffix = f"-{number}"
        candidate = f"{base[: 80 - len(suffix)].rstrip('-')}{suffix}"
    used.add(candidate)
    return candidate


def normalize_topics(topics: list[TopicIn]) -> list[dict]:
    """Normalize topic titles, merge duplicates and assign unique slugs.

    Duplicates are matched after NFC normalization, case-folding, punctuation
    removal and whitespace collapsing. The record with the earliest ``week`` is
    kept; a missing ``source_page``/``summary`` is filled from a later duplicate
    so no citation is lost. Output order follows the first appearance.
    """
    merged: dict[str, dict] = {}
    for topic in topics:
        title = _clean_title(topic.title)
        key = comparison_key(title) or "topic"
        candidate = {
            "title": title,
            "week": int(topic.week),
            "source_page": topic.source_page,
            "summary": str(topic.summary or "").strip(),
        }
        current = merged.get(key)
        if current is None:
            merged[key] = candidate
        elif candidate["week"] < current["week"]:
            if candidate["source_page"] is None:
                candidate["source_page"] = current["source_page"]
            if not candidate["summary"]:
                candidate["summary"] = current["summary"]
            merged[key] = candidate
        else:
            if current["source_page"] is None and candidate["source_page"] is not None:
                current["source_page"] = candidate["source_page"]
            if not current["summary"] and candidate["summary"]:
                current["summary"] = candidate["summary"]

    used: set[str] = set()
    result: list[dict] = []
    for topic in merged.values():
        result.append({"slug": _unique_slug(slugify(topic["title"]), used), **topic})
    return result


def merge(concepts: list[dict], into: list[dict] | None = None) -> list[dict]:
    """Merge by equal slug or near-equal title; the concept seen first keeps its fields."""
    merged = [dict(c) for c in into or []]
    for concept in concepts:
        same = next((m for m in merged if m["slug"] == concept["slug"] or SequenceMatcher(
            None, normalize(m["title"]), normalize(concept["title"])).ratio() >= SIMILAR_TITLE),
            None)
        if same is None:
            merged.append(dict(concept))
        else:
            same["source_pages"] = sorted(set(same["source_pages"]) | set(concept["source_pages"]))
    return merged
