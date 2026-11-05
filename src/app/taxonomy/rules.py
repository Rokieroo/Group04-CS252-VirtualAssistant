"""The rule stage of tagging: taxonomy terms, course codes and faculty names.

Text is folded first (lowercase, no Vietnamese diacritics, one space between words),
so "Đồ thị" in a syllabus matches the keyword "đồ thị" typed with or without marks.
"""
from __future__ import annotations

import re
import unicodedata

from app.taxonomy.tree import Taxonomy

_NOT_WORD = re.compile(r"[^a-z0-9]+")
# CSC10014, SE 301, 6.006, 6.046J. Uppercase only: "and 2023" is not a course code.
_COURSE_CODE = re.compile(r"\b(?:[A-Z]{2,4} ?\d{3,5}[A-Z]?|\d{1,2}\.\d{2,4}J?)\b")


def fold(text: str) -> str:
    """ "Đồ thị, BFS!" -> "do thi bfs" """
    decomposed = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _NOT_WORD.sub(" ", plain.casefold()).strip()


def find_course_codes(text: str) -> tuple[str, ...]:
    """Course codes written in free text, e.g. a course title "CSC10014 - Problem framing"."""
    return tuple(dict.fromkeys(match.group(0).replace(" ", "") for match in
                               _COURSE_CODE.finditer(text)))


def terms_of(subject) -> set[str]:
    """The folded phrases that identify an entry: its names and keywords."""
    return {term for term in map(fold, (subject.name, subject.name_vi, *subject.keywords)) if term}


class RuleMatcher:
    def __init__(self, taxonomy: Taxonomy):
        self._terms = [(subject.slug, _phrases(terms_of(subject)))
                       for subject in taxonomy if subject.depth != "field"]
        self._codes = [(subject.slug, re.compile("|".join(f"(?:{code})" for code in
                                                          subject.course_codes), re.IGNORECASE))
                       for subject in taxonomy if subject.course_codes]
        self._departments = [(subject.slug, _phrases({fold(name) for name in subject.departments}))
                             for subject in taxonomy if subject.departments]

    def terms(self, text: str) -> dict[str, int]:
        """slug -> distinct terms found. A match inside a longer one is dropped, so
        "binary search tree" names search trees, not binary search."""
        folded = fold(text)
        spans = [(match.start(), match.end(), slug, match.group(1))
                 for slug, pattern in self._terms for match in pattern.finditer(folded)]
        found: dict[str, set[str]] = {}
        for start, end, slug, term in spans:
            inside = any(s <= start and end <= e and (e - s) > (end - start)
                         for s, e, _, _ in spans)
            if not inside:
                found.setdefault(slug, set()).add(term)
        return {slug: len(terms) for slug, terms in found.items()}

    def codes(self, codes: tuple[str, ...]) -> set[str]:
        return {slug for slug, pattern in self._codes for code in codes
                if pattern.fullmatch(code.strip())}

    def departments(self, text: str) -> set[str]:
        folded = fold(text)
        return {slug for slug, pattern in self._departments if pattern.search(folded)}


def _phrases(terms: set[str]) -> re.Pattern:
    """Any of ``terms`` as whole words, longest first, with an optional plural."""
    alternation = "|".join(re.escape(term) for term in sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<![a-z0-9])({alternation})(?:e?s)?(?![a-z0-9])")
