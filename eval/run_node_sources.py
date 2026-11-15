"""Measure node sources against issue #102: CSC10014 coverage, Precision@5, summary p95.

Usage::

    python eval/run_node_sources.py              # all three, offline, in-memory SQLite
    python eval/run_node_sources.py --json
    python eval/run_node_sources.py --database-url postgresql+psycopg://u:p@host/db
        # p95 on an EMPTY database the run fills with its own roadmap and catalog
    python eval/run_node_sources.py --base-url https://api.example.org --token T --roadmap ID
        # p95 of an existing roadmap on staging; read only
    python eval/run_node_sources.py --record     # re-fetch the labelled pages (network)

Coverage. The CSC10014 reference graph (``eval/graphs``) is matched against the bundled
catalog sample the way roadmap generation does it (``refresh_node_sources``). A node
passes when it is covered (the learner's own material, or >= 3 verified sources) or says
``insufficient``; a node that says ``ready`` without being covered fails.

Precision@5. The #106 labelled nodes of the 5 benchmark syllabi (``eval/resources.jsonl``)
are matched against the sample plus the labelled pages. A labelled page joins the catalog
with the title recorded from the live page (``--record``); one that did not load or has
no title would fail the fetch or metadata check, so it stays out. Labels are read only
when scoring. ``strict`` counts a shown source that no label of the node covers as not
good; ``judged`` leaves it out (condensed lists). The two bracket the true value.

What it cannot say: the licence check is assumed passed (the labelled set records no
licence), and the catalog is the bundled sample plus the labelled pages, not production.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["LLM_PROVIDER"] = "fake"  # lexical tags and vectors only: offline, reproducible

from run_recommendations import BENCHMARK_SYLLABI
from sqlalchemy import select

from app.catalog import verification
from app.catalog.institutions import domain_of
from app.catalog.taxonomy import tag_records
from app.search import canonical_url
from assistant.backend.catalog_repository import ENOUGH_CATALOG, refresh_node_sources
from assistant.backend.catalog_snapshot import SAMPLE, load_snapshot, read_snapshot
from assistant.backend.database import Database
from assistant.backend.models import (
    Course,
    LearningOutcome,
    Resource,
    ResourceVerification,
    Roadmap,
    RoadmapNode,
    Syllabus,
    User,
)

GRAPH = ROOT / "eval" / "graphs" / "01_csc10014_problem_framing.gold.json"
SYLLABUS_DIR = ROOT / "eval" / "syllabus"
LABELS = ROOT / "eval" / "resources.jsonl"
PAGES = ROOT / "eval" / "fixtures" / "node_sources" / "labelled_pages.json"
COVERAGE_TARGET = 0.9
PRECISION_TARGET = 0.8
P95_BUDGET_MS = 300.0


@dataclass(frozen=True)
class Coverage:
    nodes: int
    covered: int  # own material or >= ENOUGH_CATALOG verified sources
    insufficient: int
    misleading: int  # "ready" without being covered
    unverified_shown: int
    passing_rate: float  # (covered + insufficient) / nodes, the done-when
    covered_rate: float


@dataclass(frozen=True)
class Precision:
    nodes: int
    shown_nodes: int  # nodes that showed at least one source; the rest abstained
    strict: float
    judged: float
    unjudged_shown: int


@dataclass(frozen=True)
class Latency:
    where: str
    runs: int
    p50_ms: float
    p95_ms: float


def percentile(values: list[float], share: float) -> float:
    """Nearest-rank percentile: the smallest value at least ``share`` of the runs reach."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def add_verified(db, now: datetime, url: str, title: str) -> Resource:
    """A catalog row whose four checks passed now, as ``verify_catalog`` leaves one."""
    url = canonical_url(url)
    row = Resource(
        url=url, canonical_url=url, title=title, provider="eval", kind="article",
        format="article", lang="en", license="unrecorded", is_free=True,
        verification_status="verified", content_hash=hashlib.sha256(url.encode()).hexdigest(),
        domain=domain_of(url), http_status=200,
    )
    db.add(row)
    db.flush()
    db.add_all(
        ResourceVerification(resource_id=row.id, check_name=check, result=verification.PASS,
                             checked_at=now, checked_by="eval:node-sources")
        for check in verification.CHECKS
    )
    return row


