"""Issue #101: verify or drop, the review queue and the admin decisions.

Offline: the job's fetcher is replaced by a dict of fixed responses.
"""

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from test_role_catalog import add_resource, roadmap  # noqa: F401  (fixture)

from app.catalog import verification as rules
from app.catalog.sources import load_sources
from app.catalog.taxonomy import save_tags, tag_resource
from app.search.catalog import CatalogSearch
from app.vetting.fetch import FetchResult
from app.vetting.policy import default_policy
from assistant.backend import catalog_verification, jobs
from assistant.backend.catalog_models import ResourceVerification
from assistant.backend.catalog_repository import verified_resources
from assistant.backend.models import Job, NodeResource, Resource, User

MIT = "https://ocw.mit.edu/courses/6-0002-intro-fall-2016/"
WEB = "https://example.edu/solution-ladder"
UNLICENSED = "https://example.edu/use-cases"
GONE = "https://example.edu/gone"
SLOW = "https://example.edu/slow"
FAKE = "https://ocw.mit.edu.study-notes.example/6-0002"
KHAN = "https://www.khanacademy.org/computing/computer-science"


def page(url, **changes):
    values = {"url": url, "final_url": url, "status": 200, "content_type": "text/html",
              "body": b"<html>notes</html>"}
    return FetchResult(**{**values, **changes})


class Pages:
    """A fetcher serving fixed responses; any other URL answers 404."""

    def __init__(self, *responses):
        self.responses = {r.url: r for r in responses}
        self.seen = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        pass

    def fetch(self, url):
        self.seen.append(url)
        return self.responses.get(url, page(url, status=404, body=b""))


@pytest.fixture
def pages(monkeypatch):
    fetcher = Pages(
        page(MIT), page(WEB), page(UNLICENSED), page(FAKE), page(SLOW, status=None, error="timeout"),
        page("https://source0.edu/solution-ladder"),
    )
    monkeypatch.setattr(catalog_verification, "open_fetcher", lambda sources: fetcher)
    return fetcher


def add(db, url, *, provider="web", license="CC-BY-4.0", status="pending", title="Solution ladder"):
    row = Resource(url=url, canonical_url=url, title=title, provider=provider, lang="en",
                   kind="reading", format="reading", license=license, verification_status=status)
    db.add(row)
    db.flush()
    return row


def checks(db, resource_id):
    rows = db.execute(
        select(ResourceVerification.check_name, ResourceVerification.result,
               ResourceVerification.checked_by)
        .where(ResourceVerification.resource_id == resource_id)
    )
    return sorted(rows.all())


def make_admin(app, user_id):
    with app.state.database.sessions() as db:
        db.get(User, user_id).role = "admin"
        db.commit()


# --- the four checks ---------------------------------------------------------------


def test_fetch_check_tells_dead_pages_from_unanswered_ones():
    assert rules.fetch_check(page(WEB)).result == "pass"
    assert rules.fetch_check(page(WEB, status=404)) == rules.Check("fetch", "fail", "http_404")
    assert rules.fetch_check(page(WEB, paywall="login_form")).reason == "login_form"
    # No verdict on a page that did not answer: rejected sources never come back.
    for unanswered in (page(WEB, status=None, error="timeout"), page(WEB, status=503)):
        assert rules.fetch_check(unanswered).result == "error"
    # ADR 004 section 9: robots.txt sends it to a person, not to `rejected`.
    assert rules.fetch_check(page(WEB, status=None, error="robots")).result == "review"
    assert rules.fetch_check(None) == rules.Check("fetch", "review", "manual_check_required")


def test_domain_check_refuses_blocked_mismatched_and_impersonating_hosts():
    def check(url, provider="web", final_url="", institution=None):
        facts = rules.Facts(url, "T", provider, "CC-BY-4.0", "en", "reading", "undergrad",
                            institution_domain=institution)
        return rules.domain_check(facts, sources=load_sources(), policy=default_policy(),
                                  known_domains=["mit.edu", "ocw.mit.edu"],
                                  final_url=final_url).reason

    assert check("https://www.chegg.com/homework-help") == "blocked_domain"
    assert check("https://example.edu/x", provider="mit_ocw") == "provider_domain_mismatch"
    assert check("https://example.edu/x", institution="mit.edu") == "institution_domain_mismatch"
    assert check(WEB, final_url="https://spam.example/landing") == "redirected_off_site"
    assert check(FAKE) == "impersonates:mit.edu"
    assert check(MIT, provider="mit_ocw", final_url=MIT, institution="mit.edu") == ""
    assert check("https://example.edu/x", final_url="https://www.example.edu/x") == ""


