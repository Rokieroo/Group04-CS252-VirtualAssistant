"""Issue #155: one recommendation list per node, database first, external only when short."""

from __future__ import annotations

import json

import httpx
import pytest
from conftest import roadmap_with_catalog
from sqlalchemy import select

from app.llm import LLMClient, LLMResult
from app.recommend import VERIFICATION, Feedback, needs_external, recommend
from app.search import Candidate, FakeSearch, SearchService
from app.vetting import Learner, Node, SafeFetcher, ScoredResource
from assistant.backend import jobs, resources
from assistant.backend.models import Job

NODE = Node("Binary Search Trees", ("CLO1: implement ordered search structures",), 60)
LEARNER = Learner(langs=("en", "vi"), level="university")
QUOTE = "A binary search tree keeps every left key smaller than its parent."


def catalog(i, score, *, title="Binary Search Trees", fmt="reading", url=None):
    return {"kind": "catalog", "id": f"r{i}", "title": title, "url": url or f"https://ocw{i}.mit.edu/bst",
            "provider": "mit", "institution": "MIT", "format": fmt, "duration_min": 20,
            "score": score, "reason": "matched"}


def page(url, title="Binary search tree", *, score=0.86, quote=QUOTE, fmt="reading", lang="en"):
    return ScoredResource(url, title, "web", fmt, lang, url.split("/")[2], True, 15, score, {},
                          "judge", quote, "hash", title)


class Spy:
    """An external port that records whether the recommender asked it."""

    def __init__(self, pages=()):
        self.pages, self.calls = list(pages), 0

    def __call__(self):
        self.calls += 1
        return self.pages


# --- the pure recommender ---------------------------------------------------------


def test_three_strong_database_sources_never_ask_outside():
    database = [catalog(i, 0.85) for i in range(3)]
    spy = Spy([page("https://en.wikipedia.org/wiki/BST")])
    shown = recommend(NODE, LEARNER, database=database, external=spy)
    assert spy.calls == 0
    assert {r.kind for r in shown} == {"catalog"}
    assert not needs_external(database)


def test_learners_own_material_does_not_stop_the_search():
    own = {"kind": "user_material", "id": "s1", "title": "week3.pdf", "pages": [4, 5],
           "score": 1.0, "format": "document"}
    assert needs_external([own, catalog(1, 0.9), catalog(2, 0.9)])


def test_short_database_is_filled_with_vetted_external_pages_never_verified():
    database = [catalog(1, 0.85), catalog(2, 0.7)]
    spy = Spy([page("https://en.wikipedia.org/wiki/BST"), page("https://ocw1.mit.edu/bst")])
    shown = recommend(NODE, LEARNER, database=database, external=spy)
    assert spy.calls == 1
    external = [r for r in shown if r.kind == "external"]
    assert [r.url for r in external] == ["https://en.wikipedia.org/wiki/BST"]  # catalog copy wins
    assert all(r.verification_status == "unverified" for r in external)
    assert "chưa xác minh" in external[0].reason


def test_every_recommendation_carries_kind_status_and_a_factual_reason():
    own = {"kind": "user_material", "id": "s1", "title": "BST slides.pdf", "pages": [3, 4],
           "score": 1.0, "format": "document"}
    shown = recommend(NODE, LEARNER, database=[own, catalog(1, 0.85, fmt="video")],
                      external=Spy([page("https://en.wikipedia.org/wiki/BST")]))
    assert shown[0].kind == "user_material"  # own material first, then by final score
    assert sorted(r.kind for r in shown[1:]) == ["catalog", "external"]
    for r in shown:
        assert r.kind in VERIFICATION and r.verification_status == VERIFICATION[r.kind]
        assert r.reason
    by_kind = {r.kind: r for r in shown}
    assert shown[0].reason == "Tài liệu của bạn · trang 3, 4" and shown[0].url is None
    assert by_kind["catalog"].reason == (
        "Khớp “binary”, “search”, “trees” · MIT · video 20 phút · đã xác minh")


def test_external_page_without_grounded_quote_is_never_shown():
    shown = recommend(NODE, LEARNER, database=[],
                      external=Spy([page("https://en.wikipedia.org/wiki/BST", quote="")]))
    assert shown == []


def test_not_helpful_source_is_replaced_and_similar_ones_lose_score():
    database = [catalog(1, 0.85), catalog(2, 0.85, title="Hash Tables"),
                catalog(3, 0.85, title="Binary Search Trees in depth")]
    feedback = Feedback(rejected=frozenset({"r1"}), unhelpful_titles=("Binary Search Trees",))
    shown = recommend(NODE, LEARNER, database=database, external=Spy(), feedback=feedback)
    by_id = {r.source_id: r for r in shown}
    assert "r1" not in by_id
    assert by_id["r2"].score == 0.85  # unlike the unhelpful source: untouched
    assert by_id["r3"].score < 0.85


