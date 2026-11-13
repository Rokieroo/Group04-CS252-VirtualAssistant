"""Integration tests for Roadmap Knowledge Graph API (Issue #103, spec 8, UC-03)."""

import time

import pytest
from sqlalchemy import select

from assistant.backend.models import Notification


@pytest.fixture
def course_and_roadmap(client, headers):
    # 1. Create Course
    c_res = client.post(
        "/api/v1/courses",
        headers=headers,
        json={"title": "Software Engineering", "language": "en", "level": "university"},
    )
    assert c_res.status_code == 201, c_res.text
    course_id = c_res.json()["id"]

    # 2. Ingest Syllabus with learning outcomes & assessments
    s_res = client.post(
        f"/api/v1/courses/{course_id}/syllabus",
        headers=headers,
        json={
            "raw_text": (
                "Week 1: Requirements Engineering\n"
                "Week 2: Architecture & Design\n"
                "Week 3: Testing & CI/CD\n"
                "Week 4: Deployment & Maintenance"
            ),
            "outcomes": [
                {"code": "CLO1", "description": "Requirements Engineering"},
                {"code": "CLO2", "description": "Architecture & Design"},
                {"code": "CLO3", "description": "Testing & CI/CD"},
            ],
            "assessments": [
                {"name": "Midterm Exam", "due_week": 2},
                {"name": "Final Project", "due_week": 4},
            ],
        },
    )
    assert s_res.status_code == 201, s_res.text

    # 3. Generate Roadmap
    r_res = client.post(
        f"/api/v1/courses/{course_id}/roadmap:generate",
        headers=headers,
        json={
            "nodes": [
                {"title": "Requirements Engineering", "week": 1, "type": "topic", "est_minutes": 60},
                {"title": "Architecture & Design", "week": 2, "type": "topic", "est_minutes": 90},
                {"title": "Midterm Exam", "week": 2, "type": "milestone", "est_minutes": 120},
                {"title": "Testing & CI/CD", "week": 3, "type": "topic", "est_minutes": 60},
                {"title": "Final Project", "week": 4, "type": "milestone", "est_minutes": 180},
            ]
        },
    )
    assert r_res.status_code == 201, r_res.text
    roadmap = r_res.json()
    return course_id, roadmap