def test_license_and_metadata_checks():
    sources = load_sources()
    mit = sources.providers["mit_ocw"]

    def facts(**changes):
        values = {"url": MIT, "title": "Intro", "provider": "mit_ocw",
                  "license": "CC-BY-NC-SA-4.0", "lang": "en", "format": "course",
                  "level": "undergrad"}
        return rules.Facts(**{**values, **changes})

    assert rules.license_check(facts(), mit, sources).result == "pass"
    assert rules.license_check(facts(license=None), mit, sources).result == "review"
    assert rules.license_check(facts(license="CC-BY-ND-4.0"), mit, sources).reason == "license_not_allowed"
    assert rules.license_check(facts(license="CC-BY-4.0"), mit, sources).reason == "license_not_used_by_provider"
    assert rules.metadata_check(facts()).result == "pass"
    assert rules.metadata_check(facts(title=" ")).reason == "bad_title"
    assert rules.metadata_check(facts(lang="english")).reason == "bad_language"
    assert rules.metadata_check(facts(format="podcast")).reason == "bad_format"
    assert rules.metadata_check(facts(level="phd")).reason == "bad_level"
    assert rules.metadata_check(facts(labels=(0.4, 0.5))).reason == "uncertain_subjects"
    assert rules.metadata_check(facts(labels=(0.4, 0.9))).result == "pass"


def test_decide():
    passed = [rules.Check(name, "pass") for name in rules.CHECKS]
    assert rules.decide(passed) == "verified"
    assert rules.decide([*passed[:3], rules.Check("metadata", "fail")]) == "rejected"
    assert rules.decide([*passed[:3], rules.Check("metadata", "review")]) is None
    assert rules.decide([rules.Check("fetch", "error"), *passed[1:]]) is None


# --- the job -----------------------------------------------------------------------


def test_job_verifies_rejects_and_queues_and_never_rereads(app, client, clock, pages):
    now = clock[0]
    with app.state.database.sessions() as db:
        ids = {
            "mit": add(db, MIT, provider="mit_ocw", license="CC-BY-NC-SA-4.0").id,
            "web": add(db, WEB).id,
            "unlicensed": add(db, UNLICENSED, license=None).id,
            "gone": add(db, GONE).id,
            "fake": add(db, FAKE).id,
            "slow": add(db, SLOW).id,
            "khan": add(db, KHAN, provider="khan_academy", license=None).id,
        }
        db.commit()
        result = catalog_verification.verify_catalog(db, {}, now)
        db.commit()
        status = {name: db.get(Resource, i).verification_status for name, i in ids.items()}

        assert result == {"stale": 0, "checked": 7, "deferred": False, "verified": 2,
                          "rejected": 2, "review": 2, "retry": 1}
        assert status == {"mit": "verified", "web": "verified", "unlicensed": "pending",
                          "gone": "rejected", "fake": "rejected", "slow": "pending",
                          "khan": "pending"}
        # One row per check, by the job; the fetched page's hash is kept.
        assert checks(db, ids["mit"]) == [(c, "pass", "job:verify_catalog") for c in sorted(rules.CHECKS)]
        assert db.get(Resource, ids["mit"]).content_hash == page(MIT).content_hash
        # ADR 004 section 7: no program request to a provider that forbids it.
        assert KHAN not in pages.seen
        # Done when: every verified resource has its four checks passed.
        verified = select(Resource.id).where(Resource.verification_status == "verified")
        latest = rules.latest_results(db.execute(
            select(ResourceVerification.resource_id, ResourceVerification.check_name,
                   ResourceVerification.result, ResourceVerification.checked_at)
            .where(ResourceVerification.resource_id.in_(verified))
            .order_by(ResourceVerification.checked_at.desc())))
        assert len(latest) == 2 and all(rules.is_current(v, now) for v in latest.values())

        # The queue waits for a person; the unanswered page waits one day.
        assert catalog_verification.due(db, now + timedelta(hours=1)) == []
        assert [r.id for r in catalog_verification.due(db, now + timedelta(hours=25))] == [ids["slow"]]


def test_an_offline_batch_records_nothing_and_retries(app, client, clock, monkeypatch):
    offline = Pages(*(page(f"https://example.edu/{n}", status=None, error="network") for n in range(3)))
    monkeypatch.setattr(catalog_verification, "open_fetcher", lambda sources: offline)
    sessions = app.state.database.sessions
    with sessions() as db:
        for n in range(3):
            add(db, f"https://example.edu/{n}")
        job = jobs.enqueue(db, catalog_verification.KIND, now=clock[0])
        db.commit()
        job_id = job.id
    jobs.run_once(sessions, clock[0])
    with sessions() as db:
        assert (db.get(Job, job_id).status, db.get(Job, job_id).error) == ("queued", "NetworkDown")
        assert db.scalar(select(func.count()).select_from(ResourceVerification)) == 0


def test_resources_current_nodes_need_are_verified_first(app, client, clock, roadmap):  # noqa: F811
    node = roadmap["nodes"][0]["id"]  # "Solution ladder"
    with app.state.database.sessions() as db:
        unused = add(db, "https://example.edu/a", title="Quantum chromodynamics")
        labelled = add(db, "https://example.edu/b", title="Solution ladder")
        save_tags(db, "resource", labelled.id, tag_resource({"title": labelled.title}), labelled.title)
        shown = add(db, "https://example.edu/c", title="Quantum field theory")
        db.add(NodeResource(node_id=node, resource_id=shown.id, relevance_score=0.9))
        db.commit()
        order = [r.id for r in catalog_verification.due(db, clock[0])]
    assert order == [shown.id, labelled.id, unused.id]


