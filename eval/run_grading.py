"""Measure how often the exercise grader agrees with a human grader (issue #115).

Usage::

    python eval/run_grading.py

Each case in ``eval/grading.jsonl`` is a learner response to one exercise of
``eval/exercises.jsonl`` and the mark a human grader gives it:

- ``correct``: it gives the source's own answer and nothing else, whatever the
  case, spacing, units or working shown, and an option by its letter or wording;
- ``incorrect``: a wrong value, another option, or a hedge between answers;
- ``self_check``: the source prints no short answer to mark against, so the
  learner compares their work with the source.

The labels were written from these rules before the grader was run on them and
include responses a person accepts that no string match can ("thirty").
Target: >= 85% of the 60 marks agree.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.catalog.grading import grade

CASES = ROOT / "eval" / "grading.jsonl"
EXERCISES = ROOT / "eval" / "exercises.jsonl"
LABELS = {True: "correct", False: "incorrect", None: "self_check"}
TARGET = 0.85


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def mark(case: dict, exercises: dict[str, dict]) -> str:
    """The grader's mark for one case, in the human labels' vocabulary."""
    exercise = exercises[case["exercise"]]
    return LABELS[
        grade(exercise["type"], exercise["choices"], exercise["answer"], case["response"])
    ]


def agreement(cases: list[dict], exercises: dict[str, dict]) -> tuple[float, list[dict]]:
    """Share of cases where grader and human agree, and the cases where they do not."""
    misses = [c for c in cases if mark(c, exercises) != c["human"]]
    return 1 - len(misses) / len(cases), misses


def main() -> int:
    exercises = {row["id"]: row for row in read_jsonl(EXERCISES)}
    cases = read_jsonl(CASES)
    score, misses = agreement(cases, exercises)
    for case in misses:
        print(
            f"{case['id']} {case['exercise']}: {case['response']!r} "
            f"human={case['human']} grader={mark(case, exercises)}"
        )
    print(f"Agreement: {score:.1%} on {len(cases)} cases (target {TARGET:.0%})")
    return 0 if score >= TARGET else 1


if __name__ == "__main__":
    raise SystemExit(main())
