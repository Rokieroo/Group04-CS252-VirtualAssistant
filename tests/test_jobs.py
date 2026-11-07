"""#68: background jobs, the worker, the shared search cache and link maintenance."""

import json
import threading
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app import vetting
from app.search import node_signature
from app.vetting import check_url, is_public_url, link_verdict
from assistant.backend import jobs, maintenance, worker
from assistant.backend.cache import cached_search, store_search
from assistant.backend.config import Settings
from assistant.backend.models import Job, NodeResource, Resource, SearchCacheEntry

NOW = datetime(2030, 1, 7, tzinfo=UTC)
DAY = timedelta(days=1)


@pytest.fixture
def sessions(app, client):
    """Sessions on the migrated test database (the client's startup migrates it)."""
    return app.state.database.sessions


@pytest.fixture
def echo(monkeypatch):
    calls = []

    def run(db, payload, now):
        calls.append(payload)
        if payload.get("fail"):
            raise RuntimeError("boom")
        return {"echo": payload}

    monkeypatch.setitem(jobs.HANDLERS, "echo", run)
    return calls


def add_job(sessions, kind="echo", payload=None, now=NOW, **options):
    with sessions() as db:
        job = jobs.enqueue(db, kind, payload, now=now, **options)
        db.commit()
        return job.id if job else None


def load(sessions, job_id):
    with sessions() as db:
        return db.get(Job, job_id)


# --- queue -----------------------------------------------------------------------


def test_job_runs_once_and_stores_its_result(sessions, echo):
    job_id = add_job(sessions, payload={"n": 1})
    assert jobs.run_once(sessions, NOW) == job_id
    job = load(sessions, job_id)
    assert (job.status, job.attempts) == ("done", 1)
    assert json.loads(job.result) == {"echo": {"n": 1}}
    assert jobs.run_once(sessions, NOW) is None  # nothing else is due
    assert echo == [{"n": 1}]


def test_failed_job_backs_off_then_fails_after_max_attempts(sessions, echo):
    job_id = add_job(sessions, payload={"fail": True})
    now = NOW
    for attempt in range(1, jobs.MAX_ATTEMPTS + 1):
        assert jobs.run_once(sessions, now) == job_id
        job = load(sessions, job_id)
        assert (job.attempts, job.error) == (attempt, "RuntimeError")
        if attempt < jobs.MAX_ATTEMPTS:
            assert job.status == "queued"
            assert job.run_after == now + jobs.RETRY_DELAY * 2 ** (attempt - 1)
            assert jobs.run_once(sessions, now) is None  # not due during the backoff
            now = job.run_after
    assert load(sessions, job_id).status == "failed"


def test_a_claimed_job_is_not_claimed_again_until_its_lease_expires(sessions, echo):
    job_id = add_job(sessions)
    with sessions() as db:  # a worker claims it, then dies without finishing
        assert jobs._claim(db, NOW) == job_id
        db.commit()
    assert jobs.run_once(sessions, NOW + jobs.LEASE - timedelta(seconds=1)) is None
    assert jobs.run_once(sessions, NOW + jobs.LEASE) == job_id
    job = load(sessions, job_id)
    assert (job.status, job.attempts) == ("done", 2)


def test_dedupe_key_keeps_one_job_and_unknown_kinds_are_rejected(sessions, echo):
    assert add_job(sessions, dedupe_key="daily:2030-01-07") is not None
    assert add_job(sessions, dedupe_key="daily:2030-01-07") is None
    with sessions() as db, pytest.raises(ValueError):
        jobs.enqueue(db, "no_such_job", now=NOW)


def test_schedule_daily_enqueues_upkeep_once_per_day(sessions):
    for now in (NOW, NOW + timedelta(hours=5), NOW + DAY):
        with sessions() as db:
            maintenance.schedule_daily(db, now)
            db.commit()
    with sessions() as db:
        keys = sorted(db.scalars(select(Job.dedupe_key)))
    # The monthly catalog re-reads (#105) are tested in test_catalog_jobs.py.
    assert [key for key in keys if not key.startswith("ingest_catalog:")] == [
        "check_links:2030-01-07",
        "check_links:2030-01-08",
        "fill_gaps:2030-01-07",
        "fill_gaps:2030-01-08",
        "prune:2030-01-07",
        "prune:2030-01-08",
        "verify_catalog:2030-01-07",
        "verify_catalog:2030-01-08",
    ]


