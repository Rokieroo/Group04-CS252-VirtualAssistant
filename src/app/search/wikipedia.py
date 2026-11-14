"""Wikipedia and Wikibooks through the MediaWiki Action API, in Vietnamese or English
(#157, ADR 004 ``wikipedia`` and ``wikibooks``).

Wikibooks stands in for Khan Academy, whose terms forbid automated access (ADR 004
section 2): open textbooks with exercises, behind a public API, under CC BY-SA.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import quote

from app.search.base import Candidate
from app.search.http import plain_text
from app.search.open_api import OpenApiSearch


def wiki_lang(lang: str) -> str:
    return "vi" if lang.casefold().startswith("vi") else "en"


class MediaWikiSearch(OpenApiSearch):
    """One Wikimedia project; ``name`` is both its host name and its registry id."""

    publisher = "Wikimedia Foundation"

    @property
    def kind(self) -> str:
        (only,) = self.kinds
        return only

    def _site(self, lang: str) -> str:
        return f"https://{wiki_lang(lang)}.{self.name}.org"

    def request(self, query: str, lang: str) -> tuple[str, dict[str, Any]]:
        return f"{self._site(lang)}/w/api.php", {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": self.max_results,
            "format": "json",
            "utf8": 1,
        }

    def candidates(self, payload: Any, lang: str) -> Iterable[Candidate]:
        for item in payload["query"]["search"]:
            title = plain_text(item.get("title"))
            yield Candidate(
                url=f"{self._site(lang)}/wiki/{quote(title.replace(' ', '_'))}",
                title=title,
                provider=self.name,
                kind=self.kind,
                lang=wiki_lang(lang),
                snippet=plain_text(item.get("snippet")),
                license=self.registry.licenses[0],
                institution=self.publisher,
            )


class WikipediaSearch(MediaWikiSearch):
    name = "wikipedia"
    kinds = frozenset({"article"})


class WikibooksSearch(MediaWikiSearch):
    name = "wikibooks"
    kinds = frozenset({"book"})


WikipediaProvider = WikipediaSearch
WikibooksProvider = WikibooksSearch

__all__ = [
    "MediaWikiSearch",
    "WikibooksProvider",
    "WikibooksSearch",
    "WikipediaProvider",
    "WikipediaSearch",
    "wiki_lang",
]
