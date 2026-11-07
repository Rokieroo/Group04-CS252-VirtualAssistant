"""Issue #105: fill catalog gaps by subject, keep the catalog fresh, seed dev and CI.

Offline: connectors are fakes and every fetcher serves fixed responses.
"""

import json
import time
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from test_catalog_connectors import record
from test_catalog_verification import Pages, make_admin, page
from test_role_catalog import add_resource, roadmap  # noqa: F401  (fixture)

from app.catalog.connectors import CONNECTORS, ConnectorError, FakeConnector
from app.vetting.fetch import DomainThrottle, RateBudgetExceeded
from assistant.backend import catalog_jobs, catalog_verification, jobs
from assistant.backend.catalog_ingest import ingest
from assistant.backend.catalog_models import NodeSourceStatus
from assistant.backend.catalog_repository import REMATCH
from assistant.backend.catalog_snapshot import (
    SAMPLE,
    export_snapshot,
    load_snapshot,
    read_snapshot,
)
from assistant.backend.database import Database
from assistant.backend.models import Job, Resource, ResourceVerification

SYLLABUS = Path(__file__).resolve().parents[1] / "eval/syllabus/01_csc10014_problem_framing.txt"


def kinds(db, kind):
    return list(db.scalars(select(Job).where(Job.kind == kind).order_by(Job.created_at)))


# --- limits ------------------------------------------------------------------------