# --- link maintenance --------------------------------------------------------------


def shown_resources(client, headers, sessions, urls):
    course = client.post("/api/v1/courses", headers=headers, json={"title": "Algo"})
    roadmap = client.post(
        f"/api/v1/courses/{course.json()['id']}/roadmap:generate",
        headers=headers,
        json={"nodes": [{"title": "Framing", "week": 1}]},
    ).json()
    node_id = roadmap["nodes"][0]["id"]
    with sessions() as db:
        resources = [Resource(url=url, canonical_url=url, title=url) for url in urls]
        db.add_all(resources)
        db.flush()
        db.add_all(NodeResource(node_id=node_id, resource_id=r.id) for r in resources)
        db.commit()
        return [r.id for r in resources]


def run_check(sessions, now):
    job_id = add_job(sessions, "check_links", now=now)
    assert jobs.run_once(sessions, now) == job_id
    return load(sessions, job_id)


def link_state(sessions, resource_id):
    with sessions() as db:
        resource = db.get(Resource, resource_id)
        shown = db.scalars(
            select(NodeResource.status).where(NodeResource.resource_id == resource_id)
        ).one()
        return resource.failed_checks, resource.http_status, shown


def test_link_dead_twice_in_a_row_is_removed_and_alive_resets(
    client, headers, sessions, monkeypatch
):
    replies = {
        "https://example.org/dead": [404, 404],
        "https://example.org/flaky": [500, 200],
        "https://example.org/blocked": [403, 403],
    }
    dead, flaky, blocked = shown_resources(client, headers, sessions, list(replies))
    monkeypatch.setattr(vetting, "check_url", lambda url: replies[url].pop(0))

    first = run_check(sessions, NOW)
    assert json.loads(first.result) == {"checked": 3, "removed": 0}
    assert link_state(sessions, dead) == (1, 404, "shown")
    # Checked less than 24 hours ago: not due yet.
    early = run_check(sessions, NOW + timedelta(hours=23))
    assert json.loads(early.result)["checked"] == 0

    second = run_check(sessions, NOW + DAY)
    assert json.loads(second.result) == {"checked": 3, "removed": 1}
    assert link_state(sessions, dead) == (2, 404, "removed")
    assert link_state(sessions, flaky) == (0, 200, "shown")
    assert link_state(sessions, blocked) == (0, 403, "shown")  # inconclusive


def test_no_answer_from_any_link_is_treated_as_our_outage(
    client, headers, sessions, monkeypatch
):
    urls = [f"https://example.org/{i}" for i in range(3)]
    ids = shown_resources(client, headers, sessions, urls)
    monkeypatch.setattr(vetting, "check_url", lambda url: None)
    job = run_check(sessions, NOW)
    assert (job.status, job.error) == ("queued", "NetworkDown")
    assert all(link_state(sessions, i) == (0, None, "shown") for i in ids)


def test_large_backlogs_are_checked_in_chained_batches(
    client, headers, sessions, monkeypatch
):
    urls = [f"https://example.org/{i}" for i in range(3)]
    shown_resources(client, headers, sessions, urls)
    monkeypatch.setattr(vetting, "check_url", lambda url: 200)
    monkeypatch.setattr(maintenance, "BATCH", 2)
    assert json.loads(run_check(sessions, NOW).result)["checked"] == 2
    follow_up = jobs.run_once(sessions, NOW)  # chained by the first batch
    assert json.loads(load(sessions, follow_up).result)["checked"] == 1
    assert jobs.run_once(sessions, NOW) is None


def test_link_verdicts_and_public_url_guard():
    statuses = (200, 301, 404, 500, None, 403, 429)
    assert [link_verdict(s) for s in statuses] == [
        True, True, False, False, False, None, None,
    ]
    assert is_public_url("https://93.184.216.34/page")
    for unsafe in (
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data",
        "ftp://93.184.216.34/",
        "notaurl",
    ):
        assert not is_public_url(unsafe), unsafe
    assert check_url("http://127.0.0.1:8000/") is None  # never contacted


def test_check_url_falls_back_to_get_and_never_follows_redirects():
    seen = []

    def reply(request):
        seen.append(request.method)
        if request.url.path == "/moved":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/"})
        return httpx.Response(405 if request.method == "HEAD" else 200)

    transport = httpx.MockTransport(reply)
    assert check_url("https://93.184.216.34/page", transport=transport) == 200
    assert seen == ["HEAD", "GET"]
    assert check_url("https://93.184.216.34/moved", transport=transport) == 302


