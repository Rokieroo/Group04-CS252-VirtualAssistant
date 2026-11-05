"""Tests for Resource search, feedback and roadmap replan APIs (Issue #65, spec 8.4-8.7, 10.5)."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.llm import LLMClient, LLMResult
from app.search import Candidate, FakeSearch, SearchService
from app.vetting import SafeFetcher
from assistant.backend import jobs, resources
from assistant.backend.models import (
    Course,
    Job,
    LearningOutcome,
    NodeResource,
    ResourceFeedback,
    Roadmap,
    RoadmapNode,
    ScheduleEntry,
    Syllabus,
    Task,
)

NOW = datetime(2030, 1, 7, 10, 0, tzinfo=UTC)
QUOTE_1 = "Base case is essential in recursive problem solving."
QUOTE_2 = "Recursive step calls the function with smaller inputs."
QUOTE_3 = "Tail recursion can be optimized by some modern compilers."

PAGE_TEMPLATE = """
<html lang="en"><body><article>
<h1>{title}</h1>
<p>{quote}</p>
<p>Detailed discussion and worked examples for computer science students. Unique for {url}.</p>
</article></body></html>
"""

URLS = [
    "https://ocw.mit.edu/recursion-base",
    "https://cs.stanford.edu/recursion-step",
    "https://berkeley.edu/tail-recursion",
]


class MockJudgeLLM(LLMClient):
    def complete(self, prompt, **options):
        for quote in (QUOTE_1, QUOTE_2, QUOTE_3):
            if quote in prompt:
                return LLMResult(
                    json.dumps(
                        {
                            "relevance": 4,
                            "level_fit": 4,
                            "pedagogy": 4,
                            "evidence_quote": quote,
                            "reason": f"Matches CLO1: {quote}",
                        }
                    ),
                    100,
                    20,
                    0.005,
                )
        return LLMResult(
            json.dumps(
                {
                    "relevance": 4,
                    "level_fit": 4,
                    "pedagogy": 4,
                    "evidence_quote": QUOTE_1,
                    "reason": "Recursion fundamentals",
                }
            ),
            100,
            20,
            0.005,
        )


class ModerateJudgeLLM(LLMClient):
    """Scores around 0.705 (between threshold 0.65 and strong 0.8), allowing reserve pools."""

    def complete(self, prompt, **options):
        return LLMResult(
            json.dumps(
                {
                    "relevance": 3,
                    "level_fit": 3,
                    "pedagogy": 3,
                    "evidence_quote": QUOTE_1,
                    "reason": "Moderate fit for curriculum",
                }
            ),
            100,
            20,
            0.005,
        )


def make_test_search(urls=URLS):
    candidates = [
        Candidate(
            url,
            f"Article on {url.split('/')[-1]}",
            "web",
            "article",
            "en",
            snippet=f"{QUOTE_1} on {url}",
        )
        for url in urls
    ]
    return SearchService([FakeSearch(candidates, name="web")])


def make_safe_fetcher():
    def reply(request):
        url = str(request.url)
        quote = QUOTE_1
        if "recursion-step" in url:
            quote = QUOTE_2
        elif "tail-recursion" in url:
            quote = QUOTE_3
        html = PAGE_TEMPLATE.format(title="Recursion", quote=quote, url=url)
        return httpx.Response(200, html=html)

    return SafeFetcher(
        resolver=lambda host, port: ["93.184.216.34"],
        transport=httpx.MockTransport(reply),
    )


@pytest.fixture
def mock_pipeline(monkeypatch):
    monkeypatch.setattr(resources, "make_search", make_test_search)
    monkeypatch.setattr(resources, "make_llm", MockJudgeLLM)
    monkeypatch.setattr(resources, "make_fetcher", make_safe_fetcher)


@pytest.fixture
def sessions(app):
    return app.state.database.sessions


def setup_course_and_roadmap(sessions, user_id, title="Recursion"):
    with sessions() as db:
        course = Course(
            owner_id=user_id, title="Data Structures", level="university", language="en"
        )
        db.add(course)
        db.flush()

        syllabus = Syllabus(course_id=course.id, raw_text="")
        db.add(syllabus)
        db.flush()

        db.add(
            LearningOutcome(
                syllabus_id=syllabus.id,
                code="CLO1",
                description="Write recursive algorithms with proper base cases",
            )
        )

        roadmap = Roadmap(
            course_id=course.id, user_id=user_id, title="Data Structures Roadmap"
        )
        db.add(roadmap)
        db.flush()

        node1 = RoadmapNode(
            roadmap_id=roadmap.id,
            type="topic",
            title=title,
            week=1,
            duration_minutes=60,
            due_at=NOW + timedelta(days=7),
        )
        node2 = RoadmapNode(
            roadmap_id=roadmap.id,
            type="topic",
            title="Tree Traversals",
            week=2,
            duration_minutes=60,
            due_at=NOW + timedelta(days=14),
        )
        db.add_all([node1, node2])
        db.commit()
        return course.id, roadmap.id, node1.id, node2.id


def verify_test_catalog(sessions, node_id):
    """Synthetic verifier fixture: #102 requires four checks, not merely a cached score."""
    from app.search import node_signature
    from assistant.backend.cache import cached_search
    from assistant.backend.catalog_models import ResourceVerification
    from assistant.backend.models import Resource
    from assistant.backend.resources import _outcomes

    with sessions() as db:
        node = db.get(RoadmapNode, node_id)
        roadmap = db.get(Roadmap, node.roadmap_id)
        course = db.get(Course, roadmap.course_id)
        signature = node_signature(
            node.title, list(_outcomes(db, course.id)), course.level, course.language
        )
        cached = cached_search(db, signature, NOW)
        for scored in (
            (cached["resources"] + cached.get("reserve", [])) if cached else []
        ):
            row = db.scalars(
                select(Resource).where(Resource.url == scored["url"])
            ).first()
            if row is None:
                row = Resource(
                    url=scored["url"],
                    canonical_url=scored["url"],
                    title=scored["title"],
                    lang=scored["lang"],
                    content_hash=scored["content_hash"],
                )
                db.add(row)
                db.flush()
            row.verification_status = "verified"
            row.license = "CC0-1.0"
            for check in ("fetch", "domain", "license", "metadata"):
                db.add(
                    ResourceVerification(
                        resource_id=row.id,
                        check_name=check,
                        result="pass",
                        checked_at=NOW.replace(hour=0),
                        checked_by="test:synthetic-verifier",
                    )
                )
        db.commit()


