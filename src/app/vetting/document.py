"""The readable text of a fetched resource: what the judge reads and quotes (spec 11.4).

Text is whitespace-collapsed once, here, so an ``evidence_quote`` check is a
plain substring test against exactly the text the judge was shown.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date

import trafilatura

from app.ingest import PDF, InvalidDocument, extract_pages
from app.search import Candidate
from app.vetting.fetch import FetchResult

__all__ = ["Document", "collapse", "detect_language", "read_document", "readable_pages"]

WORDS_PER_MINUTE = 200
_SPACE = re.compile(r"\s+")
_HTML_LANG = re.compile(r"<html\b[^>]*\blang\s*=\s*[\"']?([a-z]{2,3})", re.IGNORECASE)
_META = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_RATING_NAME = re.compile(r"\bname\s*=\s*[\"']?rating\b")
_ADULT_VALUE = re.compile(r"\b(?:adult|mature|rta-5042)")
# Letters only Vietnamese uses; shared accents such as "é" say nothing.
_VIETNAMESE = frozenset(
    "ăđơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ"
)


@dataclass(frozen=True)
class Document:
    text: str
    lang: str  # "vi", "en", another ISO code, or "other"
    published: date | None = None
    minutes: int | None = None
    transcript: bool = True  # readable text beyond a title and description
    adult: bool = False  # the page labels itself adult (RTA / rating meta)


def collapse(value: str) -> str:
    return _SPACE.sub(" ", value).strip()


def detect_language(text: str) -> str:
    """``vi``, ``en`` or ``other`` from the letters alone.

    shortcut: any mostly-ASCII Latin text reads as "en"; add a language-ID
    model if users allow languages beyond vi/en.
    """
    letters = [char for char in text.casefold() if char.isalpha()]
    if not letters:
        return "other"
    if sum(char in _VIETNAMESE for char in letters) >= 0.01 * len(letters):
        return "vi"
    if sum(char.isascii() for char in letters) >= 0.9 * len(letters):
        return "en"
    return "other"


def _is_adult(html: str) -> bool:
    return any(
        _RATING_NAME.search(tag) and _ADULT_VALUE.search(tag)
        for tag in (tag.casefold() for tag in _META.findall(html))
    )


def _minutes(text: str) -> int:
    return max(1, math.ceil(len(text.split()) / WORDS_PER_MINUTE))


def read_document(candidate: Candidate, fetched: FetchResult) -> Document:
    """Readable text of a page that passed the fetch; empty text when there is none."""
    if candidate.kind.casefold() == "video":
        # shortcut: title + description only; add captions once a captions API key exists.
        text = collapse(f"{candidate.title}. {candidate.snippet}")
        return Document(text, detect_language(text), transcript=False)

    content_type = fetched.content_type.casefold()
    if content_type.startswith(PDF):
        try:
            text = collapse(" ".join(extract_pages(fetched.body, PDF)))
        except InvalidDocument:
            text = ""
        return Document(text, detect_language(text), minutes=_minutes(text))
    if content_type.startswith("text/plain"):
        text = collapse(fetched.text)
        return Document(text, detect_language(text), minutes=_minutes(text))
    if "html" not in content_type:
        return Document("", "other")

    html = fetched.text
    extracted = trafilatura.bare_extraction(
        html,
        url=fetched.final_url or fetched.url,
        with_metadata=True,
        # Freshness is about the last update: a wiki page from 2006 may be edited weekly.
        date_extraction_params={"original_date": False, "extensive_search": True},
    )
    text = collapse(extracted.text or "") if extracted else ""
    declared = _HTML_LANG.search(html)
    return Document(
        text,
        declared.group(1).casefold() if declared else detect_language(text),
        published=_date(extracted.date if extracted else None),
        minutes=_minutes(text),
        adult=_is_adult(html),
    )


def readable_pages(fetched: FetchResult) -> list[str]:
    """The text of each page with its line breaks, where numbered exercises start.

    Unlike ``read_document`` nothing is collapsed: "Exercise 2.3" is found at the
    start of a line.
    """
    content_type = fetched.content_type.casefold()
    if content_type.startswith(PDF):
        try:
            return extract_pages(fetched.body, PDF)
        except InvalidDocument:
            return []
    if content_type.startswith("text/plain"):
        return [fetched.text]
    if "html" in content_type:
        text = trafilatura.extract(fetched.text, url=fetched.final_url or fetched.url)
        return [text] if text else []
    return []


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value[:10]) if value else None
    except ValueError:
        return None