# --- cache and pruning --------------------------------------------------------------


def test_node_signature_ignores_spelling_and_order_but_not_language():
    outcomes = ["CLO2 sort", "CLO1 greedy"]
    key = node_signature("Giải thuật  Tham lam", outcomes, "university", "vi")
    assert key == node_signature(
        "giai thuat tham lam!", list(reversed(outcomes)), "University", "VI"
    )
    english = node_signature("Giải thuật Tham lam", outcomes, "university", "en")
    assert key != english
    assert len(key) == 64


def test_search_cache_is_shared_for_seven_days(sessions):
    with sessions() as db:
        store_search(db, "sig", [{"url": "https://example.org"}], NOW)
        db.commit()
    with sessions() as db:
        hit = cached_search(db, "sig", NOW + 6 * DAY)
        assert hit == [{"url": "https://example.org"}]
        assert cached_search(db, "sig", NOW + 7 * DAY) is None
        assert cached_search(db, "missing", NOW) is None
        store_search(db, "sig", ["fresh"], NOW + 7 * DAY)  # refresh after expiry
        db.commit()
    with sessions() as db:
        assert cached_search(db, "sig", NOW + 13 * DAY) == ["fresh"]


def test_prune_drops_expired_cache_and_old_finished_jobs(sessions, echo):
    old = add_job(sessions)
    jobs.run_once(sessions, NOW)
    pending = add_job(sessions, run_after=NOW + 60 * DAY)
    with sessions() as db:
        store_search(db, "stale", [], NOW - 8 * DAY)
        store_search(db, "fresh", [], NOW + 30 * DAY)
        db.commit()
    with sessions() as db:
        assert maintenance.prune(db, {}, NOW + maintenance.JOB_RETENTION) == {
            "cache_entries": 1,
            "jobs": 1,
        }
        db.commit()
        assert db.get(Job, old) is None and db.get(Job, pending) is not None
        assert db.get(SearchCacheEntry, "stale") is None
        assert db.get(SearchCacheEntry, "fresh") is not None


# --- API, worker, secrets ------------------------------------------------------------


def test_only_the_owner_can_poll_a_job(
    client, user_a, headers_a, headers_b, sessions, echo
):
    mine = add_job(sessions, user_id=user_a["user"]["id"])
    system = add_job(sessions)
    polled = client.get(f"/api/v1/jobs/{mine}", headers=headers_a)
    assert polled.status_code == 200, polled.text
    assert (polled.json()["status"], polled.json()["result"]) == ("queued", None)
    jobs.run_once(sessions, NOW)
    jobs.run_once(sessions, NOW)
    done = client.get(f"/api/v1/jobs/{mine}", headers=headers_a).json()
    assert (done["status"], done["result"]) == ("done", {"echo": {}})
    for job_id, who in ((mine, headers_b), (system, headers_a), ("nope", headers_a)):
        assert client.get(f"/api/v1/jobs/{job_id}", headers=who).status_code == 404


def test_worker_schedules_upkeep_and_runs_jobs_until_stopped(app, client, monkeypatch):
    monkeypatch.setattr(vetting, "check_url", lambda url: 200)
    # The nightly catalog jobs read providers over the network; test_catalog_jobs.py.
    monkeypatch.setattr(maintenance.catalog_jobs, "schedule_nightly", lambda db, now: None)
    stop = threading.Event()
    ran = []
    real_run_once = jobs.run_once

    def run_and_stop(sessions, now):
        ran.append(real_run_once(sessions, now))
        if len(ran) == len(maintenance.DAILY):
            stop.set()
        return ran[-1]

    monkeypatch.setattr(worker, "run_once", run_and_stop)
    worker.serve(app.state.database, stop)
    with app.state.database.sessions() as db:
        statuses = {job.kind: job.status for job in db.scalars(select(Job))}
    assert statuses == {"check_links": "done", "prune": "done", "verify_catalog": "done"}


def test_search_keys_come_from_the_environment_and_stay_out_of_repr(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt-placeholder")
    monkeypatch.setenv("SEARCH_API_KEY", "search-placeholder")
    settings = Settings.from_env()
    assert (settings.youtube_api_key, settings.search_api_key) == (
        "yt-placeholder",
        "search-placeholder",
    )
    assert "placeholder" not in repr(settings)
