"""QA/QC commands: tests, lint and the weekly QA report."""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from devcli import ROOT, run

REPORTS = ROOT / "docs" / "notes" / "qa" / "reports"

REPORT_TEMPLATE = """# Weekly QA Report - Week {week}

This report summarizes QA results for week {week}. Created: {today}.

## Summary
- **Status**: _pending_ (e.g., "Pass, ready for demo" or "Blocked, 2 critical bugs remaining")

## Test Results
| Group | Total | Pass | Fail | Notes |
|---|---:|---:|---:|---|
| Unit tests (`dev qa test`) | | | | |
| Benchmark (`dev ai benchmark stats`) | | | | |
| Safeguards / red-team | | | | |

## Bug Log
| # | Severity | Description | Owner Role | Issue | Status |
|---|---|---|---|---|---|

## Limitations & Improvements
| # | Limitation | Next Steps |
|---|---|---|
"""


def _test(args: argparse.Namespace) -> int:
    return run([sys.executable, "-m", "pytest", "tests/", *args.extra])


def _lint(args: argparse.Namespace) -> int:
    return run([sys.executable, "-m", "ruff", "check", "."])


def _report(args: argparse.Namespace) -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"week-{args.week}.md"
    if path.exists():
        print(f"{path.relative_to(ROOT)} already exists; not overwriting.")
        return 1
    path.write_text(REPORT_TEMPLATE.format(week=args.week, today=datetime.now(UTC).date().isoformat()), encoding="utf-8")
    print(f"[ OK ] Created {path.relative_to(ROOT)}")
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("qa", help="QA/QC: run tests, lint, and generate weekly QA reports")
    qa_sub = p.add_subparsers(dest="qa_command", required=True)

    test = qa_sub.add_parser("test", help="run pytest; extra arguments are forwarded to pytest (e.g. -k auth)")
    test.set_defaults(func=_test, pass_extra=True)

    qa_sub.add_parser("lint", help="run ruff").set_defaults(func=_lint)

    report = qa_sub.add_parser("report", help="create docs/notes/qa/reports/week-N.md from template")
    report.add_argument("--week", type=int, required=True)
    report.set_defaults(func=_report)
