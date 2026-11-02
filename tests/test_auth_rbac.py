"""Phase 2 core loop: owner-only syllabus, roadmap and scheduling (#63)."""

from __future__ import annotations

from conftest import availability


def create_course(client, headers, title="Algorithms"):
    response = client.post(
        "/api/v1/courses", headers=headers, json={"title": title}
    )
    assert response.status_code == 201, response.text
    return response.json()


def syllabus_body(**changes):
    return {
        "text": "Week 1: Problem framing\nWeek 2: Complexity",
        "outcomes": [
            {"code": "CLO1", "text": "Frame a problem", "bloom_level": "apply"},
            {"code": "CLO2", "text": "Choose a solution ladder"},
        ],
        "assessments": [
            {"title": "Midterm", "weight": 30, "due": "week 8"},
            {"title": "Final project", "weight": "50%", "due_week": 15},
        ],
        **changes,
    }


def test_core_loop_owner_can_create_update_generate_and_schedule(client, headers_a):
    course = create_course(client, headers_a)

    created = client.post(
        f"/api/v1/courses/{course['id']}/syllabus",
        headers=headers_a,
        json=syllabus_body(),
    )
    assert created.status_code == 201, created.text
    syllabus = created.json()
    assert syllabus["syllabus_id"] == syllabus["id"]
    assert syllabus["raw_text"].startswith("Week 1")
    assert [row["code"] for row in syllabus["learning_outcomes"]] == [
        "CLO1",
        "CLO2",
    ]
    assert syllabus["learning_outcomes"][0]["description"] == "Frame a problem"
    assert syllabus["assessments"][0]["due_week"] == 8
    assert syllabus["assessments"][1]["weight"] == 50.0

    fetched = client.get(
        f"/api/v1/courses/{course['id']}/syllabus", headers=headers_a
    )
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["id"] == syllabus["id"]

    partial = client.put(
        f"/api/v1/courses/{course['id']}/syllabus",
        headers=headers_a,
        json={"raw_text": "Only the text changed"},
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["raw_text"] == "Only the text changed"
    assert len(partial.json()["learning_outcomes"]) == 2
    assert len(partial.json()["assessments"]) == 2

    updated = client.put(
        f"/api/v1/courses/{course['id']}/syllabus",
        headers=headers_a,
        json={
            "raw_text": "Updated syllabus",
            "learning_outcomes": [{"code": "CLO1", "description": "Explain"}],
            "assessments": [{"name": "Quiz", "weight": 10, "due_week": 2}],
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["id"] == syllabus["id"]
    assert updated.json()["raw_text"] == "Updated syllabus"
    assert len(updated.json()["learning_outcomes"]) == 1

    generated = client.post(
        f"/api/v1/courses/{course['id']}/roadmap:generate",
        headers=headers_a,
        json={"syllabus_id": syllabus["id"], "title": "My roadmap"},
    )
    assert generated.status_code == 201, generated.text
    roadmap = generated.json()
    assert roadmap["title"] == "My roadmap"
    assert {node["type"] for node in roadmap["nodes"]} == {"topic", "milestone"}
    fetched_roadmap = client.get(
        f"/api/v1/roadmaps/{roadmap['id']}", headers=headers_a
    )
    assert fetched_roadmap.status_code == 200, fetched_roadmap.text
    assert fetched_roadmap.json()["id"] == roadmap["id"]
    topics = [node for node in roadmap["nodes"] if node["type"] == "topic"]
    milestones = [node for node in roadmap["nodes"] if node["type"] == "milestone"]
    assert len(topics) == 1
    assert len(milestones) == 1
    assert milestones[0]["covers"] == [topics[0]["id"]]

    # One 3-hour window, capped at 30 minutes a day: one session fits, the rest does not.
    availability(client, headers_a)
    scheduled = client.post(
        f"/api/v1/roadmaps/{roadmap['id']}:schedule",
        headers=headers_a,
        json={"max_daily_minutes": 30},
    )
    assert scheduled.status_code == 200, scheduled.text
    plan = scheduled.json()
    assert plan["roadmap_id"] == roadmap["id"]
    assert len(plan["tasks"]) == len(roadmap["nodes"])
    assert [(s["starts_at"], s["ends_at"]) for s in plan["sessions"]] == [
        ("2030-01-07T02:00:00Z", "2030-01-07T02:30:00Z")
    ]
    assert all(session["status"] == "planned" for session in plan["sessions"])
    planned = 30 + sum(item["minutes"] for item in plan["unscheduled"])
    assert planned == sum(node["duration_minutes"] for node in roadmap["nodes"])

    again = client.post(
        f"/api/v1/roadmaps/{roadmap['id']}:schedule",
        headers=headers_a,
        json={"max_daily_minutes": 30},
    )
    assert again.status_code == 200, again.text
    assert len(again.json()["tasks"]) == len(plan["tasks"])
    assert len(again.json()["sessions"]) == len(plan["sessions"])

    tasks = client.get("/api/v1/tasks", headers=headers_a)
    assert tasks.status_code == 200
    assert len([task for task in tasks.json() if task["roadmap_node_id"]]) == len(
        roadmap["nodes"]
    )


def test_roadmap_schedule_without_availability_reports_every_node_unscheduled(
    client, headers_a
):
    course = create_course(client, headers_a)
    roadmap = client.post(
        f"/api/v1/courses/{course['id']}/roadmap:generate",
        headers=headers_a,
        json={"nodes": [{"title": "Framing", "est_minutes": 50, "week": 1}]},
    ).json()

    plan = client.post(
        f"/api/v1/roadmaps/{roadmap['id']}:schedule", headers=headers_a, json={}
    ).json()

    assert plan["sessions"] == []
    [missing] = plan["unscheduled"]
    assert (missing["task_id"], missing["minutes"]) == (plan["tasks"][0]["id"], 50)
    assert missing["reason"]


def test_core_loop_cross_user_requests_are_404(client, headers_a, headers_b):
    course = create_course(client, headers_a)
    created = client.post(
        f"/api/v1/courses/{course['id']}/syllabus",
        headers=headers_a,
        json=syllabus_body(),
    )
    assert created.status_code == 201, created.text
    roadmap = client.post(
        f"/api/v1/courses/{course['id']}/roadmap:generate",
        headers=headers_a,
        json={},
    )
    assert roadmap.status_code == 201, roadmap.text
    roadmap_id = roadmap.json()["id"]

    forbidden_requests = [
        client.get(
            f"/api/v1/courses/{course['id']}/syllabus", headers=headers_b
        ),
        client.get(f"/api/v1/roadmaps/{roadmap_id}", headers=headers_b),
        client.post(
            f"/api/v1/courses/{course['id']}/syllabus",
            headers=headers_b,
            json=syllabus_body(),
        ),
        client.put(
            f"/api/v1/courses/{course['id']}/syllabus",
            headers=headers_b,
            json=syllabus_body(),
        ),
        client.post(
            f"/api/v1/courses/{course['id']}/roadmap:generate",
            headers=headers_b,
            json={},
        ),
        client.post(
            f"/api/v1/roadmaps/{roadmap_id}:schedule",
            headers=headers_b,
            json={},
        ),
    ]
    assert [response.status_code for response in forbidden_requests] == [404] * 6
    assert client.get("/api/v1/courses", headers=headers_b).json() == []
