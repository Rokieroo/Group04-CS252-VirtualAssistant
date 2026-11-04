"""Measure syllabus extraction against #66's ten gold files, without feeding gold to the parser.

Default: deterministic extraction of the .txt samples through the real ingest layer.
--llm uses the configured provider (one call per syllabus; may consume quota).
--formats additionally runs the PDF/DOCX copies, counting them separately.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.ingest import detect_media_type, extract_pages
from app.syllabus import extract_syllabus


def _text(value: str) -> str:
    return " ".join(value.casefold().split()).rstrip(".")


def entities(parsed: dict, *, gold: bool = False) -> dict[str, set[tuple]]:
    weeks, topics, milestones, weights = set(), set(), set(), set()
    for row in parsed.get("weeks", []):
        week = row["week"]
        weeks.add((week,))
        for topic in ([row["topic"]] if gold else row["topics"]):
            topics.add((week, _text(topic)))
    for row in parsed.get("assessments", []):
        title = _text(row["name"] if gold else row["title"])
        due = row.get("due_week") if gold else row.get("due", "")
        if isinstance(due, str) and (match := re.fullmatch(r"(?:week|tuần)\s*(\d+)", due, re.IGNORECASE)):
            due = int(match.group(1))
        milestones.add((title, due))
        if "weight" in row:
            weights.add((title, float(row["weight"])))
    return {"weeks": weeks, "topics": topics, "milestones": milestones, "weights": weights}


def score(actual: set, expected: set) -> dict:
    tp, fp, fn = len(actual & expected), len(actual - expected), len(expected - actual)
    return {"tp": tp, "fp": fp, "fn": fn, "f1": 2 * tp / (2 * tp + fp + fn)
            if tp + fp + fn else 1.0}


def evaluate(directory: Path, *, client=None, formats: bool = False, limit=None) -> dict:
    rows = []
    totals = {name: {"tp": 0, "fp": 0, "fn": 0} for name in
              ("weeks", "topics", "milestones", "weights")}
    for gold_path in sorted(directory.glob("*.gold.json"))[:limit]:
        stem = gold_path.name.removesuffix(".gold.json")
        files = [directory / f"{stem}.txt"]
        if formats:
            files += [p for ext in (".pdf", ".docx") if (p := directory / f"{stem}{ext}").exists()]
        for path in files:
            data = path.read_bytes()
            pages = extract_pages(data, detect_media_type(path.name, data))
            # Gold is deliberately read only after extraction.
            draft = extract_syllabus(pages, client)
            expected = entities(json.loads(gold_path.read_text(encoding="utf-8")), gold=True)
            actual = entities(draft.parsed)
            metrics = {name: score(actual[name], expected[name]) for name in totals}
            for name, counts in totals.items():
                for key in counts:
                    counts[key] += metrics[name][key]
            cited = [field for field in draft.parsed["course"].values()]
            cited += [row for name in ("outcomes", "weeks", "assessments", "textbooks")
                      for row in draft.parsed[name]]
            missing = sum(not isinstance(row.get("source_page"), int) or
                          not 1 <= row["source_page"] <= len(pages) for row in cited)
            rows.append({"file": path.name, "pages": len(pages), "metrics": metrics,
                         "missing_citations": missing, "warnings": [w.code for w in draft.warnings]})
    for counts in totals.values():
        tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
        counts["f1"] = 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0
    passed = bool(rows) and all(m["f1"] >= 0.9 for m in totals.values()) and not any(
        row["missing_citations"] for row in rows)
    return {"mode": "llm" if client else "deterministic", "samples": len(rows),
            "metrics": totals, "results": rows, "passed": passed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "eval" / "syllabus")
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--formats", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    client = None
    if args.llm:
        from dotenv import load_dotenv

        from app.llm import FakeLLM, get_client

        load_dotenv(ROOT / ".env")
        client = get_client()
        if isinstance(client, FakeLLM):
            parser.error("--llm needs a real configured provider; omit it for offline evaluation")
    report = evaluate(args.directory, client=client, formats=args.formats, limit=args.limit)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
