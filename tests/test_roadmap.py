"""Syllabus parsing and roadmap node rules (#63), without HTTP or a database."""

from datetime import UTC, datetime

from app.roadmap import NodeSpec, decode_covers, derive_nodes, link, node_spec
from app.syllabus import AssessmentItem, Outcome, parse_syllabus


def test_syllabus_aliases_become_one_shape():
    payload = {
        "text": " Week 1: Framing ",
        "outcomes": ["Frame a problem", {"code": "CLO2", "title": "Choose a rung"}],
        "assessments": [{"title": "Midterm", "weight": "30%", "due": "tuần 8"}, "Final"],
    }
    parts = parse_syllabus(payload, set(payload))
    assert parts.raw_text == "Week 1: Framing"
    assert parts.outcomes == [
        Outcome("CLO1", "Frame a problem"), Outcome("CLO2", "Choose a rung")]
    assert parts.assessments == [AssessmentItem("Midterm", 30.0, 8), AssessmentItem("Final")]


def test_omitted_parts_are_left_alone_and_empty_lists_clear():
    kept = parse_syllabus({"raw_text": "new", "outcomes": []}, {"raw_text"})
    assert (kept.raw_text, kept.outcomes, kept.assessments) == ("new", None, None)
    cleared = parse_syllabus({"assessments": []}, {"assessments"})
    assert (cleared.raw_text, cleared.assessments) == (None, [])


def test_parsed_block_is_read_when_top_level_fields_are_absent():
    parsed = {"outcomes": [{"code": "CLO1", "text": "Explain"}], "assessments": []}
    parts = parse_syllabus({"parsed": parsed}, {"parsed"})
    assert parts.outcomes == [Outcome("CLO1", "Explain")]
    assert parts.assessments == []
    assert parts.raw_text.startswith("{")  # no text given: the parsed JSON is kept


def test_nodes_derive_from_outcomes_and_assessments_else_week_lines():
    assert derive_nodes(["Framing"], [("Midterm", 8)], "") == [
        NodeSpec("topic", "Framing"), NodeSpec("milestone", "Midterm", week=8)]
    assert derive_nodes([], [], "Week 2: Search; BM25.\nnoise") == [
        NodeSpec("topic", "Search", week=2), NodeSpec("topic", "BM25", week=2)]


def test_link_assigns_new_ids_and_milestones_cover_earlier_topics():
    first, second, exam, late = link([
        node_spec({"title": "A", "id": "client-chosen"}),
        node_spec({"kind": "topic", "title": "B", "est_minutes": "45"}),
        node_spec({"type": "milestone", "title": "Midterm"}),
        node_spec({"type": "bogus", "title": "C", "covers": "x, y"}),
    ])
    assert first.id != "client-chosen" and len({first.id, second.id, exam.id}) == 3
    assert (first.duration_minutes, second.duration_minutes, exam.duration_minutes) == (
        60, 45, 30)
    assert exam.covers == [first.id, second.id]
    assert (late.kind, late.covers) == ("topic", ["x", "y"])


def test_naive_due_dates_are_read_as_utc_and_covers_decode():
    naive = node_spec({"title": "A", "due_at": datetime(2030, 1, 7, 9)})
    assert naive.due_at == datetime(2030, 1, 7, 9, tzinfo=UTC)
    assert decode_covers('["n1", 2]') == ["n1", "2"]
    assert decode_covers(None) == []
