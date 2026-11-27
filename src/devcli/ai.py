"""AI implementation commands: benchmark checks and the assistant itself."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from devcli import ROOT

BENCHMARK = ROOT / "eval" / "benchmark.jsonl"
RESOURCES = ROOT / "eval" / "resources.jsonl"
EXERCISES = ROOT / "eval" / "exercises.jsonl"
SYLLABUS_DIR = ROOT / "eval" / "syllabus"
GRAPHS_DIR = ROOT / "eval" / "graphs"
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
            errors.append(f"line {n}: invalid JSON ({exc.msg})")
    return rows, errors


def load_resources(path: Path) -> tuple[list[dict], list[str]]:
    """Parse the labelled resource set, one roadmap node per line, as eval/run_resources.py reads it."""
    if not path.exists():
        return [], [f"File not found: {path}"]
    rows, errors = _read_jsonl(path)
    seen: set[str] = set()
    for n, case in rows:
        if not case.get("id") or not case.get("node", {}).get("title"):
            errors.append(f"line {n}: missing id or node.title")
        if case.get("id") in seen:
            errors.append(f"line {n}: duplicate id '{case['id']}'")
        seen.add(case.get("id"))
        if not case.get("resources"):
            errors.append(f"line {n}: missing resources list")
        for i, res in enumerate(case.get("resources") or [], start=1):
            if (
                not res.get("url")
                or not res.get("reason")
                or res.get("label") not in LABELS
            ):
                errors.append(
                    f"line {n}, resource {i}: requires url, reason, and label in {sorted(LABELS)}"
                )
    return [case for _, case in rows], [f"{path.name} {err}" for err in errors]


def validate_syllabus_benchmark(syl_dir: Path) -> list[str]:
    """Validate that syllabus samples have corresponding valid gold files."""
    errors: list[str] = []
    if not syl_dir.exists():
        return [f"Directory not found: {syl_dir}"]
    gold_files = list(syl_dir.glob("*.gold.json"))
    if not gold_files:
        errors.append(f"{syl_dir}: no .gold.json files found")
    for gf in gold_files:
        try:
            data = json.loads(gf.read_text(encoding="utf-8"))
            for req in (
                "id",
                "course_code",
                "course_name",
                "learning_outcomes",
                "weeks",
                "assessments",
            ):
                if req not in data:
                    errors.append(f"{gf.name}: missing field '{req}'")
        except json.JSONDecodeError as exc:
            errors.append(f"{gf.name}: invalid JSON ({exc.msg})")
    return errors


def validate_exercises_benchmark(path: Path) -> list[str]:
    """Validate the 60-case exercise benchmark with verbatim citations."""
    if not path.exists():
        return [f"File not found: {path}"]
    rows, parse_errors = _read_jsonl(path)
    errors = [f"exercises {err}" for err in parse_errors]
    if len(rows) < 60:
        errors.append(
            f"At least 60 exercise benchmark cases required (found {len(rows)})"
        )
    seen_ids: set[str] = set()
    for n, item in rows:
        for req in ("id", "course_code", "concept", "prompt", "source", "type"):
            if not item.get(req):
                errors.append(f"exercises line {n}: missing field '{req}'")
        item_id = item.get("id")
        if item_id:
            if item_id in seen_ids:
                errors.append(f"exercises line {n}: duplicate id '{item_id}'")
            seen_ids.add(item_id)
        source = item.get("source") or {}
        if not source.get("source_text") or not source.get("location"):
            errors.append(
                f"exercises line {n}: source must include 'source_text' and 'location'"
            )
        else:
            prompt = item.get("prompt", "")
            choices = item.get("choices") or []
            answer = item.get("answer")
            source_text = source.get("source_text", "")
            if prompt and prompt not in source_text:
                errors.append(
                    f"exercises line {n} ({item_id}): prompt does not appear verbatim in source_text"
                )
            for choice in choices:
                if choice not in source_text:
                    errors.append(
                        f"exercises line {n} ({item_id}): choice '{choice}' does not appear verbatim"
                    )
            if answer and answer not in source_text:
                errors.append(
                    f"exercises line {n} ({item_id}): answer '{answer}' does not appear verbatim"
                )
    return errors


def validate_graph_benchmark(graphs_dir: Path) -> list[str]:
    """Validate the 5 reference knowledge graphs in eval/graphs/ (issue #112)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "roadmap_graph", ROOT / "src" / "app" / "roadmap" / "graph.py"
    )
    graph_mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = graph_mod
    spec.loader.exec_module(graph_mod)
    find_cycles = graph_mod.find_cycles

    errors: list[str] = []
    if not graphs_dir.exists():
        return [f"Directory not found: {graphs_dir}"]
    gold_files = sorted(graphs_dir.glob("*.gold.json"))
    if len(gold_files) < 5:
        errors.append(
            f"{graphs_dir}: at least 5 .gold.json files required (found {len(gold_files)})"
        )
    for gf in gold_files:
        try:
            data = json.loads(gf.read_text(encoding="utf-8"))
            for req in (
                "id",
                "course_code",
                "course_name",
                "source_file",
                "raters",
                "cohens_kappa",
                "concepts",
                "edges",
            ):
                if req not in data:
                    errors.append(f"{gf.name}: missing field '{req}'")
            if float(data.get("cohens_kappa", 0.0)) < 0.7:
                errors.append(f"{gf.name}: cohens_kappa must be >= 0.7")
            concepts = data.get("concepts") or []
            if data.get("course_code") == "CSC10014" and len(concepts) < 30:
                errors.append(f"{gf.name}: CSC10014 requires >= 30 concepts")
            slugs = {c.get("slug") for c in concepts if c.get("slug")}
            for c in concepts:
                if not c.get("source_page"):
                    errors.append(f"{gf.name}: concept '{c.get('slug')}' missing source_page")
            for edge in data.get("edges") or []:
                if edge.get("parent") not in slugs or edge.get("child") not in slugs:
                    errors.append(
                        f"{gf.name}: edge {edge.get('parent')}->{edge.get('child')} points outside concepts"
                    )
                if edge.get("kind") not in ("strict", "soft"):
                    errors.append(f"{gf.name}: invalid kind '{edge.get('kind')}'")
            if find_cycles(list(slugs), data.get("edges") or []):
                errors.append(f"{gf.name}: graph contains a cycle")
        except json.JSONDecodeError as exc:
            errors.append(f"{gf.name}: invalid JSON ({exc.msg})")
    return errors


