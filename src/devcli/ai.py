"""AI implementation commands: benchmark checks and the assistant itself."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from devcli import ROOT

BENCHMARK = ROOT / "eval" / "benchmark.jsonl"
REQUIRED = ("id", "use_case", "kind", "question", "expected")
KINDS = {"normal", "missing_knowledge", "privacy", "safety"}
USE_CASE_RE = re.compile(r"^UC-\d{2}$")


def load_cases(path: Path) -> tuple[list[dict], list[str]]:
    """Parse a benchmark file and return (cases, errors)."""
    cases: list[dict] = []
    errors: list[str] = []
    seen: set[str] = set()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"dòng {n}: JSON lỗi ({exc.msg})")
            continue
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
        cases.append(case)
    return cases, errors


def _benchmark(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"Không tìm thấy {path}.")
        return 1
    cases, errors = load_cases(path)
    for err in errors:
        print(f"[FAIL] {err}")
    if args.action == "stats":
        print(f"Tổng số case: {len(cases)}")
        for key in ("kind", "use_case"):
            counts = Counter(c.get(key, "?") for c in cases)
            print(f"Theo {key}: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if not errors:
        print(f"[ OK ] {len(cases)} case hợp lệ trong {path.name}")
    return 1 if errors else 0


def _chat(args: argparse.Namespace) -> int:
    from assistant.__main__ import main as assistant_main

    return assistant_main(args.question)


def _concepts(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv

    from app.concepts.extract import extract_concepts
    from app.concepts.visual import read_visuals
    from app.llm import get_client, get_vision_client
    from assistant.backend.ingest import InvalidPdf, extract_pages

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


def _items(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv

    from app.items.generate import generate_items
    from app.llm import get_client
    from assistant.backend.ingest import InvalidPdf, extract_pages

    load_dotenv(ROOT / ".env")
    path = Path(args.file)
    try:
        pages = extract_pages(path.read_bytes())
        concepts = json.loads(Path(args.concepts).read_text(encoding="utf-8"))
    except (OSError, InvalidPdf, ValueError) as exc:
        print(f"Không đọc được đầu vào: {exc}")
        return 1
    sources = [{"id": f"p{n}", "page": n, "text": t} for n, t in enumerate(pages, 1) if t.strip()]
    llm = get_client()
    result = [{**c, "items": generate_items(llm, c, sources)} for c in concepts[:args.limit]]
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

    items = ai_sub.add_parser("items", help="sinh câu hỏi có trích dẫn trang cho concept của một PDF")
    items.add_argument("file")
    items.add_argument("--concepts", required=True, help="JSON từ `ai concepts <file> --json`")
    items.add_argument("--limit", type=int, default=5, help="số concept tối đa (mặc định 5)")
    items.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    items.set_defaults(func=_items)