def test_throttle_spends_an_hourly_budget_per_domain():
    now = [0.0]
    throttle = DomainThrottle(
        {"ocw.mit.edu": 10}, per_hour=2, clock=lambda: now[0],
        sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    throttle.wait("ocw.mit.edu")
    throttle.wait("www.ocw.mit.edu")  # another host of the same domain shares its budget
    with pytest.raises(RateBudgetExceeded) as spent:
        throttle.wait("ocw.mit.edu")
    assert spent.value.domain == "ocw.mit.edu"
    throttle.wait("openstax.org")  # other domains keep theirs
    now[0] += 3600
    throttle.wait("ocw.mit.edu")  # an hour later the budget is whole again


def test_ingest_stops_at_its_deadline_and_keeps_what_it_read_before_a_spent_budget(
    app, client, clock
):
    class Spent:
        name = "spent"

        def fetch(self, subjects, since=None):
            yield record()
            raise RateBudgetExceeded("en.wikipedia.org")

    with app.state.database.sessions() as db:
        late = ingest(db, FakeConnector([record()]), ["ct.use-cases"], now=clock[0],
                      deadline=time.monotonic() - 1)
        assert (late.error, late.records) == ("time_budget", 0)
        spent = ingest(db, Spent(), ["ct.use-cases"], now=clock[0])
        assert (spent.error, spent.created["resources"]) == ("rate_budget", 1)


def test_verification_waits_an_hour_when_a_domain_budget_is_spent(app, client, clock, monkeypatch):
    class Spent(Pages):
        def fetch(self, url):
            raise RateBudgetExceeded("source0.edu")

    monkeypatch.setattr(catalog_verification, "open_fetcher", lambda sources: Spent())
    with app.state.database.sessions() as db:
        resource = add_resource(db, clock[0], status="pending", days=2)
        result = catalog_verification.verify_catalog(db, {}, clock[0])
        db.commit()
        [chained] = kinds(db, catalog_verification.KIND)
        assert (result["checked"], result["deferred"]) == (0, True)
        assert chained.run_after == clock[0] + timedelta(hours=1)
        assert db.get(Resource, resource.id).verification_status == "pending"


# --- schedule ----------------------------------------------------------------------


def test_gaps_are_filled_each_night_and_every_connector_is_reread_each_month(app, client, clock):
    sessions = app.state.database.sessions
    for days in (0, 1, 31):  # 2030-01-07, 01-08 and 02-07
        with sessions() as db:
            catalog_jobs.schedule_nightly(db, clock[0] + timedelta(days=days))
            db.commit()
    with sessions() as db:
        fills = kinds(db, catalog_jobs.FILL)
        ingests = [job.dedupe_key for job in kinds(db, catalog_jobs.INGEST)]
    assert [(job.run_after.day, job.run_after.hour) for job in fills] == [(7, 19), (8, 19), (7, 19)]
    per_month = len(catalog_jobs.broad_subjects()) * len(CONNECTORS)
    assert len(ingests) == 2 * per_month  # the second day of January adds none
    assert {"ingest_catalog:mit_ocw:ct:2030-01", "ingest_catalog:openstax:db:2030-02"} <= set(ingests)


# --- the gap loop ------------------------------------------------------------------


def test_fill_gaps_queues_one_ingest_per_connector_and_subject_once_a_day(
    app, client, clock, roadmap  # noqa: F811
):
    with app.state.database.sessions() as db:
        first = catalog_jobs.fill_gaps(db, {}, clock[0])
        again = catalog_jobs.fill_gaps(db, {}, clock[0])
        db.commit()
        queued = {
            (json.loads(job.payload)["connector"], json.loads(job.payload)["subject"])
            for job in kinds(db, catalog_jobs.INGEST)
        }
    assert (first["insufficient_before"], first["insufficient_after"]) == (2, 2)
    assert first["subjects"] and first["ingest_jobs"] == len(first["subjects"]) * len(CONNECTORS)
    assert queued == {(c, s) for c in CONNECTORS for s in first["subjects"]}
    assert again["ingest_jobs"] == 0


def test_ingest_job_stores_new_sources_queues_their_verification_and_reports_failures(
    app, client, clock, monkeypatch
):
    def broken(fetcher, sources):
        raise ConnectorError("not_automatable_broken")

    monkeypatch.setattr(catalog_verification, "open_fetcher", lambda sources: Pages())
    monkeypatch.setitem(CONNECTORS, "fake", lambda fetcher, sources: FakeConnector([record()]))
    monkeypatch.setitem(CONNECTORS, "broken", broken)
    run = {"subject": "ct.use-cases"}
    with app.state.database.sessions() as db:
        stored = catalog_jobs.ingest_catalog(db, {**run, "connector": "fake"}, clock[0])
        failed = catalog_jobs.ingest_catalog(db, {**run, "connector": "broken"}, clock[0])
        again = catalog_jobs.ingest_catalog(db, {**run, "connector": "fake"}, clock[0])
        db.commit()
        verifications = kinds(db, catalog_verification.KIND)
    assert (stored["created"], stored["error"]) == ({"courses": 1, "resources": 1}, None)
    assert failed["error"] == "not_automatable_broken"  # reported; other connectors unaffected
    assert again["created"] == {} and len(verifications) == 1  # only new sources are verified


def test_verified_sources_reach_the_gap_nodes_and_the_gap_count_drops(
    app, client, clock, roadmap, monkeypatch  # noqa: F811
):
    sessions = app.state.database.sessions
    urls = [f"https://source{n}.edu/solution-ladder" for n in range(2)]
    monkeypatch.setattr(
        catalog_verification, "open_fetcher", lambda sources: Pages(*map(page, urls))
    )
    with sessions() as db:
        for number in range(2):  # ingested earlier, their last checks out of date
            add_resource(db, clock[0], number=number, status="pending", days=2)
        result = catalog_verification.verify_catalog(db, {}, clock[0])
        db.commit()
    assert result["verified"] == 2
    assert jobs.run_once(sessions, clock[0]) is not None  # the chain's last job queued it
    with sessions() as db:
        [rematch] = kinds(db, REMATCH)
        assert json.loads(rematch.result) == {"insufficient_before": 2, "insufficient_after": 1}
        assert db.get(NodeSourceStatus, roadmap["nodes"][0]["id"]).status == "ready"


def test_admin_sees_gaps_resources_connectors_and_dead_links(
    app, client, headers, account, clock, roadmap  # noqa: F811
):
    sessions = app.state.database.sessions
    with sessions() as db:
        jobs.enqueue(db, catalog_jobs.FILL, now=clock[0])
        db.commit()
    jobs.run_once(sessions, clock[0])
    with sessions() as db:
        for connector, error in (("fake", None), ("open_yale", "boom")):
            job = jobs.enqueue(db, catalog_jobs.INGEST, {"connector": connector, "subject": "ct"},
                               now=clock[0])
            job.status, job.updated_at = "done", clock[0]
            job.result = json.dumps({"created": {"resources": 3}, "error": error})
        dead = add_resource(db, clock[0], number=9)
        dead.failed_checks, dead.http_status = 2, 404
        db.commit()
    assert client.get("/api/v1/admin/catalog/health", headers=headers).status_code == 403
    make_admin(app, account["user"]["id"])
    health = client.get("/api/v1/admin/catalog/health", headers=headers).json()
    assert health["insufficient_nodes"] == 2 and health["gaps"][0]["nodes"] >= 1
    assert {row["connector"]: (row["runs"], row["errors"], row["last_error"])
            for row in health["connectors"]} == {"fake": (1, 0, None), "open_yale": (1, 1, "boom")}
    assert (health["dead_links"], health["dead"][0]["http_status"]) == (1, 404)
    assert health["gap_runs"][0]["kind"] == "fill_gaps"


# --- snapshot and seed -------------------------------------------------------------


def test_snapshot_carries_only_shared_rows_and_merges_by_natural_key(
    app, client, clock, roadmap, tmp_path  # noqa: F811
):
    with app.state.database.sessions() as db:
        ingest(db, FakeConnector([record()]), ["ct.use-cases"], now=clock[0])
        db.add(Resource(url="https://blog.example/web-only", canonical_url="https://blog.example/web-only",
                        title="Found by a learner's search"))
        db.commit()
        snapshot = export_snapshot(db, clock[0])
    text = json.dumps(snapshot)
    assert "web-only" not in text and "CSC10014" not in text  # no search rows, no learner rows
    assert [r["source_connector"] for r in snapshot["tables"]["resources"]] == ["fake"]

    copy = Database("sqlite:///" + (tmp_path / "copy.db").as_posix())
    copy.create_schema()
    url = record().url
    with copy.sessions() as db:
        local = Resource(url=url, canonical_url=url, title="Local", verification_status="rejected")
        db.add(local)
        db.flush()
        first = load_snapshot(db, snapshot, clock[0], restamp_by="seed:sample")
        second = load_snapshot(db, snapshot, clock[0], restamp_by="seed:sample")
        db.commit()
        # The local row keeps its id and its state; the copied rows point at it.
        assert "resources" not in first and "restamped" not in first and not second
        assert db.get(Resource, local.id).verification_status == "rejected"
        assert {v.resource_id for v in db.scalars(select(ResourceVerification))} <= {local.id}
    copy.engine.dispose()
    with pytest.raises(ValueError):
        load_snapshot(None, {"format": 99}, clock[0])


def test_bundled_sample_gives_a_new_csc10014_roadmap_catalog_sources_at_once(
    app, client, headers, clock
):
    """Done when (#105): a new machine, the sample seeded, the CSC10014 syllabus uploaded."""
    with app.state.database.sessions() as db:
        added = load_snapshot(db, read_snapshot(SAMPLE), clock[0], restamp_by="seed:sample")
        db.commit()
    assert added["restamped"] >= 15  # a sample years old still counts as freshly checked
    course = client.post("/api/v1/courses", headers=headers, json={
        "title": "Problem Framing and Solution Architecture", "level": "university",
        "language": "en"}).json()["id"]
    client.post(f"/api/v1/courses/{course}/sources", headers=headers, data={"kind": "syllabus"},
                files={"file": (SYLLABUS.name, SYLLABUS.read_bytes(), "text/plain")})
    parsed = client.post(f"/api/v1/courses/{course}/syllabus:parse", headers=headers,
                         json={"file_name": SYLLABUS.name, "use_llm": False}).json()["parsed"]
    syllabus = client.post(f"/api/v1/courses/{course}/syllabus", headers=headers, json={
        "raw_text": SYLLABUS.read_text(encoding="utf-8"),
        "outcomes": [{"code": o["code"], "description": o["text"]} for o in parsed["outcomes"]],
        "assessments": [{"name": a["title"], "weight": a["weight"],
                         "due_week": int(a["due"].split()[-1])} for a in parsed["assessments"]],
    }).json()["id"]
    graph = client.post(f"/api/v1/courses/{course}/roadmap:generate", headers=headers,
                        json={"syllabus_id": syllabus}).json()

    summary = client.get(f"/api/v1/roadmaps/{graph['id']}/sources:summary", headers=headers)
    ready = [n for n in summary.json()["nodes"] if n["status"] == "ready"]
    assert len(ready) >= len(graph["nodes"]) // 2, summary.text
    with app.state.database.sessions() as db:
        assert catalog_jobs.fill_gaps(db, {}, clock[0])["insufficient_after"] == (
            len(graph["nodes"]) - len(ready)  # the rest is what tonight's gap filling targets
        )


def test_seed_catalog_command_loads_the_sample_once(tmp_path, monkeypatch, capsys):
    from devcli.__main__ import build_parser

    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + (tmp_path / "dev.db").as_posix())
    args = build_parser().parse_args(["db", "seed-catalog", "--sample"])
    assert args.func(args) == 0 and "'resources': 34" in capsys.readouterr().out
    assert args.func(args) == 0 and "không có dòng mới" in capsys.readouterr().out
