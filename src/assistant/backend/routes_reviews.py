"""FSRS Spaced Repetition review endpoints (UC-11, issue #162)."""

from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from app.planner.fsrs import schedule_card_review

from .catalog_models import Item, NodeExercise
from .dependencies import DB, CurrentUser
from .models import ReviewCard, ReviewLog, Roadmap, RoadmapNode
from .schemas import ReviewCardOut, ReviewResultOut, ReviewSubmitIn

router = APIRouter(tags=["FSRS Spaced Repetition Reviews"])


def _resolve_user_node_id(
    db: DB,
    user_id: str,
    requested_node_id: str | None,
    card: ReviewCard | None,
    item: Item,
) -> str | None:
    """The node this review counts toward; only ever one of ``user_id``'s own roadmaps."""
    owned = (
        select(RoadmapNode.id)
        .join(Roadmap, Roadmap.id == RoadmapNode.roadmap_id)
        .where(Roadmap.user_id == user_id)
    )
    if requested_node_id:
        node_id = db.scalar(owned.where(RoadmapNode.id == requested_node_id))
        if not node_id:
            raise HTTPException(status_code=404, detail="Roadmap node not found")
        return node_id

    # Otherwise infer it, most specific first: the card's node, the exercise's, the concept's.
    candidates = []
    if card and card.node_id:
        candidates.append(RoadmapNode.id == card.node_id)
    if item.exercise_id:
        candidates.append(
            RoadmapNode.id.in_(
                select(NodeExercise.node_id).where(NodeExercise.exercise_id == item.exercise_id)
            )
        )
    if item.concept_id:
        candidates.append(RoadmapNode.concept_id == item.concept_id)
    for condition in candidates:
        if node_id := db.scalar(owned.where(condition).limit(1)):
            return node_id
    return None


@router.get("/reviews/due", response_model=list[ReviewCardOut])
def get_due_reviews(
    db: DB,
    user: CurrentUser,
    request: Request,
    limit: int = Query(50, ge=1, le=100),
):
    """Retrieve review cards due for the current user (issue #162, UC-11)."""
    now = request.app.state.now()
    cards = list(
        db.scalars(
            select(ReviewCard)
            .where(
                ReviewCard.user_id == user.id,
                ReviewCard.due_at <= now,
            )
            .order_by(ReviewCard.due_at)
            .limit(limit)
        )
    )
    if not cards:
        return []

    item_ids = [c.item_id for c in cards]
    items = {
        item.id: item for item in db.scalars(select(Item).where(Item.id.in_(item_ids)))
    }

    results: list[ReviewCardOut] = []
    for c in cards:
        item = items.get(c.item_id)
        choices_raw = item.choices if item else None
        choices: list[str] | None = None
        if choices_raw:
            try:
                parsed = json.loads(choices_raw)
                if isinstance(parsed, list):
                    choices = [str(x) for x in parsed]
            except (json.JSONDecodeError, TypeError, ValueError):
                choices = None

        results.append(
            ReviewCardOut(
                item_id=c.item_id,
                user_id=c.user_id,
                node_id=c.node_id,
                due_at=c.due_at,
                stability=c.stability,
                difficulty=c.difficulty,
                state=c.state,
                step=c.step,
                last_review=c.last_review,
                prompt=item.prompt if item else "",
                choices=choices,
                type=item.type if item else "mcq",
                source_id=item.source_id if item else None,
            )
        )
    return results


@router.post("/reviews/{item_id}", response_model=ReviewResultOut)
def submit_review(
    item_id: str,
    data: ReviewSubmitIn,
    db: DB,
    user: CurrentUser,
    request: Request,
):
    """Submit a rating (1-4) for an item review card (issue #162, UC-11)."""
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    now = request.app.state.now()
    card = db.get(ReviewCard, (user.id, item_id))
    node_id = _resolve_user_node_id(db, user.id, data.node_id, card, item)

    if card is None:
        result = schedule_card_review(
            rating=data.rating,
            reviewed_at=now,
        )
        card = ReviewCard(
            user_id=user.id,
            item_id=item_id,
            node_id=node_id,
            due_at=result.due_at,
            stability=result.stability,
            difficulty=result.difficulty,
            state=result.state,
            step=result.step,
            last_review=result.last_review,
        )
        db.add(card)
    else:
        result = schedule_card_review(
            rating=data.rating,
            reviewed_at=now,
            current_state=card.state,
            current_step=card.step,
            stability=card.stability,
            difficulty=card.difficulty,
            due_at=card.due_at,
            last_review=card.last_review,
        )
        card.due_at = result.due_at
        card.stability = result.stability
        card.difficulty = result.difficulty
        card.state = result.state
        card.step = result.step
        card.last_review = result.last_review
        card.node_id = node_id

    review_log = ReviewLog(
        id=str(uuid4()),
        user_id=user.id,
        item_id=item_id,
        node_id=node_id,
        rating=data.rating,
        reviewed_at=now,
        elapsed_days=result.elapsed_days,
        scheduled_days=result.scheduled_days,
        stability=result.stability,
        difficulty=result.difficulty,
    )
    db.add(review_log)
    db.commit()

    return ReviewResultOut(
        item_id=item_id,
        user_id=user.id,
        node_id=node_id,
        rating=data.rating,
        due_at=result.due_at,
        stability=result.stability,
        difficulty=result.difficulty,
        state=result.state,
        step=result.step,
        last_review=result.last_review,
        elapsed_days=result.elapsed_days,
        scheduled_days=result.scheduled_days,
        retrievability=result.retrievability,
    )
