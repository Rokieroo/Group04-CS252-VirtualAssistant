"""Recommendation storage, feedback events and the external display cache (#155, #156).

``get_or_generate_node_recommendations`` stores what ``app.recommend`` chose for a
learner and node; every query that leaves the process goes through the search job,
whose ``SearchService`` filters PII (spec 11.1).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.curator import Curation
from app.recommend import NO_FEEDBACK, VERIFICATION, Feedback, recommend
from app.search import canonical_url
from app.vetting import Node

from .cache import cached_search_entry
from .catalog_repository import node_sources
from .models import (
    Course,
    ExternalResult,
    Recommendation,
    RecommendationEvent,
    Resource,
    Roadmap,
    RoadmapNode,
    Source,
    User,
    utcnow,
)
from .resources import _outcomes, learner_for, request_search, search_signature
from .schemas import (
    RecommendationEventOut,
    RecommendationOut,
    RoadmapRecommendationsSummaryOut,
)

CACHE_LIFETIME = timedelta(days=7)
RECOMMENDATION_TTL = timedelta(hours=24)
EXTERNAL = "recommender"  # external_results provider holding shown pages' title and URL
UNHELPFUL_MEMORY = 50  # latest "not helpful" answers that still lower similar sources


def get_external_cached(db: Session, query_hash: str, provider: str) -> dict | list | None:
    """Retrieve external provider results from cache if fetched within 7 days."""
    row = db.get(ExternalResult, (query_hash, provider))
    if row is None:
        return None
    if utcnow() - row.fetched_at > CACHE_LIFETIME:
        return None
    try:
        return json.loads(row.payload)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def set_external_cache(
    db: Session, query_hash: str, provider: str, payload: dict | list
) -> ExternalResult:
    """Store external results in cache with current timestamp."""
    row = _remember_external(db, query_hash, provider, payload, utcnow())
    db.commit()
    return row


def _remember_external(
    db: Session, query_hash: str, provider: str, payload: dict | list, now: datetime
) -> ExternalResult:
    """Upsert one cache row in the caller's transaction."""
    text_payload = json.dumps(payload, ensure_ascii=False)
    row = db.get(ExternalResult, (query_hash, provider))
    if row is not None:
        row.payload, row.fetched_at = text_payload, now
        return row
    row = ExternalResult(
        query_hash=query_hash, provider=provider, payload=text_payload, fetched_at=now
    )
    try:
        with db.begin_nested():
            db.add(row)
    except IntegrityError:
        # A concurrent request cached the same query first; keep theirs.
        return db.get(ExternalResult, (query_hash, provider))
    return row


def _parse_external_title_url(payload: str) -> tuple[str | None, str | None]:
    try:
        data = json.loads(payload)
        if isinstance(data, dict):
            return data.get("title"), data.get("url")
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None, None


def enrich_recommendations(
    db: Session, recs: list[Recommendation]
) -> list[RecommendationOut]:
    """Batch-populate title and URL on RecommendationOut without N+1 queries."""
    if not recs:
        return []

    catalog_ids: set[str] = set()
    material_ids: set[str] = set()
    external_keys: set[str] = set()
    for rec in recs:
        if rec.resource_ref.startswith("catalog:"):
            catalog_ids.add(rec.resource_ref.removeprefix("catalog:"))
        elif rec.resource_ref.startswith("material:"):
            material_ids.add(rec.resource_ref.removeprefix("material:"))
        elif rec.resource_ref.startswith("external:"):
            external_keys.add(rec.resource_ref.removeprefix("external:"))

    resources = (
        {
            r.id: r
            for r in db.scalars(select(Resource).where(Resource.id.in_(catalog_ids)))
        }
        if catalog_ids
        else {}
    )
    sources = (
        {
            s.id: s
            for s in db.scalars(select(Source).where(Source.id.in_(material_ids)))
        }
        if material_ids
        else {}
    )
    externals = (
        {
            e.query_hash: e
            for e in db.scalars(
                select(ExternalResult).where(
                    ExternalResult.provider == EXTERNAL,
                    ExternalResult.query_hash.in_(external_keys),
                )
            )
        }
        if external_keys
        else {}
    )

    out: list[RecommendationOut] = []
    for rec in recs:
        title: str | None = None
        url: str | None = None
        if rec.resource_ref.startswith("catalog:"):
            resource = resources.get(rec.resource_ref.removeprefix("catalog:"))
            if resource:
                title = resource.title
                url = resource.canonical_url or resource.url
        elif rec.resource_ref.startswith("material:"):
            source = sources.get(rec.resource_ref.removeprefix("material:"))
            if source:
                title = source.file_name
        elif rec.resource_ref.startswith("external:"):
            cached = externals.get(rec.resource_ref.removeprefix("external:"))
            if cached:
                title, url = _parse_external_title_url(cached.payload)

        out.append(
            RecommendationOut(
                id=rec.id,
                node_id=rec.node_id,
                resource_ref=rec.resource_ref,
                kind=rec.kind,
                verification_status=VERIFICATION[rec.kind],
                rank=rec.rank,
                score=round(rec.score, 3),
                reason=rec.reason,
                title=title,
                url=url,
                created_at=rec.created_at,
                dismissed_at=rec.dismissed_at,
            )
        )
    return out


