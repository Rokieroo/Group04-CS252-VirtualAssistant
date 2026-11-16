"""Measure how much of a roadmap the placement test lets a learner skip (issue #166).

Usage::

    python eval/run_placement.py

Runs the shipped placement (``app.roadmap.placement``) on the prerequisite graphs of
the five gold courses in ``eval/graphs`` against simulated learners. The gold graph
is the test's input, the roadmap a learner would get; nothing here encodes answers.

- An *experienced* learner knows the first half of the course: every concept taught
  in its first half of weeks, plus whatever those concepts need. An *advanced* one
  knows 70%. Both answer every question truthfully.
- Exercise coverage is 100% and 70%: the 30% without a markable exercise are a
  fixed, name-hashed pick, so the run is repeatable.
- A *noisy* experienced learner slips on 10% of what they know and guesses 25% of
  what they do not (one MCQ in four). The invariant must still hold; what the
  guesses wrongly mark known is reported, not asserted.

Every topic counts the same minutes, as on a roadmap generated without durations.
Target: an experienced learner's roadmap shrinks by >= 30% on average, with no
concept marked known that they do not know and none with an unknown prerequisite.

Limitation: these are simulated learners. The issue asks for a real experienced
tester; ``POST /roadmaps/{id}/placement`` reports ``known_minutes`` and
``total_minutes`` so a trial with a person reads the same number.
"""

from __future__ import annotations

import json
import random
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.roadmap.placement import place

GRAPHS = sorted((ROOT / "eval" / "graphs").glob("*.gold.json"))
TARGET = 0.30
COVERAGES = (1.0, 0.7)
PROFILES = {"experienced": 0.5, "advanced": 0.7}
SLIP, GUESS = 0.10, 0.25


def _course(path):
    gold = json.loads(path.read_text(encoding="utf-8"))
    nodes = [c["slug"] for c in gold["concepts"]]
    weeks = {c["slug"]: c["week"] for c in gold["concepts"]}
    parents = {n: set() for n in nodes}
    for edge in gold["edges"]:
        if edge["kind"] == "strict":
            parents[edge["child"]].add(edge["parent"])
    return gold["course_code"], nodes, gold["edges"], weeks, parents


def _learner(nodes, weeks, parents, share):
    """What a learner who studied the first ``share`` of the course knows."""
    cutoff = sorted(weeks.values())[max(0, round(len(nodes) * share) - 1)]
    knows = {n for n in nodes if weeks[n] <= cutoff}
    stack = list(knows)
    while stack:  # whoever knows a concept knows what it needs
        for parent in parents[stack.pop()] - knows:
            knows.add(parent)
            stack.append(parent)
    return knows


def _no_exercise(nodes, coverage):
    ranked = sorted(nodes, key=lambda n: zlib.crc32(n.encode()))
    return set(ranked[: round(len(nodes) * (1 - coverage))])


def run(nodes, edges, knows, missing, answer):
    """One placement as the API runs it: ask the first askable candidate each turn."""
    answers, skipped = {}, set()
    while True:
        state = place(nodes, edges, answers, skipped)
        askable = [n for n in state.candidates if n not in missing]
        skipped |= set(state.candidates) - set(askable)
        if not askable:
            return state, len(answers)
        answers[askable[0]] = answer(askable[0] in knows)


def evaluate():
    rng = random.Random(166)
    rows, violations, false_known, noisy_false, max_asked = [], 0, 0, 0, 0
    for path in GRAPHS:
        code, nodes, edges, weeks, parents = _course(path)
        for profile, share in PROFILES.items():
            knows = _learner(nodes, weeks, parents, share)
            for coverage in COVERAGES:
                missing = _no_exercise(nodes, coverage)
                honest, asked = run(nodes, edges, knows, missing, lambda k: k)
                noisy, _ = run(
                    nodes,
                    edges,
                    knows,
                    missing,
                    lambda k: rng.random() >= SLIP if k else rng.random() < GUESS,
                )
                for state in (honest, noisy):
                    violations += sum(
                        not parents[n] <= state.known for n in state.known
                    )
                false_known += len(honest.known - knows)
                noisy_false += len(noisy.known - knows)
                max_asked = max(max_asked, asked)
                rows.append(
                    {
                        "course": code,
                        "profile": profile,
                        "coverage": coverage,
                        "concepts": len(nodes),
                        "knows": len(knows),
                        "asked": asked,
                        "known": len(honest.known),
                        "reduction": len(honest.known) / len(nodes),
                        "noisy_known": len(noisy.known),
                    }
                )
    experienced = [r["reduction"] for r in rows if r["profile"] == "experienced"]
    return {
        "rows": rows,
        "experienced_reduction": sum(experienced) / len(experienced),
        "experienced_min": min(experienced),
        "invariant_violations": violations,
        "false_known": false_known,
        "noisy_false_known": noisy_false,
        "max_asked": max_asked,
    }


def main() -> int:
    report = evaluate()
    print(
        f"{'course':8} {'profile':12} {'cover':>5} {'asked':>5} {'known':>9} {'cut':>5}"
    )
    for r in report["rows"]:
        print(
            f"{r['course']:8} {r['profile']:12} {r['coverage']:>5.0%} {r['asked']:>5} "
            f"{r['known']:>3}/{r['knows']:>2}/{r['concepts']:>2} {r['reduction']:>5.0%}"
        )
    print(
        f"Experienced roadmap cut: {report['experienced_reduction']:.0%} on average, "
        f"{report['experienced_min']:.0%} at worst (target {TARGET:.0%}); "
        f"at most {report['max_asked']} questions"
    )
    print(
        f"Known with an unknown prerequisite: {report['invariant_violations']}; "
        f"marked known but not known: {report['false_known']} truthful, "
        f"{report['noisy_false_known']} with slips and guesses"
    )
    ok = (
        report["experienced_reduction"] >= TARGET
        and report["invariant_violations"] == 0
        and report["false_known"] == 0
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
