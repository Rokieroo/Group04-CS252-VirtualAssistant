"""Deterministic interval scheduling, independent of HTTP, SQL and LLMs.

Intervals are half-open: [start, end). Priority 1 wins, then earlier deadlines.
The engine reports every minute it cannot place rather than exceeding capacity.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from app.planner.intervals import Interval, intersect, minutes, split_days, subtract


class PlanLimits(Protocol):
    """Horizon and session rules. The API's PlanRequest satisfies this structurally."""

    @property
    def starts_at(self) -> datetime: ...
    @property
    def ends_at(self) -> datetime: ...
    @property
    def max_session_minutes(self) -> int: ...
    @property
    def min_session_minutes(self) -> int: ...
    @property
    def daily_limit_minutes(self) -> int: ...


@dataclass(frozen=True)
class WorkItem:
    id: str
    remaining: int
    priority: int
    due_at: datetime


@dataclass(frozen=True)
class PlannedSession:
    task_id: str
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True)
class Shortfall:
    task_id: str
    minutes: int
    reason: str  # "deadline_passed" or "insufficient_capacity"


@dataclass
class Plan:
    entries: list[PlannedSession] = field(default_factory=list)
    unscheduled: list[Shortfall] = field(default_factory=list)


class Planner:
    """Greedily places work into free time, one local day's budget at a time."""

    def __init__(self, limits: PlanLimits, timezone_name: str):
        self.limits = limits
        self.zone = ZoneInfo(timezone_name)

    def plan(
        self,
        tasks: list[WorkItem],
        windows: list[Interval],
        occupied: list[Interval],
        fixed_work: list[Interval],
    ) -> Plan:
        free = self._free_slots(windows, occupied)
        daily_used = self._daily_usage(fixed_work)
        plan = Plan()
        for task in sorted(tasks, key=lambda item: (item.priority, item.due_at, item.id)):
            if task.remaining <= 0:
                continue
            left = self._place(task, free, daily_used, plan.entries)
            if left:
                plan.unscheduled.append(Shortfall(task.id, left, self._reason(task)))
        plan.entries.sort(key=lambda entry: (entry.starts_at, entry.task_id))
        return plan

    def _day(self, moment: datetime) -> date:
        return moment.astimezone(self.zone).date()

    def _free_slots(self, windows: list[Interval], occupied: list[Interval]):
        horizon = [(self.limits.starts_at, self.limits.ends_at)]
        free = subtract(intersect(windows, horizon), occupied)
        return [piece for window in free for piece in split_days(window, self.zone)]

    def _daily_usage(self, fixed_work: list[Interval]) -> dict[date, int]:
        used: dict[date, int] = defaultdict(int)
        for interval in fixed_work:
            for start, end in split_days(interval, self.zone):
                used[self._day(start)] += minutes(start, end)
        return used

    def _place(self, task: WorkItem, free, daily_used, entries) -> int:
        """Consume free slots in order (shrinking them in place); return unplaced minutes."""
        limits = self.limits
        remaining = task.remaining
        for index, (start, end) in enumerate(free):
            if remaining <= 0:
                break
            end = min(end, task.due_at)
            day = self._day(start)
            capacity = min(
                minutes(start, end), limits.daily_limit_minutes - daily_used[day]
            )
            while capacity > 0 and remaining > 0:
                length = min(limits.max_session_minutes, capacity, remaining)
                # A final short remainder is allowed; other fragments must meet the minimum.
                if length < limits.min_session_minutes and length < remaining:
                    break
                stop = start + timedelta(minutes=length)
                entries.append(PlannedSession(task.id, start, stop))
                daily_used[day] += length
                remaining -= length
                capacity -= length
                start = stop
                free[index] = (start, free[index][1])
        return remaining

    def _reason(self, task: WorkItem) -> str:
        if task.due_at <= self.limits.starts_at:
            return "deadline_passed"
        return "insufficient_capacity"


def build_plan(
    tasks: list[WorkItem],
    windows: list[Interval],
    occupied: list[Interval],
    fixed_work: list[Interval],
    limits: PlanLimits,
    timezone_name: str,
) -> Plan:
    return Planner(limits, timezone_name).plan(tasks, windows, occupied, fixed_work)
