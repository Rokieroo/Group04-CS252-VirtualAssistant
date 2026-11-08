"""Syllabus parser (#59): anchors, cite-or-refuse cleaning, checks and not_a_syllabus, offline."""

import json
from datetime import date

import pytest

from app.llm import FakeLLM
from app.syllabus import NotASyllabus, check_syllabus, extract_syllabus
from app.syllabus.anchors import (
    find_anchors,
    looks_like_syllabus,
    parse_date,
    textbook_lines,
)
from app.syllabus.extract import parse_answer

PAGES = [
    ("ĐỀ CƯƠNG HỌC PHẦN CSC10014 - Nhập môn trợ lý ảo, 4 tín chỉ. Học kỳ 07/09/2026 - "
     "20/12/2026.\nCLO1: Phát biểu bài toán. CLO 2: Chọn bậc giải pháp."),
    ("Tuần 1: Problem framing, Solution ladder\nWeek 2: Use cases\n"
     "Giữa kỳ 30% (tuần 8), Cuối kỳ 70% ngày 15/12/2026"),
]


def course(**changes):
    return {"code": "CSC10014", "title": "Nhập môn trợ lý ảo", "credits": 4,
            "term_start": "2026-09-07", "term_end": "2026-12-20", "language": "vi",
            "source_page": 1, **changes}


def week(number, *topics, page=2):
    return {"week": number, "topics": list(topics), "readings": [], "source_page": page}


def assessment(title, weight, due_week=None, due_date=None, page=2):
    return {"title": title, "kind": "midterm", "weight": weight, "due_week": due_week,
            "due_date": due_date, "source_page": page}


def outcome(code, page=1):
    return {"code": code, "text": "Phát biểu bài toán", "bloom_level": "apply", "source_page": page}


def answer(**parts):
    data = {"document_kind": "syllabus", "course": course(), "textbooks": [],
            "outcomes": [outcome("CLO1")],
            "weeks": [week(1, "Problem framing", "Solution ladder"), week(2, "Use cases")],
            "assessments": [assessment("Giữa kỳ", 30, due_week=8),
                            assessment("Cuối kỳ", 70, due_date="2026-12-15")],
            **parts}
    return json.dumps(data, ensure_ascii=False)


def test_anchors_read_vietnamese_weeks_dates_percents_and_clos():
    first, second = find_anchors(PAGES)
    assert first.clos == ("CLO1", "CLO2")
    assert first.dates == (date(2026, 9, 7), date(2026, 12, 20))
    assert second.weeks == (1, 2, 8)
    assert second.percents == (30.0, 70.0)
    assert "[Page 2] weeks 1, 2, 8 | 30%, 70%" in second.describe()


def test_dates_are_day_first_and_invalid_ones_are_skipped():
    assert parse_date("07/09/2026") == date(2026, 9, 7)
    assert parse_date("2026-09-07") == date(2026, 9, 7)
    assert parse_date("31/02/2026") is None
    assert parse_date(None) is None


def test_textbook_section_ends_at_the_first_blank_line():
    text = ("Week 1: Intro\nTextbooks:\n\n1. Introduction to Algorithms\n2. Clean Code\n\n"
            "Assessment: Final 50%\nCalculus review")
    assert textbook_lines(text) == ["1. Introduction to Algorithms", "2. Clean Code"]
    assert textbook_lines("Giáo trình: Tư duy tính toán\nTuần 1") == [
        "Tư duy tính toán", "Tuần 1"]
    assert textbook_lines("Week 1: references are optional") == []


def test_slide_text_is_not_a_syllabus_without_an_llm_call():
    llm = FakeLLM()
    slides = ["Lecture 3: Binary search trees", "Insert and delete run in O(log n). 07/10/2026"]
    assert not looks_like_syllabus(find_anchors(slides))
    with pytest.raises(NotASyllabus):
        extract_syllabus(llm, slides)
    assert llm.calls == 0


@pytest.mark.parametrize("weeks", [[], [week(1, "Problem Framing for Real-World Systems")]])
def test_model_that_finds_no_schedule_means_not_a_syllabus(weeks):
    """A slide deck titled "Week 01" yields one week and nothing else: still not a syllabus."""
    lecture = answer(outcomes=[], weeks=weeks, assessments=[])
    with pytest.raises(NotASyllabus):
        extract_syllabus(FakeLLM({"<document_text>": lecture}), PAGES)


def test_lecture_deck_with_invented_codes_and_weights_is_not_a_syllabus():
    """The model turns "Learning objectives" into CLO1 and a deliverable into a 100% weight;
    neither is written on the slides, so both are emptied and nothing is left as evidence."""
    slides = ["Week 02: Use cases. Learning objectives: model actors and goals",
              "Milestone 1: submit the project brief after 5 interviews"]
    lecture = answer(weeks=[week(2, "Use cases", page=1)], outcomes=[outcome("CLO1")],
                     assessments=[assessment("Milestone 1", 100, due_week=2)])
    with pytest.raises(NotASyllabus):
        extract_syllabus(FakeLLM({"<document_text>": lecture}), slides)


