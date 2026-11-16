"""Issue #166 done-when: every placement question is cited, a known concept never has
an unknown prerequisite, and an experienced learner's roadmap shrinks by >= 30%."""

import random
import sys
from itertools import pairwise
from pathlib import Path

import pytest
from conftest import availability, register

from app.roadmap.placement import (
    INFER_DEPTH,
    MAX_QUESTIONS,
    mark_known,
    mark_unknown,
    place,
)
from assistant.backend.models import Source

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
from run_placement import TARGET, evaluate

CHAIN = ["a", "b", "c", "d", "e"]  # a -> b -> c -> d -> e
CHAIN_EDGES = list(pairwise(CHAIN))


def _random_dag(rng, size):
    nodes = [f"n{i}" for i in range(size)]
    edges = [
        (nodes[i], nodes[j])
        for j in range(size)
        for i in range(j)
        if rng.random() < 0.15
    ]
    return nodes, edges


def test_a_known_concept_never_has_a_prerequisite_that_is_not_known():
    rng = random.Random(166)
    for _ in range(300):
        nodes, edges = _random_dag(rng, rng.randint(2, 25))
        parents = {n: {p for p, c in edges if c == n} for n in nodes}
        asked = rng.sample(nodes, rng.randint(0, min(8, len(nodes))))
        answers = {n: rng.random() < 0.6 for n in asked}
        skipped = set(rng.sample(nodes, rng.randint(0, 2))) - set(answers)
        state = place(nodes, edges, answers, skipped)
        assert all(parents[n] <= state.known for n in state.known)
        assert not state.known & {n for n, right in answers.items() if not right}
        # The learner's own corrections keep the same rule.
        node = rng.choice(nodes)
        for update in (mark_known, mark_unknown):
            after = update(nodes, edges, set(state.known), node)
            assert all(parents[n] <= after for n in after)


def test_a_right_answer_vouches_for_near_prerequisites_only():
    # Right on "e": "c" and "d" are inferred, but "a" and "b" are too far to infer,
    # so nothing is known until the far end of the chain is asked.
    state = place(CHAIN, CHAIN_EDGES, {"e": True})
    assert INFER_DEPTH == 2 and state.known == frozenset()
    assert set(state.candidates) == {"a", "b"}
    state = place(CHAIN, CHAIN_EDGES, {"e": True, "b": True})
    assert state.known == set(CHAIN) and state.tested == {"b", "e"}
    assert state.candidates == ()  # settled early, long before ten questions


def test_a_wrong_answer_rules_out_everything_that_needs_it():
    state = place(CHAIN, CHAIN_EDGES, {"c": False})
    assert state.unknown == {"c"} and set(state.candidates) == {"a", "b"}
    assert place(CHAIN, CHAIN_EDGES, {"c": False, "b": True}).known == {"a", "b"}


def test_a_concept_without_an_exercise_is_never_asked_or_guessed():
    state = place(CHAIN, CHAIN_EDGES, {}, skipped={"a"})
    assert "a" not in state.candidates
    # "a" is too far above "d" to infer, and cannot be asked: nothing below it is known.
    assert place(CHAIN, CHAIN_EDGES, {"d": True}, skipped={"a"}).known == set()


def test_at_most_ten_questions_and_most_depended_on_first():
    nodes = [f"n{i}" for i in range(30)]
    assert (
        len(place(nodes, [], {n: True for n in nodes[:MAX_QUESTIONS]}).candidates) == 0
    )
    # One root everything needs and twenty leaves: ask the root's children, which
    # settle the most either way, before any leaf.
    edges = [("root", f"mid{i}") for i in range(3)] + [
        (f"mid{i % 3}", f"leaf{i}") for i in range(20)
    ]
    nodes = ["root", *(f"mid{i}" for i in range(3)), *(f"leaf{i}" for i in range(20))]
    assert place(nodes, edges, {}).candidates[0].startswith("mid")


def test_marking_follows_prerequisites_and_unmarking_follows_dependents():
    assert mark_known(CHAIN, CHAIN_EDGES, set(), "c") == {"a", "b", "c"}
    assert mark_unknown(CHAIN, CHAIN_EDGES, set(CHAIN), "c") == {"a", "b"}


def test_experienced_learners_skip_at_least_thirty_percent_of_the_roadmap():
    report = evaluate()
    assert report["false_known"] == 0 and report["invariant_violations"] == 0
    assert report["max_asked"] <= MAX_QUESTIONS
    assert report["experienced_reduction"] >= TARGET, report


# --- API --------------------------------------------------------------------------

CHAINED = [
    "Sets",
    "Relations",
    "Functions",
]  # strict prerequisite chain, with exercises
TOPICS = [*CHAINED, "Logic"]  # Logic stands alone and has no exercise


@pytest.fixture
def course_roadmap(app, client, headers):
    course = client.post(
        "/api/v1/courses",
        headers=headers,
        json={"title": "Discrete maths", "language": "en"},
    ).json()["id"]
    roadmap = client.post(
        f"/api/v1/courses/{course}/roadmap:generate",
        headers=headers,
        json={
            "nodes": [
                # One week: no week-order edges, only the strict chain added below.
                *({"title": title, "week": 1} for title in TOPICS),
                {"title": "Final", "type": "milestone", "week": 2},
            ]
        },
    ).json()
    ids = {n["title"]: n["id"] for n in roadmap["nodes"]}
    for parent, child in pairwise(CHAINED):
        response = client.post(
            f"/api/v1/roadmaps/{roadmap['id']}/graph/edges",
            headers=headers,
            json={"parent": ids[parent], "child": ids[child], "kind": "strict"},
        )
        assert response.status_code == 201, response.text
    for number, title in enumerate(CHAINED, 1):
        with app.state.database.sessions() as db:
            source = Source(
                course_id=course,
                file_name=f"{title.lower()}.txt",
                page=number,
                text=f"Problems\nExercise {number}: Compute {number} + 10.\nAnswer: {number + 10}",
            )
            db.add(source)
            db.commit()
            source_id = source.id
        response = client.post(
            f"/api/v1/roadmap-nodes/{ids[title]}/materials",
            headers=headers,
            json={"source_id": source_id},
        )
        assert response.status_code == 201, response.text
    return roadmap, ids


