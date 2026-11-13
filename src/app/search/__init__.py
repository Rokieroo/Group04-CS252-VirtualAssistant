"""Resource search: provider abstraction, PII filtering, and orchestration (spec 11)."""

from __future__ import annotations

from app.search.base import Candidate, SearchProvider
from app.search.catalog import CatalogProvider, CatalogSearch
from app.search.fake import FakeSearch
from app.search.khan_academy import KhanAcademyProvider, KhanAcademySearch
from app.search.openalex import OpenAlexProvider, OpenAlexSearch
from app.search.openstax import OpenStaxProvider, OpenStaxSearch
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
from app.search.wikipedia import WikipediaProvider, WikipediaSearch
from app.search.youtube import YouTubeProvider, YouTubeSearch

__all__ = [
    "Candidate",
    "CatalogProvider",
    "CatalogSearch",
    "FakeSearch",
    "KhanAcademyProvider",
    "KhanAcademySearch",
    "OpenAlexProvider",
    "OpenAlexSearch",
    "OpenStaxProvider",
    "OpenStaxSearch",
    "SearchProvider",
    "SearchRunRecord",
    "SearchService",
    "WebProvider",
    "WebSearch",
    "WebSearchProvider",
    "WikipediaProvider",
    "WikipediaSearch",
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