# ==============================================================================
# 1. Search resources endpoint tests
# ==============================================================================


def test_search_resources_enqueues_background_job(client, headers, sessions):
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    _, _, node_id, _ = setup_course_and_roadmap(sessions, user_id)

    response = client.post(
        f"/api/v1/roadmap-nodes/{node_id}/resources:search", headers=headers
    )
    assert response.status_code == 202
    data = response.json()
    assert "run_id" in data
    run_id = data["run_id"]

    # Verify Job is queued in the database
    with sessions() as db:
        job = db.get(Job, run_id)
        assert job is not None
        assert job.kind == "search_resources"
        assert job.status == "queued"
        payload = json.loads(job.payload)
        assert payload["node_id"] == node_id


def test_search_resources_ownership_check(client, headers, headers_a, sessions):
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    _, _, node_id, _ = setup_course_and_roadmap(sessions, user_id)

    # Calling as another user returns 404
    response = client.post(
        f"/api/v1/roadmap-nodes/{node_id}/resources:search", headers=headers_a
    )
    assert response.status_code == 404


def test_search_resources_rate_limit(client, headers, sessions):
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    _, _, node_id, _ = setup_course_and_roadmap(sessions, user_id)

    # Enqueue up to the 20 requests/hour limit
    for _ in range(20):
        res = client.post(
            f"/api/v1/roadmap-nodes/{node_id}/resources:search", headers=headers
        )
        assert res.status_code == 202

    # 21st request should be rate-limited (HTTP 429)
    res_21 = client.post(
        f"/api/v1/roadmap-nodes/{node_id}/resources:search", headers=headers
    )
    assert res_21.status_code == 429
    assert "Retry-After" in res_21.headers


