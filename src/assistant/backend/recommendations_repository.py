"""Recommendation repository and external caching (issue #156, Phase 4).

Stores recommendations, user feedback events (shown, opened, helpful, not_helpful, pinned),
and external result cache (7-day validity). All queries to external providers are sanitized
via pii_filter.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.privacy import build_safe_external_query

from .catalog_models import NodeMaterial
from .models import (
    ExternalResult,
    NodeResource,
    NodeSubject,
    Recommendation,
    RecommendationEvent,
    Resource,
    ResourceSubject,
    Roadmap,
    RoadmapNode,
    Source,
    utcnow,
)
from .schemas import (
    RecommendationEventOut,
    RecommendationOut,
    RoadmapRecommendationsSummaryOut,
)

CACHE_LIFETIME = timedelta(days=7)
RECOMMENDATION_TTL = timedelta(hours=24)


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
    text_payload = json.dumps(payload, ensure_ascii=False)
    row = db.get(ExternalResult, (query_hash, provider))
    if row is not None:
        row.payload = text_payload
        row.fetched_at = utcnow()
    else:
        row = ExternalResult(
            query_hash=query_hash,
            provider=provider,
            payload=text_payload,
            fetched_at=utcnow(),
        )
        db.add(row)
    db.commit()
    return row


def enrich_recommendation(db: Session, rec: Recommendation) -> RecommendationOut:
    """Populate title and URL on RecommendationOut based on resource reference."""
    title: str | None = None
    url: str | None = None

    if rec.resource_ref.startswith("catalog:"):
        res_id = rec.resource_ref.removeprefix("catalog:")
        resource = db.get(Resource, res_id)
        if resource:
            title = resource.title
            url = resource.canonical_url or resource.url
    elif rec.resource_ref.startswith("material:"):
        src_id = rec.resource_ref.removeprefix("material:")
        source = db.get(Source, src_id)
        if source:
            title = source.title
    elif rec.resource_ref.startswith("external:"):
        ext_key = rec.resource_ref.removeprefix("external:")
        cached = db.get(ExternalResult, (ext_key, "recommender"))
        if cached:
            try:
                data = json.loads(cached.payload)
                if isinstance(data, dict):
                    title = data.get("title")
                    url = data.get("url")
            except (json.JSONDecodeError, TypeError, ValueError):
                title = None
                url = None

    return RecommendationOut(
        id=rec.id,
        node_id=rec.node_id,
        resource_ref=rec.resource_ref,
        kind=rec.kind,
        rank=rec.rank,
        score=round(rec.score, 3),
        reason=rec.reason,
        title=title,
        url=url,
        created_at=rec.created_at,
        dismissed_at=rec.dismissed_at,
    )


def get_or_generate_node_recommendations(
    db: Session,
    node: RoadmapNode,
    user_id: str,
    limit: int = 5,
) -> list[RecommendationOut]:
    """Retrieve active recommendations for a node, recalculating if >24h old or empty."""
    active_recs = db.scalars(
        select(Recommendation)
        .where(
            Recommendation.user_id == user_id,
            Recommendation.node_id == node.id,
            Recommendation.dismissed_at.is_(None),
        )
        .order_by(Recommendation.rank)
    ).all()

    # If active recommendations exist and newest is fresher than 24h, return them
    if active_recs:
        newest = max(r.created_at for r in active_recs)
        if utcnow() - newest < RECOMMENDATION_TTL:
            return [enrich_recommendation(db, r) for r in active_recs[:limit]]

    # Otherwise, clean stale undismissed recommendations and generate fresh candidates
    if active_recs:
        for r in active_recs:
            r.dismissed_at = utcnow()
        db.commit()

    candidates: list[tuple[str, str, float, str]] = []  # (resource_ref, kind, score, reason)

    # 1. Verified catalog resources linked to this node or shared subjects
    node_res_ids = select(NodeResource.resource_id).where(NodeResource.node_id == node.id)
    linked_resources = db.scalars(
        select(Resource).where(
            Resource.id.in_(node_res_ids),
            Resource.verification_status == "verified",
        )
    ).all()

    for res in linked_resources:
        candidates.append((
            f"catalog:{res.id}",
            "verified",
            0.95,
            "Nguồn tài liệu chính thống đã được thẩm định chất lượng",
        ))

    # Match by subjects if not enough linked resources
    if len(candidates) < limit:
        sub_ids = select(NodeSubject.subject_id).where(NodeSubject.node_id == node.id)
        shared_res_ids = select(ResourceSubject.resource_id).where(
            ResourceSubject.subject_id.in_(sub_ids)
        )
        subject_resources = db.scalars(
            select(Resource)
            .where(
                Resource.id.in_(shared_res_ids),
                Resource.verification_status == "verified",
            )
            .limit(limit)
        ).all()
        for res in subject_resources:
            ref = f"catalog:{res.id}"
            if not any(c[0] == ref for c in candidates):
                candidates.append((
                    ref,
                    "verified",
                    0.90,
                    "Nguồn học liệu xác minh phù hợp chủ đề môn học",
                ))

    # 2. Node course materials uploaded by student/instructor
    node_materials = db.scalars(
        select(NodeMaterial).where(NodeMaterial.node_id == node.id)
    ).all()
    for mat in node_materials:
        ref = f"material:{mat.source_id}"
        if not any(c[0] == ref for c in candidates):
            candidates.append((
                ref,
                "material",
                0.88,
                "Tài liệu bài giảng chính khóa của môn học",
            ))

    # 3. External provider candidate (sanitized via pii_filter)
    safe_query = build_safe_external_query(node_title=node.title)
    if safe_query:
        query_hash = hashlib.sha256(safe_query.encode("utf-8")).hexdigest()
        cached = get_external_cached(db, query_hash, "recommender")
        if not cached:
            cached_payload = {
                "title": f"Tham khảo mở rộng: {safe_query}",
                "url": f"https://openstax.org/search?q={safe_query.replace(' ', '+')}",
                "provider": "openstax",
            }
            set_external_cache(db, query_hash, "recommender", cached_payload)

        candidates.append((
            f"external:{query_hash}",
            "external",
            0.82,
            "Tài liệu tham khảo học liệu mở bổ trợ cho chủ đề",
        ))

    # If still empty, supply a safe general verified or external suggestion
    if not candidates:
        safe_q = build_safe_external_query(node_title=node.title or "General Topic")
        q_hash = hashlib.sha256(safe_q.encode("utf-8")).hexdigest()
        candidates.append((
            f"external:{q_hash}",
            "external",
            0.75,
            "Tài liệu mở rộng theo tiêu chuẩn mở",
        ))

    # Save candidates to database
    created_rows: list[Recommendation] = []
    for rank, (ref, kind, score, reason) in enumerate(candidates[:limit], start=1):
        rec = Recommendation(
            user_id=user_id,
            node_id=node.id,
            resource_ref=ref,
            kind=kind,
            rank=rank,
            score=score,
            reason=reason,
            created_at=utcnow(),
        )
        db.add(rec)
        created_rows.append(rec)

    db.commit()
    return [enrich_recommendation(db, r) for r in created_rows]


def record_recommendation_event(
    db: Session,
    recommendation_id: str,
    user_id: str,
    event: str,
) -> RecommendationEventOut | None:
    """Record an interaction event (shown, opened, helpful, not_helpful, pinned)."""
    rec = db.get(Recommendation, recommendation_id)
    if rec is None or rec.user_id != user_id:
        return None

    event_row = RecommendationEvent(
        recommendation_id=rec.id,
        event=event,
        created_at=utcnow(),
    )
    db.add(event_row)

    if event == "not_helpful":
        rec.dismissed_at = utcnow()

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

    # Events summary
    rec_ids = [r.id for r in active_recs]
    events = (
        db.scalars(
            select(RecommendationEvent.event).where(
                RecommendationEvent.recommendation_id.in_(rec_ids)
            )
        ).all()
        if rec_ids
        else []
    )
    events_summary = Counter(events)
    pinned_count = events_summary.get("pinned", 0)

    return RoadmapRecommendationsSummaryOut(
        roadmap_id=roadmap.id,
        total_nodes=len(node_ids),
        total_recommendations=len(active_recs),
        by_kind=dict(by_kind),
        events_summary=dict(events_summary),
        pinned_count=pinned_count,
    )
