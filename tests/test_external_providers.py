"""Unit and offline integration tests for external search providers (Issue #157).

Tests OpenAlex, Wikipedia, OpenStax, and Khan Academy providers with recorded payloads
to ensure zero network calls during CI, strict license & URL requirements, and error resilience.
"""

from __future__ import annotations

import httpx

from app.search import (
    KhanAcademySearch,
    OpenAlexSearch,
    OpenStaxSearch,
    SearchRunRecord,
    SearchService,
    WikipediaSearch,
)


class MockClient:
    """Mock HTTP client that returns canned responses matching requested endpoints."""

    def __init__(self, handler):
        self.handler = handler

    def get(self, url, params=None, headers=None):
        return self.handler(url, params=params, headers=headers)


# ---------------------------------------------------------------------------
# OpenAlex Tests
# ---------------------------------------------------------------------------

OPENALEX_PAYLOAD = {
    "results": [
        {
            "id": "https://openalex.org/W123456",
            "doi": "https://doi.org/10.1234/test.1",
            "title": "Introduction to Graph Algorithms",
            "type": "article",
            "language": "en",
            "primary_location": {
                "landing_page_url": "https://doi.org/10.1234/test.1",
                "pdf_url": "https://arxiv.org/pdf/1234.pdf",
                "license": "cc-by",
                "source": {
                    "display_name": "Journal of Computer Science",
                    "host_organization_name": "Open Science Publishing",
                },
            },
            "open_access": {"is_oa": True, "oa_status": "gold"},
            "authorships": [
                {"institutions": [{"display_name": "MIT Department of EECS"}]}
            ],
            "abstract_inverted_index": {
                "Graph": [0],
                "algorithms": [1],
                "and": [2],
                "their": [3],
                "applications.": [4],
            },
        },
        {
            "id": "https://openalex.org/W789012",
            "doi": "https://doi.org/10.1234/test.2",
            "title": "Discrete Mathematics for Computing",
            "type": "book",
            "language": "en",
            "primary_location": {
                "landing_page_url": "https://example.org/books/discrete-math",
                "license": "cc-by-nc-sa-4.0",
                "source": {"display_name": "University Open Press"},
            },
            "open_access": {"is_oa": True},
            "concepts": [{"display_name": "Mathematics"}, {"display_name": "Logic"}],
        },
        # Unlicensed work -> MUST BE DROPPED
        {
            "id": "https://openalex.org/W999999",
            "doi": "https://doi.org/10.1234/no-license",
            "title": "Unlicensed Proprietary Paper",
            "primary_location": {
                "landing_page_url": "https://example.org/no-license",
                "license": None,
            },
        },
        # Missing URL work -> MUST BE DROPPED
        {
            "id": "",
            "title": "Paper Without URL",
            "primary_location": {
                "license": "cc-by",
            },
        },
    ]
}


def test_openalex_search_success_and_license_filtering():
    def handler(url, params=None, headers=None):
        assert params.get("search") == "graph algorithms"
        assert params.get("filter") == "is_oa:true"
        req = httpx.Request("GET", url, params=params)
        return httpx.Response(200, json=OPENALEX_PAYLOAD, request=req)

    provider = OpenAlexSearch(client=MockClient(handler), max_results=5)
    candidates = provider.search("graph algorithms")

    assert len(candidates) == 2
    # Verify first candidate
    c1 = candidates[0]
    assert c1.url == "https://doi.org/10.1234/test.1"
    assert c1.title == "Introduction to Graph Algorithms"
    assert c1.provider == "openalex"
    assert c1.license == "CC-BY-4.0"
    assert c1.institution in ("Open Science Publishing", "MIT Department of EECS")
    assert "Graph algorithms and their applications." in c1.snippet
    assert c1.kind == "article"

    # Verify second candidate (book with CC-BY-NC-SA)
    c2 = candidates[1]
    assert c2.url in ("https://doi.org/10.1234/test.2", "https://example.org/books/discrete-math")
    assert c2.license == "CC-BY-NC-SA-4.0"
    assert c2.institution == "University Open Press"
    assert c2.kind == "book"

    # Acceptance criteria: None has missing license or missing url
    assert all(c.license and c.url for c in candidates)


def test_openalex_error_handling_and_empty():
    def fail_handler(url, params=None, headers=None):
        req = httpx.Request("GET", url)
        raise httpx.ConnectError("Connection refused", request=req)

    provider = OpenAlexSearch(client=MockClient(fail_handler))
    assert provider.search("testing") == []
    assert provider.last_error == "network"

    # Empty query
    assert provider.search("") == []
    assert provider.search("   ") == []


