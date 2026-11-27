"""Offline recommender benchmark, external red-team, and provenance tests (issue #160)."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1] / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from run_recommendations import (
    NDCG_TARGET,
    PRECISION_TARGET,
    ContentJudge,
    evaluate_external_redteam,
    evaluate_three_configs,
)

from app.curator import Curation
from app.vetting import ScoredResource
from assistant.backend.cache import store_search
from assistant.backend.catalog_repository import verified_resources
from assistant.backend.models import (
    Course,
    Recommendation,
    Resource,
    Roadmap,
    RoadmapNode,
    User,
)
from assistant.backend.recommendations_repository import (
    get_or_generate_node_recommendations,
    record_recommendation_event,
)
from assistant.backend.resources import search_signature


@pytest.fixture(scope="module")
def three_config_results():
    """Run the 5-syllabus offline 3-configuration evaluation once per module."""
    return evaluate_three_configs()


def test_three_configs_show_the_pipeline_effects(three_config_results):
    """Synthetic external pages add coverage and formats; oracle votes never hurt ranking."""
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


def test_recommender_meets_the_ranking_targets(three_config_results):
    """#155 done-when, offline: ``recommend`` over the #106-labelled catalog plus external pages.

    External pages are fixtures and the judge a label-blind stand-in, so this proves the
    product's merge (database first, external when short, MMR) ranks what the labels call
    good on top; it does not measure live search quality.
    """
    configs, _ = three_config_results
    unified = {cfg.config: cfg for cfg in configs}["db_plus_external"]
    assert unified.precision_at_5 >= PRECISION_TARGET
    assert unified.ndcg_at_5 >= NDCG_TARGET


def _judged(page: str) -> dict:
    prompt = (
        "<learning_goal>Stage: Binary Search Trees</learning_goal>\n"
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


@pytest.mark.xfail(strict=True, reason="2/20 invented fixture domains (scribd-vips.xyz, "
                   "leaked-textbooks.ru) carry no blocklist signal")
def test_no_pirated_page_reaches_the_top5(redteam):
    assert redteam.pirated_leaked_to_top5 == 0


@pytest.mark.xfail(strict=True, reason="10/15 directives neutralized; SQL, mass-print, "
                   "infinite-repeat, false-fact and 'forget context' directives stay in the text")
def test_no_injection_page_reaches_the_top5(redteam):
    assert redteam.injection_directives_stripped == redteam.injection_pages_tested
    assert redteam.injection_leaked_to_top5 == 0


def test_repository_external_provenance_and_not_helpful_dismissal(app, client, clock):
    """Cached external pages are served unverified, never stored as Resource, and replaced."""
    _ = client  # Trigger FastAPI lifespan so Alembic migrations initialize tables
    now = clock[0]
    with app.state.database.sessions() as db:
        user = User(email=f"eval-user-{uuid4().hex}@example.com", password_hash="x",
                    name="Eval User")
        db.add(user)
        db.flush()
        course = Course(title="CS201 Algorithms", owner_id=user.id, language="en")
        db.add(course)
        db.flush()
        roadmap = Roadmap(course_id=course.id, user_id=user.id, title="Main Track")
        db.add(roadmap)
        db.flush()
        node = RoadmapNode(roadmap_id=roadmap.id, type="topic",
                           title="Graph Traversals: BFS & DFS", week=9)
        db.add(node)
        db.flush()
        # What the search job caches for the node: two vetted pages.
        pages = [ScoredResource(
            url=f"https://{host}/graph-traversal", title=f"Graph traversal notes ({host})",
            provider="web", format="reading", lang="en", domain=host, is_free=True,
            minutes=None, score=0.85, breakdown={}, reason="", content_hash=host, excerpt="",
            evidence_quote="Breadth-first search visits vertices level by level.")
            for host in ("cs.stanford.edu", "en.wikipedia.org")]
        store_search(db, search_signature(db, node, course),
                     asdict(Curation("ready", pages)), now)
        db.commit()

        recs = get_or_generate_node_recommendations(db, node, user.id, now, limit=5)
        assert {(r.kind, r.verification_status) for r in recs} == {("external", "unverified")}
        assert all(r.resource_ref.startswith("external:") and r.url for r in recs)
        # External candidates never become Resource rows or verified catalog entries here.
        assert db.query(Resource).count() == 0
        assert verified_resources(db, now) == []

        target = recs[0]
        event = record_recommendation_event(db, target.id, user.id, "not_helpful", now)
        assert event is not None and event.event == "not_helpful"
        assert db.get(Recommendation, target.id).dismissed_at is not None

        remaining = get_or_generate_node_recommendations(db, node, user.id, now, limit=5)
        assert target.resource_ref not in {r.resource_ref for r in remaining}
        assert len(remaining) == 1
