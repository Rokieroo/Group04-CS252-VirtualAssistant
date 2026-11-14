"""Open search providers (#157): recorded payloads only, no network in CI.

Payloads are trimmed copies of real responses (2026-11-14). Every provider must
drop results without a URL or a license registered for it in catalog_sources.yaml.
"""

from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from app.catalog.sources import load_sources
from app.search import SearchService
from app.search.openalex import OpenAlexSearch, abstract
from app.search.openstax import OpenStaxSearch
from app.search.wikipedia import WikibooksSearch, WikipediaSearch


class Response:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.org")
            raise httpx.HTTPStatusError(
                "error", request=request, response=httpx.Response(self.status_code, request=request)
            )

    def json(self):
        return self.payload


class Client:
    """Answers with the queued replies in order (the last one repeats); exceptions are raised."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[tuple[str, dict, dict]] = []

    def get(self, url, *, headers=None):
        parsed = httpx.URL(url)
        endpoint = str(parsed.copy_with(query=None))
        self.calls.append((endpoint, dict(parsed.params.multi_items()), headers or {}))
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, Response) else Response(reply)


def location(license_, url="https://zenodo.org/record/6502327"):
    return {
        "landing_page_url": url,
        "pdf_url": url,
        "license": license_,
        "source": {
            "display_name": "Zenodo",
            "host_organization_name": "European Organization for Nuclear Research",
        },
    }


OPENALEX = {
    "results": [
        {
            "title": "GRAPH ALGORITHMS",
            "type": "conference-paper",
            "language": "en",
            "best_oa_location": location("cc-by"),
            "abstract_inverted_index": {"Graphs": [0], "are": [1], "everywhere": [2]},
        },
        {
            "title": "Open Data Structures",
            "type": "book",
            "language": "en",
            "best_oa_location": location("cc-by-sa", "https://opendatastructures.org/"),
        },
        # Each of these must be dropped.
        {"title": "No license", "type": "article", "best_oa_location": location(None, "https://a.org/1")},
        {"title": "NC-ND", "type": "article", "best_oa_location": location("cc-by-nc-nd", "https://a.org/2")},
        {"title": "Other OA", "type": "article", "best_oa_location": location("other-oa", "https://a.org/3")},
        {"title": "No open copy", "type": "article", "best_oa_location": None},
    ]
}

WIKI = {
    "query": {
        "search": [
            {"title": "Cây nhị phân", "snippet": 'Trong khoa học máy tính, <span class="searchmatch">cây</span> nhị phân'},
            {"title": "Cây tìm kiếm nhị phân", "snippet": "cấu trúc dữ liệu"},
        ]
    }
}

OPENSTAX = {
    "meta": {"total_count": 3},
    "items": [
        {
            "id": 74,
            "meta": {"html_url": "https://openstax.org/details/books/calculus-volume-1", "locale": "en"},
            "title": "Calculus Volume 1",
            "book_state": "live",
            "license_name": "Creative Commons Attribution-NonCommercial-ShareAlike License",
            "license_version": "4.0",
            "description": "<p>Calculus is designed for the typical two- or three-semester course.</p>",
        },
        {
            "id": 1,
            "meta": {"html_url": "https://openstax.org/details/books/old-calculus", "locale": "en"},
            "title": "Old Calculus",
            "book_state": "retired",
            "license_name": "Creative Commons Attribution License",
            "license_version": "4.0",
        },
        {
            "id": 2,
            "meta": {"html_url": "https://openstax.org/details/books/unknown", "locale": "en"},
            "title": "No License Calculus",
            "book_state": "live",
            "license_name": "",
            "license_version": "",
        },
    ],
}


def no_backoff(provider):
    provider.backoff = 0
    return provider


def test_openalex_keeps_only_registered_licenses_of_the_open_copy():
    client = Client(OPENALEX)
    results = OpenAlexSearch(client=client).search("graph algorithms", lang="en")

    assert [r.title for r in results] == ["GRAPH ALGORITHMS", "Open Data Structures"]
    paper, book = results
    assert (paper.license, paper.kind, paper.url) == ("CC-BY-4.0", "article", "https://zenodo.org/record/6502327")
    assert paper.institution == "European Organization for Nuclear Research"
    assert paper.snippet == "Graphs are everywhere"
    assert (book.license, book.kind) == ("CC-BY-SA-4.0", "book")
    url, params, headers = client.calls[0]
    assert url == "https://api.openalex.org/works"
    assert params["filter"].startswith("is_oa:true,best_oa_location.license:")
    assert "cc-by-nc-nd" not in params["filter"].split(":")[-1].split("|")
    assert "github.com" in headers["User-Agent"]


def test_openalex_abstract_is_rebuilt_in_word_order():
    assert abstract({"b": [1], "a": [0, 2]}) == "a b a"
    assert abstract(None) == ""


@pytest.mark.parametrize("provider_class, site", [(WikipediaSearch, "wikipedia"), (WikibooksSearch, "wikibooks")])
def test_mediawiki_links_the_learners_language(provider_class, site):
    client = Client(WIKI)
    results = provider_class(client=client).search("cây nhị phân", lang="vi")

    assert client.calls[0][0] == f"https://vi.{site}.org/w/api.php"
    assert results[0].url == f"https://vi.{site}.org/wiki/C%C3%A2y_nh%E1%BB%8B_ph%C3%A2n"
    assert results[0].snippet == "Trong khoa học máy tính, cây nhị phân"
    assert {(r.license, r.lang, r.institution) for r in results} == {
        ("CC-BY-SA-4.0", "vi", "Wikimedia Foundation")
    }
    provider_class(client=client).search("binary tree", lang="en")
    assert client.calls[1][0] == f"https://en.{site}.org/w/api.php"


def test_openstax_shares_the_catalog_connectors_book_rules():
    client = Client(OPENSTAX)
    results = OpenStaxSearch(client=client).search("calculus", lang="en")

    assert [(r.title, r.license) for r in results] == [("Calculus Volume 1", "CC-BY-NC-SA-4.0")]
    assert results[0].snippet.startswith("Calculus is designed")
    url, params, _ = client.calls[0]
    assert url == "https://openstax.org/apps/cms/api/v2/pages/"
    # The registry endpoint's filters survive next to the search parameters.
    registry = dict(httpx.URL(load_sources().providers["openstax"].endpoint).params.multi_items())
    assert params == {**registry, "search": "calculus", "limit": "5"}


@pytest.mark.parametrize(
    "provider_class, payload",
    [(OpenAlexSearch, OPENALEX), (WikipediaSearch, WIKI), (WikibooksSearch, WIKI), (OpenStaxSearch, OPENSTAX)],
)
def test_no_result_lacks_a_license_or_url(provider_class, payload):
    provider = provider_class(client=Client(payload))
    results = provider.search("anything", lang="en")
    licenses = provider.registry.licenses

    assert results
    assert all(r.url.startswith("https://") and r.license in licenses for r in results)
    assert all(len(r.snippet) <= 300 for r in results)


def test_unsupported_kind_and_blank_query_make_no_request():
    client = Client(WIKI)
    assert WikipediaSearch(client=client).search("tree", kind="video") == []
    assert OpenStaxSearch(client=client).search("tree", kind="article") == []
    assert WikipediaSearch(client=client).search("   ") == []
    assert client.calls == []


def test_transient_failures_are_retried_then_succeed():
    client = Client(httpx.ConnectTimeout("slow"), Response({}, status=503), WIKI)
    provider = no_backoff(WikipediaSearch(client=client))

    assert len(provider.search("tree", lang="en")) == 2
    assert provider.last_error is None
    assert len(client.calls) == 3


@pytest.mark.parametrize(
    "reply, error, calls",
    [
        (httpx.ConnectError("down"), "network", 3),
        (Response({}, status=404), "http_404", 1),  # not transient: no retry
        ({"unexpected": True}, "KeyError", 1),
    ],
)
def test_failures_end_empty_with_a_secret_free_label(reply, error, calls):
    client = Client(reply)
    provider = no_backoff(OpenAlexSearch(client=client))

    assert provider.search("tree") == []
    assert provider.last_error == error
    assert len(client.calls) == calls


def test_a_provider_whose_terms_forbid_automation_cannot_be_built():
    sources = load_sources()
    locked = replace(sources.providers["wikipedia"], automated=False)
    forbidden = replace(sources, providers={**sources.providers, "wikipedia": locked})

    with pytest.raises(ValueError, match="not_automatable_wikipedia"):
        WikipediaSearch(sources=forbidden)


def test_service_logs_one_free_run_per_query_and_provider():
    runs = []
    providers = [
        OpenAlexSearch(client=Client(OPENALEX)),
        WikipediaSearch(client=Client(WIKI)),
        no_backoff(OpenStaxSearch(client=Client(httpx.ConnectError("down")))),
    ]
    service = SearchService(providers=providers, max_results=10)

    results = service.search(queries=["graph algorithms"], lang="en", record_run=runs.append)

    assert {r.provider for r in results} == {"openalex_works", "wikipedia"}
    assert [(r.provider, r.status, r.cost_usd) for r in runs] == [
        ("openalex_works", "ok", 0.0),
        ("wikipedia", "ok", 0.0),
        ("openstax", "error", 0.0),
    ]
    assert service.last_errors == {"openstax": "network"}
