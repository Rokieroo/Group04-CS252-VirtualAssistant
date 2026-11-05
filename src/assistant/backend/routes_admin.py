"""Admin-only views: the cost and quota dashboard (issue #69)."""

from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from .costs import cost_report
from .dependencies import DB, AdminUser
from .schemas import CostReport

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/catalog/subject-review-queue")
def subject_review_queue(db: DB, admin: AdminUser, limit: int = Query(100, ge=1, le=500)):
    """Only shared resource labels: never include private node/material text (#99)."""
    from .catalog_models import ResourceSubject
    from .models import Resource
    rows = db.execute(select(ResourceSubject, Resource.title).join(
        Resource, ResourceSubject.resource_id == Resource.id).where(
        ResourceSubject.confidence < 0.6).order_by(
        ResourceSubject.confidence, ResourceSubject.resource_id).limit(limit))
    return {"labels": [{"resource_id": r.resource_id, "title": title,
                        "subject_id": r.subject_id, "confidence": r.confidence, "method": r.method}
                       for r, title in rows]}


@router.get("/costs", response_model=CostReport)
def get_costs(
    request: Request,
    db: DB,
    admin: AdminUser,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
):
    """LLM and search spend per node, provider latency and daily quota use."""
    return cost_report(db, now=request.app.state.now(), days=days)