def validate_redteam_fixtures(fix_dir: Path) -> list[str]:
    """Validate redteam prompt injection, pirated URLs, PII samples, and answer leak fixtures."""
    if not fix_dir.exists():
        return [f"Directory not found: {fix_dir}"]
    errors: list[str] = []
    pirated_file = fix_dir / "pirated_urls.jsonl"
    if not pirated_file.exists():
        errors.append(f"File not found: {pirated_file}")
    else:
        rows, parse_errors = _read_jsonl(pirated_file)
        errors += [f"pirated_urls {err}" for err in parse_errors]
        errors += [
            f"pirated_urls line {n}: missing url" for n, row in rows if not row.get("url")
        ]
    leaks_file = fix_dir / "answer_leaks.jsonl"
    if not leaks_file.exists():
        errors.append(f"File not found: {leaks_file}")
    else:
        rows, parse_errors = _read_jsonl(leaks_file)
        errors += [f"answer_leaks {err}" for err in parse_errors]
        if len(rows) < 30:
            errors.append(
                f"At least 30 answer-leak red-team cases required (found {len(rows)})"
            )
        for n, row in rows:
            if not row.get("id") or not row.get("prompt"):
                errors.append(
                    f"answer_leaks line {n}: missing id or answer-leak challenge prompt"
                )
    inj_files = list((fix_dir / "injections").glob("*.html"))
    if len(inj_files) < 15:
        errors.append(
            f"At least 15 injection HTML files required (found {len(inj_files)})"
        )
    pii_files = list((fix_dir / "pii_syllabi").glob("*.txt"))
    if len(pii_files) < 10:
        errors.append(
            f"At least 10 PII syllabus sample files required (found {len(pii_files)})"
        )
    return errors


