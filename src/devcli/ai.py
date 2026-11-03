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


def load_resources(path: Path) -> tuple[list[dict], list[str]]:
    """Parse resources benchmark file and return (items, errors)."""
    items: list[dict] = []
    errors: list[str] = []
    seen: set[str] = set()
    req = ("id", "course_code", "week", "milestone_topic", "url", "is_quality", "justification")
    if not path.exists():
        return [], [f"Không tìm thấy {path}"]
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"resources dòng {n}: JSON lỗi ({exc.msg})")
            continue
        missing = [k for k in req if k not in item]
        if missing:
            errors.append(f"resources dòng {n}: thiếu trường {', '.join(missing)}")
        if item.get("id") in seen:
            errors.append(f"resources dòng {n}: id '{item['id']}' bị trùng")
        seen.add(item.get("id"))
        items.append(item)
    return items, errors


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
    errors: list[str] = []
    if not fix_dir.exists():
        return [f"Không tìm thấy thư mục {fix_dir}"]
    pirated_file = fix_dir / "pirated_urls.jsonl"
    if not pirated_file.exists():
        errors.append(f"Không tìm thấy {pirated_file}")
    else:
        for n, line in enumerate(pirated_file.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not row.get("url"):
                    errors.append(f"pirated_urls dòng {n}: thiếu url")
            except json.JSONDecodeError as exc:
                errors.append(f"pirated_urls dòng {n}: JSON lỗi ({exc.msg})")
    inj_files = list((fix_dir / "injections").glob("*.html"))
    if len(inj_files) < 15:
        errors.append(f"Cần tối thiểu 15 file injection HTML (tìm thấy {len(inj_files)})")
    pii_files = list((fix_dir / "pii_syllabi").glob("*.txt"))
    if len(pii_files) < 10:
        errors.append(f"Cần tối thiểu 10 file PII syllabus sample (tìm thấy {len(pii_files)})")
    return errors


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

    # Validate additional benchmarks if validating default or explicit suite
    all_ok = not errors
    if args.action == "validate" and path == BENCHMARK:
        # Validate resources
        res_items, res_errs = load_resources(RESOURCES)
        for err in res_errs:
            print(f"[FAIL] {err}")
        if res_errs:
            all_ok = False
        else:
            print(f"[ OK ] {len(res_items)} tài nguyên học tập hợp lệ trong {RESOURCES.name}")

        # Validate syllabus
        syl_errs = validate_syllabus_benchmark(SYLLABUS_DIR)
        for err in syl_errs:
            print(f"[FAIL] {err}")
        if syl_errs:
            all_ok = False
        else:
            gold_count = len(list(SYLLABUS_DIR.glob("*.gold.json")))
            print(f"[ OK ] {gold_count} syllabus benchmark + gold hợp lệ trong {SYLLABUS_DIR.name}/")

        # Validate redteam
        red_errs = validate_redteam_fixtures(FIXTURES_DIR)
        for err in red_errs:
            print(f"[FAIL] {err}")
        if red_errs:
            all_ok = False
        else:
            print("[ OK ] Red-team fixtures (injections, pirated URLs, PII) hợp lệ")

    if args.action == "stats":
        print(f"Tổng số case: {len(cases)}")
        for key in ("kind", "use_case"):
            counts = Counter(c.get(key, "?") for c in cases)
            print(f"Theo {key}: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        if RESOURCES.exists():
            res_items, _ = load_resources(RESOURCES)
            print(f"Tổng số tài nguyên học tập (resources): {len(res_items)}")
            quality_count = sum(1 for r in res_items if r.get("is_quality"))
            print(f"  Chất lượng tốt (đồng thuận): {quality_count}/{len(res_items)} ({quality_count/len(res_items)*100:.1f}%)")

    if not errors:
        print(f"[ OK ] {len(cases)} case hợp lệ trong {path.name}")
    return 0 if all_ok else 1


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


def _items(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv

    from app.ingest import InvalidPdf, extract_pages
    from app.items.generate import generate_items
    from app.llm import get_client

    load_dotenv(ROOT / ".env")
    path = Path(args.file)
    concepts_path = Path(args.concepts)
    if not concepts_path.exists():
        print(f"Không tìm thấy file concept {concepts_path}.")
        return 1
    try:
        data = path.read_bytes()
        pages = extract_pages(data)
    except (OSError, InvalidPdf) as exc:
        print(f"Không đọc được {path}: {exc}")
        return 1
    concepts = json.loads(concepts_path.read_text(encoding="utf-8"))[: args.limit]
    result = generate_items(get_client(), pages, concepts)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    for c in result:
        print(f"\n# {c['concept_title']} ({len(c['items'])} item)")
        for item in c["items"]:
            print(f"- [{item['kind']}] {item['prompt']}")
            print(f"  Nguồn trang: {item['source_page']}")
            if item.get("choices"):
                for idx, ch in enumerate(item["choices"]):
                    prefix = "  * " if idx == item["correct_index"] else "    "
                    print(f"{prefix}{chr(65 + idx)}. {ch}")
            elif item.get("answer"):
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
