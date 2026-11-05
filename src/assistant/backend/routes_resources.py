"""Resource search, retrieval and learner feedback endpoints (issue #65, spec 8.5-8.7)."""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import asdict
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select

from app.curator import Curation, replace
from app.search import node_signature

from .cache import cached_search, store_search
from .dependencies import DB, CurrentUser
from .jobs import enqueue
from .models import (
    Course,
    Job,
    NodeResource,
    Resource,
    ResourceFeedback,
    Roadmap,
    RoadmapNode,
)
from .resources import _outcomes
from .schemas import (
    NodeResourcesOut,
    ResourceFeedbackIn,
    ResourceFeedbackOut,
    ResourceItemOut,
    ResourceSearchOut,
)

router = APIRouter(tags=["Learning resources"])

RESOURCE_SEARCH_PER_HOUR = 20


@router.post(
    "/roadmap-nodes/{node_id}/resources:search",
    response_model=ResourceSearchOut,
    status_code=202,
    responses={
        202: {"description": "Resource search enqueued"},
        429: {"description": "Resource search rate limit reached"},
    },
)
def search_node_resources(
    node_id: str,
    request: Request,
    db: DB,
    user: CurrentUser,
):
    """Enqueue background resource search for this roadmap node (spec 8.5).

    Returns 202 with run_id. Rate limited to 20 searches per hour per user.
    """
    node = db.get(RoadmapNode, node_id)
    if node is None:
        raise HTTPException(404, "Roadmap node not found")
    roadmap = db.get(Roadmap, node.roadmap_id)
    if roadmap is None or roadmap.user_id != user.id:
        raise HTTPException(404, "Roadmap node not found")

    now = request.app.state.now()
    recent = db.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.user_id == user.id,
            Job.kind == "search_resources",
            Job.created_at > now - timedelta(hours=1),
        )
    )
    if recent >= RESOURCE_SEARCH_PER_HOUR:
        raise HTTPException(
            429,
            "Resource search rate limit reached (20 requests per hour)",
            headers={"Retry-After": "3600"},
        )

    job = enqueue(
        db, "search_resources", {"node_id": node.id}, now=now, user_id=user.id
    )
    db.commit()
    return {"run_id": job.id}


@router.get(
    "/roadmap-nodes/{node_id}/resources",
    response_model=NodeResourcesOut,
)
def get_node_resources(
    node_id: str,
    request: Request,
    db: DB,
    user: CurrentUser,
):
    """Retrieve curated resources and coverage gaps for a roadmap node (spec 8.6).

    Status is 'searching' if a search is in progress, 'ready' if at least 2 vetted
    resources meet quality threshold (>= 0.65), or 'insufficient' otherwise.
    """
    node = db.get(RoadmapNode, node_id)
    if node is None:
        raise HTTPException(404, "Roadmap node not found")
    roadmap = db.get(Roadmap, node.roadmap_id)
    if roadmap is None or roadmap.user_id != user.id:
        raise HTTPException(404, "Roadmap node not found")

    now = request.app.state.now()

    # If there is a queued or running search job for this node, return "searching".
    active_jobs = db.scalars(
        select(Job).where(
            Job.kind == "search_resources",
            Job.status.in_(["queued", "running"]),
            Job.user_id == user.id,
        )
    ).all()
    is_searching = any(
        json.loads(j.payload).get("node_id") == node.id for j in active_jobs
    )
    if is_searching:
        return NodeResourcesOut(status="searching", resources=[], gaps=[])

    course = db.get(Course, roadmap.course_id)
    outcomes = _outcomes(db, course.id)
    signature = node_signature(
        node.title, list(outcomes), course.level, course.language
    )
    cached = cached_search(db, signature, now)
    curation = Curation.from_dict(cached) if cached is not None else None

    links = list(
        db.scalars(
            select(NodeResource).where(
                NodeResource.node_id == node.id, NodeResource.status == "shown"
            )
        ).all()
    )

    if not links:
        gaps = (
            curation.gaps
            if (curation and curation.gaps)
            else ["Chưa tìm được nguồn đủ tốt"]
        )
        return NodeResourcesOut(status="insufficient", resources=[], gaps=gaps)

    resources_by_id = {
        r.id: r
        for r in db.scalars(
            select(Resource).where(Resource.id.in_([l.resource_id for l in links]))
        ).all()
    }

    scored_by_url = {}
    if curation:
        for s in curation.resources + curation.reserve:
            scored_by_url[s.url] = s

    # Order links according to curation.resources order if available, else by relevance_score
    if curation:
        url_order = {r.url: i for i, r in enumerate(curation.resources)}
        links.sort(
            key=lambda l: url_order.get(
                resources_by_id[l.resource_id].url
                if l.resource_id in resources_by_id
                else "",
                999,
            )
        )
    else:
        links.sort(key=lambda l: l.relevance_score, reverse=True)

    from .catalog_repository import verified_resources

    verified_ids = {r["id"] for r in verified_resources(db, now)}
    items = []
    for rank, link in enumerate(links, start=1):
        res = resources_by_id.get(link.resource_id)
        if res is None or res.id not in verified_ids:
            continue
        scored = scored_by_url.get(res.url)
        if (scored.score if scored else link.relevance_score) < 0.65:
            continue
        if len(items) >= 5:
            break
        rank = len(items) + 1
        parsed_domain = urllib.parse.urlparse(res.url).netloc or "web"
        items.append(
            ResourceItemOut(
                id=res.id,
                rank=rank,
                title=scored.title if scored else res.title,
                url=res.url,
                domain=scored.domain if scored else parsed_domain,
                format=scored.format if scored else res.kind,
                language=scored.lang if scored else res.lang,
                duration_min=scored.minutes if scored else None,
                is_free=scored.is_free if scored else True,
                score=scored.score if scored else link.relevance_score,
                breakdown=scored.breakdown if scored else {},
                reason=scored.reason if scored else "",
                evidence_quote=scored.evidence_quote if scored else "",
                pinned=scored.pinned if scored else False,
            )
        )

    status = "ready" if len(items) >= 2 else "insufficient"
    gaps = (
        curation.gaps
        if (curation and curation.gaps)
        else (["Chưa tìm được nguồn đủ tốt"] if status == "insufficient" else [])
    )
    return NodeResourcesOut(status=status, resources=items, gaps=gaps)


