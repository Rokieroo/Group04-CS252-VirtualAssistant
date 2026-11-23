"""Cost and quota report behind the admin dashboard (issues #69 and #161).

Every figure is aggregated by the database over an indexed ``created_at`` window,
so the report costs a fixed number of queries plus one per provider, however many
searches are logged.
"""

from datetime import datetime, timedelta
from math import ceil

from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from .models import ResourceSearch, SearchRun

TOP_NODES = 50
ALERT_WINDOW = timedelta(hours=1)
ALERT_ERROR_RATE = 0.2  # a provider failing more than this share of its calls is flagged
ALERT_MIN_CALLS = 5  # fewer calls than this are too few to call a provider failing


def _total(column):
    return func.coalesce(func.sum(column), 0)


def _errors():
    return _total(case((SearchRun.status == "error", 1), else_=0))


def _p95_latency(db: Session, provider: str, since: datetime, calls: int) -> int:
    """Nearest-rank 95th percentile; portable where ``percentile_cont`` is not (SQLite)."""
    return db.scalar(
        select(SearchRun.latency_ms)
        .where(SearchRun.provider == provider, SearchRun.created_at >= since)
        .order_by(SearchRun.latency_ms)
        .offset(ceil(0.95 * calls) - 1)
        .limit(1)
    ) or 0


def failing_providers(db: Session, now: datetime) -> list[dict]:
    """Providers whose calls failed more than ``ALERT_ERROR_RATE`` in the last hour."""
    rows = db.execute(
        select(SearchRun.provider, func.count().label("calls"), _errors().label("errors"))
        .where(SearchRun.created_at >= now - ALERT_WINDOW)
        .group_by(SearchRun.provider)
        .order_by(SearchRun.provider)
    ).mappings()
    return [
        {**row, "error_rate": row["errors"] / row["calls"]}
        for row in rows
        if row["calls"] >= ALERT_MIN_CALLS and row["errors"] > ALERT_ERROR_RATE * row["calls"]
    ]


def cost_report(db: Session, *, now: datetime, days: int) -> dict:
    """Spend per node, per provider and per day over the last ``days``."""
    since = now - timedelta(days=days)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    searches = ResourceSearch
    cost = searches.llm_cost_usd + searches.search_cost_usd
    window = searches.created_at >= since

    count, cache_hits, llm_calls, llm_today, llm_cost, search_cost = db.execute(
        select(
            func.count(),
            _total(searches.cache_hit),
            _total(searches.llm_calls),
            _total(case((searches.created_at >= today, searches.llm_calls), else_=0)),
            _total(searches.llm_cost_usd),
            _total(searches.search_cost_usd),
        ).where(window)
    ).one()

    nodes = db.execute(
        select(
            searches.node_id,
            searches.node_title,
            func.count().label("searches"),
            _total(searches.cache_hit).label("cache_hits"),
            _total(searches.llm_calls).label("llm_calls"),
            _total(searches.llm_cost_usd).label("llm_cost_usd"),
            _total(searches.search_cost_usd).label("search_cost_usd"),
            _total(cost).label("cost_usd"),
            func.max(searches.created_at).label("last_search_at"),
        )
        .where(window)
        .group_by(searches.node_id, searches.node_title)
        .order_by(desc("cost_usd"), searches.node_title)
        .limit(TOP_NODES)
    ).mappings()

    runs = SearchRun
    providers = db.execute(
        select(
            runs.provider,
            func.count().label("calls"),
            _errors().label("errors"),
            _total(case((runs.created_at >= today, 1), else_=0)).label("calls_today"),
            func.coalesce(func.avg(runs.latency_ms), 0).label("avg_latency_ms"),
            func.coalesce(func.max(runs.latency_ms), 0).label("max_latency_ms"),
            _total(runs.cost_usd).label("cost_usd"),
        )
        .where(runs.created_at >= since)
        .group_by(runs.provider)
        .order_by(runs.provider)
    ).mappings()

    day = func.date(searches.created_at).label("day")
    daily = db.execute(
        select(day, func.count().label("searches"), _total(cost).label("cost_usd"))
        .where(window)
        .group_by(day)
        .order_by(day)
    ).mappings()

    total_cost = llm_cost + search_cost
    return {
        "days": days,
        "since": since,
        "totals": {
            "searches": count,
            "cache_hits": cache_hits,
            "llm_calls": llm_calls,
            "llm_calls_today": llm_today,
            "llm_cost_usd": llm_cost,
            "search_cost_usd": search_cost,
            "cost_usd": total_cost,
            "cost_per_search_usd": total_cost / count if count else 0.0,
        },
        "nodes": [dict(row) for row in nodes],
        "providers": [
            {
                **row,
                "error_rate": row["errors"] / row["calls"],
                "p95_latency_ms": _p95_latency(db, row["provider"], since, row["calls"]),
            }
            for row in providers
        ],
        "daily": [dict(row) for row in daily],
        "alerts": failing_providers(db, now),
    }
