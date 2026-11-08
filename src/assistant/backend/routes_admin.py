"""Admin-only views: the cost and quota dashboard (issue #69), catalog review (#101)
and catalog health (#105)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, StringConstraints
from sqlalchemy import select

from . import catalog_verification
from .catalog_health import catalog_health
from .costs import cost_report
from .dependencies import DB, AdminUser
from .schemas import CatalogHealth, CostReport

router = APIRouter(prefix="/admin", tags=["Admin"])

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class RejectIn(BaseModel):
    reason: Reason  # e.g. "takedown" (ADR 004 section 8); kept in the audit rows


class VerifyIn(RejectIn):
    license: str | None = None  # an id of catalog_sources.yaml, for an unknown license


class DecisionOut(BaseModel):
    id: str
    verification_status: str
    license: str | None


def _decided(db, decide) -> DecisionOut:
    try:
        resource = decide()
    except LookupError:
        raise HTTPException(404, "resource_not_found") from None
    except ValueError as exc:  # unknown_license | license_required | never_fetched
        raise HTTPException(422, str(exc)) from None
    db.commit()
    return DecisionOut(
        id=resource.id,
        verification_status=resource.verification_status,
        license=resource.license,
    )


@router.get("/catalog/review-queue")
def review_queue(db: DB, admin: AdminUser, limit: int = Query(100, ge=1, le=500)):
    """Resources the job could not decide alone: unknown license, unsure labels, robots."""
    return {"resources": catalog_verification.review_queue(db, limit)}


@router.post("/catalog/resources/{resource_id}:verify", response_model=DecisionOut)
def verify_resource(resource_id: str, body: VerifyIn, request: Request, db: DB, admin: AdminUser):
    return _decided(
        db,
        lambda: catalog_verification.verify_by_admin(
            db,
            resource_id,
            reason=body.reason,
            license=body.license,
            admin_id=admin.id,
            now=request.app.state.now(),
        ),
    )


@router.post("/catalog/resources/{resource_id}:reject", response_model=DecisionOut)
def reject_resource(resource_id: str, body: RejectIn, request: Request, db: DB, admin: AdminUser):
    return _decided(
        db,
        lambda: catalog_verification.reject_by_admin(
            db, resource_id, reason=body.reason, admin_id=admin.id, now=request.app.state.now()
        ),
    )


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


@router.get("/catalog/health", response_model=CatalogHealth)
def get_catalog_health(
    request: Request,
    db: DB,
    admin: AdminUser,
    days: Annotated[int, Query(ge=1, le=30)] = 7,
):
    """Gaps per subject, resources per status, failing connectors and dead links (#105)."""
    return catalog_health(db, now=request.app.state.now(), days=days)


@router.get("/costs", response_model=CostReport)
def get_costs(
    request: Request,
    db: DB,
    admin: AdminUser,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
):
    """LLM and search spend per node, provider latency and daily quota use."""
    return cost_report(db, now=request.app.state.now(), days=days)
