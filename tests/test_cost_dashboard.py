"""Issue #69: every resource search is logged with its cost, and admins see it per node."""

import json
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from app.finder import find_resources
from app.llm import FakeLLM, LLMClient, LLMResult, MeteredLLM
from app.search import Candidate, FakeSearch, SearchService
from app.vetting import Learner, Node, SafeFetcher
from assistant.backend import jobs, resources
from assistant.backend.models import (
    Course,
    Job,
    LearningOutcome,
    NodeResource,
    ResourceSearch,
    Roadmap,
    RoadmapNode,
    SearchRun,
    Syllabus,
    User,
)

NOW = datetime(2030, 1, 7, tzinfo=UTC)
QUOTE = "Every recursive function needs a base case that stops the calls."
PAGE = (
    "<html lang='en'><body><article><h1>Recursion</h1>"
    f"<p>Recursion is when a function calls itself. {QUOTE}</p>"
    "<p>Worked example: factorial(n) returns n * factorial(n - 1).</p>"
    "</article></body></html>"
)
VERDICT = json.dumps({"relevance": 4, "level_fit": 4, "pedagogy": 3,
                      "evidence_quote": QUOTE, "reason": "Bao phủ CLO1."})
URLS = [f"https://site{i}.edu/recursion" for i in range(3)]


class PricedLLM(LLMClient):
    """A judge that bills one cent per call."""

    def complete(self, prompt, **options):
        return LLMResult(VERDICT, 100, 20, 0.01)


def web(urls, *, error=None):
    provider = FakeSearch(
        [Candidate(url, "Recursion", "web", "article", "en") for url in urls],
        error=error, name="web",
    )
    provider.cost_per_call = 0.001
    return provider


def fetcher():
    def reply(request):
        host = request.headers["host"]
        return httpx.Response(200, html=PAGE.replace("Recursion is", f"{host}: recursion is"))

    return SafeFetcher(resolver=lambda host, port: ["93.184.216.34"],
                       transport=httpx.MockTransport(reply))


def test_metered_llm_adds_up_calls_tokens_and_cost():
    meter = MeteredLLM(PricedLLM())
    meter.complete("a")
    meter.complete("b")
    assert (meter.calls, meter.input_tokens, meter.output_tokens) == (2, 200, 40)
    assert meter.cost_usd == pytest.approx(0.02)
    assert FakeLLM().complete("x").cost_usd == 0.0


def test_search_runs_carry_latency_and_bill_only_answered_calls():
    service = SearchService([web(URLS), web([], error=RuntimeError("quota"))])
    service.search(queries=["recursion"])
    answered, failed = service.last_runs
    assert answered.cost_usd == 0.001 and answered.latency_ms >= 0
    assert failed.status == "error" and failed.cost_usd == 0.0


def test_find_resources_reports_what_the_search_did_and_spent():
    with fetcher() as shared:
        found = find_resources(
            Node("Recursion", ("CLO1: base cases",)),
            Learner(),
            search=SearchService([web(URLS)]),
            llm=PricedLLM(),
            fetcher=shared,
        )
    stats = found.stats
    assert stats.queries == 5 and stats.candidates == 3
    assert stats.vetted == 3 and stats.kept == len(found.curation.resources) == 3
    assert stats.llm_calls == 3 and stats.llm_cost_usd == pytest.approx(0.03)
    assert stats.search_cost_usd == pytest.approx(5 * 0.001)  # one call per query
    assert len(stats.runs) == 5


# --- the job and the dashboard ------------------------------------------------------


@pytest.fixture
def sessions(app, client):
    return app.state.database.sessions


@pytest.fixture
def pipeline(monkeypatch):
    monkeypatch.setattr(resources, "make_search", lambda: SearchService([web(URLS)]))
    monkeypatch.setattr(resources, "make_llm", PricedLLM)
    monkeypatch.setattr(resources, "make_fetcher", fetcher)


@pytest.fixture
def user_id(client, headers):
    return client.get("/api/v1/me", headers=headers).json()["id"]


