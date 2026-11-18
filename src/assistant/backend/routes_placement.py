"""Placement test (UC-17, #166): skip the concepts an experienced learner already knows."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .catalog_models import Placement
from .dependencies import DB, CurrentUser
from .models import Course, Roadmap
from .placement_repository import (
    StaleAnswer,
    answer_placement,
    set_known,
    start_placement,
)
from .routes_core import _owned_roadmap
from .routes_learning import AttemptOut, ExerciseOut, _node

router = APIRouter(tags=["Placement"])

Known = Literal["tested", "inferred", "learner"]


class PlacementQuestionOut(BaseModel):
    node_id: str
    title: str
    exercise: ExerciseOut  # quoted from its source, with citation and location


class PlacementOut(BaseModel):
    id: str
    roadmap_id: str
    status: Literal["active", "finished"]
    asked: int
    max_questions: int
    question: PlacementQuestionOut | None
    known: list[str]  # provisional until ``finished``, then saved on the nodes
    unknown: list[str]
    skipped: list[str]  # concepts with no exercise to mark: never guessed
    total_minutes: int
    known_minutes: int
    last_attempt: AttemptOut | None = None


class PlacementAnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exercise_id: str  # the open question's exercise; another one is a stale answer
    response: str = Field(min_length=1, max_length=4000)


class KnownIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    known: bool


class KnownOut(BaseModel):
    node_id: str
    known: Known | None
    changed: list[str]  # every concept whose state changed, this one included


@router.post("/roadmaps/{roadmap_id}/placement", response_model=PlacementOut)
def start(roadmap_id: str, db: DB, user: CurrentUser, request: Request):
    """Start a placement test on the roadmap, or resume the open one."""
    roadmap = _owned_roadmap(db, roadmap_id, user.id)
    course = db.get(Course, roadmap.course_id)
    result = start_placement(db, roadmap, course, user.id, request.app.state.now())
    db.commit()
    return result


@router.post("/placements/{placement_id}/answers", response_model=PlacementOut)
def answer(
    placement_id: str,
    body: PlacementAnswerIn,
    db: DB,
    user: CurrentUser,
    request: Request,
):
    """Mark the open question against its source's key and open the next one."""
    # Row lock (PostgreSQL): two answers to one question cannot both advance it.
    placement = db.get(Placement, placement_id, with_for_update=True)
    if placement is None or placement.user_id != user.id:
        raise HTTPException(404, "Placement not found")
    roadmap = db.get(Roadmap, placement.roadmap_id)
    course = db.get(Course, roadmap.course_id)
    try:
        result = answer_placement(
            db,
            placement,
            roadmap,
            course,
            request.app.state.now(),
            body.exercise_id,
            body.response,
        )
    except StaleAnswer:
        raise HTTPException(
            409, "Not the open question; start the placement again to resume"
        ) from None
    db.commit()
    return result


@router.put("/roadmap-nodes/{node_id}/known", response_model=KnownOut)
def known(node_id: str, body: KnownIn, db: DB, user: CurrentUser):
    """The learner corrects the placement: mark or unmark a concept as known."""
    node, _, _ = _node(db, node_id, user.id)
    try:
        changed = set_known(db, node, body.known)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    db.commit()
    return {"node_id": node.id, "known": node.known, "changed": changed}
