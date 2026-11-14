"""Offline recommender benchmark, external red-team, and provenance tests (issue #160)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1] / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from run_recommendations import (
    ContentJudge,
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


def test_three_configs_show_the_pipeline_effects(three_config_results):
    """Synthetic external pages add coverage and formats; oracle votes never hurt ranking.

    Precision@5 / nDCG@5 are not asserted against the spec targets: the pages are fixtures,
    so the numbers describe the fixture, not recommendation quality (see the script).
    """
    configs, per_syllabus = three_config_results
    by_name = {cfg.config: cfg for cfg in configs}
    db_only = by_name["db_only"]
    db_ext = by_name["db_plus_external"]
    db_ext_fb = by_name["db_plus_external_plus_feedback"]

    assert db_only.total_nodes == 50  # 5 benchmark syllabi * 10 weeks
    assert db_ext.covered_nodes > db_only.covered_nodes
    assert db_ext.avg_formats_in_top5 > db_only.avg_formats_in_top5
    assert db_ext_fb.precision_at_5 >= db_ext.precision_at_5
    assert db_ext_fb.ndcg_at_5 >= db_ext.ndcg_at_5
    assert set(per_syllabus["db_plus_external_plus_feedback"]) == {
        "CSC10014", "CS102", "CS201", "CS202", "CS203"}


def _judged(page: str) -> dict:
    prompt = (
        "<learning_goal>Chặng: Binary Search Trees</learning_goal>\n"
        f"<page_text>{page}</page_text>"
    )
    return json.loads(ContentJudge().generate(prompt))


def test_the_offline_judge_cannot_read_labels():
    """Words that name a fixture's label must not move the score (the old answer key)."""
    page = "Binary search trees keep keys ordered so lookups take logarithmic time."
    for label_word in ("spam", "pirated", "low-quality", "unrelated", "dump", "high-level outline"):
        assert _judged(f"{page} {label_word}")["relevance"] == _judged(page)["relevance"] == 4
    assert _judged("Phones and laptops on sale with free shipping this week.")["relevance"] == 0


@pytest.fixture(scope="module")
def redteam():
    return evaluate_external_redteam()  # also asserts that an on-topic control page is shown


def test_k12_adult_pages_and_external_provenance_hold(redteam):
    assert redteam.k12_adult_pages_tested == 3
    assert redteam.k12_adult_leaked_to_top5 == 0
    assert redteam.external_marked_verified == 0


@pytest.mark.xfail(strict=True, reason="domain blocklist misses file lockers, cheat services and "
                   "torrent trackers (14/20 fixture URLs are not BLOCKED)")
def test_no_pirated_page_reaches_the_top5(redteam):
    assert redteam.pirated_leaked_to_top5 == 0


@pytest.mark.xfail(strict=True, reason="strip_commands removes none of the 15 fixture directives; "
                   "an on-topic injected page is shown")
def test_no_injection_page_reaches_the_top5(redteam):
    assert redteam.injection_directives_stripped == redteam.injection_pages_tested
    assert redteam.injection_leaked_to_top5 == 0


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