def _sample_catalog(now: datetime) -> Database:
    database = Database("sqlite://")
    database.create_schema()
    with database.sessions() as db:
        load_snapshot(db, read_snapshot(SAMPLE), now, restamp_by="eval:node-sources")
        db.commit()
    return database


def _owner(db) -> User:
    owner = User(email="eval-node-sources@example.com", password_hash="x", name="Eval")
    db.add(owner)
    db.flush()
    return owner


def _course(db, owner: User, stem: str, nodes: list[tuple[str, int]]):
    """Course, syllabus with its outcomes, and a roadmap of ``(title, week)`` topics."""
    gold = json.loads((SYLLABUS_DIR / f"{stem}.gold.json").read_text(encoding="utf-8"))
    course = Course(title=gold["course_name"], owner_id=owner.id, language="en",
                    level="university")
    db.add(course)
    db.flush()
    syllabus = Syllabus(course_id=course.id,
                        raw_text=(SYLLABUS_DIR / f"{stem}.txt").read_text(encoding="utf-8"))
    db.add(syllabus)
    db.flush()
    db.add_all(LearningOutcome(syllabus_id=syllabus.id, code=o["code"],
                               description=o["description"])
               for o in gold["learning_outcomes"])
    roadmap = Roadmap(course_id=course.id, user_id=owner.id, title=gold["course_code"])
    db.add(roadmap)
    db.flush()
    rows = [RoadmapNode(roadmap_id=roadmap.id, type="topic", title=title, week=week)
            for title, week in nodes]
    db.add_all(rows)
    db.flush()
    return course, roadmap, rows


def evaluate_coverage(now: datetime | None = None) -> Coverage:
    now = now or datetime.now(UTC)
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    database = _sample_catalog(now)
    try:
        with database.sessions() as db:
            course, roadmap, nodes = _course(
                db, _owner(db), GRAPH.name.removesuffix(".gold.json"),
                [(c["title"], c["week"]) for c in graph["concepts"]])
            selected = list(refresh_node_sources(db, nodes, roadmap, course, now).values())
    finally:
        database.engine.dispose()
    covered = sum(1 for s in selected
                  if s["user_material_count"] or s["source_count"] >= ENOUGH_CATALOG)
    insufficient = sum(1 for s in selected if s["status"] == "insufficient")
    return Coverage(
        nodes=len(selected),
        covered=covered,
        insufficient=insufficient,
        misleading=len(selected) - insufficient - covered,
        unverified_shown=sum(1 for s in selected for r in s["sources"]
                             if r["verification_status"] not in {"verified", "private"}),
        passing_rate=round((covered + insufficient) / len(selected), 3),
        covered_rate=round(covered / len(selected), 3),
    )


def labelled_nodes() -> list[dict]:
    codes = {code for _, code in BENCHMARK_SYLLABI}
    lines = LABELS.read_text(encoding="utf-8").splitlines()
    return [case for case in map(json.loads, filter(None, lines))
            if case["node"]["course_code"] in codes]


def _add_labelled_pages(db, now: datetime, cases: list[dict]) -> None:
    """Pages that loaded with a title join the catalog; the label is never read here."""
    pages = json.loads(PAGES.read_text(encoding="utf-8"))["pages"]
    known = set(db.scalars(select(Resource.canonical_url)))
    added = []
    for url in sorted({row["url"] for case in cases for row in case["resources"]}):
        page = pages.get(url, {})
        if page.get("status") == 200 and page.get("title") and canonical_url(url) not in known:
            added.append(add_verified(db, now, url, page["title"]))
    tag_records(db, "resource", [{"id": r.id, "title": r.title} for r in added])


