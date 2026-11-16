"""Issue #163 done-when, offline (``LLM_PROVIDER=fake``): node Q&A citations and answer leaks.

Usage::

    python eval/run_qa.py

1. Every UC-12 case in ``eval/benchmark.jsonl`` is asked over the fixture pages of
   ``eval/run_retrieval.py``. A ``normal`` case counts only when an answer cites the
   case's expected file and page with a quote found verbatim on that page; a
   ``missing_knowledge`` or ``privacy`` case counts only when nothing is cited.
   Target: >= 90% of at least 30 cases.
2. Each of the 30 attacks in ``eval/fixtures/redteam/answer_leaks.jsonl`` asks for
   every hint level, on its graded item before and after an attempt and on a
   practice item before an attempt. The ladder takes no free text, so an attack's
   wording has no channel; what is measured is that no hint carries the source's
   answer or solution where the policy forbids it. Target: 0 leaks.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))
os.environ.setdefault("LLM_PROVIDER", "fake")

from run_retrieval import FIXTURE_SOURCES

from app.qa import answer_question, exercise_hint

BENCHMARK = ROOT / "eval" / "benchmark.jsonl"
ANSWER_LEAKS = ROOT / "eval" / "fixtures" / "redteam" / "answer_leaks.jsonl"
CITATION_TARGET = 0.90
MIN_QUESTIONS = 30

# A practice item with its source's key, so a leak is a substring anyone can check.
EXERCISE = SimpleNamespace(
    answer="42 giờ",
    solution_ref="Tổng chi phí = 3 bậc x 14 giờ = 42 giờ",
    location="Exercise 3:",
)
CITATION = {"title": "problems.pdf", "page": 2}
ATTEMPT = SimpleNamespace(response="40 giờ")


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _cited_right(case: dict[str, Any], answer: Any) -> bool:
    file_name, page = case["source"].rsplit("#", 1)
    pages = {(s["file_name"], s["page"]): s["text"] for s in FIXTURE_SOURCES}
    return any(
        (c.file_name, c.page) == (file_name, int(page))
        and " ".join(c.quote.split()).casefold()
        in " ".join(pages[(c.file_name, c.page)].split()).casefold()
        for c in answer.citations
    )


def evaluate_questions(path: Path = BENCHMARK) -> dict[str, Any]:
    results = []
    for case in _rows(path):
        if case["use_case"] != "UC-12":
            continue  # generation (UC-10) and companion (UC-14) cases are not questions
        answer = answer_question(case["question"], FIXTURE_SOURCES)
        correct = _cited_right(case, answer) if case["kind"] == "normal" else not answer.found
        results.append(
            {
                "id": case["id"],
                "kind": case["kind"],
                "correct": correct,
                "answer": answer.text,
                "cited": [f"{c.file_name}#{c.page}" for c in answer.citations],
            }
        )
    correct = sum(r["correct"] for r in results)
    accuracy = correct / len(results) if results else 0.0
    return {
        "total": len(results),
        "correct": correct,
        "accuracy": accuracy,
        "passed": len(results) >= MIN_QUESTIONS and accuracy >= CITATION_TARGET,
        "results": results,
    }


def _leaks(content: str) -> bool:
    return EXERCISE.answer in content or EXERCISE.solution_ref in content


def evaluate_leaks(path: Path = ANSWER_LEAKS) -> dict[str, Any]:
    # Positive control: the one case where the policy allows the solution must show it,
    # or a leak detector that never fires would report 0.
    control = exercise_hint(
        EXERCISE, CITATION, level=3, graded=False, attempts=[ATTEMPT], concept="Chi phí"
    )
    assert _leaks(control.content), "level 3 after an attempt must show the source's solution"
    results = []
    for attack in _rows(path):
        graded = attack["assessment_type"] != "practice"
        trials = [(graded, []), (graded, [ATTEMPT] if graded else []), (False, [])]
        leaked = [
            level
            for level in (1, 2, 3)
            for is_graded, attempts in trials
            if _leaks(
                exercise_hint(
                    EXERCISE,
                    CITATION,
                    level=level,
                    graded=is_graded,
                    attempts=attempts,
                    concept="Chi phí",
                ).content
            )
        ]
        results.append({"id": attack["id"], "category": attack["category"], "leaked_levels": leaked})
    leaks = sum(bool(r["leaked_levels"]) for r in results)
    return {"total": len(results), "leaks": leaks, "passed": leaks == 0, "results": results}


def main() -> int:
    questions = evaluate_questions()
    print(f"UC-12 cited correctly: {questions['correct']}/{questions['total']} "
          f"({questions['accuracy']:.1%}; target >= {CITATION_TARGET:.0%} of >= {MIN_QUESTIONS})")
    for r in questions["results"]:
        if not r["correct"]:
            print(f"  MISS {r['id']} ({r['kind']}): cited {r['cited'] or 'nothing'}")
    leaks = evaluate_leaks()
    print(f"Answer-leak attacks: {leaks['leaks']}/{leaks['total']} leaked (target 0)")
    passed = questions["passed"] and leaks["passed"]
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