def enrich_recommendation(db: Session, rec: Recommendation) -> RecommendationOut:
    """Populate title and URL on RecommendationOut based on resource reference."""
    return enrich_recommendations(db, [rec])[0]


def get_or_generate_node_recommendations(
    db: Session,
    node: RoadmapNode,
    user_id: str,
    now: datetime,
    limit: int = 5,
) -> list[RecommendationOut]:
    """The node's active recommendations, recomputed when stale or when an input changed.

    Inputs are the node's database sources, the shared external search cache and
    this learner's "not helpful" answers; a newer cache entry or answer than the
    newest recommendation means the stored list no longer reflects them.
    """
    roadmap = db.get(Roadmap, node.roadmap_id)
    course = db.get(Course, roadmap.course_id)
    active = db.scalars(
        select(Recommendation)
        .where(
            Recommendation.user_id == user_id,
            Recommendation.node_id == node.id,
            Recommendation.dismissed_at.is_(None),
        )
        .order_by(Recommendation.rank)
    ).all()
    feedback, answered_at = _feedback(db, user_id, node.id)
    outcomes = _outcomes(db, course.id)
    cached = cached_search_entry(db, search_signature(db, node, course, outcomes=outcomes), now)
    changed_at = max((t for t in (answered_at, cached and cached[1]) if t), default=None)
    if active:
        newest = max(r.created_at for r in active)
        # An input as new as the list came after it: an answer always refers to a list.
        if now - newest < RECOMMENDATION_TTL and (changed_at is None or changed_at < newest):
            return enrich_recommendations(db, active[:limit])
        for row in active:  # superseded, not rejected: answers live in the events
            row.dismissed_at = now

    def vetted_pages():
        if cached is not None:
            curation = Curation.from_dict(cached[0])
            return curation.resources + curation.reserve
        # Searching takes minutes (fetch + judge), so it runs as a job; its results
        # reach the next request through the cache and replace this list.
        request_search(db, node.id, user_id, now)
        return []

    # One more database candidate per rejected source, so a rejection is replaced
    # from what the database already holds (spec 11.6: no new search).
    wanted = limit + len(feedback.rejected)
    sources = node_sources(db, [node], roadmap, course, now, limit=wanted)[node.id]["sources"]
    chosen = recommend(
        Node(node.title, outcomes, node.duration_minutes),
        learner_for(course, db.get(User, roadmap.user_id)),
        database=sources,
        external=vetted_pages,
        feedback=feedback,
        limit=limit,
    )
    rows = []
    for rank, item in enumerate(chosen, start=1):
        rows.append(
            Recommendation(
                user_id=user_id,
                node_id=node.id,
                resource_ref=_ref(db, item, now),
                kind=item.kind,
                rank=rank,
                score=item.score,
                reason=item.reason,
                created_at=now,
            )
        )
    db.add_all(rows)
    db.commit()
    return enrich_recommendations(db, rows)


