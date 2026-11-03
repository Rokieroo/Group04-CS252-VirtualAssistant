"""Admin-only views: the cost and quota dashboard (issue #69)."""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from .costs import cost_report
from .dependencies import DB, AdminUser
from .schemas import CostReport

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/costs", response_model=CostReport)
def get_costs(
    request: Request,
    db: DB,
    admin: AdminUser,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
):
    """LLM and search spend per node, provider latency and daily quota use."""
    return cost_report(db, now=request.app.state.now(), days=days)
