"""Tests for recommendations storage, events, external caching, and PII filtering (issue #156)."""

from datetime import timedelta
from pathlib import Path

from app.catalog.privacy import build_safe_external_query, pii_filter
from assistant.backend.models import (
    Course,
    ExternalResult,
    Roadmap,
    RoadmapNode,
    utcnow,
)
from assistant.backend.recommendations_repository import (
    get_external_cached,
    set_external_cache,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "eval" / "fixtures" / "redteam" / "pii_syllabi"


# --- PII Redaction Tests (acceptance criterion) ------------------------------


def test_pii_filter_redacts_all_10_redteam_fixtures():
    """Verify that all 10 PII syllabus samples are stripped of sensitive personal data."""
    fixture_files = list(FIXTURES_DIR.glob("*.txt"))
    assert len(fixture_files) >= 10, f"Expected 10 PII fixtures, found {len(fixture_files)}"

    for fixture in fixture_files:
        raw_text = fixture.read_text(encoding="utf-8")
        clean_text = pii_filter(
            raw_text,
            learner_name="John Doe",
            learner_email="john.doe.student@university.edu",
            filenames=[fixture.name, "secret_syllabus.pdf"],
        )

        # 1. No email addresses
        assert "@" not in clean_text, f"{fixture.name} leaked email: {clean_text}"

        # 2. No phone numbers
        assert "09" not in clean_text or "Threads" in clean_text, f"{fixture.name} leaked phone"
        assert "+84" not in clean_text
        assert "555-0199" not in clean_text

        # 3. No citizen IDs / SSN / passwords
        assert "079194001234" not in clean_text
        assert "123-45-6789" not in clean_text
        assert "SuperSecret" not in clean_text
        assert "MyP@ssword" not in clean_text
        assert "xoxb" not in clean_text

        # 4. No learner credentials or filenames
        assert "John Doe" not in clean_text
        assert "john.doe.student" not in clean_text
        assert fixture.name not in clean_text
        assert "secret_syllabus.pdf" not in clean_text

        # 5. External query builder extracts only clean academic keywords
        safe_query = build_safe_external_query(
            node_title="Topic 1",
            concept_names=[clean_text.splitlines()[0]],
            learner_name="John Doe",
            learner_email="john.doe.student@university.edu",
            filenames=[fixture.name],
        )
        assert "@" not in safe_query
        assert "John Doe" not in safe_query
        assert fixture.name not in safe_query


# --- Authorization & Ownership Tests (acceptance criterion: other user -> 404) ---


def _seed_user_a_roadmap_node(app, user_id):
    """Seed a course, roadmap, and node owned by User A."""
    with app.state.database.sessions() as db:
        course = Course(title="Algorithms", owner_id=user_id)
        db.add(course)
        db.flush()

        roadmap = Roadmap(course_id=course.id, user_id=user_id, title="Main Track")
        db.add(roadmap)
        db.flush()

        node = RoadmapNode(
            roadmap_id=roadmap.id,
            type="topic",
            title="Dynamic Programming",
            week=1,
        )
        db.add(node)
        db.commit()
        return roadmap.id, node.id


def test_authorization_user_b_gets_404_for_user_a_recommendations(
    app, client, user_a, headers_a, user_b, headers_b
):
    """Recommendations, events, and summaries of User A return 404 for User B."""
    roadmap_id, node_id = _seed_user_a_roadmap_node(app, user_a["user"]["id"])

    # 1. User B cannot read User A's node recommendations -> 404
    resp = client.get(
        f"/api/v1/roadmap-nodes/{node_id}/recommendations",
        headers=headers_b,
    )
    assert resp.status_code == 404, resp.text

    # User A gets recommendations -> 200
    resp_a = client.get(
        f"/api/v1/roadmap-nodes/{node_id}/recommendations",
        headers=headers_a,
    )
    assert resp_a.status_code == 200, resp_a.text
    recs = resp_a.json()["recommendations"]
    assert len(recs) > 0
    rec_id = recs[0]["id"]

    # 2. User B cannot post events to User A's recommendation -> 404
    resp_event_b = client.post(
        f"/api/v1/recommendations/{rec_id}/events",
        headers=headers_b,
        json={"event": "helpful"},
    )
    assert resp_event_b.status_code == 404

    # 3. User B cannot get summary of User A's roadmap recommendations -> 404
    resp_sum_b = client.get(
        f"/api/v1/roadmaps/{roadmap_id}/recommendations:summary",
        headers=headers_b,
    )
    assert resp_sum_b.status_code == 404


def test_recommendation_lifecycle_events_and_summary(
    app, client, user_a, headers_a
):
    """User can fetch recommendations, log feedback events, and query roadmap summary."""
    roadmap_id, node_id = _seed_user_a_roadmap_node(app, user_a["user"]["id"])

    # Fetch recommendations
    resp = client.get(
        f"/api/v1/roadmap-nodes/{node_id}/recommendations?limit=3",
        headers=headers_a,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["node_id"] == node_id
    recs = data["recommendations"]
    assert 1 <= len(recs) <= 3
    rec_id = recs[0]["id"]

    # Record feedback events
    client.post(
        f"/api/v1/recommendations/{rec_id}/events",
        headers=headers_a,
        json={"event": "shown"},
    )
    client.post(
        f"/api/v1/recommendations/{rec_id}/events",
        headers=headers_a,
        json={"event": "helpful"},
    )
    client.post(
        f"/api/v1/recommendations/{rec_id}/events",
        headers=headers_a,
        json={"event": "pinned"},
    )

    # Check summary
    summary_resp = client.get(
        f"/api/v1/roadmaps/{roadmap_id}/recommendations:summary",
        headers=headers_a,
    )
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["roadmap_id"] == roadmap_id
    assert summary["total_nodes"] == 1
    assert summary["pinned_count"] == 1
    assert summary["events_summary"].get("helpful") == 1
    assert summary["events_summary"].get("pinned") == 1

    # Record not_helpful dismisses the recommendation
    dismiss_resp = client.post(
        f"/api/v1/recommendations/{rec_id}/events",
        headers=headers_a,
        json={"event": "not_helpful"},
    )
    assert dismiss_resp.status_code == 201

    after_dismiss = client.get(
        f"/api/v1/roadmaps/{roadmap_id}/recommendations:summary",
        headers=headers_a,
    )
    assert after_dismiss.status_code == 200
    after_data = after_dismiss.json()
    assert after_data["total_recommendations"] == len(recs) - 1
    assert after_data["events_summary"].get("not_helpful") == 1
    assert after_data["events_summary"].get("helpful") == 1


# --- External Cache Tests (acceptance criterion: 7-day cache) -----------------


def test_external_results_7_day_cache(client, app):
    """Cache returns entries younger than 7 days and expires older entries."""
    query_hash = "abcdef0123456789"
    provider = "openstax"
    payload = {"results": [{"title": "Calculus", "url": "https://example.com"}]}

    with app.state.database.sessions() as db:
        # Store in cache
        set_external_cache(db, query_hash, provider, payload)
        cached = get_external_cached(db, query_hash, provider)
        assert cached == payload

        # Artificially age the cache row past 7 days
        row = db.get(ExternalResult, (query_hash, provider))
        row.fetched_at = utcnow() - timedelta(days=8)
        db.commit()

        # Expired cache returns None
        assert get_external_cached(db, query_hash, provider) is None


def test_enrich_recommendations_batches_queries(app, user_a):
    """Enriching a list of recommendations uses one query per reference source type."""
    import json
    from uuid import uuid4

    from sqlalchemy import event

    from assistant.backend.models import Recommendation, Resource, Roadmap, Source
    from assistant.backend.recommendations_repository import enrich_recommendations

    user_id = user_a["user"]["id"]
    roadmap_id, node_id = _seed_user_a_roadmap_node(app, user_id)

    with app.state.database.sessions() as db:
        roadmap = db.get(Roadmap, roadmap_id)
        assert roadmap is not None
        r1 = Resource(
            id=str(uuid4()),
            title="Catalog Book 1",
            url="https://example.org/book1",
            canonical_url="https://example.org/book1",
            verification_status="verified",
        )
        r2 = Resource(
            id=str(uuid4()),
            title="Catalog Book 2",
            url="https://example.org/book2",
            canonical_url="https://example.org/book2",
            verification_status="verified",
        )
        s1 = Source(
            id=str(uuid4()),
            course_id=roadmap.course_id,
            file_name="slides1.pdf",
            page=1,
            text="Dynamic programming recurrence",
        )
        e1 = ExternalResult(
            query_hash="h1" + "0" * 62,
            provider="recommender",
            payload=json.dumps({"title": "External Guide", "url": "https://openstax.org/g1"}),
            fetched_at=utcnow(),
        )
        db.add_all([r1, r2, s1, e1])
        recs = [
            Recommendation(
                user_id=user_id,
                node_id=node_id,
                resource_ref=f"catalog:{r1.id}",
                kind="verified",
                rank=1,
                score=0.95,
                reason="Catalog",
                created_at=utcnow(),
            ),
            Recommendation(
                user_id=user_id,
                node_id=node_id,
                resource_ref=f"catalog:{r2.id}",
                kind="verified",
                rank=2,
                score=0.90,
                reason="Catalog",
                created_at=utcnow(),
            ),
            Recommendation(
                user_id=user_id,
                node_id=node_id,
                resource_ref=f"material:{s1.id}",
                kind="material",
                rank=3,
                score=0.88,
                reason="Slides",
                created_at=utcnow(),
            ),
            Recommendation(
                user_id=user_id,
                node_id=node_id,
                resource_ref=f"external:{e1.query_hash}",
                kind="external",
                rank=4,
                score=0.82,
                reason="Open",
                created_at=utcnow(),
            ),
        ]
        db.add_all(recs)
        db.commit()

        queries: list[str] = []

        def _track(conn, cursor, statement, parameters, context, executemany):
            queries.append(statement)

        engine = db.get_bind()
        event.listen(engine, "before_cursor_execute", _track)
        try:
            enriched = enrich_recommendations(db, recs)
        finally:
            event.remove(engine, "before_cursor_execute", _track)

    assert len(queries) == 3  # 1 Resource IN + 1 Source IN + 1 ExternalResult IN
    assert [item.title for item in enriched] == [
        "Catalog Book 1",
        "Catalog Book 2",
        "slides1.pdf",
        "External Guide",
    ]
    assert enriched[0].url == "https://example.org/book1"
    assert enriched[3].url == "https://openstax.org/g1"
