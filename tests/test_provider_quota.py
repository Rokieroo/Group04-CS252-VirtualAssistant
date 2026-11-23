"""Issue #161: daily provider quotas, the failing-provider alert and p95 latency."""

from datetime import UTC, datetime, timedelta

import pytest

from app.search import Candidate, FakeSearch, SearchService
from assistant.backend.costs import cost_report, failing_providers
from assistant.backend.models import SearchRun, User
from assistant.backend.provider_quota import (
    DAILY_ENV,
    LEARNER_ENV,
    parse_limits,
    remaining_calls,
)

NOW = datetime(2030, 1, 7, 12, tzinfo=UTC)


@pytest.fixture
def db(app, client):
    with app.state.database.sessions() as session:
        yield session


def learner(db, email):
    row = User(email=email, password_hash="x")
    db.add(row)
    db.flush()
    return row.id


def calls(db, user_id, provider, count, *, at=NOW, status="ok", latency_ms=0):
    db.add_all(
        SearchRun(user_id=user_id, query="q", provider=provider, status=status,
                  latency_ms=latency_ms, created_at=at)
        for _ in range(count)
    )
    db.flush()


def test_limits_read_name_calls_pairs():
    assert parse_limits(DAILY_ENV, " youtube=90, web=2000 ,") == {"youtube": 90, "web": 2000}
    assert parse_limits(DAILY_ENV, "") == {}


@pytest.mark.parametrize("value", ["youtube", "youtube=-1", "=5", "web=ten"])
def test_malformed_limits_name_their_variable(value):
    with pytest.raises(ValueError, match=f"{DAILY_ENV} must look like"):
        parse_limits(DAILY_ENV, value)


def test_service_stops_calling_a_provider_once_its_quota_is_spent():
    page = [Candidate("https://a.edu/x", "X", "web", "article", "en")]
    service = SearchService(
        [FakeSearch(page, name="web"), FakeSearch(page, name="youtube")], quota={"web": 2}
    )
    service.search(queries=["a", "b", "c"])
    assert [run.provider for run in service.last_runs] == ["web"] * 2 + ["youtube"] * 3
    assert service.last_skipped == {"web"}


def test_remaining_calls_take_the_tighter_of_the_daily_and_learner_quotas(db, monkeypatch):
    monkeypatch.setenv(DAILY_ENV, "web=5")
    monkeypatch.setenv(LEARNER_ENV, "web=2,youtube=3")
    ann, bob = learner(db, "ann@example.com"), learner(db, "bob@example.com")
    calls(db, ann, "web", 2)
    calls(db, bob, "web", 1)
    calls(db, bob, "web", 9, at=NOW - timedelta(days=1))  # yesterday's calls do not count
    assert remaining_calls(db, ann, NOW) == {"web": 0, "youtube": 3}
    assert remaining_calls(db, bob, NOW) == {"web": 1, "youtube": 3}
    monkeypatch.setenv(DAILY_ENV, "web=3")  # everyone's calls today use the daily quota up
    assert remaining_calls(db, bob, NOW)["web"] == 0


def test_without_quotas_every_provider_is_unlimited(db, monkeypatch):
    monkeypatch.delenv(DAILY_ENV, raising=False)
    monkeypatch.delenv(LEARNER_ENV, raising=False)
    assert remaining_calls(db, "anyone", NOW) == {}


def test_provider_failing_over_a_fifth_of_its_calls_in_the_hour_is_flagged(db):
    ann = learner(db, "ann@example.com")
    calls(db, ann, "web", 3, at=NOW - timedelta(minutes=5))
    calls(db, ann, "web", 2, at=NOW - timedelta(minutes=5), status="error")
    calls(db, ann, "youtube", 4)
    calls(db, ann, "youtube", 1, status="error")  # exactly 20%: not over
    calls(db, ann, "openalex", 2, status="error")  # too few calls to judge
    calls(db, ann, "wikipedia", 5, at=NOW - timedelta(hours=2), status="error")  # an old outage
    assert failing_providers(db, NOW) == [
        {"provider": "web", "calls": 5, "errors": 2, "error_rate": 0.4}
    ]


def test_report_gives_each_provider_its_error_rate_and_p95_latency(db):
    ann = learner(db, "ann@example.com")
    for latency in range(1, 21):
        calls(db, ann, "web", 1, latency_ms=latency, status="error" if latency > 18 else "ok")
    [web] = cost_report(db, now=NOW, days=7)["providers"]
    assert web["p95_latency_ms"] == 19  # nearest rank: the 19th of 20 calls
    assert web["error_rate"] == pytest.approx(0.1)
