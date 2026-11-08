"""Measure how well a learner's slides are attached to roadmap nodes (issue #114).

Usage::

    python eval/run_materials.py --slides ../../Theory/Slides          # offline
    python eval/run_materials.py --slides ../../Theory/Slides --llm    # + one LLM call per deck

The CSC10014 week 1-3 decks are course material and are not committed; pass the
folder that holds them. Nodes are what roadmap:generate derives from the CSC10014
syllabus gold (one topic per learning outcome); milestones take no material.

A slide is attached correctly when its node is one the gold accepts for it
(``eval/materials.json``); slides gold marks as teaching nothing are left out.
Target: >= 85% of slides attached correctly. "Auto" counts the slides at or above
review confidence, which need no confirmation from the learner.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.ingest import extract_pages
from app.materials import REVIEW, Node, map_pages
from app.roadmap import derive_nodes, link

GOLD = ROOT / "eval" / "materials.json"
TARGET = 0.85


def nodes_and_codes(gold: dict) -> tuple[list[Node], dict[str, str]]:
    """Topic nodes of the CSC10014 roadmap and node id -> learning outcome code."""
    syllabus = json.loads((ROOT / "eval" / "syllabus" / gold["syllabus"]).read_text("utf-8"))
    code = {row["description"]: row["code"] for row in syllabus["learning_outcomes"]}
    specs = [s for s in link(derive_nodes(list(code), [], "")) if s.kind == "topic"]
    return [Node(s.id, s.title) for s in specs], {s.id: code[s.title] for s in specs}


def score(matches, ranges, codes) -> tuple[int, int, int, int]:
    """(correct, gradable, auto-accepted, auto-accepted and correct) for one deck."""
    accepted = {page: ok for start, end, ok in ranges for page in range(start, end + 1)}
    by_page = {m.page: m for m in matches}
    gradable = [page for page, ok in accepted.items() if ok]
    right = [p for p in gradable if p in by_page and codes[by_page[p].node_id] in accepted[p]]
    auto = [p for p in gradable if p in by_page and by_page[p].confidence >= REVIEW]
    return len(right), len(gradable), len(auto), len(set(auto) & set(right))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--slides", type=Path, required=True, help="folder of the decks")
    parser.add_argument("--llm", action="store_true", help="use LLM_PROVIDER from .env")
    args = parser.parse_args()
    llm = None
    if args.llm:
        from dotenv import load_dotenv

        from app.llm import get_client

        load_dotenv(ROOT / ".env")
        llm = get_client()
    gold = json.loads(GOLD.read_text("utf-8"))
    nodes, codes = nodes_and_codes(gold)
    totals = [0, 0, 0, 0]
    for deck, ranges in gold["decks"].items():
        pages = extract_pages((args.slides / deck).read_bytes())
        counts = score(map_pages(pages, nodes, llm=llm), ranges, codes)
        totals = [a + b for a, b in zip(totals, counts, strict=True)]
        print(f"  {deck:66} {counts[0]:3}/{counts[1]:3}")
    right, gradable, auto, auto_right = totals
    accuracy = right / gradable
    print(f"Slides attached correctly: {right}/{gradable} = {accuracy:.0%} (target {TARGET:.0%})")
    print(f"Auto-accepted: {auto} slides, {auto_right / max(1, auto):.0%} of them correct")
    print("PASS" if accuracy >= TARGET else "FAIL")
    return 0 if accuracy >= TARGET else 1


if __name__ == "__main__":
    raise SystemExit(main())