def _take(client, headers, roadmap, knows):
    """Answer every question as a learner who knows ``knows``; return the last result."""
    result = client.post(f"/api/v1/roadmaps/{roadmap['id']}/placement", headers=headers)
    assert result.status_code == 200, result.text
    result, questions = result.json(), []
    while result["status"] == "active":
        question = result["question"]
        questions.append(question)
        number = TOPICS.index(question["title"]) + 1
        response = str(number + 10) if question["title"] in knows else "0"
        result = client.post(
            f"/api/v1/placements/{result['id']}/answers",
            headers=headers,
            json={"exercise_id": question["exercise"]["id"], "response": response},
        )
        assert result.status_code == 200, result.text
        result = result.json()
        assert result["last_attempt"]["mode"] == "auto"
    return result, questions


def test_placement_asks_cited_questions_and_the_planner_skips_what_is_known(
    client, headers, course_roadmap
):
    roadmap, ids = course_roadmap
    result, questions = _take(client, headers, roadmap, knows={"Sets", "Relations"})

    assert 0 < len(questions) <= MAX_QUESTIONS
    for question in questions:  # every question has its source and position in it
        exercise = question["exercise"]
        assert exercise["citation"]["source_id"] and exercise["location"].startswith(
            "Exercise"
        )
        assert exercise["origin"] == "user_material" and exercise["auto_grade"]
    assert {q["title"] for q in questions} <= set(CHAINED)
    assert result["skipped"] == [ids["Logic"]]  # no exercise: skipped, not guessed
    assert set(result["known"]) == {ids["Sets"], ids["Relations"]}
    assert result["unknown"] == [ids["Functions"]]
    assert (result["known_minutes"], result["total_minutes"]) == (120, 240)

    graph = client.get(
        f"/api/v1/roadmaps/{roadmap['id']}/graph", headers=headers
    ).json()
    known = {n["title"]: n["known"] for n in graph["nodes"]}
    assert known["Functions"] is known["Logic"] is known["Final"] is None
    assert {known["Sets"], known["Relations"]} <= {"tested", "inferred"}

    availability(client, headers, end="2030-01-07T23:00:00+07:00")
    plan = client.post(
        f"/api/v1/roadmaps/{roadmap['id']}:schedule", headers=headers, json={}
    ).json()
    task_node = {t["id"]: t["roadmap_node_id"] for t in plan["tasks"]}
    planned = {task_node[s["task_id"]] for s in plan["sessions"]}
    planned |= {task_node[u["task_id"]] for u in plan["unscheduled"]}
    assert planned == {ids["Functions"], ids["Logic"], ids["Final"]}

    exported = client.get("/api/v1/me/export", headers=headers).json()
    assert [p["finished_at"] is not None for p in exported["placements"]] == [True]


def test_answers_must_be_for_the_open_question_of_ones_own_placement(
    client, headers, course_roadmap
):
    roadmap, _ = course_roadmap
    started = client.post(
        f"/api/v1/roadmaps/{roadmap['id']}/placement", headers=headers
    ).json()
    resumed = client.post(
        f"/api/v1/roadmaps/{roadmap['id']}/placement", headers=headers
    ).json()
    assert resumed["id"] == started["id"] and resumed["question"] == started["question"]
    url = f"/api/v1/placements/{started['id']}/answers"
    exercise_id = started["question"]["exercise"]["id"]

    stranger = register(client, name="Han", email="han@example.com")
    other = {"Authorization": "Bearer " + stranger["access_token"]}
    body = {"exercise_id": exercise_id, "response": "11"}
    assert client.post(url, headers=other, json=body).status_code == 404
    assert (
        client.post(
            f"/api/v1/roadmaps/{roadmap['id']}/placement", headers=other
        ).status_code
        == 404
    )
    stale = {"exercise_id": "another", "response": "11"}
    assert client.post(url, headers=headers, json=stale).status_code == 409
    assert client.post(url, headers=headers, json=body).status_code == 200
    assert (
        client.post(url, headers=headers, json=body).status_code == 409
    )  # double submit


def test_the_learner_corrects_the_result_without_breaking_prerequisites(
    client, headers, course_roadmap
):
    roadmap, ids = course_roadmap

    def put(title, known):
        return client.put(
            f"/api/v1/roadmap-nodes/{ids[title]}/known",
            headers=headers,
            json={"known": known},
        )

    marked = put("Functions", True).json()
    assert marked["known"] == "learner"
    assert set(marked["changed"]) == {ids["Sets"], ids["Relations"], ids["Functions"]}
    unmarked = put("Relations", False).json()
    assert unmarked["known"] is None
    assert set(unmarked["changed"]) == {ids["Relations"], ids["Functions"]}
    assert put("Final", True).status_code == 422  # a milestone is a test, not a concept

    # A later placement does not ask what the learner already said they know.
    _, questions = _take(client, headers, roadmap, knows=set(TOPICS))
    assert "Sets" not in {q["title"] for q in questions}
