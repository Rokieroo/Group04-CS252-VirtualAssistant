"""Tests for outcome reuse and batched resource linking in recommendations and search."""

from __future__ import annotations

from dataclasses import asdict

from conftest import roadmap_with_catalog
from sqlalchemy import event, select

from app.curator import Curation
from app.vetting import ScoredResource
from assistant.backend import recommendations_repository, resources
from assistant.backend.models import NodeResource, Resource, Roadmap, RoadmapNode, User


def _scored(url: str, title: str, score: float = 0.88) -> ScoredResource:
    return ScoredResource(
        url,
        title,
        "web",
        "article",
        "en",
        url.split("/")[2],
        True,
        15,
        score,
        {},
        "judge",
        "Binary search trees support ordered lookup.",
        f"hash-{title}",
        title.lower(),
    )


def test_recommendations_reuses_outcomes_once_on_miss(
    client, headers, app, clock, monkeypatch
):
    _, node_id = roadmap_with_catalog(
        client,
        headers,
        app,
        clock[0],
        [
            "Binary Search Trees lecture notes",
            "Binary Search Trees worked examples",
            "Binary Search Trees problem set",
        ],
    )
    repo_calls = 0
    orig_repo_outcomes = recommendations_repository._outcomes

    def counted_repo_outcomes(db, course_id):
        nonlocal repo_calls
        repo_calls += 1
        return orig_repo_outcomes(db, course_id)

    monkeypatch.setattr(recommendations_repository, "_outcomes", counted_repo_outcomes)
    # Force search_signature fallback path to verify it doesn't re-query either when outcomes passed.
    res_calls = 0
    orig_res_outcomes = resources._outcomes

    def counted_res_outcomes(db, course_id):
        nonlocal res_calls
        res_calls += 1
        return orig_res_outcomes(db, course_id)

    monkeypatch.setattr(resources, "_outcomes", counted_res_outcomes)

    resp = client.get(
        f"/api/v1/roadmap-nodes/{node_id}/recommendations", headers=headers
    )
    assert resp.status_code == 200
    assert len(resp.json()["recommendations"]) == 3
    assert repo_calls == 1
    assert res_calls == 0


def test_search_resources_reuses_outcomes_and_link_batches_queries(
    client, headers, app, clock, monkeypatch
):
    _, node_id = roadmap_with_catalog(client, headers, app, clock[0], [])

    with app.state.database.sessions() as db:
        node = db.get(RoadmapNode, node_id)
        roadmap = db.get(Roadmap, node.roadmap_id)
        course_id = roadmap.course_id
        user = db.get(User, roadmap.user_id)
        user_id = user.id

        # Pre-populate one existing resource and one existing shown NodeResource link.
        pre_existing = Resource(
            url="https://ocw.mit.edu/bst-existing",
            canonical_url="https://ocw.mit.edu/bst-existing",
            title="Existing BST Notes",
            provider="mit",
            kind="article",
            format="article",
        )
        db.add(pre_existing)
        db.flush()
        db.add(
            NodeResource(
                node_id=node_id,
                resource_id=pre_existing.id,
                status="shown",
                relevance_score=0.70,
            )
        )
        db.commit()

    curation = Curation(
        status="ready",
        resources=[
            _scored("https://ocw.mit.edu/bst-existing", "Existing BST Notes", 0.91),
            _scored("https://stanford.edu/bst-1", "Stanford BST 1", 0.89),
            _scored("https://stanford.edu/bst-1#section", "Stanford BST 1 Dup", 0.89),
            _scored("https://berkeley.edu/bst-2", "Berkeley BST 2", 0.86),
            _scored("https://cmu.edu/bst-3", "CMU BST 3", 0.84),
        ],
    )

    with app.state.database.sessions() as db:
        selects: list[str] = []

        def listener(conn, cursor, statement, parameters, context, executemany):
            del conn, cursor, parameters, context, executemany
            if statement.lstrip().upper().startswith("SELECT"):
                selects.append(statement)

        engine = app.state.database.engine
        event.listen(engine, "before_cursor_execute", listener)
        try:
            resources._link(db, node_id, curation)
            db.flush()
        finally:
            event.remove(engine, "before_cursor_execute", listener)

        links = db.scalars(
            select(NodeResource).where(NodeResource.node_id == node_id)
        ).all()
        assert len(links) == 4
        assert any(
            lk.resource_id == pre_existing.id and lk.relevance_score == 0.91
            for lk in links
        )
        assert len([s for s in selects if "FROM resources" in s]) == 1
        assert len([s for s in selects if "FROM node_resources" in s]) == 1

    outcome_calls = 0
    orig_outcomes = resources._outcomes

    def counted_outcomes(db, cid):
        nonlocal outcome_calls
        outcome_calls += 1
        return orig_outcomes(db, cid)

    monkeypatch.setattr(resources, "_outcomes", counted_outcomes)
    monkeypatch.setattr(
        resources, "cached_search", lambda db, sig, now: asdict(curation)
    )

    with app.state.database.sessions() as db:
        result = resources.search_resources(db, {"node_id": node_id}, clock[0])
        assert result["shown"] == 5
        assert outcome_calls == 1
        assert course_id and user_id