def test_pages_in_the_learners_first_language_fit_best():
    shown = recommend(NODE, LEARNER, database=[], external=Spy([
        page("https://vi.wikipedia.org/wiki/BST", lang="vi"),
        page("https://en.wikipedia.org/wiki/BST"),
    ]))
    assert [r.url for r in shown] == ["https://en.wikipedia.org/wiki/BST",
                                      "https://vi.wikipedia.org/wiki/BST"]
    assert shown[1].score == round(0.86 * 0.9, 3)


# --- the API and the search job -----------------------------------------------------


class Judge(LLMClient):
    def complete(self, prompt, **options):
        return LLMResult(json.dumps({"relevance": 4, "level_fit": 4, "pedagogy": 4,
                                     "evidence_quote": QUOTE, "reason": "on topic"}), 10, 5, 0.0)


class CountingSearch(FakeSearch):
    calls = 0

    def search(self, *args, **kwargs):
        CountingSearch.calls += 1
        return super().search(*args, **kwargs)


EXTERNAL_URLS = ["https://cs.stanford.edu/bst-notes", "https://berkeley.edu/bst-lab"]


@pytest.fixture
def fake_provider(monkeypatch):
    CountingSearch.calls = 0
    candidates = [Candidate(url, "Binary Search Trees notes", "web", "article", "en",
                            snippet=QUOTE) for url in EXTERNAL_URLS]

    def reply(request):  # one page per URL: vetting drops pages with the same content
        return httpx.Response(200, html=(
            f"<html lang='en'><body><article><h1>Binary Search Trees</h1><p>{QUOTE}</p>"
            f"<p>Worked examples for students at {request.url}.</p></article></body></html>"))

    monkeypatch.setattr(resources, "make_search",
                        lambda: SearchService([CountingSearch(candidates, name="web")]))
    monkeypatch.setattr(resources, "make_llm", Judge)
    monkeypatch.setattr(resources, "make_fetcher", lambda: SafeFetcher(
        resolver=lambda host, port: ["93.184.216.34"], transport=httpx.MockTransport(reply)))
    return CountingSearch


def recommendations(client, headers, node_id):
    response = client.get(f"/api/v1/roadmap-nodes/{node_id}/recommendations", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["recommendations"]


def search_jobs(app):
    with app.state.database.sessions() as db:
        return db.scalars(select(Job).where(Job.kind == "search_resources")).all()


def test_api_serves_catalog_without_any_provider_call(client, headers, app, clock, fake_provider):
    _, node = roadmap_with_catalog(client, headers, app, clock[0], [
        "Binary Search Trees lecture notes", "Binary Search Trees worked examples",
        "Binary Search Trees problem set"])
    shown = recommendations(client, headers, node)
    assert len(shown) == 3
    assert {(r["kind"], r["verification_status"]) for r in shown} == {("catalog", "verified")}
    assert all(r["reason"] and r["title"] and r["url"] for r in shown)
    assert search_jobs(app) == []
    jobs.run_once(app.state.database.sessions, clock[0])
    assert fake_provider.calls == 0


def test_api_searches_once_when_short_and_labels_external_unverified(
    client, headers, app, clock, fake_provider
):
    _, node = roadmap_with_catalog(client, headers, app, clock[0], [])
    assert recommendations(client, headers, node) == []
    assert recommendations(client, headers, node) == []
    assert len(search_jobs(app)) == 1  # once a day per node, however often it is opened

    assert jobs.run_once(app.state.database.sessions, clock[0]) is not None
    assert fake_provider.calls > 0
    shown = recommendations(client, headers, node)  # the new cache entry replaces the list
    assert {r["url"] for r in shown} == set(EXTERNAL_URLS)
    assert {(r["kind"], r["verification_status"]) for r in shown} == {("external", "unverified")}
    assert all("chưa xác minh" in r["reason"] for r in shown)


def test_not_helpful_replaces_the_source_on_the_next_request(client, headers, app, clock):
    _, node = roadmap_with_catalog(client, headers, app, clock[0], [
        f"Binary Search Trees notes, part {i}" for i in range(1, 8)])
    first = recommendations(client, headers, node)
    assert len(first) == 5
    disliked = first[0]
    response = client.post(f"/api/v1/recommendations/{disliked['id']}/events", headers=headers,
                           json={"event": "not_helpful"})
    assert response.status_code == 201
    after = recommendations(client, headers, node)
    assert disliked["resource_ref"] not in {r["resource_ref"] for r in after}
    assert len(after) == len(first)  # the next candidate came up, no new search
    assert search_jobs(app) == []