# ==============================================================================
# 2. Get resources endpoint tests (searching, ready, insufficient)
# ==============================================================================


def test_get_resources_searching_status_when_job_active(client, headers, sessions):
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    _, _, node_id, _ = setup_course_and_roadmap(sessions, user_id)

    # Enqueue search
    client.post(f"/api/v1/roadmap-nodes/{node_id}/resources:search", headers=headers)

    # GET returns searching status
    res = client.get(f"/api/v1/roadmap-nodes/{node_id}/resources", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "searching"
    assert data["resources"] == []


def test_get_resources_ready_after_job_completes(
    client, headers, sessions, mock_pipeline
):
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    _, _, node_id, _ = setup_course_and_roadmap(sessions, user_id)

    # Enqueue and execute the search job
    search_res = client.post(
        f"/api/v1/roadmap-nodes/{node_id}/resources:search", headers=headers
    )
    run_id = search_res.json()["run_id"]

    assert jobs.run_once(sessions, NOW) == run_id

    verify_test_catalog(sessions, node_id)

    # GET returns ready with curated resources
    res = client.get(f"/api/v1/roadmap-nodes/{node_id}/resources", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert len(data["resources"]) >= 2

    first = data["resources"][0]
    assert first["rank"] == 1
    assert first["title"]
    assert first["url"]
    assert first["domain"]
    assert first["score"] >= 0.65
    assert "relevance" in first["breakdown"]
    assert first["reason"]
    assert first["evidence_quote"]


def test_get_resources_insufficient_when_few_found(
    client, headers, sessions, monkeypatch
):
    # Only 1 candidate available -> less than MIN_SOURCES (2)
    single_search = lambda: SearchService(
        [
            FakeSearch(
                [
                    Candidate(
                        "https://single.org/res",
                        "Single",
                        "web",
                        "article",
                        "en",
                        snippet=QUOTE_1,
                    )
                ],
                name="web",
            )
        ]
    )
    monkeypatch.setattr(resources, "make_search", single_search)
    monkeypatch.setattr(resources, "make_llm", MockJudgeLLM)
    monkeypatch.setattr(resources, "make_fetcher", make_safe_fetcher)

    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    _, _, node_id, _ = setup_course_and_roadmap(sessions, user_id)

    search_res = client.post(
        f"/api/v1/roadmap-nodes/{node_id}/resources:search", headers=headers
    )
    assert jobs.run_once(sessions, NOW) == search_res.json()["run_id"]

    res = client.get(f"/api/v1/roadmap-nodes/{node_id}/resources", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "insufficient"
    assert len(data["gaps"]) > 0


# ==============================================================================
# 3. Feedback and replacement endpoint tests
# ==============================================================================


def test_resource_feedback_helpful(client, headers, sessions, mock_pipeline):
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    _, _, node_id, _ = setup_course_and_roadmap(sessions, user_id)

    search_res = client.post(
        f"/api/v1/roadmap-nodes/{node_id}/resources:search", headers=headers
    )
    assert jobs.run_once(sessions, NOW) == search_res.json()["run_id"]

    verify_test_catalog(sessions, node_id)

    get_res = client.get(f"/api/v1/roadmap-nodes/{node_id}/resources", headers=headers)
    resource_id = get_res.json()["resources"][0]["id"]

    # Send helpful=True feedback
    fb_res = client.post(
        f"/api/v1/resources/{resource_id}/feedback",
        headers=headers,
        json={"node_id": node_id, "helpful": True},
    )
    assert fb_res.status_code == 200
    assert fb_res.json() == {"status": "ok", "replacement": None}

    # Verify feedback row in DB
    with sessions() as db:
        fb = db.scalars(
            select(ResourceFeedback).where(
                ResourceFeedback.user_id == user_id,
                ResourceFeedback.resource_id == resource_id,
            )
        ).first()
        assert fb is not None
        assert fb.rating == 1


def test_resource_feedback_unhelpful_returns_replacement(
    client, headers, sessions, monkeypatch
):
    pool_urls = [f"https://example{i}.org/recursion-{i}" for i in range(8)]
    monkeypatch.setattr(resources, "make_search", lambda: make_test_search(pool_urls))
    monkeypatch.setattr(resources, "make_llm", ModerateJudgeLLM)
    monkeypatch.setattr(resources, "make_fetcher", make_safe_fetcher)

    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    _, _, node_id, _ = setup_course_and_roadmap(sessions, user_id)

    search_res = client.post(
        f"/api/v1/roadmap-nodes/{node_id}/resources:search", headers=headers
    )
    assert jobs.run_once(sessions, NOW) == search_res.json()["run_id"]

    verify_test_catalog(sessions, node_id)

    get_res = client.get(f"/api/v1/roadmap-nodes/{node_id}/resources", headers=headers)
    resources_before = get_res.json()["resources"]
    assert len(resources_before) == 5
    dropped_resource_id = resources_before[0]["id"]
    dropped_url = resources_before[0]["url"]

    # Send helpful=False feedback
    fb_res = client.post(
        f"/api/v1/resources/{dropped_resource_id}/feedback",
        headers=headers,
        json={"node_id": node_id, "helpful": False, "reason": "wrong_level"},
    )
    assert fb_res.status_code == 200
    data = fb_res.json()
    assert data["status"] == "ok"
    replacement = data["replacement"]

    # Replacement is picked from the 3 reserve resources
    assert replacement is not None
    assert replacement["id"] != dropped_resource_id
    assert replacement["url"] != dropped_url

    # Check database state: dropped resource status is 'replaced'
    with sessions() as db:
        dropped_link = db.get(NodeResource, (node_id, dropped_resource_id))
        assert dropped_link.status == "replaced"

        rep_link = db.get(NodeResource, (node_id, replacement["id"]))
        assert rep_link.status == "shown"

        fb = db.scalars(
            select(ResourceFeedback).where(
                ResourceFeedback.user_id == user_id,
                ResourceFeedback.resource_id == dropped_resource_id,
            )
        ).first()
        assert fb is not None
        assert fb.rating == 0
        assert fb.comment == "wrong_level"

    # Subsequent GET no longer lists the replaced resource
    after_res = client.get(
        f"/api/v1/roadmap-nodes/{node_id}/resources", headers=headers
    )
    shown_ids = [r["id"] for r in after_res.json()["resources"]]
    assert dropped_resource_id not in shown_ids
    assert replacement["id"] in shown_ids


# ==============================================================================
# 4. Roadmap replan endpoint tests
# ==============================================================================


def test_roadmap_replan_proposal_diff_without_commit(client, headers, sessions):
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    _, roadmap_id, _, _ = setup_course_and_roadmap(sessions, user_id)

    # Setup availability for user
    client.put(
        "/api/v1/availability",
        headers=headers,
        json={
            "windows": [
                {
                    "starts_at": (NOW + timedelta(days=1)).isoformat(),
                    "ends_at": (NOW + timedelta(days=1, hours=3)).isoformat(),
                },
                {
                    "starts_at": (NOW + timedelta(days=2)).isoformat(),
                    "ends_at": (NOW + timedelta(days=2, hours=3)).isoformat(),
                },
            ]
        },
    )

    # Initial schedule
    sched_res = client.post(f"/api/v1/roadmaps/{roadmap_id}:schedule", headers=headers)
    assert sched_res.status_code == 200
    initial_entries_count = len(sched_res.json()["sessions"])
    assert initial_entries_count > 0

    # Call replan with approve=False -> returns proposal diff
    replan_res = client.post(
        f"/api/v1/roadmaps/{roadmap_id}:replan",
        headers=headers,
        json={"approve": False},
    )
    assert replan_res.status_code == 200
    data = replan_res.json()
    assert data["roadmap_id"] == roadmap_id
    assert data["committed"] is False
    assert "diff" in data
    assert "moved" in data["diff"]
    assert "added" in data["diff"]
    assert "dropped" in data["diff"]

    # Verify no database schedule changes occurred
    with sessions() as db:
        entries = db.scalars(
            select(ScheduleEntry).where(ScheduleEntry.user_id == user_id)
        ).all()
        assert len(entries) == initial_entries_count


def test_roadmap_replan_rate_limit_one_proposal_per_day(client, headers, sessions):
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    _, roadmap_id, _, _ = setup_course_and_roadmap(sessions, user_id)

    # First proposal succeeds
    res1 = client.post(
        f"/api/v1/roadmaps/{roadmap_id}:replan",
        headers=headers,
        json={"approve": False},
    )
    assert res1.status_code == 200

    # Second proposal on the same day returns 429
    res2 = client.post(
        f"/api/v1/roadmaps/{roadmap_id}:replan",
        headers=headers,
        json={"approve": False},
    )
    assert res2.status_code == 429
    assert "Retry-After" in res2.headers


def test_roadmap_replan_approve_commits_and_preserves_completed_work(
    client, headers, sessions
):
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    _, roadmap_id, node1_id, _ = setup_course_and_roadmap(sessions, user_id)

    # Set availability
    client.put(
        "/api/v1/availability",
        headers=headers,
        json={
            "windows": [
                {
                    "starts_at": (NOW + timedelta(days=1)).isoformat(),
                    "ends_at": (NOW + timedelta(days=1, hours=3)).isoformat(),
                },
                {
                    "starts_at": (NOW + timedelta(days=2)).isoformat(),
                    "ends_at": (NOW + timedelta(days=2, hours=3)).isoformat(),
                },
                {
                    "starts_at": (NOW + timedelta(days=3)).isoformat(),
                    "ends_at": (NOW + timedelta(days=3, hours=3)).isoformat(),
                },
            ]
        },
    )

    sched_res = client.post(f"/api/v1/roadmaps/{roadmap_id}:schedule", headers=headers)
    assert sched_res.status_code == 200

    # Complete node 1's task directly
    with sessions() as db:
        task1 = db.scalars(
            select(Task).where(
                Task.owner_id == user_id, Task.roadmap_node_id == node1_id
            )
        ).one()
        task1.status = "completed"
        task1.completed_minutes = task1.duration_minutes

        # Add a completed schedule entry for task 1
        completed_entry = ScheduleEntry(
            user_id=user_id,
            task_id=task1.id,
            starts_at=NOW - timedelta(hours=2),
            ends_at=NOW - timedelta(hours=1),
            status="completed",
            actual_minutes=60,
        )
        db.add(completed_entry)
        db.commit()
        completed_entry_id = completed_entry.id

    # Call replan with approve=True
    replan_res = client.post(
        f"/api/v1/roadmaps/{roadmap_id}:replan", headers=headers, json={"approve": True}
    )
    assert replan_res.status_code == 200
    data = replan_res.json()
    assert data["committed"] is True

    # Completed session and task 1 must remain completely untouched
    with sessions() as db:
        entry = db.get(ScheduleEntry, completed_entry_id)
        assert entry is not None
        assert entry.status == "completed"
        assert entry.actual_minutes == 60

        task1 = db.get(Task, task1.id)
        assert task1.status == "completed"