def load_cases(path: Path) -> tuple[list[dict], list[str]]:
    """Parse a benchmark file and return (cases, errors)."""
    rows, errors = _read_jsonl(path)
    seen: set[str] = set()
    for n, case in rows:
        missing = [k for k in REQUIRED if not case.get(k)]
        if missing:
            errors.append(f"line {n}: missing fields {', '.join(missing)}")
        if case.get("kind") and case["kind"] not in KINDS:
            errors.append(
                f"line {n}: kind '{case['kind']}' not in {sorted(KINDS)}"
            )
        if case.get("use_case") and not USE_CASE_RE.match(case["use_case"]):
            errors.append(f"line {n}: use_case '{case['use_case']}' must match UC-01")
        if case.get("id") in seen:
            errors.append(f"line {n}: duplicate id '{case['id']}'")
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
        print(f"File not found: {path}.")
        return 1

    cases, errors = load_cases(path)
    if args.action == "stats":
        print(f"Total cases: {len(cases)}")
        for key in ("kind", "use_case"):
            counts = Counter(c.get(key, "?") for c in cases)
            print(
                f"By {key}: "
                + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
            )
        nodes, _ = load_resources(RESOURCES)
        labels = Counter(
            res.get("label") for node in nodes for res in node.get("resources") or []
        )
        if labels:
            print(
                f"Labelled resources: {labels.total()} across {len(nodes)} stages, "
                f"good={labels['good']}, bad={labels['bad']}"
            )

    ok = _report(errors, f"{len(cases)} valid cases in {path.name}")
    if args.action == "validate" and path == BENCHMARK:
        # The default run also checks the other #66 and #112 suites, so CI covers them too.
        nodes, resource_errors = load_resources(RESOURCES)
        gold_count = len(list(SYLLABUS_DIR.glob("*.gold.json")))
        graph_gold_count = len(list(GRAPHS_DIR.glob("*.gold.json")))
        ok = all(
            [
                ok,
                _report(
                    resource_errors,
                    f"{len(nodes)} stages with labelled resources in {RESOURCES.name}",
                ),
                _report(
                    validate_syllabus_benchmark(SYLLABUS_DIR),
                    f"{gold_count} valid syllabus benchmark + gold files in {SYLLABUS_DIR.name}/",
                ),
                _report(
                    validate_exercises_benchmark(EXERCISES),
                    f"60 valid exercise benchmark cases in {EXERCISES.name}",
                ),
                _report(
                    validate_graph_benchmark(GRAPHS_DIR),
                    f"{graph_gold_count} valid knowledge graph gold files in {GRAPHS_DIR.name}/",
                ),
                _report(
                    validate_redteam_fixtures(FIXTURES_DIR),
                    "Valid red-team fixtures (injections, pirated URLs, PII, answer_leaks)",
                ),
            ]
        )
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
        print(f"Could not read {path}: {exc}")
        return 1
    visuals = read_visuals(get_vision_client(), data, len(pages))
    concepts = extract_concepts(get_client(), pages, visuals)
    if args.json:
        print(json.dumps(concepts, ensure_ascii=False, indent=2))
        return 0
    for c in concepts:
        print(
            f"- {c['title']} [{c['slug']}, {c['bloom_level']}, pages {c['source_pages']}]"
        )
        print(f"  {c['summary']}")
    print(f"{path.name}: {len(pages)} pages, {len(concepts)} concepts")
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
        print(f"Could not read {path}: {exc}")
        return 1
    try:
        draft = extract_syllabus(get_client(), pages)
    except NotASyllabus as exc:
        print(f"{path.name}: not_a_syllabus ({exc})")
        return 1
    except (ValueError, RetryableError) as exc:
        print(f"{path.name}: LLM did not return a usable result ({exc})")
        return 1
    if args.json:
        result = {
            "parsed": draft.parsed,
            "warnings": [asdict(w) for w in draft.warnings],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    parsed = draft.parsed
    course = parsed["course"]
    print(
        f"# {course['code']} {course['title']} ({course['credits']} credits, "
        f"{course['term_start']} – {course['term_end']})"
    )
    for outcome in parsed["outcomes"]:
        print(
            f"- {outcome['code']} [{outcome['bloom_level']}, page {outcome['source_page']}] "
            f"{outcome['text']}"
        )
    for week in parsed["weeks"]:
        print(
            f"- Week {week['week']} [page {week['source_page']}]: {'; '.join(week['topics'])}"
        )
    for item in parsed["assessments"]:
        due = (
            item["due_date"] or (item["due_week"] and f"week {item['due_week']}") or "?"
        )
        print(
            f"- {item['title']} ({item['kind']}): {item['weight']}%, due {due} "
            f"[page {item['source_page']}]"
        )
    for warning in draft.warnings:
        print(
            f"[{'BLOCK' if warning.blocking else 'WARN'}] {warning.code}: {warning.message}"
        )
    print(f"{path.name}: {len(pages)} pages, {len(draft.warnings)} warnings")
    return 0


def _items(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv

    from app.ingest import InvalidPdf, extract_pages
    from app.items.find import find_items

    load_dotenv(ROOT / ".env")
    path = Path(args.file)
    try:
        pages = extract_pages(path.read_bytes())
        concepts = json.loads(Path(args.concepts).read_text(encoding="utf-8"))
    except (OSError, InvalidPdf, ValueError) as exc:
        print(f"Could not read input: {exc}")
        return 1
    sources = [
        {"id": f"p{n}", "page": n, "text": t}
        for n, t in enumerate(pages, 1)
        if t.strip()
    ]
    result = [
        {**c, "items": find_items(c, sources)} for c in concepts[: args.limit]
    ]
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    for c in result:
        print(f"## {c['title']}")
        for item in c["items"]:
            print(f"- [{item['type']}, page {item['source_id'][1:]}] {item['prompt']}")
            for choice in item["choices"]:
                print(f"    {'*' if choice == item['answer'] else ' '} {choice}")
            if item["rubric"]:
                print(f"    Answer: {item['answer']}")
                print(f"    Rubric: {'; '.join(item['rubric'])}")
    print(
        f"{path.name}: {sum(len(c['items']) for c in result)} items across {len(result)} concepts"
    )
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
        print("LLM provider is temporarily unavailable; please try again later.")
        return 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Could not parse syllabus: {exc}")
        return 1
    print(json.dumps(draft.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _tag_catalog(args):
    from dotenv import load_dotenv
    from sqlalchemy import text

    from app.catalog.taxonomy import tag_records
    from app.db import session_scope
    from app.llm import get_client
    from app.llm.embeddings import get_embedding_encoder

    load_dotenv(ROOT / ".env")
    with session_scope() as db:
        rows = list(
            db.execute(
                text(
                    "SELECT r.id,r.title,cc.code,cc.title AS course FROM resources r "
                    "LEFT JOIN catalog_courses cc ON cc.id=r.catalog_course_id"
                )
            ).mappings()
        )
        count = tag_records(
            db, "resource", rows, embedding=get_embedding_encoder(), llm=get_client()
        )
    print(f"[ OK ] Tagged {count} catalog resources")
    return 0


def _demands(db, values: list[str], benchmark: bool) -> list[tuple[str, object]]:
    """(label, SyllabusDemand) per --syllabus (a database id or a *.gold.json), in order."""
    from app.catalog.demand import SyllabusDemand
    from assistant.backend.catalog_ingest import syllabus_demand

    items = [(value, Path(value)) for value in values]
    if benchmark:
        items += [(str(path), path) for path in sorted(SYLLABUS_DIR.glob("*.gold.json"))]
    demands = []
    for value, path in items:
        if path.is_file():
            gold = json.loads(path.read_text(encoding="utf-8"))
            demands.append((gold["course_code"], SyllabusDemand.from_gold(gold)))
        elif (demand := syllabus_demand(db, value)) is not None:
            demands.append((value, demand))
        else:
            raise LookupError(value)
    return demands


def _catalog_ingest(args: argparse.Namespace) -> int:
    from datetime import UTC, datetime

    from dotenv import load_dotenv

    from app.catalog.connectors import ConnectorError, build_connectors
    from app.catalog.demand import priority_batches
    from app.catalog.sources import load_sources
    from app.vetting.fetch import DomainThrottle, SafeFetcher
    from assistant.backend.catalog_ingest import ingest, node_candidates
    from assistant.backend.config import Settings
    from assistant.backend.database import Database

    load_dotenv(ROOT / ".env")
    database = Database(Settings.from_env().database_url)
    database.create_schema()
    with database.sessions() as db:
        try:
            demands = _demands(db, args.syllabus or [], args.benchmark)
        except LookupError as exc:
            print(f"[FAIL] Syllabus not found: {exc}")
            return 2
    if not demands:
        print("[FAIL] Provide --syllabus <id or .gold.json file> or --benchmark")
        return 2
    since = datetime.fromisoformat(args.since).replace(tzinfo=UTC) if args.since else None
    sources = load_sources()
    now = datetime.now(UTC)
    failed = False
    with SafeFetcher(throttle=DomainThrottle(sources.rate_limits())) as fetcher:
        try:
            connectors = build_connectors(fetcher, args.connector, sources)
        except ConnectorError as exc:
            print(f"[FAIL] {exc.reason}")
            return 2
        for (label, _), (_, subjects) in zip(demands, priority_batches(d for _, d in demands)):
            print(f"== {label}: {len(subjects)} new subject tags {subjects}")
            for connector in connectors if subjects else []:
                # One transaction per connector: a later failure keeps earlier work.
                with database.sessions() as db:
                    report = ingest(db, connector, subjects, now=now, since=since, sources=sources)
                    db.commit()
                failed |= report.error is not None
                status = f"[FAIL] {report.error}" if report.error else "[ OK ]"
                print(
                    f"  {status} {report.connector}: {report.records} records, "
                    f"created {dict(report.created)}, updated {report.updated}, "
                    f"skipped {dict(report.skipped)}"
                )
    with database.sessions() as db:
        for label, demand in demands:
            counts = node_candidates(db, demand)
            ready = sum(count >= args.min for _, count in counts)
            print(f"== {label}: {ready}/{len(counts)} stages have >= {args.min} pending/verified candidates")
            for title, count in counts:
                print(f"  {'[ OK ]' if count >= args.min else '[MISSING]'} {count:>3}  {title[:70]}")
    return 1 if failed else 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("ai", help="AI implementation: benchmarks and assistant")
    ai_sub = p.add_subparsers(dest="ai_command", required=True)

    ai_sub.add_parser(
        "tag-catalog", help="assign taxonomy labels and embeddings to ingested catalog resources"
    ).set_defaults(func=_tag_catalog)

    ingest = ai_sub.add_parser(
        "catalog-ingest",
        help="ingest catalog resources (MIT OCW, OpenStax, Open Yale, manual YAML) for syllabus subjects",
    )
    ingest.add_argument(
        "--syllabus",
        action="append",
        help="syllabus id in DB or eval/syllabus/*.gold.json file; repeatable in priority order",
    )
    ingest.add_argument(
        "--benchmark", action="store_true", help="append all benchmark syllabi (#66) after --syllabus"
    )
    ingest.add_argument(
        "--connector",
        action="append",
        help="run only this connector (mit_ocw, openstax, open_yale, manual_yaml); repeatable",
    )
    ingest.add_argument("--since", help="ISO date; connectors with modification dates skip older entries")
    ingest.add_argument(
        "--min", type=int, default=5, help="minimum candidates per stage to report [ OK ] (default 5)"
    )
    ingest.set_defaults(func=_catalog_ingest)

    bench = ai_sub.add_parser(
        "benchmark", help="validate or summarize eval/benchmark.jsonl"
    )
    bench.add_argument("action", choices=["validate", "stats"])
    bench.add_argument("--file", default=str(BENCHMARK))
    bench.set_defaults(func=_benchmark)

    chat = ai_sub.add_parser(
        "chat", help="run the assistant (single question or interactive mode)"
    )
    chat.add_argument("question", nargs="*")
    chat.set_defaults(func=_chat)

    concepts = ai_sub.add_parser(
        "concepts", help="extract concepts from a PDF file (uses LLM_PROVIDER)"
    )
    concepts.add_argument("file")
    concepts.add_argument("--json", action="store_true", help="print output as JSON")
    concepts.set_defaults(func=_concepts)

    syllabus = ai_sub.add_parser(
        "syllabus", help="parse a PDF/DOCX/TXT syllabus (uses LLM_PROVIDER)"
    )
    syllabus.add_argument("file")
    syllabus.add_argument("--json", action="store_true", help="print output as JSON")
    syllabus.set_defaults(func=_syllabus)

    preview = ai_sub.add_parser(
        "syllabus-preview",
        help="preview a syllabus with source verification; offline by default",
    )
    preview.add_argument("file")
    preview.add_argument(
        "--llm",
        action="store_true",
        help="use the team's LLM parser instead of offline parsing",
    )
    preview.set_defaults(func=_syllabus_preview)

    items = ai_sub.add_parser(
        "items", help="extract existing exercises from a PDF without AI question authoring"
    )
    items.add_argument("file")
    items.add_argument(
        "--concepts", required=True, help="JSON from `ai concepts <file> --json`"
    )
    items.add_argument(
        "--limit", type=int, default=5, help="maximum number of concepts (default 5)"
    )
    items.add_argument("--json", action="store_true", help="print output as JSON")
    items.set_defaults(func=_items)
