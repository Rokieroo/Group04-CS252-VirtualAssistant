"""Deterministic interval scheduling, independent of HTTP, SQL and LLMs.

Intervals are half-open: [start, end). Work is placed earliest-deadline-first among
the items whose dependencies are done, priority 1 first (spec 10.3, 10.4). The engine
reports every minute it cannot place rather than exceeding capacity.
"""

import heapq
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from graphlib import TopologicalSorter
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
    """Work to place. The defaults keep a plain task unconstrained.

    ``depends_on`` ids outside the plan count as done. ``buffer_days`` is the gap
    between this item's deadline and the deadline of everything it depends on
    (a milestone's review buffer, spec 10.3.2).
    """

    id: str
    remaining: int
    priority: int
    due_at: datetime
    release_at: datetime | None = None
    depends_on: tuple[str, ...] = ()
    buffer_days: int = 0


@dataclass(frozen=True)
class PlannedSession:
    task_id: str
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True)
class Shortfall:
    task_id: str
    minutes: int
    reason: str  # "deadline_passed", "insufficient_capacity" or "blocked_by_dependency"


@dataclass
class Plan:
    entries: list[PlannedSession] = field(default_factory=list)
    unscheduled: list[Shortfall] = field(default_factory=list)
    # Local Mondays of weeks whose capacity ran out before a deadline (spec 10.4).
    overloaded_weeks: list[date] = field(default_factory=list)


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
        """Raises graphlib.CycleError when ``depends_on`` forms a cycle."""
        by_id = {task.id: task for task in tasks}
        graph = {
            task.id: [dep for dep in task.depends_on if dep in by_id] for task in tasks
        }
        deadlines = self._deadlines(by_id, graph)
        free = self._free_slots(windows, occupied)
        daily_used = self._daily_usage(fixed_work)
        weekly_used = self._weekly_usage(daily_used)
        finished: dict[str, datetime] = {}
        failed: set[str] = set()
        overloaded: set[date] = set()
        plan = Plan()
        order = TopologicalSorter(graph)
        order.prepare()
        ready: list[tuple[int, datetime, str]] = []
        while order.is_active():
            for task_id in order.get_ready():
                task = by_id[task_id]
                heapq.heappush(ready, (task.priority, deadlines[task_id], task_id))
            _, deadline, task_id = heapq.heappop(ready)
            order.done(task_id)
            task = by_id[task_id]
            if task.remaining <= 0:
                continue
            if any(dep in failed for dep in graph[task_id]):
                reason, left = "blocked_by_dependency", task.remaining
            else:
                not_before = max(
                    [self.limits.starts_at, task.release_at or self.limits.starts_at]
                    + [finished[dep] for dep in graph[task_id] if dep in finished]
                )
                left = self._place(
                    task, not_before, deadline, free, daily_used, plan, weekly_used
                )
                reason = self._reason(deadline)
            if left:
                failed.add(task_id)
                plan.unscheduled.append(Shortfall(task_id, left, reason))
                if reason == "insufficient_capacity":
                    overloaded.add(self._week(min(deadline, self.limits.ends_at)))
            else:
                # Free slots are walked in time order: the last session is the latest.
                finished[task_id] = plan.entries[-1].ends_at
        plan.entries.sort(key=lambda entry: (entry.starts_at, entry.task_id))
        plan.overloaded_weeks = sorted(overloaded)
        return plan

    def _deadlines(self, by_id, graph) -> dict[str, datetime]:
        """Move each deadline before its dependents' deadlines minus their buffer, so
        earliest-deadline-first never strands a dependency."""
        deadlines = {task_id: task.due_at for task_id, task in by_id.items()}
        for task_id in reversed(list(TopologicalSorter(graph).static_order())):
            buffer = timedelta(days=by_id[task_id].buffer_days)
            for dep in graph[task_id]:
                deadlines[dep] = min(deadlines[dep], deadlines[task_id] - buffer)
        return deadlines

    def _day(self, moment: datetime) -> date:
        return moment.astimezone(self.zone).date()

    @staticmethod
    def _monday(day: date) -> date:
        return day - timedelta(days=day.weekday())

    def _week(self, end: datetime) -> date:
        # Ends are exclusive: a deadline at Monday 00:00 belongs to the week before.
        return self._monday(self._day(end - timedelta(microseconds=1)))

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

    def _weekly_usage(self, daily_used: dict[date, int]) -> dict[date, int]:
        used: dict[date, int] = defaultdict(int)
        for used_day, value in daily_used.items():
            used[self._monday(used_day)] += value
        return used

    def _place(
        self,
        task,
        not_before,
        deadline,
        free,
        daily_used,
        plan,
        weekly_used: dict[date, int],
    ) -> int:
        """Place sessions inside [not_before, deadline), removing the time used from
        ``free`` in place; return the minutes left unplaced."""
        remaining = task.remaining
        if remaining <= 0:
            return 0
        limits = self.limits
        weekly_limit = getattr(limits, "weekly_limit_minutes", 10080)
        kept: list[Interval] = []
        for idx, (slot_start, slot_end) in enumerate(free):
            if slot_start >= deadline:
                kept.extend(free[idx:])
                break
            start, end = max(slot_start, not_before), min(slot_end, deadline)
            if start >= end:
                kept.append((slot_start, slot_end))
                continue
            day = self._day(start)
            week_start = self._monday(day)
            capacity = min(
                minutes(start, end),
                limits.daily_limit_minutes - daily_used[day],
                weekly_limit - weekly_used[week_start],
            )
            cursor = start
            while capacity > 0 and remaining > 0:
                length = min(limits.max_session_minutes, capacity, remaining)
                # A final short remainder is allowed; other fragments must meet the minimum.
                if length < limits.min_session_minutes and length < remaining:
                    break
                stop = cursor + timedelta(minutes=length)
                plan.entries.append(PlannedSession(task.id, cursor, stop))
                daily_used[day] += length
                weekly_used[week_start] += length
                remaining -= length
                capacity -= length
                cursor = stop
            if cursor > start:
                kept.extend(
                    piece
                    for piece in ((slot_start, start), (cursor, slot_end))
                    if piece[0] < piece[1]
                )
                if remaining <= 0:
                    kept.extend(free[idx + 1 :])
                    break
            else:
                kept.append((slot_start, slot_end))
        free[:] = kept
        return remaining

    def _reason(self, deadline: datetime) -> str:
        if deadline <= self.limits.starts_at:
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
