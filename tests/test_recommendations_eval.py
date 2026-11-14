"""Offline recommender benchmark, external red-team, and provenance tests (issue #160)."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1] / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from run_recommendations import (
    NDCG_TARGET,
    PRECISION_TARGET,
    evaluate_external_redteam,
    evaluate_three_configs,
)

from assistant.backend.catalog_repository import verified_resources
from assistant.backend.models import (
    Course,
    Recommendation,
    Resource,
    Roadmap,
    RoadmapNode,
    User,
    utcnow,
)
from assistant.backend.recommendations_repository import (
    get_or_generate_node_recommendations,
    record_recommendation_event,
)


@pytest.fixture(scope="module")
def three_config_results():
    """Run the 5-syllabus offline 3-configuration evaluation once per module."""
    return evaluate_three_configs()


def test_three_config_benchmark_meets_targets_and_shows_progression(three_config_results):
    """Adding external sources raises coverage/diversity; feedback raises P@5 and nDCG@5."""
    configs, per_syllabus = three_config_results
    by_name = {cfg.config: cfg for cfg in configs}

    assert set(by_name) == {
        "db_only",
        "db_plus_external",
        "db_plus_external_plus_feedback",
    }

    db_only = by_name["db_only"]
    db_ext = by_name["db_plus_external"]
    db_ext_fb = by_name["db_plus_external_plus_feedback"]

    # 5 benchmark syllabi * 10 weeks = 50 nodes
    assert db_only.total_nodes == 50
    assert db_ext.covered_nodes > db_only.covered_nodes
    assert db_ext.coverage_rate == 1.0
    assert db_ext_fb.coverage_rate == 1.0

    # Format diversity increases when external video/exercise/textbook sources complement DB articles
    assert db_ext.avg_formats_in_top5 > db_only.avg_formats_in_top5
    assert db_ext.avg_formats_in_top5 >= 2.5
    assert db_ext_fb.avg_formats_in_top5 >= db_ext.avg_formats_in_top5

    # Ranking metrics clear targets and improve with learner feedback via vet(..., ratings=ratings)
    assert db_ext.precision_at_5 >= PRECISION_TARGET
    assert db_ext.ndcg_at_5 >= NDCG_TARGET
    assert db_ext_fb.precision_at_5 > db_ext.precision_at_5
    assert db_ext_fb.ndcg_at_5 > db_ext.ndcg_at_5

    assert set(per_syllabus["db_plus_external_plus_feedback"]) == {
        "CSC10014",
        "CS102",
        "CS201",
        "CS202",
        "CS203",
    }


def test_external_redteam_and_provenance_invariants():
    """0/15 injections, 0/20 pirated URLs, 0/3 K-12 adult pages enter top-5; 0 external marked verified."""
    report = evaluate_external_redteam()

    assert report.injection_pages_tested == 15
    assert report.injection_leaked_to_top5 == 0
    assert report.pirated_urls_tested == 20
    assert report.pirated_leaked_to_top5 == 0
    assert report.k12_adult_pages_tested == 3
    assert report.k12_adult_leaked_to_top5 == 0
    assert report.external_marked_verified == 0


def test_repository_external_provenance_and_not_helpful_dismissal(app, client):
    """External recommendations never mark Resource verified and are dismissed on not_helpful."""
    _ = client  # Trigger FastAPI lifespan so Alembic migrations initialize tables
    with app.state.database.sessions() as db:
        user = User(
            email=f"eval-user-{uuid4().hex}@example.com",
            password_hash="x",
            name="Eval User",
        )
        db.add(user)
        db.flush()

        course = Course(title="CS201 Algorithms", owner_id=user.id)
        db.add(course)
        db.flush()

        roadmap = Roadmap(course_id=course.id, user_id=user.id, title="Main Track")
        db.add(roadmap)
        db.flush()

        node = RoadmapNode(
            roadmap_id=roadmap.id,
            type="topic",
            title="Graph Traversals: BFS & DFS",
            week=9,
        )
        db.add(node)
        db.commit()

        recs = get_or_generate_node_recommendations(db, node, user.id, limit=5)
        external_recs = [r for r in recs if r.kind == "external"]
        assert len(external_recs) >= 1
        assert all(r.resource_ref.startswith("external:") for r in external_recs)

        # External candidates must never appear in Resource rows or verified_resources()
        assert db.query(Resource).count() == 0
        assert verified_resources(db, utcnow()) == []

        target = external_recs[0]
        event = record_recommendation_event(db, target.id, user.id, "not_helpful")
        assert event is not None
        assert event.event == "not_helpful"

        db_row = db.get(Recommendation, target.id)
        assert db_row is not None
        assert db_row.dismissed_at is not None

        # Dismissed recommendation must not remain among active undismissed rows
        remaining = get_or_generate_node_recommendations(db, node, user.id, limit=5)
        assert all(r.id != target.id for r in remaining)