def add_node(sessions, user_id, title="Recursion"):
    with sessions() as db:
        course = Course(owner_id=user_id, title="CS252", level="university", language="en")
        db.add(course)
        db.flush()
        syllabus = Syllabus(course_id=course.id, raw_text="")
        db.add(syllabus)
        db.flush()
        db.add(LearningOutcome(syllabus_id=syllabus.id, code="CLO1",
                               description="Write recursive functions with a base case"))
        roadmap = Roadmap(course_id=course.id, user_id=user_id, title="CS252")
        db.add(roadmap)
        db.flush()
        node = RoadmapNode(roadmap_id=roadmap.id, type="topic", title=title,
                           duration_minutes=60)
        db.add(node)
        db.commit()
        return node.id


def run_search(sessions, node_id, user_id):
    with sessions() as db:
        job = jobs.enqueue(db, "search_resources", {"node_id": node_id}, now=NOW,
                           user_id=user_id)
        db.commit()
        job_id = job.id
    assert jobs.run_once(sessions, NOW) == job_id
    with sessions() as db:
        job = db.get(Job, job_id)
        assert job.status == "done", job.error
        return json.loads(job.result)


def make_admin(sessions, user_id):
    with sessions() as db:
        db.get(User, user_id).role = "admin"
        db.commit()


def test_search_job_logs_the_search_and_its_provider_calls(sessions, user_id, pipeline):
    node_id = add_node(sessions, user_id)
    result = run_search(sessions, node_id, user_id)
    assert result["status"] == "ready" and result["shown"] == 3
    assert result["cost_usd"] == pytest.approx(0.03 + 0.005)
    with sessions() as db:
        [search] = db.scalars(select(ResourceSearch)).all()
        assert (search.node_id, search.cache_hit, search.kept) == (node_id, 0, 3)
        assert (search.queries, search.candidates, search.llm_calls) == (5, 3, 3)
        runs = db.scalars(select(SearchRun)).all()
        assert len(runs) == 5 and {run.search_id for run in runs} == {search.id}
        assert sum(run.cost_usd for run in runs) == pytest.approx(0.005)
        shown = db.scalars(select(NodeResource).where(NodeResource.node_id == node_id)).all()
        assert len(shown) == 3


def test_same_node_signature_is_served_from_cache_at_no_cost(sessions, user_id, pipeline,
                                                            monkeypatch):
    run_search(sessions, add_node(sessions, user_id), user_id)
    monkeypatch.setattr(resources, "make_llm", lambda: pytest.fail("cache must be used"))
    second = run_search(sessions, add_node(sessions, user_id), user_id)
    assert second["cache_hit"] is True and second["cost_usd"] == 0
    assert second["shown"] == 3


def test_deleted_node_finishes_without_searching(sessions, user_id, pipeline):
    assert run_search(sessions, "missing-node", user_id) == {"status": "node_deleted"}


def test_dashboard_is_admin_only(client, headers):
    assert client.get("/api/v1/admin/costs", headers=headers).status_code == 403
    assert client.get("/api/v1/admin/costs").status_code == 401


def test_dashboard_shows_cost_per_node_and_provider_latency(sessions, client, headers,
                                                            user_id, pipeline):
    run_search(sessions, add_node(sessions, user_id), user_id)
    run_search(sessions, add_node(sessions, user_id), user_id)  # cache hit
    make_admin(sessions, user_id)

    report = client.get("/api/v1/admin/costs?days=7", headers=headers).json()
    totals = report["totals"]
    assert (totals["searches"], totals["cache_hits"], totals["llm_calls"]) == (2, 1, 3)
    assert totals["llm_calls_today"] == 3
    assert totals["cost_usd"] == pytest.approx(0.035)
    assert totals["cost_per_search_usd"] == pytest.approx(0.0175)
    first, second = report["nodes"]
    assert first["cost_usd"] == pytest.approx(0.035) and second["cost_usd"] == 0
    assert first["node_title"] == "Recursion"
    [provider] = report["providers"]
    assert provider["provider"] == "web" and provider["calls"] == provider["calls_today"] == 5
    assert provider["cost_usd"] == pytest.approx(0.005)
    [day] = report["daily"]
    assert day["day"] == "2030-01-07" and day["searches"] == 2


def test_dashboard_window_is_validated(sessions, client, headers, user_id):
    make_admin(sessions, user_id)
    assert client.get("/api/v1/admin/costs?days=0", headers=headers).status_code == 422
    empty = client.get("/api/v1/admin/costs", headers=headers).json()
    assert empty["totals"]["searches"] == 0 and empty["nodes"] == []
