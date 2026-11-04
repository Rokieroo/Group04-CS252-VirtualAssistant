"""The syllabus F1 metric in eval/run_syllabus.py (#59), checked against the real gold files."""

import json
import sys
from pathlib import Path

EVAL = Path(__file__).resolve().parents[1] / "eval"
sys.path.insert(0, str(EVAL))

from run_syllabus import DATASET, FIELDS, f1, score, similar


def as_parsed(gold: dict) -> dict:
    """What a perfect parser returns for a gold file: topics split at commas."""
    return {
        "weeks": [{"week": w["week"], "topics": w["topic"].split(", ")} for w in gold["weeks"]],
        "assessments": [{"title": a["name"], "weight": a["weight"], "due_week": a["due_week"]}
                        for a in gold["assessments"]],
    }


def test_a_perfect_parse_scores_one_on_every_gold_file():
    gold_files = sorted(DATASET.glob("*.gold.json"))
    assert len(gold_files) == 10
    for gold_file in gold_files:
        gold = json.loads(gold_file.read_text(encoding="utf-8"))
        counts = score(as_parsed(gold), gold)
        assert all(f1(counts, name) == 1.0 for name in FIELDS), gold_file.name


def test_wrong_weights_and_missing_weeks_lower_the_score():
    gold = json.loads(next(DATASET.glob("01_*.gold.json")).read_text(encoding="utf-8"))
    parsed = as_parsed(gold)
    parsed["weeks"] = parsed["weeks"][:5]
    parsed["assessments"][0]["weight"] += 10
    counts = score(parsed, gold)
    assert f1(counts, "weeks") == 2 * 5 / (5 + 10)
    assert f1(counts, "weights") == 2 * 2 / (3 + 3)
    assert f1(counts, "milestones") == 1.0


def test_similar_ignores_case_punctuation_and_a_dropped_word():
    assert similar("System Architecture, API Design, Data Modeling, and Defensive Safeguards.",
                   "System architecture, API design, data modeling, defensive safeguards")
    assert not similar("Final Exam", "Midterm Project Milestone")