# ---------------------------------------------------------------------------
# Wikipedia Tests
# ---------------------------------------------------------------------------

WIKIPEDIA_VI_PAYLOAD = {
    "query": {
        "search": [
            {
                "title": "Thuật toán tìm kiếm theo chiều rộng",
                "pageid": 12345,
                "snippet": '<span class="searchmatch">Thuật</span> <span class="searchmatch">toán</span> tìm kiếm theo chiều rộng (BFS) là một giải thuật duyệt đồ thị.',
            },
            {
                "title": "Đồ thị có hướng",
                "pageid": 67890,
                "snippet": "Trong toán học, một đồ thị có hướng là...",
            },
        ]
    }
}


def test_wikipedia_search_vietnamese_and_english():
    def handler(url, params=None, headers=None):
        assert "vi.wikipedia.org" in url
        assert params.get("action") == "query"
        assert params.get("list") == "search"
        req = httpx.Request("GET", url, params=params)
        return httpx.Response(200, json=WIKIPEDIA_VI_PAYLOAD, request=req)

    provider = WikipediaSearch(client=MockClient(handler), max_results=5)
    candidates = provider.search("thuật toán đồ thị", lang="vi")

    assert len(candidates) == 2
    c1 = candidates[0]
    assert "vi.wikipedia.org/wiki/" in c1.url
    assert c1.title == "Thuật toán tìm kiếm theo chiều rộng"
    assert c1.provider == "wikipedia"
    assert c1.license == "CC-BY-SA-4.0"
    assert c1.institution == "Wikimedia Foundation"
    assert "<span" not in c1.snippet  # HTML stripped
    assert "BFS" in c1.snippet
    assert c1.lang == "vi"

    # Acceptance criteria: None has missing license or missing url
    assert all(c.license and c.url for c in candidates)


def test_wikipedia_error_and_empty():
    def fail_handler(url, params=None, headers=None):
        req = httpx.Request("GET", url)
        return httpx.Response(500, request=req)

    provider = WikipediaSearch(client=MockClient(fail_handler))
    assert provider.search("query") == []
    assert provider.last_error == "http_500"
    assert provider.search("   ") == []


# ---------------------------------------------------------------------------
# OpenStax Tests
# ---------------------------------------------------------------------------

OPENSTAX_PAYLOAD = {
    "meta": {"total_count": 2},
    "items": [
        {
            "id": 101,
            "title": "College Physics 2e",
            "book_state": "live",
            "license_name": "Creative Commons Attribution License",
            "license_version": "4.0",
            "description": "<p>Introductory algebra-based physics textbook covering mechanics and thermodynamics.</p>",
            "meta": {
                "html_url": "https://openstax.org/details/books/college-physics-2e",
                "locale": "en",
            },
        },
        {
            "id": 102,
            "title": "Principles of Management",
            "book_state": "live",
            "license_name": "Creative Commons Attribution-NonCommercial-ShareAlike License",
            "license_version": "4.0",
            "description": "Foundational management topics.",
            "meta": {
                "html_url": "https://openstax.org/details/books/principles-management",
                "locale": "en",
            },
        },
        # Unrecognized license -> MUST BE DROPPED
        {
            "id": 103,
            "title": "Restricted Book",
            "book_state": "live",
            "license_name": "All Rights Reserved",
            "license_version": "1.0",
            "meta": {"html_url": "https://openstax.org/details/books/restricted"},
        },
        # Deprecated book -> MUST BE DROPPED
        {
            "id": 104,
            "title": "Deprecated Physics 1e",
            "book_state": "deprecated",
            "license_name": "Creative Commons Attribution License",
            "license_version": "4.0",
            "meta": {"html_url": "https://openstax.org/details/books/deprecated"},
        },
    ],
}


