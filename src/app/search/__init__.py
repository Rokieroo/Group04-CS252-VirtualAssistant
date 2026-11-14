"""Resource search: provider abstraction, PII filtering, and orchestration (spec 11).

The open providers backed by the source registry (``app.search.openalex``,
``app.search.openstax``, ``app.search.wikipedia``) are imported from their own
modules: they depend on ``app.catalog``, whose import chain reaches this package.
"""

from __future__ import annotations

from app.search.base import Candidate, SearchProvider
from app.search.catalog import CatalogProvider, CatalogSearch
from app.search.fake import FakeSearch
from app.search.pii_filter import contains_pii, filter_pii, strip_pii
from app.search.service import (
    SearchRunRecord,
    SearchService,
    canonical_url,
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
    "canonical_url",
    "contains_pii",
    "filter_pii",
    "generate_queries",
    "node_signature",
    "record_search_run",
    "search",
    "strip_pii",
]
