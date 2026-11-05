"""End-to-End integration tests for the Spec 3.0 Core Loop (Issue #67).

Tests the full sequential pipeline across:
1. Ingest Syllabus (PDF / text) & extract preview with citations (UC-01, UC-02)
2. Confirm Syllabus & generate DAG Roadmap with prerequisite edges (UC-02, UC-03)
3. Schedule Roadmap sessions into free slots without overload (UC-04)
4. Trigger search & curate verified resources for milestone nodes (UC-05, UC-06)
5. Replan roadmap when schedule delays or adjustments occur (UC-07)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.llm import LLMClient, LLMResult
from app.search import Candidate, FakeSearch, SearchService
from app.vetting import SafeFetcher
from assistant.backend import jobs, resources

NOW = datetime(2030, 1, 7, 9, 0, tzinfo=UTC)

QUOTE_FRAMING = "Problem framing defines the problem space and success metrics."
QUOTE_SOLUTION = "Solution ladder establishes levels from human process to automation."

PAGE_TEMPLATE = """
<html lang="en"><body><article>
<h1>{title}</h1>
<p>{quote}</p>
<p>In-depth tutorial and materials for university computer science curriculum. URL: {url}</p>
</article></body></html>
"""


class E2EJudgeLLM(LLMClient):
    """Deterministic Mock LLM returning grounded evidence quotes for search curation."""

    def complete(self, prompt: str, **options) -> LLMResult:
        quote = QUOTE_FRAMING
        if "solution" in prompt.lower() or "ladder" in prompt.lower():
            quote = QUOTE_SOLUTION
        return LLMResult(
            json.dumps(
                {
                    "relevance": 5,
                    "level_fit": 4,
                    "pedagogy": 5,
                    "evidence_quote": quote,
                    "reason": f"Matches course learning outcome: {quote}",
                }
            ),
            120,
            30,
            0.005,
        )


def make_e2e_safe_fetcher():
    def reply(request):
        url = str(request.url)
        quote = QUOTE_SOLUTION if "solution" in url else QUOTE_FRAMING
        html = PAGE_TEMPLATE.format(
            title="Curated Study Resource", quote=quote, url=url
        )
        return httpx.Response(200, html=html)

    return SafeFetcher(
        resolver=lambda host, port: ["93.184.216.34"],
        transport=httpx.MockTransport(reply),
    )


@pytest.fixture
def e2e_mock_pipeline(monkeypatch):
    pool_urls = [
        "https://mit.edu/csc10014/problem-framing",
        "https://stanford.edu/solution-ladder-guide",
        "https://cs.cmu.edu/requirements-engineering",
    ]
    candidates = [
        Candidate(
            url=url,
            title="Resource for " + url.split("/")[-1],
            provider="web",
            kind="reading",
            lang="en",
            snippet="High quality curriculum material for CS students",
        )
        for url in pool_urls
    ]
    monkeypatch.setattr(
        resources,
        "make_search",
        lambda: SearchService([FakeSearch(candidates, name="web")]),
    )
    monkeypatch.setattr(resources, "make_llm", E2EJudgeLLM)
    monkeypatch.setattr(resources, "make_fetcher", make_e2e_safe_fetcher)


def _verify_test_catalog(sessions, node_id: str) -> None:
    """Synthetic verifier helper: #102 requires four checks, not merely a cached score."""
    from sqlalchemy import select

    from app.search import node_signature
    from assistant.backend.cache import cached_search
    from assistant.backend.catalog_models import ResourceVerification
    from assistant.backend.models import Course, Resource, Roadmap, RoadmapNode
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


