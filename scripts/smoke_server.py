"""Smoke-test a running server end to end over HTTP (issue #18).

Registers a throwaway learner, uploads the CSC10014 benchmark syllabus, confirms it,
builds the roadmap, reads the knowledge graph, saves a layout and tries an edge that
would close a cycle (must be refused with 409). Every step writes rows, so running it
against the API logged in as ``pathly_app`` proves that role has what it needs.

    python scripts/smoke_server.py https://learn.example.edu.vn
    python scripts/smoke_server.py http://127.0.0.1:8000

Exit code 0 means every step passed. Uses only the standard library and httpx.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import httpx

SYLLABUS = Path(__file__).resolve().parents[1] / "eval/syllabus/01_csc10014_problem_framing.txt"


def step(name: str, response: httpx.Response, *expected: int) -> dict:
    ok = response.status_code in expected
    print(f"{'ok ' if ok else 'FAIL'} {response.status_code} {name}")
    if not ok:
        print(response.text[:500])
        raise SystemExit(1)
    return response.json() if response.content else {}


def main(base: str) -> None:
    api = httpx.Client(base_url=base.rstrip("/") + "/api/v1", timeout=60)
    step("health", api.get("/health"), 200)

    email = f"smoke-{uuid.uuid4().hex[:10]}@example.com"
    token = step(
        "register",
        api.post(
            "/auth/register",
            json={"name": "Smoke Test", "email": email,
                  "password": "smoke-test-password-2026", "birth_year": 2003},
        ),
        201,
    )["access_token"]
    api.headers["Authorization"] = f"Bearer {token}"

    course = step(
        "create course",
        api.post("/courses", json={"title": "Smoke CSC10014", "level": "university",
                                   "language": "en"}),
        201,
    )
    cid = course["id"]
    step(
        "upload syllabus",
        api.post(f"/courses/{cid}/sources", data={"kind": "syllabus"},
                 files={"file": (SYLLABUS.name, SYLLABUS.read_bytes(), "text/plain")}),
        201,
    )
    preview = step(
        "parse syllabus",
        api.post(f"/courses/{cid}/syllabus:parse",
                 json={"file_name": SYLLABUS.name, "use_llm": False}),
        200,
    )["parsed"]
    syllabus = step(
        "confirm syllabus",
        api.post(f"/courses/{cid}/syllabus", json={
            "raw_text": "\n".join(f"Week {w.get('week', i + 1)}: {w.get('topic', '')}"
                                  for i, w in enumerate(preview["weeks"])),
            "outcomes": [{"code": o.get("code") or f"CLO{i + 1}",
                          "description": o.get("description") or o.get("text") or "outcome"}
                         for i, o in enumerate(preview["outcomes"])],
            "assessments": [{"name": "Midterm", "weight": 40.0, "due_week": 5},
                            {"name": "Final", "weight": 60.0, "due_week": 10}],
        }),
        201,
    )
    roadmap = step(
        "generate roadmap",
        api.post(f"/courses/{cid}/roadmap:generate", json={"syllabus_id": syllabus["id"]}),
        201,
    )
    rid = roadmap["id"]
    graph = step("read graph", api.get(f"/roadmaps/{rid}/graph"), 200)
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    print(f"     graph: {len(nodes)} nodes, {len(edges)} edges")

    layout = {"positions": [{"node_id": n["id"], "x": i * 40.0, "y": 0.0}
                            for i, n in enumerate(nodes)]}
    step("save layout", api.put(f"/roadmaps/{rid}/graph/layout", json=layout), 200, 204)

    if edges:
        edge = edges[0]
        parent = edge["parent"]
        child = edge["child"]
        step(
            "reject cycle",
            api.post(f"/roadmaps/{rid}/graph/edges",
                     json={"parent_id": child, "child_id": parent, "kind": "strict"}),
            409,
        )
    step("node sources", api.get(f"/roadmaps/{rid}/sources:summary"), 200)
    print("smoke test passed")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000")