def test_expired_passes_go_stale_hidden_until_checked_again(app, client, clock, pages):
    now = clock[0]
    with app.state.database.sessions() as db:
        old = add_resource(db, now, number=0, days=31)
        fresh = add_resource(db, now, number=1, days=29)
        db.commit()
        assert catalog_verification.mark_stale(db, now) == 1
        assert {r["id"] for r in verified_resources(db, now)} == {fresh.id}
        db.refresh(old)
        assert old.verification_status == "stale"

        result = catalog_verification.verify_catalog(db, {}, now)
        db.commit()
        db.refresh(old)
        assert (result["stale"], result["verified"], old.verification_status) == (0, 1, "verified")
        assert {r["id"] for r in verified_resources(db, now)} == {old.id, fresh.id}


@pytest.mark.parametrize("status", ["pending", "rejected", "stale"])
def test_unverified_statuses_never_reach_a_node_even_with_fresh_passes(
    app, client, headers, clock, roadmap, status  # noqa: F811
):
    node = roadmap["nodes"][0]["id"]
    with app.state.database.sessions() as db:
        resource = add_resource(db, clock[0], status=status)
        db.add(NodeResource(node_id=node, resource_id=resource.id, relevance_score=0.95))
        db.commit()
        assert verified_resources(db, clock[0]) == []
        assert CatalogSearch(session=db, now=clock[0]).search("Solution ladder", lang="en") == []
    sources = client.get(f"/api/v1/concepts/{node}/sources", headers=headers).json()
    assert sources["sources"] == [] and sources["status"] == "insufficient"
    legacy = client.get(f"/api/v1/roadmap-nodes/{node}/resources", headers=headers).json()
    assert legacy["resources"] == []
    summary = client.get(f"/api/v1/roadmaps/{roadmap['id']}/sources:summary", headers=headers)
    assert all(n["source_count"] == 0 for n in summary.json()["nodes"])


# --- people ------------------------------------------------------------------------


def test_students_get_403_from_every_catalog_admin_route(client, headers):
    body = {"reason": "looks fine", "license": "CC-BY-4.0"}
    assert client.get("/api/v1/admin/catalog/review-queue", headers=headers).status_code == 403
    for action in ("verify", "reject"):
        path = f"/api/v1/admin/catalog/resources/any-id:{action}"
        assert client.post(path, headers=headers, json=body).status_code == 403
        assert client.post(path, json=body).status_code == 401


def test_admin_reviews_the_queue_with_a_reason(app, client, headers, account, clock, pages):
    make_admin(app, account["user"]["id"])
    with app.state.database.sessions() as db:
        unlicensed = add(db, UNLICENSED, license=None).id
        catalog_verification.verify_catalog(db, {}, clock[0])
        takedown = add_resource(db, clock[0], number=0).id
        db.commit()
    clock[0] += timedelta(minutes=5)  # a reviewer acts after the job's run, never with it
    base = "/api/v1/admin/catalog"

    queue = client.get(f"{base}/review-queue", headers=headers).json()["resources"]
    assert [r["id"] for r in queue] == [unlicensed]
    assert {c["check"]: (c["result"], c["reason"]) for c in queue[0]["checks"]}["license"] == (
        "review", "license_unknown")

    verify = f"{base}/resources/{unlicensed}:verify"
    assert client.post(verify, headers=headers, json={"reason": "ok"}).status_code == 422
    missing = client.post(verify, headers=headers, json={"reason": "read the footer"})
    assert (missing.status_code, missing.json()["detail"]) == (422, "license_required")
    assert client.post(verify, headers=headers,
                       json={"reason": "footer", "license": "CC-BY-ND-4.0"}).status_code == 422
    done = client.post(verify, headers=headers,
                       json={"reason": "footer says CC BY 4.0", "license": "CC-BY-4.0"})
    assert done.json() == {"id": unlicensed, "verification_status": "verified", "license": "CC-BY-4.0"}

    reject = client.post(f"{base}/resources/{takedown}:reject", headers=headers,
                         json={"reason": "takedown"})
    assert reject.json()["verification_status"] == "rejected"
    assert client.post(f"{base}/resources/nope:reject", headers=headers,
                       json={"reason": "takedown"}).status_code == 404

    with app.state.database.sessions() as db:
        assert {r["id"] for r in verified_resources(db, clock[0])} == {unlicensed}
        admin_rows = db.scalars(select(ResourceVerification).where(
            ResourceVerification.checked_by == account["user"]["id"])).all()
        assert sorted((r.check_name, r.result) for r in admin_rows) == [
            ("admin", "fail"), *((c, "pass") for c in sorted(rules.CHECKS))]
        assert all('"reason"' in r.details for r in admin_rows)
    assert client.get(f"{base}/review-queue", headers=headers).json()["resources"] == []


def test_review_queue_empty_optimization(app, client):
    with app.state.database.sessions() as db:
        # With no open review resources, review_queue returns empty list directly
        assert catalog_verification.review_queue(db) == []
