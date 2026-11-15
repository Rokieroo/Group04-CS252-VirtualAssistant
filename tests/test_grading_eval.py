"""The exercise grader marks only against the source's key and meets #115's agreement target."""

import sys
import unicodedata
from pathlib import Path

EVAL = Path(__file__).resolve().parents[1] / "eval"
sys.path.insert(0, str(EVAL))

from run_grading import CASES, EXERCISES, LABELS, TARGET, agreement, read_jsonl

from app.catalog.grading import gradable, grade


def test_benchmark_has_sixty_well_formed_cases_on_real_exercises():
    exercises = {row["id"]: row for row in read_jsonl(EXERCISES)}
    cases = read_jsonl(CASES)
    assert len(cases) == 60 and len({c["id"] for c in cases}) == 60
    assert all(c["exercise"] in exercises and c["response"].strip() for c in cases)
    assert {c["human"] for c in cases} == set(LABELS.values())
    # Every exercise the source gives a key for is marked both right and wrong.
    keyed = {i for i, e in exercises.items() if e["answer"] is not None}
    for label in ("correct", "incorrect"):
        assert keyed == {c["exercise"] for c in cases if c["human"] == label}, label


def test_grader_agrees_with_the_human_grader_on_the_benchmark():
    exercises = {row["id"]: row for row in read_jsonl(EXERCISES)}
    score, misses = agreement(read_jsonl(CASES), exercises)
    assert score >= TARGET, [m["id"] for m in misses]


def test_only_a_short_printed_key_is_ever_marked():
    assert gradable("numeric", "12") and gradable("mcq", "B") and gradable("short", "Third normal form")
    assert not gradable("short", None) and not gradable("short", "  ")
    assert not gradable("proof", "QED") and not gradable("code", "print(1)")
    assert not gradable("short", "A foreign key references a key of another relation")
    assert grade("proof", [], "QED", "QED") is None


def test_options_numbers_and_phrases_are_read_as_a_person_would():
    choices = ["Manual", "Script"]
    assert grade("mcq", choices, "A", "manual") is True
    assert grade("mcq", choices, "A", "(a)") is True
    assert grade("mcq", choices, "B. Script", "b) script") is True
    assert grade("mcq", choices, "A", "A. Script") is False  # letter and wording disagree
    assert grade("mcq", choices, "A", "C") is False  # no such option
    assert grade("numeric", [], "1.2", "6/5 ms") is True
    assert grade("numeric", [], "1.2", "1,2") is True
    assert grade("numeric", [], "20", "4 x 5 = 20") is True
    assert grade("numeric", [], "20", "20 or 30") is False
    assert grade("numeric", [], "20", "no idea") is False
    decomposed = unicodedata.normalize("NFD", "Khoá ngoại")
    assert grade("short", [], "Khoá ngoại", decomposed) is True