def test_e2e_core_loop_syllabus_to_roadmap_to_schedule_to_resources(
    client, e2e_mock_pipeline, sample_pdf
):
    """E2E Test verifying full journey: UC-01 -> UC-02 -> UC-03 -> UC-04 -> UC-05 -> UC-07."""
    # Step 1: User Registration & Authentication
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Le Hong Dang",
            "email": "dang.qa@example.com",
            "password": "secure-qa-password-2026",
            "birth_year": 2003,
        },
    )
    assert reg_res.status_code == 201
    auth_header = {"Authorization": "Bearer " + reg_res.json()["access_token"]}

    # Step 2: Create Course (CSC10014)
    course_res = client.post(
        "/api/v1/courses",
        headers=auth_header,
        json={
            "title": "Problem Framing and Solution Architecture",
            "level": "university",
            "language": "en",
        },
    )
    assert course_res.status_code == 201
    course_id = course_res.json()["id"]

    # Step 3: UC-01 Upload Syllabus (Text format from benchmark) with kind="syllabus"
    syllabus_path = Path("eval/syllabus/01_csc10014_problem_framing.txt")
    syllabus_bytes = syllabus_path.read_bytes()
    upload_res = client.post(
        f"/api/v1/courses/{course_id}/sources",
        headers=auth_header,
        data={"kind": "syllabus"},
        files={"file": ("01_csc10014_problem_framing.txt", syllabus_bytes, "text/plain")},
    )
    assert upload_res.status_code == 201
    assert upload_res.json()["file_name"] == "01_csc10014_problem_framing.txt"

    # Step 4: UC-02 Parse Syllabus Preview with deterministic citations
    parse_res = client.post(
        f"/api/v1/courses/{course_id}/syllabus:parse",
        headers=auth_header,
        json={"file_name": "01_csc10014_problem_framing.txt", "use_llm": False},
    )
    assert parse_res.status_code == 200
    preview = parse_res.json()
    assert preview["can_confirm"] is True
    parsed = preview["parsed"]
    assert len(parsed["outcomes"]) >= 1
    assert len(parsed["weeks"]) >= 1
    assert len(parsed["assessments"]) >= 1

    # Step 5: Save & Confirm Syllabus
    save_syl_res = client.post(
        f"/api/v1/courses/{course_id}/syllabus",
        headers=auth_header,
        json={
            "raw_text": "Week 1: Problem Framing\nWeek 2: Solution Ladder",
            "outcomes": [
                {
                    "code": "CLO1",
                    "description": "Frame business problems and analyze requirements",
                },
                {"code": "CLO2", "description": "Select appropriate solution ladder"},
            ],
            "assessments": [
                {"name": "Midterm Exam", "weight": 40.0, "due_week": 5},
                {"name": "Final Project", "weight": 60.0, "due_week": 10},
            ],
        },
    )
    assert save_syl_res.status_code == 201
    syllabus_data = save_syl_res.json()
    assert len(syllabus_data["learning_outcomes"]) == 2
    assert len(syllabus_data["assessments"]) == 2

    # Step 6: UC-03 Generate Roadmap from confirmed syllabus
    gen_roadmap_res = client.post(
        f"/api/v1/courses/{course_id}/roadmap:generate",
        headers=auth_header,
        json={"syllabus_id": syllabus_data["id"]},
    )
    assert gen_roadmap_res.status_code == 201
    roadmap = gen_roadmap_res.json()
    roadmap_id = roadmap["id"]
    nodes = roadmap["nodes"]
    assert len(nodes) >= 3  # topics + milestones
    topic_nodes = [n for n in nodes if n["type"] == "topic"]
    milestone_nodes = [n for n in nodes if n["type"] == "milestone"]
    assert len(topic_nodes) >= 2
    assert len(milestone_nodes) >= 1

    first_topic = topic_nodes[0]
    assert first_topic["duration_minutes"] > 0

    # Step 6.5: Set User Availability for scheduling
    client.put(
        "/api/v1/availability",
        headers=auth_header,
        json={
            "windows": [
                {
                    "starts_at": "2030-01-07T09:00:00+07:00",
                    "ends_at": "2030-01-07T21:00:00+07:00",
                },
                {
                    "starts_at": "2030-01-08T09:00:00+07:00",
                    "ends_at": "2030-01-08T21:00:00+07:00",
                },
                {
                    "starts_at": "2030-01-09T09:00:00+07:00",
                    "ends_at": "2030-01-09T21:00:00+07:00",
                },
            ]
        },
    )

    # Step 7: UC-04 Schedule Roadmap into study sessions
    schedule_res = client.post(
        f"/api/v1/roadmaps/{roadmap_id}:schedule",
        headers=auth_header,
        json={"max_daily_minutes": 180, "starts_at": "2030-01-07T09:00:00+07:00"},
    )
    assert schedule_res.status_code == 200
    schedule_data = schedule_res.json()
    assert len(schedule_data["tasks"]) == len(nodes)
    assert len(schedule_data["sessions"]) >= 1
    assert "overloaded_weeks" in schedule_data

    # Step 8: UC-05 Search & curate resources for the first topic node
    search_job_res = client.post(
        f"/api/v1/roadmap-nodes/{first_topic['id']}/resources:search",
        headers=auth_header,
    )
    assert search_job_res.status_code in (200, 202)
    run_id = search_job_res.json()["run_id"]

    # Execute background worker for resource curation
    app = client.app
    sessions = app.state.database.sessions
    assert jobs.run_once(sessions, NOW) == run_id

    # Verify test catalog verification status for curated items (epic #92 / #102)
    _verify_test_catalog(sessions, first_topic["id"])

    # Verify curated resources retrieved
    resources_res = client.get(
        f"/api/v1/roadmap-nodes/{first_topic['id']}/resources",
        headers=auth_header,
    )
    assert resources_res.status_code == 200
    res_list = resources_res.json()["resources"]
    assert len(res_list) > 0
    top_resource = res_list[0]
    assert top_resource["score"] >= 0.65
    assert len(top_resource["evidence_quote"]) > 0

    # Step 9: UC-06 User provides feedback on curated resource
    feedback_res = client.post(
        f"/api/v1/resources/{top_resource['id']}/feedback",
        headers=auth_header,
        json={
            "node_id": first_topic["id"],
            "helpful": True,
            "reason": "good_examples",
        },
    )
    assert feedback_res.status_code == 200
    assert feedback_res.json()["status"] == "ok"

    # Step 10: UC-07 Replan Roadmap when schedule shifts
    replan_preview = client.post(
        f"/api/v1/roadmaps/{roadmap_id}:replan",
        headers=auth_header,
        json={"approve": False},
    )
    assert replan_preview.status_code == 200
    preview_data = replan_preview.json()
    assert preview_data["committed"] is False
    assert "diff" in preview_data

    replan_commit = client.post(
        f"/api/v1/roadmaps/{roadmap_id}:replan",
        headers=auth_header,
        json={"approve": True},
    )
    assert replan_commit.status_code == 200
    assert replan_commit.json()["committed"] is True