def _ref(db: Session, item, now: datetime) -> str:
    """``kind:key`` of a recommended source; an external page is remembered for display."""
    if item.kind == "user_material":
        return f"material:{item.source_id}"
    if item.kind == "catalog":
        return f"catalog:{item.source_id}"
    key = hashlib.sha256(item.source_id.encode("utf-8")).hexdigest()
    _remember_external(db, key, EXTERNAL, {"title": item.title, "url": item.url}, now)
    return f"external:{key}"


def _feedback(db: Session, user_id: str, node_id: str) -> tuple[Feedback, datetime | None]:
    """This learner's "not helpful" answers, and when the node last received one."""
    answers = db.execute(
        select(Recommendation, RecommendationEvent.created_at)
        .join(RecommendationEvent, RecommendationEvent.recommendation_id == Recommendation.id)
        .where(Recommendation.user_id == user_id, RecommendationEvent.event == "not_helpful")
        .order_by(RecommendationEvent.created_at.desc())
        .limit(UNHELPFUL_MEMORY)
    ).all()
    if not answers:
        return NO_FEEDBACK, None
    shown = enrich_recommendations(db, [rec for rec, _ in answers])
    rejected = {
        canonical_url(out.url) if rec.kind == "external" else rec.resource_ref.split(":", 1)[1]
        for (rec, _), out in zip(answers, shown, strict=True)
        if rec.node_id == node_id and (rec.kind != "external" or out.url)
    }
    on_node = [at for rec, at in answers if rec.node_id == node_id]
    titles = tuple(out.title for out in shown if out.title)
    return Feedback(frozenset(rejected), titles), max(on_node, default=None)


def record_recommendation_event(
    db: Session,
    recommendation_id: str,
    user_id: str,
    event: str,
    now: datetime,
) -> RecommendationEventOut | None:
    """Record an interaction event (shown, opened, helpful, not_helpful, pinned)."""
    rec = db.get(Recommendation, recommendation_id)
    if rec is None or rec.user_id != user_id:
        return None

    event_row = RecommendationEvent(
        recommendation_id=rec.id,
        event=event,
        created_at=now,
    )
    db.add(event_row)

    if event == "not_helpful":
        rec.dismissed_at = now

    db.commit()
    return RecommendationEventOut(
        id=event_row.id,
        recommendation_id=event_row.recommendation_id,
        event=event_row.event,
        created_at=event_row.created_at,
    )


def summarize_roadmap_recommendations(
    db: Session,
    roadmap_id: str,
    user_id: str,
) -> RoadmapRecommendationsSummaryOut | None:
    """Summarize recommendation metrics across all nodes of a roadmap."""
    roadmap = db.get(Roadmap, roadmap_id)
    if roadmap is None or roadmap.user_id != user_id:
        return None

    node_ids = list(
        db.scalars(select(RoadmapNode.id).where(RoadmapNode.roadmap_id == roadmap.id))
    )
    if not node_ids:
        return RoadmapRecommendationsSummaryOut(
            roadmap_id=roadmap.id,
            total_nodes=0,
            total_recommendations=0,
            by_kind={},
            events_summary={},
            pinned_count=0,
        )

    # Active recommendations
    active_recs = db.scalars(
        select(Recommendation).where(
            Recommendation.node_id.in_(node_ids),
            Recommendation.user_id == user_id,
            Recommendation.dismissed_at.is_(None),
        )
    ).all()

    by_kind = Counter(r.kind for r in active_recs)

    # Events summary across all recommendations (including dismissed/not_helpful ones)
    event_counts = db.execute(
        select(RecommendationEvent.event, func.count())
        .join(Recommendation, Recommendation.id == RecommendationEvent.recommendation_id)
        .where(
            Recommendation.node_id.in_(node_ids),
            Recommendation.user_id == user_id,
        )
        .group_by(RecommendationEvent.event)
    ).all()
    events_summary = {event: int(count) for event, count in event_counts}
    pinned_count = events_summary.get("pinned", 0)

    return RoadmapRecommendationsSummaryOut(
        roadmap_id=roadmap.id,
        total_nodes=len(node_ids),
        total_recommendations=len(active_recs),
        by_kind=dict(by_kind),
        events_summary=events_summary,
        pinned_count=pinned_count,
    )
