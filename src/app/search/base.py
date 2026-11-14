"""The one interface every search provider implements (spec 11.1-11.2)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

__all__ = ["Candidate", "SearchProvider"]


@dataclass
class Candidate:
    """A raw resource a provider found, before vetting or scoring."""

    url: str
    title: str
    provider: str
    kind: str
    lang: str
    snippet: str = ""
    license: str = ""  # a license id of catalog_sources.yaml; "" when unknown
    institution: str = ""  # publisher or host institution


class SearchProvider(ABC):
    """A source of candidate URLs.

    Providers are deliberately small: they receive an already PII-filtered
    query and return candidates.  They must not raise for network, key, or
    quota failures; the search service additionally guards every call so one
    broken vendor can never break the whole resource-finder flow.
    """

    name = "search"
    cost_per_call = 0.0  # USD per answered request, for the cost dashboard

    @abstractmethod
    def search(
        self,
        query: str,
        *,
        lang: str = "vi",
        kind: str | None = None,
        safe: bool = True,
    ) -> list[Candidate]:
        """Return candidates for ``query``.

        ``safe`` is passed through to providers that support SafeSearch (it is
        required for K-12 users).  ``kind`` is a soft filter such as ``video``
        or ``article``.
        """