@router.post(
    "/resources/{resource_id}/feedback",
    response_model=ResourceFeedbackOut,
)
def resource_feedback(
    resource_id: str,
    data: ResourceFeedbackIn,
    request: Request,
    db: DB,
    user: CurrentUser,
):
    """Store feedback for a resource; if not helpful, replaces it from reserve (spec 8.7)."""
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise HTTPException(404, "Resource not found")
    node = db.get(RoadmapNode, data.node_id)
    if node is None:
        raise HTTPException(404, "Roadmap node not found")
    roadmap = db.get(Roadmap, node.roadmap_id)
    if roadmap is None or roadmap.user_id != user.id:
        raise HTTPException(404, "Roadmap node not found")

    link = db.get(NodeResource, (node.id, resource.id))
    if link is None:
        raise HTTPException(404, "Resource not associated with this node")

    now = request.app.state.now()
    feedback = ResourceFeedback(
        user_id=user.id,
        resource_id=resource.id,
        rating=1 if data.helpful else 0,
        comment=data.reason,
    )
    db.add(feedback)

    replacement_out = None
    if not data.helpful:
        link.status = "replaced"
        course = db.get(Course, roadmap.course_id)
        outcomes = _outcomes(db, course.id)
        signature = node_signature(
            node.title, list(outcomes), course.level, course.language
        )
        cached = cached_search(db, signature, now)
        if cached is not None:
            curation = Curation.from_dict(cached)
            try:
                new_curation = replace(curation, resource.url)
                store_search(db, signature, asdict(new_curation), now)
                old_urls = {r.url for r in curation.resources}
                rep_scored = next(
                    (r for r in new_curation.resources if r.url not in old_urls), None
                )
                if rep_scored:
                    rep_row = db.scalars(
                        select(Resource).where(Resource.url == rep_scored.url)
                    ).first()
                    from .catalog_repository import verified_resources

                    verified_ids = {r["id"] for r in verified_resources(db, now)}
                    if rep_row is None or rep_row.id not in verified_ids:
                        raise KeyError("no_verified_replacement")
                    rep_link = db.get(NodeResource, (node.id, rep_row.id))
                    if rep_link is None:
                        rep_link = NodeResource(
                            node_id=node.id,
                            resource_id=rep_row.id,
                            relevance_score=rep_scored.score,
                            status="shown",
                        )
                        db.add(rep_link)
                    else:
                        rep_link.status = "shown"
                        rep_link.relevance_score = rep_scored.score

                    shown_count = db.scalar(
                        select(func.count())
                        .select_from(NodeResource)
                        .where(
                            NodeResource.node_id == node.id,
                            NodeResource.status == "shown",
                        )
                    )
                    replacement_out = ResourceItemOut(
                        id=rep_row.id,
                        rank=shown_count,
                        title=rep_scored.title,
                        url=rep_row.url,
                        domain=rep_scored.domain,
                        format=rep_scored.format,
                        language=rep_scored.lang,
                        duration_min=rep_scored.minutes,
                        is_free=rep_scored.is_free,
                        score=rep_scored.score,
                        breakdown=rep_scored.breakdown,
                        reason=rep_scored.reason,
                        evidence_quote=rep_scored.evidence_quote,
                        pinned=rep_scored.pinned,
                    )
            except KeyError:
                replacement_out = None

    db.commit()
    return ResourceFeedbackOut(status="ok", replacement=replacement_out)
