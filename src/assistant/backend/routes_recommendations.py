"""API routes for learning resource recommendations and feedback (issue #156, Phase 4)."""

from fastapi import APIRouter, HTTPException, Query

from .dependencies import DB, CurrentUser
from .models import Roadmap, RoadmapNode
from .recommendations_repository import (
    get_or_generate_node_recommendations,
    record_recommendation_event,
    summarize_roadmap_recommendations,
)
from .schemas import (
    NodeRecommendationsOut,
    RecommendationEventCreate,
    RecommendationEventOut,
    RoadmapRecommendationsSummaryOut,
)

router = APIRouter(tags=["Recommendations"])


@router.get(
    "/roadmap-nodes/{node_id}/recommendations",
    response_model=NodeRecommendationsOut,
)
def get_node_recommendations(
    node_id: str,
    db: DB,
    user: CurrentUser,
    limit: int = Query(default=5, ge=1, le=20),
):
    """Retrieve recommendations for a roadmap node, recalculating if stale (>24h)."""
    node = db.get(RoadmapNode, node_id)
    if node is None:
        raise HTTPException(404, "Roadmap node not found")

    roadmap = db.get(Roadmap, node.roadmap_id)
    if roadmap is None or roadmap.user_id != user.id:
        raise HTTPException(404, "Roadmap node not found")

    recommendations = get_or_generate_node_recommendations(
        db, node, user.id, limit=limit
    )
    return NodeRecommendationsOut(node_id=node.id, recommendations=recommendations)


@router.post(
    "/recommendations/{recommendation_id}/events",
    response_model=RecommendationEventOut,
    status_code=201,
)
def submit_recommendation_event(
    recommendation_id: str,
    data: RecommendationEventCreate,
    db: DB,
    user: CurrentUser,
):
    """Log an interaction event for a recommendation (shown, opened, helpful, not_helpful, pinned)."""
    event_out = record_recommendation_event(
        db, recommendation_id, user.id, data.event
    )
    if event_out is None:
        raise HTTPException(404, "Recommendation not found")
    return event_out


@router.get(
    "/roadmaps/{roadmap_id}/recommendations:summary",
    response_model=RoadmapRecommendationsSummaryOut,
)
def get_roadmap_recommendations_summary(
    roadmap_id: str,
    db: DB,
    user: CurrentUser,
):
    """Summarize recommendation metrics across all nodes of a roadmap."""
    summary = summarize_roadmap_recommendations(db, roadmap_id, user.id)
    if summary is None:
        raise HTTPException(404, "Roadmap not found")
    return summary