def test_one_rubric_row_taken_as_a_weight_is_not_a_grading_scheme():
    """The model read "Milestone 1" off a rubric row worth 20%: 20 is written there, but
    one weight alone is not a grading scheme."""
    slides = ["Decomposition and use cases",
              "Rubric Milestone 1: Problem & evidence 20%, Use-case diagram 25%"]
    lecture = answer(weeks=[], outcomes=[], assessments=[assessment("Milestone 1", 20)])
    with pytest.raises(NotASyllabus):
        extract_syllabus(FakeLLM({"<document_text>": lecture}), slides)


def test_one_week_deck_with_a_full_rubric_is_not_a_syllabus():
    """Week02/Week03 slides: the model called them a syllabus, with their own week and a
    rubric or homework split that sums to 100%. A syllabus never schedules one week only."""
    slides = ["Week 03: Pitfalls and pipelines",
              "Homework: HW1 15%, HW2 25%, HW3 20%, HW4 20%, HW5 20%"]
    weights = [("HW1", 15), ("HW2", 25), ("HW3", 20), ("HW4", 20), ("HW5", 20)]
    lecture = answer(weeks=[week(3, "Pitfalls", page=1)], outcomes=[],
                     assessments=[assessment(title, w, due_week=4) for title, w in weights])
    with pytest.raises(NotASyllabus):
        extract_syllabus(FakeLLM({"<document_text>": lecture}), slides)


def test_document_the_model_classifies_as_slides_is_not_a_syllabus():
    slides = answer(document_kind="lecture_slides")
    with pytest.raises(NotASyllabus, match="lecture_slides"):
        extract_syllabus(FakeLLM({"<document_text>": slides}), PAGES)


def test_a_schedule_alone_is_enough():
    schedule = answer(outcomes=[], assessments=[])
    assert len(extract_syllabus(FakeLLM({"<document_text>": schedule}), PAGES).parsed["weeks"]) == 2


def test_extract_returns_cited_parts_without_warnings():
    draft = extract_syllabus(FakeLLM({"<syllabus_anchors>": answer()}), PAGES)
    assert draft.warnings == [] and not draft.blocking
    assert draft.parsed["course"]["code"] == "CSC10014"
    assert [w["week"] for w in draft.parsed["weeks"]] == [1, 2]
    assert draft.parsed["assessments"][1]["due_date"] == "2026-12-15"
    assert all(item["source_page"] in (1, 2) for part in ("outcomes", "weeks", "assessments")
               for item in draft.parsed[part])


def test_values_without_a_shown_page_are_dropped_or_left_empty():
    raw = answer(course=course(source_page=9),
                 weeks=[week(1, "Problem framing"), week(2, "Use cases", page=None),
                        week(3, page=2)])
    parsed, dropped = parse_answer(raw, PAGES)
    assert parsed["course"] == dict.fromkeys(parsed["course"])  # every field left empty
    assert [w["week"] for w in parsed["weeks"]] == [1]
    assert dropped == 3  # the course, the uncited week and the week without topics


def test_codes_and_weights_not_written_on_their_page_are_emptied():
    raw = answer(outcomes=[outcome("CLO2"), outcome("CLO7")],
                 assessments=[assessment("Giữa kỳ", 30, due_week=8),
                              assessment("Đồ án", 40, due_week=9)])
    parsed, dropped = parse_answer(raw, PAGES)
    assert [o["code"] for o in parsed["outcomes"]] == ["CLO2", None]  # "CLO 2" is written
    assert [a["weight"] for a in parsed["assessments"]] == [30, None]
    assert dropped == 2


def test_dropped_values_become_a_warning():
    raw = answer(weeks=[week(1, "Problem framing"), week(2, "Use cases", page=7)])
    draft = extract_syllabus(FakeLLM({"<document_text>": raw}), PAGES)
    assert [w.code for w in draft.warnings] == ["missing_source"]


def test_unusable_answer_raises_value_error():
    with pytest.raises(ValueError, match="JSON object"):
        parse_answer("[]", PAGES)
    with pytest.raises(ValueError):
        parse_answer("not json", PAGES)


def test_checks_flag_blocking_weights_and_dates_outside_the_term():
    parsed = json.loads(answer(assessments=[
        assessment("Giữa kỳ", 30, due_week=8),
        assessment("Cuối kỳ", 60, due_date="2027-01-10"),
    ]))
    warnings = {w.code: w for w in check_syllabus(parsed)}
    assert warnings["weights_sum"].blocking and "90%" in warnings["weights_sum"].message
    assert warnings["date_outside_term"].blocking


def test_weights_within_one_point_of_100_pass():
    parsed = json.loads(answer(assessments=[assessment("A", 33.3, due_week=4),
                                            assessment("B", 66.0, due_week=9)]))
    assert check_syllabus(parsed) == []


def test_checks_flag_week_order_repeated_topics_and_undated_assessments():
    parsed = json.loads(answer(
        weeks=[week(2, "Use cases"), week(1, "Problem framing"), week(3, "use cases!")],
        assessments=[assessment("Đồ án", 100)],
    ))
    warnings = check_syllabus(parsed)
    assert [w.code for w in warnings] == ["weeks_order", "topic_repeated",
                                          "assessment_without_due"]
    assert not any(w.blocking for w in warnings)
