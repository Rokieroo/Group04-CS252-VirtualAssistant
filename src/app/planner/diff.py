"""Compare two plans per task, for replan proposals (spec 10.5, UC-07)."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class Session(Protocol):
    """A planned session. PlannedSession and the ScheduleEntry row both satisfy this."""

    @property
    def task_id(self) -> str: ...
    @property
    def starts_at(self) -> datetime: ...
    @property
    def ends_at(self) -> datetime: ...


@dataclass(frozen=True)
class PlanDiff:
    moved: list[str]  # task ids planned in both, at different times
    added: list[str]  # task ids planned only in the new plan
    dropped: list[str]  # task ids planned only in the old plan


def diff(old: Iterable[Session], new: Iterable[Session]) -> PlanDiff:
    before, after = _times(old), _times(new)
    return PlanDiff(
        moved=sorted(t for t in before.keys() & after.keys() if before[t] != after[t]),
        added=sorted(after.keys() - before.keys()),
        dropped=sorted(before.keys() - after.keys()),
    )


def _times(sessions: Iterable[Session]) -> dict[str, list[tuple[datetime, datetime]]]:
    times: dict[str, list[tuple[datetime, datetime]]] = defaultdict(list)
    for session in sessions:
        times[session.task_id].append((session.starts_at, session.ends_at))
    return {task_id: sorted(spans) for task_id, spans in times.items()}
