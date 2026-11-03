"""Resource search: provider abstraction, PII filtering, and orchestration (spec 11)."""

from __future__ import annotations

from app.search.base import Candidate, SearchProvider
from app.search.catalog import CatalogProvider, CatalogSearch
from app.search.fake import FakeSearch
from app.search.pii_filter import contains_pii, filter_pii
from app.search.service import (
    SearchRunRecord,
    SearchService,
    generate_queries,
    record_search_run,
    search,
)
from app.search.signature import node_signature
from app.search.web import WebProvider, WebSearch, WebSearchProvider
from app.search.youtube import YouTubeProvider, YouTubeSearch

__all__ = [
    "Candidate",
    "CatalogProvider",
    "CatalogSearch",
    "FakeSearch",
    "SearchProvider",
    "SearchRunRecord",
    "SearchService",
    "WebProvider",
    "WebSearch",
    "WebSearchProvider",
    "YouTubeProvider",
    "YouTubeSearch",
    "contains_pii",
    "filter_pii",
    "generate_queries",
    "node_signature",
    "record_search_run",
    "search",
]