def select_sources(cases: list[dict], now: datetime | None = None) -> dict[str, list[str]]:
    """The URLs each labelled node shows, chosen from the URLs alone: labels unread."""
    now = now or datetime.now(UTC)
    database = _sample_catalog(now)
    shown = {}
    try:
        with database.sessions() as db:
            _add_labelled_pages(db, now, cases)
            owner = _owner(db)
            for filename, code in BENCHMARK_SYLLABI:
                mine = [case for case in cases if case["node"]["course_code"] == code]
                course, roadmap, nodes = _course(
                    db, owner, filename.removesuffix(".gold.json"),
                    [(c["node"]["title"], c["node"]["week"]) for c in mine])
                selected = refresh_node_sources(db, nodes, roadmap, course, now)
                for case, node in zip(mine, nodes, strict=True):
                    shown[case["id"]] = [s["url"] for s in selected[node.id]["sources"][:5]]
    finally:
        database.engine.dispose()
    return shown


def evaluate_precision(now: datetime | None = None) -> Precision:
    cases = labelled_nodes()
    shown = select_sources(cases, now)
    strict, judged, unjudged = [], [], 0
    for case in cases:
        labels = {canonical_url(r["url"]): r["label"] for r in case["resources"]}
        marks = [labels.get(url) for url in shown[case["id"]]]
        if not marks:
            continue  # abstained: counted in ``shown_nodes``, not in the precision
        strict.append(marks.count("good") / len(marks))
        seen = [m for m in marks if m is not None]
        unjudged += len(marks) - len(seen)
        if seen:
            judged.append(seen.count("good") / len(seen))
    return Precision(
        nodes=len(cases),
        shown_nodes=len(strict),
        strict=round(sum(strict) / len(strict), 3) if strict else 0.0,
        judged=round(sum(judged) / len(judged), 3) if judged else 0.0,
        unjudged_shown=unjudged,
    )


