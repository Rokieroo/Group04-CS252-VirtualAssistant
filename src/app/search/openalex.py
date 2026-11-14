"""Open-access papers and books from the OpenAlex works API (#157, ADR 004 ``openalex_works``).

Only the open copy (``best_oa_location``) is linked, under the license OpenAlex
reports for that copy; works without one of the registered licenses are dropped.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.search.base import Candidate
from app.search.http import plain_text
from app.search.open_api import OpenApiSearch

WORKS_URL = "https://api.openalex.org/works"
# OpenAlex license key -> registry id. Keys absent here (cc-by-nc, cc-by-nd,
# cc-by-nc-nd, other-oa, publisher-specific-oa, ...) are never shown.
# shortcut: OpenAlex reports the license family without its version, so 4.0 is
# assumed; read the landing page if a version ever changes what we may show.
LICENSES = {
    "cc0": "CC0-1.0",
    "public-domain": "CC0-1.0",
    "cc-by": "CC-BY-4.0",
    "cc-by-sa": "CC-BY-SA-4.0",
    "cc-by-nc-sa": "CC-BY-NC-SA-4.0",
}
_FIELDS = "id,doi,title,type,language,best_oa_location,abstract_inverted_index"


def abstract(inverted: Any) -> str:
    """OpenAlex ships abstracts as ``{word: [positions]}``."""
    if not isinstance(inverted, dict):
        return ""
    words = {i: word for word, positions in inverted.items() for i in positions or ()}
    return " ".join(words[i] for i in sorted(words))


class OpenAlexSearch(OpenApiSearch):
    name = "openalex_works"
    kinds = frozenset({"article", "book"})

    def request(self, query: str, lang: str) -> tuple[str, dict[str, Any]]:
        # Filter licenses at the API so the free daily budget is not spent on works we drop.
        oa = "is_oa:true,best_oa_location.license:" + "|".join(LICENSES)
        return WORKS_URL, {
            "search": query,
            "filter": oa,
            "per_page": self.max_results,
            "select": _FIELDS,
        }

    def candidates(self, payload: Any, lang: str) -> Iterable[Candidate]:
        for item in payload["results"]:
            location = item.get("best_oa_location") or {}
            source = location.get("source") or {}
            yield Candidate(
                url=plain_text(location.get("landing_page_url") or location.get("pdf_url")),
                title=plain_text(item.get("title")),
                provider=self.name,
                kind="book" if "book" in str(item.get("type")) else "article",
                lang=str(item.get("language") or lang),
                snippet=plain_text(abstract(item.get("abstract_inverted_index"))),
                license=LICENSES.get(str(location.get("license")).casefold(), ""),
                institution=plain_text(
                    source.get("host_organization_name") or source.get("display_name")
                ),
            )


OpenAlexProvider = OpenAlexSearch

__all__ = ["LICENSES", "OpenAlexProvider", "OpenAlexSearch", "abstract"]
