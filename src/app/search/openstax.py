"""Live OpenStax books matching a query (#157, ADR 004 ``openstax``).

Books are read by the catalog connector's :func:`~app.catalog.connectors.openstax.book`,
so search and the catalog share one license table and one rule for retired books.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.catalog.connectors.openstax import book
from app.search.base import Candidate
from app.search.open_api import OpenApiSearch


class OpenStaxSearch(OpenApiSearch):
    name = "openstax"
    kinds = frozenset({"book"})
    publisher = "OpenStax, Rice University"

    def request(self, query: str, lang: str) -> tuple[str, dict[str, Any]]:
        # The registry endpoint already selects books and the fields `book` reads.
        return str(self.registry.endpoint), {"search": query, "limit": self.max_results}

    def candidates(self, payload: Any, lang: str) -> Iterable[Candidate]:
        for item in payload["items"]:
            record = book(self.registry, item, str(self.registry.endpoint))
            if record is None:
                continue
            yield Candidate(
                url=record.url,
                title=record.title,
                provider=self.name,
                kind="book",
                lang=record.language,
                snippet=record.description,
                license=record.license or "",
                institution=self.publisher,
            )


OpenStaxProvider = OpenStaxSearch

__all__ = ["OpenStaxProvider", "OpenStaxSearch"]
