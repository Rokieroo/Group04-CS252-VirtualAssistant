"""Roadmap review persistence and planner budget regressions (#57)."""

from datetime import timedelta

from app.planner import WorkItem, build_plan, minutes
from assistant.backend.schemas import PlanRequest


def test_weekly_budget_counts_existing_work(clock):
    start = clock[0]
    end = start + timedelta(days=2)
    plan = build_plan(
        [WorkItem("a", 120, 1, end)],
        [(start, end)],
        [],
        [(start, start + timedelta(minutes=30))],
        PlanRequest(
            starts_at=start,
            ends_at=end,
            daily_limit_minutes=120,
            weekly_limit_minutes=60,
        ),
        "UTC",
    )
    assert sum(minutes(e.starts_at, e.ends_at) for e in plan.entries) == 30
    assert plan.unscheduled[0].minutes == 90


def test_reviewed_prerequisites_affect_real_schedule(client, headers_a, clock):
    start = clock[0] + timedelta(hours=1)
    client.put(
        "/api/v1/availability",
        headers=headers_a,
        json={
            "windows": [
                {
                    "starts_at": start.isoformat(),
                    "ends_at": (start + timedelta(hours=6)).isoformat(),
                }
            ]
        },
    )
    course = client.post(
        "/api/v1/courses", headers=headers_a, json={"title": "Schedule test"}
    ).json()
    roadmap = client.post(
        f"/api/v1/courses/{course['id']}/roadmap:generate",
        headers=headers_a,
        json={
            "nodes": [
                {"title": "First", "week": 1, "est_minutes": 50},
                {"title": "Second", "week": 1, "est_minutes": 50},
            ]
        },
    ).json()
    a, b = [n["id"] for n in roadmap["nodes"]]
    edge = {
        "parent_id": a,
        "child_id": b,
        "kind": "strict",
        "origin": "user",
        "confidence": 1,
    }
    client.post(
        f"/api/v1/roadmaps/{roadmap['id']}/edges",
        headers=headers_a,
        json={k: v for k, v in edge.items() if k in {"parent_id", "child_id", "kind"}},
    )
    response = client.post(
        f"/api/v1/roadmaps/{roadmap['id']}:schedule",
        headers=headers_a,
        json={"weekly_minutes": 100, "max_daily_minutes": 100},
    )
    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan["sessions"], plan
    task_ids = {t["title"]: t["id"] for t in plan["tasks"]}
    first = [x for x in plan["sessions"] if x["task_id"] == task_ids["First"]]
    second = [x for x in plan["sessions"] if x["task_id"] == task_ids["Second"]]
    assert first and second
    assert max(x["ends_at"] for x in first) <= min(x["starts_at"] for x in second)


def test_real_syllabus_to_generated_roadmap(client, headers_a, headers_b):
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[1]
        / "eval/syllabus/01_csc10014_problem_framing.txt"
    ).read_text(encoding="utf-8")
    course = client.post(
        "/api/v1/courses", headers=headers_a, json={"title": "CSC10014 integration"}
    ).json()
    base = f"/api/v1/courses/{course['id']}"
    response = client.post(
        base + "/syllabus:parse", headers=headers_a, json={"text": text}
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    assert not any(w.get("blocking") for w in preview.get("warnings", [])), preview
    confirmed = client.post(
        base + "/syllabus", headers=headers_a, json={"parsed": preview["parsed"]}
    )
    assert confirmed.status_code == 201, confirmed.text
    result = client.post(
        base + "/roadmap:generate",
        headers=headers_a,
        json={"syllabus_id": confirmed.json()["id"]},
    )
    assert result.status_code == 201, result.text
    roadmap = result.json()
    assert any(n["type"] == "topic" for n in roadmap["nodes"])
    assert any(n["type"] == "milestone" for n in roadmap["nodes"])
    endpoint = f"/api/v1/roadmaps/{roadmap['id']}/edges"
    edges = client.get(endpoint, headers=headers_a)
    assert edges.status_code == 200
    assert client.get(endpoint, headers=headers_b).status_code == 404
    assert sorted(
        client.get(f"/api/v1/roadmaps/{roadmap['id']}", headers=headers_a).json()[
            "nodes"
        ],
        key=lambda n: n["id"],
    ) == sorted(roadmap["nodes"], key=lambda n: n["id"])
