"""Offline search provider for tests: deterministic, no network, no cost."""

from __future__ import annotations

from app.search.base import Candidate, SearchProvider

__all__ = ["FakeSearch"]


class FakeSearch(SearchProvider):
    """Return a fixed candidate list and remember every query it receives.

    ``error`` lets a test simulate an external provider that is down or over
    quota.  The real service must keep working when this raises.
    """

    name = "fake"

    def __init__(
        self,
        candidates: list[Candidate] | None = None,
        *,
        error: Exception | None = None,
        name: str | None = None,
    ):
        self.candidates = list(
            candidates
            if candidates is not None
            else [
                Candidate(
                    url="https://example.test/fake-article",
                    title="Fake lecture notes",
                    provider="fake",
                    kind="article",
                    lang="en",
                    snippet="Offline fixture for unit tests.",
                ),
                Candidate(
                    url="https://example.test/fake-video",
                    title="Fake lecture video",
                    provider="fake",
                    kind="video",
                    lang="vi",
                    snippet="Offline fixture for unit tests.",
                ),
            ]
        )
        self.error = error
        self.name = name or type(self).name
        self.calls = 0
        self.queries: list[str] = []
        self.last_error: str | None = None

    def search(
        self,
        query: str,
        *,
        lang: str = "vi",
        kind: str | None = None,
        safe: bool = True,
    ) -> list[Candidate]:
        self.calls += 1
        self.queries.append(query)
        if self.error is not None:
            self.last_error = type(self.error).__name__
            raise self.error
        self.last_error = None
        matches = [
            candidate
            for candidate in self.candidates
            if not kind or candidate.kind == kind
        ]
        # Prefer the requested language without hiding useful cross-language
        # fixtures, mirroring how the catalog behaves.
        return sorted(matches, key=lambda item: item.lang != lang)