def test_get_roadmap_graph_full_and_milestones(client, headers, course_and_roadmap):
    _, roadmap = course_and_roadmap
    roadmap_id = roadmap["id"]

    res = client.get(f"/api/v1/roadmaps/{roadmap_id}/graph", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 5

    # Check node fields
    titles = {n["title"]: n for n in data["nodes"]}
    assert "Requirements Engineering" in titles
    assert "Architecture & Design" in titles
    assert "Midterm Exam" in titles
    assert "Testing & CI/CD" in titles
    assert "Final Project" in titles

    req_node = titles["Requirements Engineering"]
    assert req_node["type"] == "topic"
    assert req_node["week"] == 1
    assert req_node["status"] in ("pending", "in_progress", "completed")
    assert "source_count" in req_node
    assert "user_material_count" in req_node
    assert req_node["sources_status"] in ("ready", "insufficient")
    assert req_node["layer"] >= 1
    assert isinstance(req_node["outcome_ids"], list)

    midterm_node = titles["Midterm Exam"]
    assert midterm_node["type"] == "milestone"
    assert midterm_node["layer"] >= 2

    # Verify covers edges for milestone
    covers_edges = [e for e in data["edges"] if e["kind"] == "covers"]
    assert len(covers_edges) > 0
    for ce in covers_edges:
        assert ce["child"] in (midterm_node["id"], titles["Final Project"]["id"])
        assert ce["confidence"] == 1.0


def test_transitive_reduction_parameter(client, headers, course_and_roadmap):
    _, roadmap = course_and_roadmap
    roadmap_id = roadmap["id"]
    nodes = roadmap["nodes"]
    n1, n2, n3 = nodes[0]["id"], nodes[1]["id"], nodes[3]["id"]

    # Add edges: n1 -> n2, n2 -> n3, and shortcut n1 -> n3
    client.post(
        f"/api/v1/roadmaps/{roadmap_id}/graph/edges",
        headers=headers,
        json={"parent": n1, "child": n2, "kind": "strict"},
    )
    client.post(
        f"/api/v1/roadmaps/{roadmap_id}/graph/edges",
        headers=headers,
        json={"parent": n2, "child": n3, "kind": "strict"},
    )
    client.post(
        f"/api/v1/roadmaps/{roadmap_id}/graph/edges",
        headers=headers,
        json={"parent": n1, "child": n3, "kind": "strict"},
    )

    # Without reduction: n1 -> n3 is present
    res_full = client.get(f"/api/v1/roadmaps/{roadmap_id}/graph?reduce=false", headers=headers)
    assert res_full.status_code == 200
    edges_full = [(e["parent"], e["child"]) for e in res_full.json()["edges"]]
    assert (n1, n3) in edges_full

    # With reduction: shortcut n1 -> n3 is removed because n1 -> n2 -> n3 exists
    res_red = client.get(f"/api/v1/roadmaps/{roadmap_id}/graph?reduce=true", headers=headers)
    assert res_red.status_code == 200
    edges_red = [(e["parent"], e["child"]) for e in res_red.json()["edges"]]
    assert (n1, n2) in edges_red
    assert (n2, n3) in edges_red
    assert (n1, n3) not in edges_red


def test_local_subgraph_depth_and_direction(client, headers, course_and_roadmap):
    _, roadmap = course_and_roadmap
    roadmap_id = roadmap["id"]
    nodes = roadmap["nodes"]
    n1, n2, n3 = nodes[0]["id"], nodes[1]["id"], nodes[3]["id"]

    client.post(
        f"/api/v1/roadmaps/{roadmap_id}/graph/edges",
        headers=headers,
        json={"parent": n1, "child": n2, "kind": "strict"},
    )
    client.post(
        f"/api/v1/roadmaps/{roadmap_id}/graph/edges",
        headers=headers,
        json={"parent": n2, "child": n3, "kind": "strict"},
    )

    # Local subgraph around n2 with depth=1, direction=descendants
    res_desc = client.get(
        f"/api/v1/roadmap-nodes/{n2}/graph?depth=1&direction=descendants",
        headers=headers,
    )
    assert res_desc.status_code == 200
    node_ids_desc = {n["id"] for n in res_desc.json()["nodes"]}
    assert n2 in node_ids_desc
    assert n3 in node_ids_desc
    assert n1 not in node_ids_desc

    # Local subgraph around n2 with depth=1, direction=ancestors
    res_anc = client.get(
        f"/api/v1/roadmap-nodes/{n2}/graph?depth=1&direction=ancestors",
        headers=headers,
    )
    assert res_anc.status_code == 200
    node_ids_anc = {n["id"] for n in res_anc.json()["nodes"]}
    assert n2 in node_ids_anc
    assert n1 in node_ids_anc
    assert n3 not in node_ids_anc

    # Direction=both includes both sides
    res_both = client.get(
        f"/api/v1/roadmap-nodes/{n2}/graph?depth=1&direction=both",
        headers=headers,
    )
    assert res_both.status_code == 200
    node_ids_both = {n["id"] for n in res_both.json()["nodes"]}
    assert {n1, n2, n3}.issubset(node_ids_both)


def test_add_edge_cycle_rejection_409(client, headers, course_and_roadmap):
    _, roadmap = course_and_roadmap
    roadmap_id = roadmap["id"]
    nodes = roadmap["nodes"]
    n1, n2 = nodes[0]["id"], nodes[1]["id"]

    # Edge n1 -> n2
    res1 = client.post(
        f"/api/v1/roadmaps/{roadmap_id}/graph/edges",
        headers=headers,
        json={"parent": n1, "child": n2, "kind": "strict"},
    )
    assert res1.status_code == 201

    # Opposite edge n2 -> n1 creates cycle: expect 409 with error='cycle' and path
    res2 = client.post(
        f"/api/v1/roadmaps/{roadmap_id}/graph/edges",
        headers=headers,
        json={"parent": n2, "child": n1, "kind": "strict"},
    )
    assert res2.status_code == 409
    err = res2.json()["detail"]
    assert err["error"] == "cycle"
    assert err["path"] == [n2, n1, n2]

    # Self edge n1 -> n1 creates cycle: expect 409
    res_self = client.post(
        f"/api/v1/roadmaps/{roadmap_id}/graph/edges",
        headers=headers,
        json={"parent": n1, "child": n1, "kind": "strict"},
    )
    assert res_self.status_code == 409
    assert res_self.json()["detail"]["error"] == "cycle"


def test_edge_from_milestone_back_to_a_covered_topic_is_a_cycle(
    client, headers, course_and_roadmap
):
    """The graph draws covered topic -> milestone; the reverse edge must be refused."""
    _, roadmap = course_and_roadmap
    roadmap_id = roadmap["id"]
    graph = client.get(f"/api/v1/roadmaps/{roadmap_id}/graph", headers=headers).json()
    covers = next(e for e in graph["edges"] if e["kind"] == "covers")

    res = client.post(
        f"/api/v1/roadmaps/{roadmap_id}/graph/edges",
        headers=headers,
        json={"parent": covers["child"], "child": covers["parent"], "kind": "strict"},
    )
    assert res.status_code == 409, res.text
    assert res.json()["detail"]["error"] == "cycle"
    edges = client.get(f"/api/v1/roadmaps/{roadmap_id}/graph", headers=headers).json()["edges"]
    assert not any(
        e["parent"] == covers["child"] and e["child"] == covers["parent"] for e in edges
    )


def test_edge_modifications_trigger_replan_notification(app, client, headers, course_and_roadmap):
    _, roadmap = course_and_roadmap
    roadmap_id = roadmap["id"]
    nodes = roadmap["nodes"]
    n1, n2 = nodes[0]["id"], nodes[1]["id"]

    # Add edge
    client.post(
        f"/api/v1/roadmaps/{roadmap_id}/graph/edges",
        headers=headers,
        json={"parent": n1, "child": n2, "kind": "strict"},
    )

    with app.state.database.sessions() as db:
        notif = db.scalar(
            select(Notification).where(
                Notification.message.like(f"Roadmap {roadmap_id} edges updated%")
            )
        )
        assert notif is not None
        assert "replan" in notif.message.lower()

    # Delete edge
    del_res = client.delete(
        f"/api/v1/roadmaps/{roadmap_id}/graph/edges/{n1}/{n2}",
        headers=headers,
    )
    assert del_res.status_code == 204


def test_rate_limiting_edge_edits(app, client, headers, course_and_roadmap):
    from assistant.backend.routes_learning import _edge_edits

    _, roadmap = course_and_roadmap
    roadmap_id = roadmap["id"]
    nodes = roadmap["nodes"]
    n1, n2 = nodes[0]["id"], nodes[1]["id"]

    # Make 1 call
    res = client.post(
        f"/api/v1/roadmaps/{roadmap_id}/graph/edges",
        headers=headers,
        json={"parent": n1, "child": n2, "kind": "strict"},
    )
    assert res.status_code == 201

    # Fill rate limiter to 120 with app.state.now() timestamp
    now_ts = app.state.now().timestamp()
    for uid in list(_edge_edits.keys()):
        _edge_edits[uid] = [now_ts] * 120

    # 121st request must trigger 429
    res_blocked = client.post(
        f"/api/v1/roadmaps/{roadmap_id}/graph/edges",
        headers=headers,
        json={"parent": n1, "child": n2, "kind": "strict"},
    )
    assert res_blocked.status_code == 429

    # Clean up history for remaining tests
    _edge_edits.clear()


def test_graph_and_layout_user_isolation(app, client, headers, headers_b, course_and_roadmap):
    _, roadmap = course_and_roadmap
    roadmap_id = roadmap["id"]
    node_id = roadmap["nodes"][0]["id"]
    node2_id = roadmap["nodes"][1]["id"]

    # User A creates an edge and saves layout + task mastery status
    add_res = client.post(
        f"/api/v1/roadmaps/{roadmap_id}/graph/edges",
        headers=headers,
        json={"parent": node_id, "child": node2_id, "kind": "strict"},
    )
    assert add_res.status_code == 201
    assert (
        client.put(
            f"/api/v1/roadmaps/{roadmap_id}/graph/layout",
            headers=headers,
            json=[{"node_id": node_id, "x": 120, "y": 240, "pinned": True}],
        ).status_code
        == 200
    )

    # Create a completed task for User A on node_id so User A's graph shows mastery status
    from assistant.backend.models import Task

    with app.state.database.sessions() as db:
        owner_id = roadmap["user_id"]
        db.add(
            Task(
                owner_id=owner_id,
                assignee_id=owner_id,
                title="Mastery task",
                duration_minutes=60,
                due_at=app.state.now(),
                status="completed",
                roadmap_node_id=node_id,
            )
        )
        db.commit()

    # User A sees completed mastery status on node_id
    graph_a = client.get(f"/api/v1/roadmaps/{roadmap_id}/graph", headers=headers).json()
    node_a = next(n for n in graph_a["nodes"] if n["id"] == node_id)
    assert node_a["status"] == "completed"

    # User B cannot read User A's graph, edges, or node subgraph
    assert client.get(f"/api/v1/roadmaps/{roadmap_id}/graph", headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/roadmaps/{roadmap_id}/edges", headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/roadmap-nodes/{node_id}/graph", headers=headers_b).status_code == 404

    # User B cannot add or delete edges on User A's roadmap
    assert (
        client.post(
            f"/api/v1/roadmaps/{roadmap_id}/graph/edges",
            headers=headers_b,
            json={"parent": node_id, "child": node2_id},
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/roadmaps/{roadmap_id}/graph/edges/{node_id}/{node2_id}",
            headers=headers_b,
        ).status_code
        == 404
    )

    # User B cannot get or put layout on User A's roadmap
    assert (
        client.get(f"/api/v1/roadmaps/{roadmap_id}/graph/layout", headers=headers_b).status_code
        == 404
    )
    assert (
        client.put(
            f"/api/v1/roadmaps/{roadmap_id}/graph/layout",
            headers=headers_b,
            json=[{"node_id": node_id, "x": 100, "y": 200, "pinned": False}],
        ).status_code
        == 404
    )

    # User B cannot read or modify User A's node sources, exercises, or materials
    assert client.get(f"/api/v1/concepts/{node_id}/sources", headers=headers_b).status_code == 404
    assert (
        client.get(f"/api/v1/roadmap-nodes/{node_id}/exercises", headers=headers_b).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/roadmap-nodes/{node_id}/materials", headers=headers_b).status_code
        == 404
    )

    # Verify User A's edge and layout remain intact after User B's rejected attempts
    edges_a = client.get(f"/api/v1/roadmaps/{roadmap_id}/edges", headers=headers).json()
    assert any(e["parent_id"] == node_id and e["child_id"] == node2_id for e in edges_a)
    layout_a = client.get(f"/api/v1/roadmaps/{roadmap_id}/graph/layout", headers=headers).json()
    assert layout_a["positions"][0]["x"] == 120.0


def test_layout_endpoints_and_limits(client, headers, course_and_roadmap):
    _, roadmap = course_and_roadmap
    roadmap_id = roadmap["id"]
    node1 = roadmap["nodes"][0]["id"]
    node2 = roadmap["nodes"][1]["id"]

    # PUT layout as array of positions
    put_res1 = client.put(
        f"/api/v1/roadmaps/{roadmap_id}/graph/layout",
        headers=headers,
        json=[
            {"node_id": node1, "x": 150.5, "y": 250.0, "pinned": True},
            {"node_id": node2, "x": 300.0, "y": 400.0, "pinned": False},
        ],
    )
    assert put_res1.status_code == 200
    assert put_res1.json()["saved"] == 2

    # GET layout
    get_res = client.get(f"/api/v1/roadmaps/{roadmap_id}/graph/layout", headers=headers)
    assert get_res.status_code == 200
    positions = {p["node_id"]: p for p in get_res.json()["positions"]}
    assert positions[node1]["x"] == 150.5
    assert positions[node1]["pinned"] is True
    assert positions[node2]["x"] == 300.0

    # PUT layout exceeding 1000 positions -> 422
    over_limit = [{"node_id": node1, "x": 0, "y": 0, "pinned": False}] * 1001
    bad_res = client.put(
        f"/api/v1/roadmaps/{roadmap_id}/graph/layout",
        headers=headers,
        json=over_limit,
    )
    assert bad_res.status_code == 422


def test_graph_performance_300_nodes(app, client, headers):
    # Create large course with 300 nodes
    c_res = client.post(
        "/api/v1/courses",
        headers=headers,
        json={"title": "Large Course 300", "language": "en"},
    )
    assert c_res.status_code == 201
    course_id = c_res.json()["id"]

    # 300 sequential nodes across 60 weeks (5 topics per week)
    nodes_in = [
        {"title": f"Topic {i}", "week": (i // 5) + 1, "type": "topic", "est_minutes": 30}
        for i in range(290)
    ] + [
        {
            "title": f"Exam {i}",
            "week": (i + 1) * 6,
            "type": "milestone",
            "est_minutes": 60,
        }
        for i in range(10)
    ]

    r_res = client.post(
        f"/api/v1/courses/{course_id}/roadmap:generate",
        headers=headers,
        json={"nodes": nodes_in},
    )
    assert r_res.status_code == 201
    roadmap_id = r_res.json()["id"]

    # Warmup requests
    for _ in range(3):
        warmup = client.get(f"/api/v1/roadmaps/{roadmap_id}/graph", headers=headers)
        assert warmup.status_code == 200
        assert len(warmup.json()["nodes"]) == 300

    # Measure latency of GET /graph (p95 local < 300 ms)
    latencies = []
    for _ in range(10):
        t0 = time.perf_counter()
        res = client.get(f"/api/v1/roadmaps/{roadmap_id}/graph", headers=headers)
        t1 = time.perf_counter()
        assert res.status_code == 200
        latencies.append((t1 - t0) * 1000.0)

    p95 = sorted(latencies)[8]
    assert p95 < 300.0, f"p95 latency was {p95:.1f}ms, expected < 300ms"


def test_course_roadmap_discovery_is_owned_and_persistent(client, headers, headers_b, course_and_roadmap):
    course_id, roadmap = course_and_roadmap
    path = f"/api/v1/courses/{course_id}/roadmaps"
    response = client.get(path, headers=headers)
    assert response.status_code == 200
    assert [r["id"] for r in response.json()] == [roadmap["id"]]
    assert sorted(response.json()[0]["nodes"], key=lambda n: n["id"]) == sorted(roadmap["nodes"], key=lambda n: n["id"])
    assert client.get(path, headers=headers).json() == response.json()
    newer = client.post(
        f"/api/v1/courses/{course_id}/roadmap:generate", headers=headers,
        json={"nodes": [{"title": "Second saved plan", "week": 1, "type": "topic"}]},
    )
    assert newer.status_code == 201, newer.text
    discovered = client.get(path, headers=headers).json()
    assert [r["id"] for r in discovered] == [newer.json()["id"], roadmap["id"]]
    assert client.get(path, headers=headers_b).status_code == 404
    assert client.get(path).status_code == 401
    assert client.get("/api/v1/courses/missing/roadmaps", headers=headers).status_code == 404
    empty = client.post("/api/v1/courses", headers=headers, json={"title": "Empty course"}).json()
    assert client.get(f"/api/v1/courses/{empty['id']}/roadmaps", headers=headers).json() == []


def test_put_layout_batches_sql_and_validates_node_ownership(
    app, client, headers, course_and_roadmap
):
    from sqlalchemy import event

    course_id, roadmap = course_and_roadmap
    roadmap_id = roadmap["id"]
    nodes = roadmap["nodes"]

    # Create a second roadmap owned by the same user to verify 422 node_outside_roadmap.
    other_res = client.post(
        f"/api/v1/courses/{course_id}/roadmap:generate",
        headers=headers,
        json={
            "nodes": [
                {"title": "Other Track", "week": 1, "type": "topic", "est_minutes": 45}
            ]
        },
    )
    assert other_res.status_code == 201
    other_node_id = other_res.json()["nodes"][0]["id"]

    outside = client.put(
        f"/api/v1/roadmaps/{roadmap_id}/graph/layout",
        headers=headers,
        json=[{"node_id": other_node_id, "x": 10, "y": 20, "pinned": True}],
    )
    assert outside.status_code == 422
    assert outside.json()["detail"] == "node_outside_roadmap"

    unknown = client.put(
        f"/api/v1/roadmaps/{roadmap_id}/graph/layout",
        headers=headers,
        json=[{"node_id": "nonexistent-node", "x": 10, "y": 20, "pinned": False}],
    )
    assert unknown.status_code == 404

    # Seed node 0 first so the next batch exercises both update and insert in one PUT.
    first = client.put(
        f"/api/v1/roadmaps/{roadmap_id}/graph/layout",
        headers=headers,
        json=[{"node_id": nodes[0]["id"], "x": 1, "y": 2, "pinned": False}],
    )
    assert first.status_code == 200

    statements: list[str] = []

    def _track(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = app.state.database.engine
    event.listen(engine, "before_cursor_execute", _track)
    try:
        payload = [
            {"node_id": n["id"], "x": float(idx * 50), "y": float(idx * 25), "pinned": idx % 2 == 0}
            for idx, n in enumerate(nodes)
        ]
        res = client.put(
            f"/api/v1/roadmaps/{roadmap_id}/graph/layout",
            headers=headers,
            json=payload,
        )
    finally:
        event.remove(engine, "before_cursor_execute", _track)

    assert res.status_code == 200
    assert res.json()["saved"] == len(nodes)
    # Bounded SQL regardless of position count (auth + roadmap + node check + layout select + writes).
    assert len(statements) <= 12

    saved = client.get(f"/api/v1/roadmaps/{roadmap_id}/graph/layout", headers=headers).json()
    by_id = {p["node_id"]: p for p in saved["positions"]}
    assert by_id[nodes[0]["id"]]["pinned"] is True
    assert by_id[nodes[-1]["id"]]["x"] == float((len(nodes) - 1) * 50)


def test_edge_rate_limit_evicts_stale_users_and_is_thread_safe(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from assistant.backend import routes_learning

    routes_learning._edge_edits.clear()
    try:
        monkeypatch.setattr(routes_learning, "_EDGE_EDIT_CACHE_CAP", 4)
        for i in range(6):
            routes_learning._edge_edits[f"stale-{i}"] = [100.0]

        routes_learning._check_edge_rate_limit("active-user", 1000.0)
        assert "active-user" in routes_learning._edge_edits
        assert all(not uid.startswith("stale-") for uid in routes_learning._edge_edits)

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [
                pool.submit(routes_learning._check_edge_rate_limit, "concurrent-user", 2000.0)
                for _ in range(40)
            ]
            for f in futures:
                f.result()
        assert len(routes_learning._edge_edits["concurrent-user"]) == 40
    finally:
        routes_learning._edge_edits.clear()
