"""AI implementation commands: benchmark checks and the assistant itself."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from devcli import ROOT

BENCHMARK = ROOT / "eval" / "benchmark.jsonl"
RESOURCES = ROOT / "eval" / "resources.jsonl"
SYLLABUS_DIR = ROOT / "eval" / "syllabus"
FIXTURES_DIR = ROOT / "eval" / "fixtures" / "redteam"

REQUIRED = ("id", "use_case", "kind", "question", "expected")
KINDS = {"normal", "missing_knowledge", "privacy", "safety"}
USE_CASE_RE = re.compile(r"^UC-\d{2}$")
LABELS = {"good", "bad"}


def _read_jsonl(path: Path) -> tuple[list[tuple[int, dict]], list[str]]:
    """Return the (line number, row) pairs of a JSONL file and its parse errors."""
    rows: list[tuple[int, dict]] = []
    errors: list[str] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append((n, json.loads(line)))
        except json.JSONDecodeError as exc:
            errors.append(f"dòng {n}: JSON lỗi ({exc.msg})")
    return rows, errors


def load_resources(path: Path) -> tuple[list[dict], list[str]]:
    """Parse the labelled resource set, one roadmap node per line, as eval/run_resources.py reads it."""
    if not path.exists():
        return [], [f"Không tìm thấy {path}"]
    rows, errors = _read_jsonl(path)
    seen: set[str] = set()
    for n, case in rows:
        if not case.get("id") or not case.get("node", {}).get("title"):
            errors.append(f"dòng {n}: thiếu id hoặc node.title")
        if case.get("id") in seen:
            errors.append(f"dòng {n}: id '{case['id']}' bị trùng")
        seen.add(case.get("id"))
        if not case.get("resources"):
            errors.append(f"dòng {n}: thiếu danh sách resources")
        for i, res in enumerate(case.get("resources") or [], start=1):
            if not res.get("url") or not res.get("reason") or res.get("label") not in LABELS:
                errors.append(f"dòng {n}, nguồn {i}: cần url, reason và label thuộc {sorted(LABELS)}")
    return [case for _, case in rows], [f"{path.name} {err}" for err in errors]


def validate_syllabus_benchmark(syl_dir: Path) -> list[str]:
    """Validate that syllabus samples have corresponding valid gold files."""
    errors: list[str] = []
    if not syl_dir.exists():
        return [f"Không tìm thấy thư mục {syl_dir}"]
    gold_files = list(syl_dir.glob("*.gold.json"))
    if not gold_files:
        errors.append(f"{syl_dir}: không tìm thấy file .gold.json nào")
    for gf in gold_files:
        try:
            data = json.loads(gf.read_text(encoding="utf-8"))
            for req in ("id", "course_code", "course_name", "learning_outcomes", "weeks", "assessments"):
                if req not in data:
                    errors.append(f"{gf.name}: thiếu trường '{req}'")
        except json.JSONDecodeError as exc:
            errors.append(f"{gf.name}: JSON lỗi ({exc.msg})")
    return errors


def validate_redteam_fixtures(fix_dir: Path) -> list[str]:
    """Validate redteam prompt injection, pirated URLs, and PII samples."""
    if not fix_dir.exists():
        return [f"Không tìm thấy thư mục {fix_dir}"]
    errors: list[str] = []
    pirated_file = fix_dir / "pirated_urls.jsonl"
    if not pirated_file.exists():
        errors.append(f"Không tìm thấy {pirated_file}")
    else:
        rows, parse_errors = _read_jsonl(pirated_file)
        errors += [f"pirated_urls {err}" for err in parse_errors]
        errors += [f"pirated_urls dòng {n}: thiếu url" for n, row in rows if not row.get("url")]
    inj_files = list((fix_dir / "injections").glob("*.html"))
    if len(inj_files) < 15:
        errors.append(f"Cần tối thiểu 15 file injection HTML (tìm thấy {len(inj_files)})")
    pii_files = list((fix_dir / "pii_syllabi").glob("*.txt"))
    if len(pii_files) < 10:
        errors.append(f"Cần tối thiểu 10 file PII syllabus sample (tìm thấy {len(pii_files)})")
    return errors


def load_cases(path: Path) -> tuple[list[dict], list[str]]:
    """Parse a benchmark file and return (cases, errors)."""
    rows, errors = _read_jsonl(path)
    seen: set[str] = set()
    for n, case in rows:
        missing = [k for k in REQUIRED if not case.get(k)]
        if missing:
            errors.append(f"dòng {n}: thiếu trường {', '.join(missing)}")
        if case.get("kind") and case["kind"] not in KINDS:
            errors.append(f"dòng {n}: kind '{case['kind']}' không thuộc {sorted(KINDS)}")
        if case.get("use_case") and not USE_CASE_RE.match(case["use_case"]):
            errors.append(f"dòng {n}: use_case '{case['use_case']}' phải có dạng UC-01")
        if case.get("id") in seen:
            errors.append(f"dòng {n}: id '{case['id']}' bị trùng")
        seen.add(case.get("id"))
    return [case for _, case in rows], errors


def _report(errors: list[str], ok_message: str) -> bool:
    """Print each error, or the OK line when there are none; return whether it passed."""
    for err in errors:
        print(f"[FAIL] {err}")
    if not errors:
        print(f"[ OK ] {ok_message}")
    return not errors


def _benchmark(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"Không tìm thấy {path}.")
        return 1

    cases, errors = load_cases(path)
    if args.action == "stats":
        print(f"Tổng số case: {len(cases)}")
        for key in ("kind", "use_case"):
            counts = Counter(c.get(key, "?") for c in cases)
            print(f"Theo {key}: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        nodes, _ = load_resources(RESOURCES)
        labels = Counter(res.get("label") for node in nodes for res in node.get("resources") or [])
        if labels:
            print(f"Nguồn gắn nhãn: {labels.total()} trên {len(nodes)} chặng, "
                  f"good={labels['good']}, bad={labels['bad']}")

    ok = _report(errors, f"{len(cases)} case hợp lệ trong {path.name}")
    if args.action == "validate" and path == BENCHMARK:
        # The default run also checks the other #66 suites, so CI covers them too.
        nodes, resource_errors = load_resources(RESOURCES)
        gold_count = len(list(SYLLABUS_DIR.glob("*.gold.json")))
        ok = all([
            ok,
            _report(resource_errors, f"{len(nodes)} chặng có nguồn gắn nhãn trong {RESOURCES.name}"),
            _report(validate_syllabus_benchmark(SYLLABUS_DIR),
                    f"{gold_count} syllabus benchmark + gold hợp lệ trong {SYLLABUS_DIR.name}/"),
            _report(validate_redteam_fixtures(FIXTURES_DIR),
                    "Red-team fixtures (injections, pirated URLs, PII) hợp lệ"),
        ])
    return 0 if ok else 1


def _chat(args: argparse.Namespace) -> int:
    from assistant.__main__ import main as assistant_main

    return assistant_main(args.question)


def _concepts(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv

    from app.concepts.extract import extract_concepts
    from app.concepts.visual import read_visuals
    from app.ingest import InvalidPdf, extract_pages
    from app.llm import get_client, get_vision_client

    load_dotenv(ROOT / ".env")  # LLM_PROVIDER / LLM_API_KEY; real env vars win
    path = Path(args.file)
    try:
        data = path.read_bytes()
        pages = extract_pages(data)
    except (OSError, InvalidPdf) as exc:
        print(f"Không đọc được {path}: {exc}")
        return 1
    visuals = read_visuals(get_vision_client(), data, len(pages))
    concepts = extract_concepts(get_client(), pages, visuals)
    if args.json:
        print(json.dumps(concepts, ensure_ascii=False, indent=2))
        return 0
    for c in concepts:
        print(f"- {c['title']} [{c['slug']}, {c['bloom_level']}, trang {c['source_pages']}]")
        print(f"  {c['summary']}")
    print(f"{path.name}: {len(pages)} trang, {len(concepts)} concept")
    return 0


def _syllabus(args: argparse.Namespace) -> int:
    from dataclasses import asdict

    from dotenv import load_dotenv

    from app.ingest import (
        InvalidDocument,
        UnsupportedType,
        detect_media_type,
        extract_pages,
    )
    from app.llm import RetryableError, get_client
    from app.syllabus import NotASyllabus, extract_syllabus

    load_dotenv(ROOT / ".env")  # LLM_PROVIDER / LLM_API_KEY; real env vars win
    path = Path(args.file)
    try:
        data = path.read_bytes()
        pages = extract_pages(data, detect_media_type(path.name, data))
    except (OSError, InvalidDocument, UnsupportedType) as exc:
        print(f"Không đọc được {path}: {exc}")
        return 1
    try:
        draft = extract_syllabus(get_client(), pages)
    except NotASyllabus as exc:
        print(f"{path.name}: not_a_syllabus ({exc})")
        return 1
    except (ValueError, RetryableError) as exc:
        print(f"{path.name}: LLM không trả được kết quả dùng được ({exc})")
        return 1
    if args.json:
        result = {"parsed": draft.parsed, "warnings": [asdict(w) for w in draft.warnings]}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    parsed = draft.parsed
    course = parsed["course"]
    print(f"# {course['code']} {course['title']} ({course['credits']} tín chỉ, "
          f"{course['term_start']} – {course['term_end']})")
    for outcome in parsed["outcomes"]:
        print(f"- {outcome['code']} [{outcome['bloom_level']}, trang {outcome['source_page']}] "
              f"{outcome['text']}")
    for week in parsed["weeks"]:
        print(f"- Tuần {week['week']} [trang {week['source_page']}]: {'; '.join(week['topics'])}")
    for item in parsed["assessments"]:
        due = item["due_date"] or (item["due_week"] and f"tuần {item['due_week']}") or "?"
        print(f"- {item['title']} ({item['kind']}): {item['weight']}%, hạn {due} "
              f"[trang {item['source_page']}]")
    for warning in draft.warnings:
        print(f"[{'CHẶN' if warning.blocking else 'WARN'}] {warning.code}: {warning.message}")
    print(f"{path.name}: {len(pages)} trang, {len(draft.warnings)} cảnh báo")
    return 0


def _items(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv

    from app.ingest import InvalidPdf, extract_pages
    from app.items.generate import generate_items

    load_dotenv(ROOT / ".env")
    path = Path(args.file)
    try:
        pages = extract_pages(path.read_bytes())
        concepts = json.loads(Path(args.concepts).read_text(encoding="utf-8"))
    except (OSError, InvalidPdf, ValueError) as exc:
        print(f"Không đọc được đầu vào: {exc}")
        return 1
    sources = [{"id": f"p{n}", "page": n, "text": t} for n, t in enumerate(pages, 1) if t.strip()]
    result = [{**c, "items": generate_items(None, c, sources)} for c in concepts[:args.limit]]
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    for c in result:
        print(f"## {c['title']}")
        for item in c["items"]:
            print(f"- [{item['type']}, trang {item['source_id'][1:]}] {item['prompt']}")
            for choice in item["choices"]:
                print(f"    {'*' if choice == item['answer'] else ' '} {choice}")
            if item["rubric"]:
                print(f"    Đáp án: {item['answer']}")
                print(f"    Rubric: {'; '.join(item['rubric'])}")
    print(f"{path.name}: {sum(len(c['items']) for c in result)} item cho {len(result)} concept")
    return 0


def _syllabus_preview(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv

    from app.ingest import MAX_UPLOAD_BYTES, detect_media_type, extract_pages
    from app.llm import RetryableError, get_client
    from app.syllabus import preview_syllabus

    try:
        path = Path(args.file)
        if path.stat().st_size > MAX_UPLOAD_BYTES:
            raise ValueError("file_too_large")
        data = path.read_bytes()
        pages = extract_pages(data, detect_media_type(path.name, data))
        if args.llm:
            load_dotenv(ROOT / ".env")
        draft = preview_syllabus(pages, get_client() if args.llm else None)
    except RetryableError:
        print("Nhà cung cấp LLM tạm thời không khả dụng; hãy thử lại sau.")
        return 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Không phân tích được syllabus: {exc}")
        return 1
    print(json.dumps(draft.to_dict(), ensure_ascii=False, indent=2))
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("ai", help="AI implementation: benchmark và trợ lý")
    ai_sub = p.add_subparsers(dest="ai_command", required=True)

    bench = ai_sub.add_parser("benchmark", help="kiểm tra hoặc thống kê eval/benchmark.jsonl")
    bench.add_argument("action", choices=["validate", "stats"])
    bench.add_argument("--file", default=str(BENCHMARK))
    bench.set_defaults(func=_benchmark)

    chat = ai_sub.add_parser("chat", help="chạy trợ lý (hỏi một câu, hoặc chế độ tương tác)")
    chat.add_argument("question", nargs="*")
    chat.set_defaults(func=_chat)

    concepts = ai_sub.add_parser("concepts", help="đề xuất concept từ một file PDF (dùng LLM_PROVIDER)")
    concepts.add_argument("file")
    concepts.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    concepts.set_defaults(func=_concepts)

    syllabus = ai_sub.add_parser("syllabus", help="phân tích syllabus PDF/DOCX/TXT (dùng LLM_PROVIDER)")
    syllabus.add_argument("file")
    syllabus.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    syllabus.set_defaults(func=_syllabus)

    preview = ai_sub.add_parser("syllabus-preview", help="xem trước syllabus có kiểm tra nguồn; mặc định offline")
    preview.add_argument("file")
    preview.add_argument("--llm", action="store_true", help="dùng parser LLM của nhóm thay cho đọc offline")
    preview.set_defaults(func=_syllabus_preview)

    items = ai_sub.add_parser("items", help="sinh câu hỏi có trích dẫn trang cho concept của một PDF")
    items.add_argument("file")
    items.add_argument("--concepts", required=True, help="JSON từ `ai concepts <file> --json`")
    items.add_argument("--limit", type=int, default=5, help="số concept tối đa (mặc định 5)")
    items.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    items.set_defaults(func=_items)