def test_openstax_search_books_and_license_filtering():
    def handler(url, params=None, headers=None):
        assert params.get("type") == "books.Book"
        assert params.get("search") == "physics"
        req = httpx.Request("GET", url, params=params)
        return httpx.Response(200, json=OPENSTAX_PAYLOAD, request=req)

    provider = OpenStaxSearch(client=MockClient(handler))
    candidates = provider.search("physics")

    assert len(candidates) == 2
    c1 = candidates[0]
    assert c1.url == "https://openstax.org/details/books/college-physics-2e"
    assert c1.title == "College Physics 2e"
    assert c1.provider == "openstax"
    assert c1.kind == "book"
    assert c1.license == "CC-BY-4.0"
    assert c1.institution == "OpenStax (Rice University)"
    assert "<p>" not in c1.snippet

    c2 = candidates[1]
    assert c2.license == "CC-BY-NC-SA-4.0"

    # Acceptance criteria: None has missing license or missing url
    assert all(c.license and c.url for c in candidates)


# ---------------------------------------------------------------------------
# Khan Academy Tests
# ---------------------------------------------------------------------------

KHAN_PAYLOAD = {
    "items": [
        {
            "title": "Algorithms: Graph Representation",
            "ka_url": "/computing/computer-science/algorithms/graph-representation",
            "description": "Learn how graphs are represented using adjacency matrices and lists.",
            "kind": "article",
        },
        {
            "title": "Breadth-First Search (BFS) Video",
            "url": "https://www.khanacademy.org/computing/computer-science/algorithms/breadth-first-search/v/bfs",
            "description": "Visualizing BFS step by step.",
            "kind": "video",
        },
        # Item with no url -> MUST BE DROPPED
        {
            "title": "Broken Item",
            "url": "",
        },
    ]
}


def test_khan_academy_search():
    def handler(url, params=None, headers=None):
        assert params.get("query") == "algorithms"
        req = httpx.Request("GET", url, params=params)
        return httpx.Response(200, json=KHAN_PAYLOAD, request=req)

    provider = KhanAcademySearch(client=MockClient(handler))
    candidates = provider.search("algorithms")

    assert len(candidates) == 2
    c1 = candidates[0]
    assert c1.url == "https://www.khanacademy.org/computing/computer-science/algorithms/graph-representation"
    assert c1.title == "Algorithms: Graph Representation"
    assert c1.provider == "khan_academy"
    assert c1.kind == "article"
    assert c1.license == "CC-BY-NC-SA-4.0"
    assert c1.institution == "Khan Academy"

    c2 = candidates[1]
    assert c2.url.startswith("https://www.khanacademy.org")
    assert c2.kind == "video"
    assert c2.license == "CC-BY-NC-SA-4.0"

    # Acceptance criteria: None has missing license or missing url
    assert all(c.license and c.url for c in candidates)


# ---------------------------------------------------------------------------
# Integration with SearchService
# ---------------------------------------------------------------------------

def test_search_service_orchestration_with_new_providers():
    def alex_handler(url, params=None, headers=None):
        return httpx.Response(200, json=OPENALEX_PAYLOAD, request=httpx.Request("GET", url))

    def wiki_handler(url, params=None, headers=None):
        return httpx.Response(200, json=WIKIPEDIA_VI_PAYLOAD, request=httpx.Request("GET", url))

    def stax_handler(url, params=None, headers=None):
        return httpx.Response(200, json=OPENSTAX_PAYLOAD, request=httpx.Request("GET", url))

    def khan_handler(url, params=None, headers=None):
        return httpx.Response(200, json=KHAN_PAYLOAD, request=httpx.Request("GET", url))

    providers = [
        OpenAlexSearch(client=MockClient(alex_handler)),
        WikipediaSearch(client=MockClient(wiki_handler)),
        OpenStaxSearch(client=MockClient(stax_handler)),
        KhanAcademySearch(client=MockClient(khan_handler)),
    ]

    recorded_runs: list[SearchRunRecord] = []
    service = SearchService(providers=providers, max_results=20)
    results = service.search(
        query="graph algorithms",
        record_run=lambda rec: recorded_runs.append(rec),
    )

    assert len(results) > 0
    # Every returned candidate must have valid license and url
    for candidate in results:
        assert candidate.url.startswith("http")
        assert candidate.license in ("CC-BY-4.0", "CC-BY-NC-SA-4.0", "CC-BY-SA-4.0")
        assert candidate.provider in ("openalex", "wikipedia", "openstax", "khan_academy")
        assert candidate.institution

    # Verify search_runs were recorded for all providers
    recorded_providers = {r.provider for r in recorded_runs}
    assert recorded_providers == {"openalex", "wikipedia", "openstax", "khan_academy"}
    for run in recorded_runs:
        assert run.status == "ok"
        assert run.results_count > 0
        assert run.cost_usd == 0.0
