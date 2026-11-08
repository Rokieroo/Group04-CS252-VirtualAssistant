"""Measure the syllabus parser on the labelled syllabi: F1 per field (issue #59, spec 9).

Usage::

    python eval/run_syllabus.py                     # every *.gold.json in eval/syllabus/
    python eval/run_syllabus.py --limit 3           # the free Gemini tier allows ~20 calls/day
    python eval/run_syllabus.py --refuse slides.pdf # also check a file is not_a_syllabus

Each gold file (built in issue #66) sits next to its document under the same stem; the
PDF or DOCX is read when there is one, else the .txt, so every ingest format is used.
Four fields are scored, per syllabus and micro-averaged over all of them:

- weeks: the week numbers;
- topics: a week's topics joined, against the gold topic of the same week;
- milestones: an assessment title with its due week;
- weights: an assessment title with its weight (± 0.5).

Titles and topics match when their word sets overlap by at least 0.7 (Dice), so splitting
a week's topics at commas or dropping an "and" is not a miss. ``LLM_PROVIDER`` from
``.env`` is used: one call per syllabus.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

from app.concepts import comparison_key
from app.ingest import detect_media_type, extract_pages
from app.llm import RetryableError, get_client
from app.syllabus import NotASyllabus, extract_syllabus

DATASET = ROOT / "eval" / "syllabus"
FIELDS = ("weeks", "topics", "milestones", "weights")
TARGET = 0.9
SIMILAR = 0.7


def similar(a: str, b: str) -> bool:
    words_a, words_b = set(comparison_key(a).split()), set(comparison_key(b).split())
    if not words_a or not words_b:
        return False
    return 2 * len(words_a & words_b) / (len(words_a) + len(words_b)) >= SIMILAR


def _matched(predicted: list, gold: list, same) -> int:
    """Greedy one-to-one matches between the two lists."""
    left, hits = list(gold), 0
    for item in predicted:
        found = next((g for g in left if same(item, g)), None)
        if found is not None:
            left.remove(found)
            hits += 1
    return hits


def score(parsed: dict, gold: dict) -> Counter:
    """True positives, predicted and gold counts per field, e.g. ``topics_tp``."""
    weeks = parsed["weeks"]
    tests = parsed["assessments"]
    pairs = {
        "weeks": ([w["week"] for w in weeks], [w["week"] for w in gold["weeks"]],
                  lambda p, g: p == g),
        "topics": ([(w["week"], ", ".join(w["topics"])) for w in weeks],
                   [(w["week"], w["topic"]) for w in gold["weeks"]],
                   lambda p, g: p[0] == g[0] and similar(p[1], g[1])),
        "milestones": ([(a["title"], a["due_week"]) for a in tests],
                       [(a["name"], a["due_week"]) for a in gold["assessments"]],
                       lambda p, g: p[1] == g[1] and similar(p[0], g[0])),
        "weights": ([(a["title"], a["weight"]) for a in tests],
                    [(a["name"], a["weight"]) for a in gold["assessments"]],
                    lambda p, g: p[1] is not None and abs(p[1] - g[1]) <= 0.5
                    and similar(p[0], g[0])),
    }
    counts: Counter = Counter()
    for name, (predicted, expected, same) in pairs.items():
        counts[f"{name}_tp"] += _matched(predicted, expected, same)
        counts[f"{name}_pred"] += len(predicted)
        counts[f"{name}_gold"] += len(expected)
    return counts


def f1(counts: Counter, name: str) -> float:
    total = counts[f"{name}_pred"] + counts[f"{name}_gold"]
    return 2 * counts[f"{name}_tp"] / total if total else 1.0


def unsourced(parsed: dict) -> int:
    """Values without a page; cite-or-refuse means this is always 0."""
    items = [item for part in ("outcomes", "weeks", "assessments", "textbooks")
             for item in parsed[part]]
    course_set = any(parsed["course"][k] for k in parsed["course"] if k != "source_page")
    return (sum(not item.get("source_page") for item in items)
            + int(course_set and not parsed["course"]["source_page"]))


def document_for(gold_file: Path) -> Path:
    stem = gold_file.name.removesuffix(".gold.json")
    for suffix in (".pdf", ".docx", ".txt"):
        if (path := gold_file.with_name(stem + suffix)).is_file():
            return path
    raise FileNotFoundError(f"no document next to {gold_file.name}")


def read_pages(path: Path) -> list[str]:
    data = path.read_bytes()
    return extract_pages(data, detect_media_type(path.name, data))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, default=DATASET)
    parser.add_argument("--limit", type=int, default=None, help="evaluate the first N syllabi")
    parser.add_argument("--refuse", type=Path, action="append", default=[],
                        help="a file that must be refused as not_a_syllabus (repeatable)")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")  # LLM_PROVIDER / LLM_API_KEY; real env vars win
    llm = get_client()
    total: Counter = Counter()
    no_page = 0
    print("| syllabus | file | " + " | ".join(FIELDS) + " | no page | warnings |")
    print("| --- | --- |" + " ---: |" * (len(FIELDS) + 2))
    for gold_file in sorted(args.dir.glob("*.gold.json"))[: args.limit]:
        gold = json.loads(gold_file.read_text(encoding="utf-8"))
        path = document_for(gold_file)
        try:
            draft = extract_syllabus(llm, read_pages(path))
        except (ValueError, RetryableError) as exc:  # NotASyllabus included: all a miss
            print(f"| {gold['id']} | {path.suffix} | error: {exc} |")
            total += score({"weeks": [], "assessments": []}, gold)
            continue
        counts = score(draft.parsed, gold)
        total += counts
        no_page += unsourced(draft.parsed)
        cells = " | ".join(f"{f1(counts, name):.2f}" for name in FIELDS)
        codes = ", ".join(w.code for w in draft.warnings) or "-"
        print(f"| {gold['id']} | {path.suffix} | {cells} | {unsourced(draft.parsed)} | {codes} |")

    scores = {name: f1(total, name) for name in FIELDS}
    print("\n" + ", ".join(f"F1 {name} = {value:.3f}" for name, value in scores.items()))
    print(f"Values without a source page: {no_page}")
    refused = []
    for path in args.refuse:
        try:
            extract_syllabus(llm, read_pages(path))
            refused.append(False)
            print(f"{path.name}: parsed as a syllabus (expected not_a_syllabus)")
        except NotASyllabus:
            refused.append(True)
            print(f"{path.name}: not_a_syllabus")
        except (ValueError, RetryableError) as exc:  # not checked, so not counted as refused
            refused.append(False)
            print(f"{path.name}: error: {exc}")
    ok = min(scores.values()) >= TARGET and no_page == 0 and all(refused)
    print(f"Target F1 >= {TARGET} on every field: {'met' if ok else 'not met'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
