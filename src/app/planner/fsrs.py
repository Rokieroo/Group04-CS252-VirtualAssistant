"""FSRS spaced repetition scheduler and node mastery calculations (UC-11, issue #162)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fsrs import Card, Rating, Scheduler, State


@dataclass(frozen=True)
class ReviewScheduleResult:
    due_at: datetime
    stability: float
    difficulty: float
    state: int
    step: int
    last_review: datetime
    elapsed_days: float
    scheduled_days: float
    retrievability: float


def schedule_card_review(
    *,
    rating: int,
    reviewed_at: datetime | None = None,
    current_state: int = 1,
    current_step: int = 0,
    stability: float | None = None,
    difficulty: float | None = None,
    due_at: datetime | None = None,
    last_review: datetime | None = None,
) -> ReviewScheduleResult:
    """Schedule the next review of a card using FSRS-4.5 / fsrs v5.

    Rating: 1 (Again), 2 (Hard), 3 (Good), 4 (Easy).
    """
    if rating not in (1, 2, 3, 4):
        raise ValueError(f"Rating must be 1, 2, 3, or 4; got {rating}")

    now = reviewed_at or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    scheduler = Scheduler()

    card_state = State(current_state) if current_state in (1, 2, 3) else State.Learning

    stab = stability if stability is not None and stability > 0 else None
    diff = difficulty if difficulty is not None and difficulty > 0 else None

    card = Card(
        state=card_state,
        step=current_step,
        stability=stab,
        difficulty=diff,
        due=due_at,
        last_review=last_review,
    )

    fsrs_rating = Rating(rating)
    updated_card, _ = scheduler.review_card(card, fsrs_rating, now)

    elapsed_days = (
        max(0.0, (now - last_review).total_seconds() / 86400.0) if last_review else 0.0
    )
    scheduled_days = max(0.0, (updated_card.due - now).total_seconds() / 86400.0)
    retrievability = float(scheduler.get_card_retrievability(updated_card, now))

    return ReviewScheduleResult(
        due_at=updated_card.due,
        stability=float(updated_card.stability or 0.0),
        difficulty=float(updated_card.difficulty or 0.0),
        state=int(updated_card.state.value),
        step=int(updated_card.step or 0),
        last_review=updated_card.last_review or now,
        elapsed_days=round(elapsed_days, 4),
        scheduled_days=round(scheduled_days, 4),
        retrievability=round(retrievability, 4),
    )


def compute_card_retrievability(
    card_dict_or_obj: Any,
    now: datetime | None = None,
) -> float:
    """Calculate the memory retrievability (probability of recall) for a card."""
    ref_time = now or datetime.now(UTC)
    if ref_time.tzinfo is None:
        ref_time = ref_time.replace(tzinfo=UTC)

    if isinstance(card_dict_or_obj, dict):
        state = card_dict_or_obj.get("state", 1)
        step = card_dict_or_obj.get("step", 0)
        stability = card_dict_or_obj.get("stability")
        difficulty = card_dict_or_obj.get("difficulty")
        due = card_dict_or_obj.get("due_at") or card_dict_or_obj.get("due")
        last_review = card_dict_or_obj.get("last_review")
    else:
        state = getattr(card_dict_or_obj, "state", 1)
        step = getattr(card_dict_or_obj, "step", 0)
        stability = getattr(card_dict_or_obj, "stability", None)
        difficulty = getattr(card_dict_or_obj, "difficulty", None)
        due = getattr(
            card_dict_or_obj, "due_at", getattr(card_dict_or_obj, "due", None)
        )
        last_review = getattr(card_dict_or_obj, "last_review", None)

    if not stability or stability <= 0 or not last_review:
        return 0.0

    card_state = State(state) if state in (1, 2, 3) else State.Learning

    card = Card(
        state=card_state,
        step=step,
        stability=stability,
        difficulty=difficulty if difficulty and difficulty > 0 else None,
        due=due,
        last_review=last_review,
    )
    scheduler = Scheduler()
    r = float(scheduler.get_card_retrievability(card, ref_time))
    return max(0.0, min(1.0, r))


def compute_node_mastery(
    cards: list[Any],
    now: datetime | None = None,
) -> float:
    """Calculate the mastery score of a node as the average retrievability of its cards.

    Returns float in range [0.0, 1.0]. Returns 0.0 if the node has no cards.
    """
    if not cards:
        return 0.0

    retrievabilities = [compute_card_retrievability(c, now) for c in cards]
    avg = sum(retrievabilities) / len(retrievabilities)
    return round(max(0.0, min(1.0, avg)), 4)
