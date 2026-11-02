"""QA/QC commands: tests, lint and the weekly QA report."""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from devcli import ROOT, run

REPORTS = ROOT / "docs" / "qa" / "reports"

REPORT_TEMPLATE = """# Báo cáo QA tuần {week} (Weekly QA Report)

Báo cáo này tổng hợp kết quả kiểm thử của tuần {week}. Ngày tạo: {today}.

## Kết luận
- **Trạng thái**: _chưa điền_ (ví dụ: "Đạt, sẵn sàng demo" hoặc "Chưa đạt, còn 2 bug chặn")

## Kết quả kiểm thử
| Nhóm | Số test | Pass | Fail | Ghi chú |
|---|---:|---:|---:|---|
| Unit test (`dev qa test`) | | | | |
| Benchmark (`dev ai benchmark stats`) | | | | |
| Safeguard / red-team | | | | |

## Bug log
| # | Mức độ | Mô tả | Role phụ trách | Issue | Trạng thái |
|---|---|---|---|---|---|

## Hạn chế & Hướng cải thiện (Limitations)
| # | Hạn chế | Hướng cải thiện |
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
        print(f"{path.relative_to(ROOT)} đã tồn tại, không ghi đè.")
        return 1
    path.write_text(REPORT_TEMPLATE.format(week=args.week, today=datetime.now(UTC).date().isoformat()), encoding="utf-8")
    print(f"[ OK ] Đã tạo {path.relative_to(ROOT)}")
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("qa", help="QA/QC: chạy test, lint và tạo báo cáo QA hằng tuần")
    qa_sub = p.add_subparsers(dest="qa_command", required=True)

    test = qa_sub.add_parser("test", help="chạy pytest; tham số thêm được chuyển cho pytest (vd: -k auth)")
    test.set_defaults(func=_test, pass_extra=True)

    qa_sub.add_parser("lint", help="chạy ruff").set_defaults(func=_lint)

    report = qa_sub.add_parser("report", help="tạo docs/qa/reports/week-N.md từ template")
    report.add_argument("--week", type=int, required=True)
    report.set_defaults(func=_report)