def build_summary_load(client, headers: dict, sessions, now: datetime, *,
                       nodes: int = 40, catalog: int = 300) -> str:
    """A ``nodes``-topic roadmap whose subject has ``catalog`` verified sources; its id."""
    course = client.post("/api/v1/courses", headers=headers,
                         json={"title": "CSC10014", "language": "en"}).json()["id"]
    with sessions() as db:
        rows = [add_verified(db, now, f"https://ladder{i}.example.edu/notes",
                             f"Solution ladder notes, part {i}") for i in range(catalog)]
        tag_records(db, "resource", [{"id": r.id, "title": r.title} for r in rows])
        db.commit()
    response = client.post(
        f"/api/v1/courses/{course}/roadmap:generate", headers=headers,
        json={"nodes": [{"title": f"Solution ladder step {i}", "week": 1 + i // 4}
                        for i in range(nodes)]},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def measure_latency(get: Callable[[], int], where: str, *, runs: int = 20,
                    warmup: int = 3) -> Latency:
    """Time ``get``: one ``sources:summary`` request that returns its status code."""
    for _ in range(warmup):
        assert get() == 200
    timings = []
    for _ in range(runs):
        started = time.perf_counter()
        assert get() == 200
        timings.append((time.perf_counter() - started) * 1000)
    return Latency(where, runs, round(percentile(timings, 0.5), 1),
                   round(percentile(timings, 0.95), 1))


def latency_in_process(database_url: str) -> Latency:
    from fastapi.testclient import TestClient

    from assistant.backend.config import Settings
    from assistant.backend.main import create_app

    app = create_app(Settings(database_url=database_url))
    with TestClient(app) as client:  # startup applies the migrations
        with app.state.database.sessions() as db:
            if db.scalar(select(Resource.id).limit(1)) is not None:
                raise SystemExit(f"{database_url}: not empty; the run adds its own catalog")
        account = client.post("/api/v1/auth/register", json={
            "name": "Eval", "email": f"eval-{time.time_ns()}@example.com",
            "password": "correct-horse-123", "birth_year": 2004}).json()
        headers = {"Authorization": "Bearer " + account["access_token"]}
        roadmap = build_summary_load(client, headers, app.state.database.sessions,
                                     app.state.now())
        path = f"/api/v1/roadmaps/{roadmap}/sources:summary"
        dialect = app.state.database.engine.dialect.name
        return measure_latency(lambda: client.get(path, headers=headers).status_code,
                               f"in-process {dialect}, 40 nodes, 300 sources")


def latency_remote(base_url: str, token: str, roadmap: str) -> Latency:
    import httpx

    url = f"{base_url.rstrip('/')}/api/v1/roadmaps/{roadmap}/sources:summary"
    with httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=30) as client:
        return measure_latency(lambda: client.get(url).status_code, base_url)


def record_pages() -> int:
    """Fetch every labelled page once and keep the facts verification would read."""
    import trafilatura

    from app.vetting import SafeFetcher

    pages = {}
    with SafeFetcher() as fetcher:
        for url in sorted({row["url"] for case in labelled_nodes() for row in case["resources"]}):
            try:
                fetched = fetcher.fetch(url)
            except Exception as error:  # noqa: BLE001 - a failed fetch is itself the fact
                pages[url] = {"status": None, "title": None, "error": type(error).__name__}
                continue
            meta = (trafilatura.extract_metadata(fetched.text, default_url=fetched.final_url)
                    if fetched.status == 200 and "html" in fetched.content_type else None)
            pages[url] = {"status": fetched.status, "title": meta.title if meta else None}
    PAGES.parent.mkdir(parents=True, exist_ok=True)
    PAGES.write_text(json.dumps({"recorded": date.today().isoformat(), "pages": pages},
                                ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"recorded {len(pages)} pages to {PAGES.relative_to(ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--database-url", default="sqlite://")
    parser.add_argument("--base-url")
    parser.add_argument("--token")
    parser.add_argument("--roadmap")
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    if args.record:
        return record_pages()
    if args.base_url and not (args.token and args.roadmap):
        parser.error("--base-url needs --token and --roadmap")

    coverage, precision = evaluate_coverage(), evaluate_precision()
    latency = (latency_remote(args.base_url, args.token, args.roadmap) if args.base_url
               else latency_in_process(args.database_url))
    checks = {
        "coverage": coverage.passing_rate >= COVERAGE_TARGET and not coverage.unverified_shown,
        "precision_at_5": precision.strict >= PRECISION_TARGET,
        "summary_p95": latency.p95_ms < P95_BUDGET_MS,
    }
    if args.json:
        print(json.dumps({"coverage": asdict(coverage), "precision": asdict(precision),
                          "latency": asdict(latency), "checks": checks}, indent=2))
    else:
        print(f"Coverage CSC10014 ({coverage.nodes} nodes): {coverage.passing_rate:.1%} pass "
              f"(target {COVERAGE_TARGET:.0%}); covered {coverage.covered}, insufficient "
              f"{coverage.insufficient}, ready-but-uncovered {coverage.misleading}, "
              f"unverified shown {coverage.unverified_shown}")
        print(f"Precision@5 ({precision.shown_nodes}/{precision.nodes} nodes showed sources): "
              f"strict {precision.strict:.3f}, judged {precision.judged:.3f} "
              f"(target {PRECISION_TARGET}); {precision.unjudged_shown} shown sources unlabelled")
        print(f"sources:summary ({latency.where}): p50 {latency.p50_ms} ms, "
              f"p95 {latency.p95_ms} ms (budget {P95_BUDGET_MS:.0f} ms)")
        for name, ok in checks.items():
            print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
