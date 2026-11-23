"""Epic #94, done-when 1: a real syllabus, reviewed and confirmed, opens as a graph of
every topic and assessment of the course, ordered by week."""

from pathlib import Path

import pytest

SYLLABI = sorted((Path(__file__).resolve().parents[1] / "eval/syllabus").glob("*.txt"))


def confirmed_graph(client, headers, text):
    """Parse, confirm as the review screen does (the parsed draft), generate, read the graph."""
    course = client.post("/api/v1/courses", headers=headers, json={"title": "Course"}).json()
    base = f"/api/v1/courses/{course['id']}"
    parsed = client.post(base + "/syllabus:parse", headers=headers, json={"text": text}).json()[
        "parsed"
    ]
    syllabus = client.post(base + "/syllabus", headers=headers, json={"parsed": parsed})
    assert syllabus.status_code == 201, syllabus.text
    roadmap = client.post(
        base + "/roadmap:generate", headers=headers, json={"syllabus_id": syllabus.json()["id"]}
    ).json()
    graph = client.get(f"/api/v1/roadmaps/{roadmap['id']}/graph", headers=headers).json()
    return parsed, roadmap, graph


@pytest.mark.parametrize("path", SYLLABI, ids=[p.stem for p in SYLLABI])
def test_graph_shows_every_week_topic_and_assessment_in_week_order(client, headers, path):
    parsed, roadmap, graph = confirmed_graph(client, headers, path.read_text(encoding="utf-8"))
    topics = [(n["week"], n["title"]) for n in graph["nodes"] if n["type"] == "topic"]
    reviewed = [(w["week"], title) for w in parsed["weeks"] for title in w["topics"]]
    assert sorted(topics) == sorted(reviewed) and len({w for w, _ in topics}) >= 10
    milestones = [n["title"] for n in graph["nodes"] if n["type"] == "milestone"]
    assert sorted(milestones) == sorted(a["title"] for a in parsed["assessments"])

    weeks = [n["week"] for n in roadmap["nodes"] if n["week"] is not None]
    assert weeks == sorted(weeks)  # the roadmap reads week by week
    week_of = {n["id"]: n["week"] for n in graph["nodes"]}
    for edge in graph["edges"]:
        if edge["kind"] == "covers":  # an assessment covers only what was taught by then
            assert week_of[edge["parent"]] <= week_of[edge["child"]], edge


def test_csc10014_weeks_keep_the_outcomes_they_name(client, headers):
    """The CLO filter and node panel read ``outcome_ids``; a week names its outcomes'
    terms ("Solution Ladder"), and a week naming none stays unlinked rather than guessed."""
    path = next(p for p in SYLLABI if p.stem.startswith("01_csc10014"))
    _, roadmap, graph = confirmed_graph(client, headers, path.read_text(encoding="utf-8"))
    syllabus = client.get(f"/api/v1/courses/{roadmap['course_id']}/syllabus", headers=headers)
    code_of = {o["id"]: o["code"] for o in syllabus.json()["learning_outcomes"]}
    linked = {
        n["week"]: sorted(code_of[i] for i in n["outcome_ids"])
        for n in graph["nodes"]
        if n["type"] == "topic"
    }
    assert {week: linked[week] for week in (1, 2, 3)} == {
        1: ["CLO1", "CLO2"], 2: ["CLO3"], 3: ["CLO4"]
    }
    assert linked[4] == []
