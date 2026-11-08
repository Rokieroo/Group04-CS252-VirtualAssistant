"""Evaluate BM25 retrieval on ``eval/benchmark.jsonl`` (issue #11).

Usage::

    python eval/run_retrieval.py
    python eval/run_retrieval.py --thresholds 0.5 1.0 1.5 2.0 2.5 3.0

The script supports both the repository's sample benchmark shape
(``question`` / ``kind`` / ``source``) and the canonical shape
(``query`` / ``category`` / ``expected_pages`` / ``expected_source_ids`` /
``sources``). For normal cases it reports top-5 hit rate; for
``missing_knowledge`` cases it reports the share of queries that correctly
return no hits. It prints a table ready to paste into ``docs/progress/phase1/AI.md``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.retrieval import MIN_SCORE, BM25Retriever

BENCHMARK = ROOT / "eval" / "benchmark.jsonl"
DEFAULT_THRESHOLDS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
NORMAL = "normal"
MISSING = "missing_knowledge"
_PAGE_IN_SOURCE = re.compile(r"#(\d+)\s*$")

# Offline fixture used when the local database has no `sources` rows yet. The
# text deliberately mirrors CSC10014 slides so the sample benchmark is
# meaningful in CI and on a fresh clone.
FIXTURE_SOURCES: list[dict[str, Any]] = [
    {
        "id": "s_12",
        "page": 12,
        "file_name": "CSC10014_2026_Week01_Problem_Framing.pdf",
        "text": (
            "Problem framing. Xác định đúng vấn đề trước khi chọn giải pháp. "
            "Ai là người dùng, họ đau ở đâu và vì sao vấn đề này đáng giải quyết."
        ),
    },
    {
        "id": "s_31",
        "page": 31,
        "file_name": "CSC10014_2026_Week02_Decomposition.pdf",
        "text": (
            "Use case và yêu cầu. Chia hệ thống thành các use case nhỏ; mỗi use case "
            "có actor, trigger và kết quả mong đợi."
        ),
    },
    {
        "id": "s_45",
        "page": 45,
        "file_name": "CSC10014_2026_Week02_Decomposition.pdf",
        "text": (
            "Decomposition. Chia bài toán lớn thành bài toán con độc lập, sắp thứ tự "
            "phụ thuộc và kiểm tra bằng ví dụ cụ thể."
        ),
    },
    {
        "id": "s_53",
        "page": 53,
        "file_name": "Week 0 - Orientation.pdf",
        "text": (
            "Minimum Requirements. Dự án cuối kỳ cần tối thiểu 8 đến 12 use cases "
            "kèm non-goals. Mỗi use case mô tả actor, luồng chính và kết quả mong đợi; "
            "bộ use cases phải đủ nhỏ để làm trong sáu tuần."
        ),
    },
    {
        "id": "s_77",
        "page": 77,
        "file_name": "CSC10014_2026_Week01_Problem_Framing.pdf",
        "text": (
            "Solution ladder gồm 7 bậc giải pháp từ quy trình thủ công đến agent. "
            "Bậc 0 là Human process, bậc 1 là Static FAQ page, bậc 2 là Rules & lookup, "
            "bậc 3 Search BM25, bậc 4 là Classical ML, bậc 5 là LLM + retrieval, "
            "bậc 6 là Agent + tools. Solution ladder khuyên chọn bậc thấp nhất đủ dùng; "
            "chỉ leo lên bậc cao hơn khi bậc thấp hơn không giải quyết được. "
            "Bậc 3 Search BM25 dùng cho tìm kiếm tài liệu trước khi gọi LLM."
        ),
    },
    {
        "id": "s_90",
        "page": 90,
        "file_name": "CSC10014_2026_Week03_Pitfalls_Pipelines.pdf",
        "text": (
            "Pitfalls và pipelines. Prompt injection, dữ liệu bẩn và chi phí LLM. "
            "Luôn đặt text slide trong khối dữ liệu và không làm theo chỉ dẫn bên trong. "
            "Pipeline chuẩn gồm ingest, concept, item generation, grading và scheduler."
        ),
    },
]


@dataclass
class EvalCase:
    case_id: str
    query: str
    category: str
    expected_pages: set[int]
    expected_source_ids: set[str]
    sources: list[dict[str, Any]] | None = None


@dataclass
class ThresholdResult:
    threshold: float
    normal_total: int
    normal_hits: int
    missing_total: int
    missing_empty: int

    @property
    def normal_rate(self) -> float:
        return self.normal_hits / self.normal_total if self.normal_total else 0.0

    @property
    def missing_rate(self) -> float:
        return self.missing_empty / self.missing_total if self.missing_total else 0.0


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, int)):
        return [value]
    return list(value)


def _to_page(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _expected_fields(case: dict[str, Any]) -> tuple[set[int], set[str]]:
    pages = {
        page
        for page in (_to_page(value) for value in _as_list(case.get("expected_pages")))
        if page is not None
    }
    source_ids = {
        str(value) for value in _as_list(case.get("expected_source_ids"))
    }

    # Sample benchmark uses `"source": "file.pdf#77"` instead of expected_pages.
    source = case.get("source")
    if isinstance(source, str):
        match = _PAGE_IN_SOURCE.search(source)
        if match:
            pages.add(int(match.group(1)))
    elif isinstance(source, dict):
        page = _to_page(source.get("page"))
        if page is not None:
            pages.add(page)
        if source.get("source_id") is not None:
            source_ids.add(str(source["source_id"]))

    if not pages and case.get("expected_page") is not None:
        page = _to_page(case["expected_page"])
        if page is not None:
            pages.add(page)
    return pages, source_ids


def load_benchmark(path: Path) -> list[EvalCase]:
    """Load JSONL cases, supporting both sample and canonical field names."""
    cases: list[EvalCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: JSON lỗi ({exc.msg})") from exc

        query = raw.get("query") or raw.get("question") or ""
        category = raw.get("category") or raw.get("kind") or ""
        pages, source_ids = _expected_fields(raw)
        sources = raw.get("sources")
        if sources is not None and not isinstance(sources, list):
            raise ValueError(f"{path}:{line_number}: 'sources' phải là một danh sách")

        cases.append(
            EvalCase(
                case_id=str(raw.get("id") or line_number),
                query=str(query),
                category=str(category),
                expected_pages=pages,
                expected_source_ids=source_ids,
                sources=sources,
            )
        )
    return cases


def load_sources_from_db() -> list[dict[str, Any]]:
    """Read `sources` from the configured database; empty when unavailable."""
    try:
        from sqlalchemy.exc import SQLAlchemyError

        from app.db import get_connection
    except ImportError:
        return []

    try:
        with get_connection() as connection:
            rows = connection.exec_driver_sql(
                "SELECT id, text, page, file_name FROM sources ORDER BY page"
            ).mappings().all()
        return [dict(row) for row in rows]
    except (OSError, SQLAlchemyError):
        return []


def pick_sources() -> tuple[list[dict[str, Any]], str]:
    """Prefer real DB rows, fall back to the bundled slide fixture."""
    db_sources = load_sources_from_db()
    if db_sources:
        return db_sources, "database"
    return FIXTURE_SOURCES, "fixture"


def _hit_matches(hit: Any, pages: set[int], source_ids: set[str]) -> bool:
    return (hit.source_id in source_ids) or (hit.page is not None and hit.page in pages)


def evaluate_threshold(
    cases: list[EvalCase],
    default_sources: list[dict[str, Any]],
    threshold: float,
    top_k: int = 5,
) -> ThresholdResult:
    normal_total = normal_hits = missing_total = missing_empty = 0

    for case in cases:
        if case.category == NORMAL:
            if not case.expected_pages and not case.expected_source_ids:
                continue
            normal_total += 1
        elif case.category == MISSING:
            missing_total += 1
        else:
            continue

        sources = case.sources if case.sources else default_sources
        hits = BM25Retriever(sources).retrieve(
            case.query,
            top_k=top_k,
            min_score=threshold,
        )

        if case.category == NORMAL:
            if any(
                _hit_matches(hit, case.expected_pages, case.expected_source_ids)
                for hit in hits[:top_k]
            ):
                normal_hits += 1
        elif not hits:
            missing_empty += 1

    return ThresholdResult(
        threshold=threshold,
        normal_total=normal_total,
        normal_hits=normal_hits,
        missing_total=missing_total,
        missing_empty=missing_empty,
    )


def _percent(part: int, total: int) -> str:
    if not total:
        return "n/a"
    return f"{100.0 * part / total:.1f}% ({part}/{total})"


def print_table(results: list[ThresholdResult], default_threshold: float) -> None:
    print()
    print("Bảng kết quả BM25 (top-5) — dán vào docs/progress/phase1/AI.md:")
    print()
    header = (
        f"{'MIN_SCORE':>9} | {'Top-5 hit rate (normal)':>24} | "
        f"{'Missing trả rỗng':>20}"
    )
    print(header)
    print("-" * len(header))
    for result in results:
        marker = " *" if abs(result.threshold - default_threshold) < 1e-9 else ""
        print(
            f"{result.threshold:>9.1f} | "
            f"{_percent(result.normal_hits, result.normal_total):>24} | "
            f"{_percent(result.missing_empty, result.missing_total):>20}{marker}"
        )
    print()
    print(f"* = MIN_SCORE mặc định hiện tại ({default_threshold:g}).")


def _recommended(results: list[ThresholdResult]) -> ThresholdResult | None:
    """Highest threshold that keeps the best normal hit rate."""
    if not results:
        return None
    best_normal = max(result.normal_rate for result in results)
    eligible = [result for result in results if result.normal_rate == best_normal]
    return max(eligible, key=lambda result: (result.missing_rate, result.threshold))


def _configure_console() -> None:
    """Avoid UnicodeEncodeError when a Windows console is not UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    parser = argparse.ArgumentParser(description="Đo top-5 hit rate của BM25 retrieval")
    parser.add_argument("--benchmark", default=str(BENCHMARK), help="đường dẫn benchmark JSONL")
    parser.add_argument(
        "--thresholds",
        nargs="+",
        type=float,
        default=DEFAULT_THRESHOLDS,
        help="các ngưỡng MIN_SCORE cần quét",
    )
    parser.add_argument("--top-k", type=int, default=5, help="số trang lấy ra cho mỗi truy vấn")
    args = parser.parse_args(argv)

    path = Path(args.benchmark)
    if not path.exists():
        print(f"Không tìm thấy benchmark: {path}")
        return 1

    cases = load_benchmark(path)
    sources, origin = pick_sources()
    normal_cases = sum(1 for case in cases if case.category == NORMAL)
    missing_cases = sum(1 for case in cases if case.category == MISSING)

    print(f"Benchmark: {path}")
    print(
        f"Case: {len(cases)} (normal={normal_cases}, "
        f"missing_knowledge={missing_cases}, khác={len(cases) - normal_cases - missing_cases})"
    )
    print(f"Nguồn: {len(sources)} trang từ {origin}")

    results = [
        evaluate_threshold(cases, sources, threshold, top_k=args.top_k)
        for threshold in args.thresholds
    ]
    print_table(results, MIN_SCORE)

    recommendation = _recommended(results)
    if recommendation is not None:
        print(
            "Gợi ý: MIN_SCORE = "
            f"{recommendation.threshold:g} "
            f"(normal {_percent(recommendation.normal_hits, recommendation.normal_total)}, "
            f"missing trả rỗng {_percent(recommendation.missing_empty, recommendation.missing_total)})."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
