"""Measure the resource finder on labelled nodes: Precision@5 (issue #62, spec 15).

Usage::

    python eval/run_resources.py                  # every node in eval/resources.jsonl
    python eval/run_resources.py --limit 3        # the free Gemini tier allows ~20 calls/day

Each line of the file (built in issue #66) is one roadmap node and its labelled URLs::

    {"id": "R01",
     "node": {"title": "Recursion", "outcomes": ["CLO1: ..."], "level": "năm 2 đại học",
              "est_minutes": 90},
     "resources": [{"url": "https://...", "title": "...", "kind": "article", "lang": "en",
                    "label": "good", "reason": "..."}]}

The real fetcher and ``LLM_PROVIDER`` from ``.env`` are used, so a run costs up to 12
judge calls per node.  Precision@5 is the share of shown resources labelled good,
averaged over the nodes that showed any; nodes that abstained are counted apart.
Labels match by canonical URL, so label the address a page finally loads from.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

from app.curator import curate
from app.llm import get_client
from app.search import Candidate, canonical_url
from app.vetting import Learner, Node, SafeFetcher, vet

DATASET = ROOT / "eval" / "resources.jsonl"
TARGET = 0.8


def _inputs(case: dict) -> tuple[Node, Learner, list[Candidate]]:
    node = case["node"]
    candidates = [
        Candidate(row["url"], row.get("title", ""), "benchmark", row.get("kind", "article"),
                  row.get("lang", "vi"))
        for row in case["resources"]
    ]
    return (
        Node(node["title"], tuple(node.get("outcomes", ())), node.get("est_minutes")),
        Learner(level=node.get("level", "")),
        candidates,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, default=DATASET)
    parser.add_argument("--limit", type=int, default=None, help="evaluate the first N nodes")
    args = parser.parse_args()
    if not args.file.is_file():
        print(f"{args.file} not found: the labelled set comes from issue #66.")
        return 1

    load_dotenv(ROOT / ".env")  # LLM_PROVIDER / LLM_API_KEY; real env vars win
    lines = args.file.read_text(encoding="utf-8").splitlines()
    cases = [json.loads(line) for line in lines if line.strip()][: args.limit]
    llm = get_client()
    precisions, abstained = [], []
    print("| node | shown | good | P@5 | status |\n| --- | ---: | ---: | ---: | --- |")
    with SafeFetcher() as fetcher:
        for case in cases:
            node, learner, candidates = _inputs(case)
            good = {canonical_url(row["url"]) for row in case["resources"]
                    if row.get("label") == "good"}
            vetted = vet(candidates, node, learner, llm=llm, fetcher=fetcher)
            curation = curate(vetted.resources, est_minutes=node.est_minutes)
            shown = curation.resources
            hits = sum(canonical_url(resource.url) in good for resource in shown)
            if shown:
                precisions.append(hits / len(shown))
            else:
                abstained.append(case["id"])
            p_at_5 = f"{hits / len(shown):.2f}" if shown else "-"
            print(f"| {case['id']} | {len(shown)} | {hits} | {p_at_5} | {curation.status} |")

    mean = sum(precisions) / len(precisions) if precisions else 0.0
    print(f"\nPrecision@5 = {mean:.3f} over {len(precisions)} nodes (target >= {TARGET})")
    print(f"Abstained ({len(abstained)}): {', '.join(abstained) or '-'}")
    return 0 if mean >= TARGET else 1


if __name__ == "__main__":
    raise SystemExit(main())
