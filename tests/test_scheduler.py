from datetime import UTC, date, datetime, timedelta
from graphlib import CycleError

import pytest
from pydantic import ValidationError

from app.planner import (
    PlannedSession,
    WorkItem,
    build_plan,
    diff,
    intersect,
    merge,
    minutes,
    subtract,
)
from assistant.backend.schemas import PlanRequest

START = datetime(2030, 1, 7, 2, tzinfo=UTC)


def at(offset):
    return START + timedelta(minutes=offset)


def request(**changes):
    return PlanRequest(starts_at=START, ends_at=at(180), **changes)


def test_interval_union_difference_and_half_open_boundaries():
    assert merge([(at(0), at(30)), (at(20), at(60)), (at(60), at(90))]) == [
        (at(0), at(90))
    ]
    assert subtract([(at(0), at(90))], [(at(20), at(30)), (at(60), at(100))]) == [
        (at(0), at(20)),
        (at(30), at(60)),
    ]
    assert intersect([(at(0), at(30))], [(at(30), at(60))]) == []


def test_plan_splits_tasks_around_busy_time_and_preserves_every_minute():
    result = build_plan(
        [WorkItem("a", 100, 1, at(180))],
        [(at(0), at(180))],
        [(at(30), at(60))],
        [],
        request(),
        "Asia/Ho_Chi_Minh",
    )
    assert sum(minutes(x.starts_at, x.ends_at) for x in result.entries) == 100
    assert result.unscheduled == []
    assert all(x.ends_at <= at(30) or x.starts_at >= at(60) for x in result.entries)
    assert all(minutes(x.starts_at, x.ends_at) <= 60 for x in result.entries)


def test_priority_then_deadline_and_short_remainder():
    tasks = [WorkItem("low", 60, 3, at(60)), WorkItem("urgent", 65, 1, at(70))]
    result = build_plan(tasks, [(at(0), at(70))], [], [], request(), "UTC")
    assert [x.task_id for x in result.entries] == ["urgent", "urgent"]
    assert minutes(result.entries[-1].starts_at, result.entries[-1].ends_at) == 5
    assert result.unscheduled[0].task_id == "low"
    assert result.unscheduled[0].minutes == 60


def test_deadlines_are_hard_limits_and_overdue_work_is_reported():
    tasks = [WorkItem("late", 30, 1, at(-1)), WorkItem("soon", 80, 2, at(45))]
    result = build_plan(tasks, [(at(0), at(180))], [], [], request(), "UTC")
    assert all(x.ends_at <= at(45) for x in result.entries)
    assert {x.task_id: (x.minutes, x.reason) for x in result.unscheduled} == {
        "late": (30, "deadline_passed"),
        "soon": (35, "insufficient_capacity"),
    }


def test_local_midnight_resets_daily_budget():
    start = datetime.fromisoformat("2030-01-07T23:00:00+07:00")
    end = start + timedelta(hours=3)
    data = PlanRequest(starts_at=start, ends_at=end, daily_limit_minutes=60)
    result = build_plan(
        [WorkItem("a", 180, 1, end)], [(start, end)], [], [], data, "Asia/Ho_Chi_Minh"
    )
    assert sum(minutes(x.starts_at, x.ends_at) for x in result.entries) == 120
    assert result.unscheduled[0].minutes == 60
    assert (
        len({x.starts_at.astimezone(start.tzinfo).date() for x in result.entries}) == 2
    )


def test_existing_work_counts_against_daily_budget():
    result = build_plan(
        [WorkItem("a", 90, 1, at(180))],
        [(at(0), at(180))],
        [(at(0), at(45))],
        [(at(0), at(45))],
        request(daily_limit_minutes=60),
        "UTC",
    )
    assert sum(minutes(x.starts_at, x.ends_at) for x in result.entries) == 15
    assert result.unscheduled[0].minutes == 75


@pytest.mark.parametrize(
    "changes",
    [
        {"starts_at": "2030-01-07T09:00:00", "ends_at": "2030-01-07T10:00:00"},
        {"starts_at": START, "ends_at": START},
        {
            "starts_at": START,
            "ends_at": at(10),
            "min_session_minutes": 60,
            "max_session_minutes": 30,
        },
        {"starts_at": START, "ends_at": START + timedelta(days=91)},
        {"starts_at": START + timedelta(seconds=1), "ends_at": at(10)},
    ],
)
def test_invalid_plan_ranges_are_rejected(changes):
    with pytest.raises(ValidationError):
        PlanRequest(**changes)


def test_scheduling_invariants_for_varied_capacity():
    # Exercise busy intervals, priorities, partial capacity and multiple task sizes together.
    for capacity in (20, 45, 90, 180):
        tasks = [
            WorkItem(str(i), 17 + i * 19, i % 3 + 1, at(180 - i * 10)) for i in range(7)
        ]
        result = build_plan(
            tasks, [(at(0), at(capacity))], [(at(30), at(50))], [], request(), "UTC"
        )
        for previous, current in zip(result.entries, result.entries[1:]):
            assert previous.ends_at <= current.starts_at
        for item in tasks:
            scheduled = sum(
                minutes(x.starts_at, x.ends_at)
                for x in result.entries
                if x.task_id == item.id
            )
            pending = sum(x.minutes for x in result.unscheduled if x.task_id == item.id)
            assert scheduled + pending == item.remaining
        assert all(
            x.starts_at >= START and x.ends_at <= at(capacity) for x in result.entries
        )


DAY = timedelta(days=1)


def days(count, **changes):
    """A plan over ``count`` days with one 09:00-11:00 UTC window each day."""
    data = PlanRequest(starts_at=START, ends_at=START + count * DAY, **changes)
    windows = [
        (START + i * DAY + timedelta(hours=7), START + i * DAY + timedelta(hours=9))
        for i in range(count)
    ]
    return data, windows


def sessions_of(result, task_id):
    return [x for x in result.entries if x.task_id == task_id]


def test_dependent_never_starts_before_its_dependency_finishes():
    # The child is more urgent, yet it has to wait for its parent.
    tasks = [
        WorkItem("parent", 90, 3, at(180)),
        WorkItem("child", 30, 1, at(170), depends_on=("parent",)),
    ]
    result = build_plan(tasks, [(at(0), at(180))], [], [], request(), "UTC")
    parent_end = max(x.ends_at for x in sessions_of(result, "parent"))
    assert all(x.starts_at >= parent_end for x in sessions_of(result, "child"))
    assert result.unscheduled == []


def test_unknown_dependencies_count_as_done():
    tasks = [WorkItem("a", 30, 1, at(180), depends_on=("finished-last-week",))]
    result = build_plan(tasks, [(at(0), at(180))], [], [], request(), "UTC")
    assert sessions_of(result, "a")[0].starts_at == at(0)


def test_work_never_starts_before_its_release():
    tasks = [WorkItem("later", 60, 1, at(180), release_at=at(90)),
             WorkItem("now", 30, 2, at(180))]
    result = build_plan(tasks, [(at(0), at(180))], [], [], request(), "UTC")
    assert all(x.starts_at >= at(90) for x in sessions_of(result, "later"))
    # The time before the release stays free for other work.
    assert sessions_of(result, "now")[0].starts_at == at(0)


def test_buffer_makes_dependencies_finish_days_before_the_milestone():
    data, windows = days(10)
    tasks = [
        WorkItem("topic", 100, 2, START + 10 * DAY),
        WorkItem("exam", 30, 2, START + 6 * DAY, depends_on=("topic",), buffer_days=3),
    ]
    result = build_plan(tasks, windows, [], [], data, "UTC")
    assert max(x.ends_at for x in sessions_of(result, "topic")) <= START + 3 * DAY
    assert result.unscheduled == []


def test_failed_dependency_blocks_its_dependents_and_marks_its_week():
    # Only 60 minutes a day: the topic cannot finish 3 days before the exam.
    data, windows = days(10, daily_limit_minutes=60)
    tasks = [
        WorkItem("topic", 420, 2, START + 10 * DAY),
        WorkItem("exam", 30, 2, START + 9 * DAY, depends_on=("topic",), buffer_days=3),
    ]
    result = build_plan(tasks, windows, [], [], data, "UTC")
    reasons = {x.task_id: (x.minutes, x.reason) for x in result.unscheduled}
    assert reasons == {
        "topic": (420 - 6 * 60, "insufficient_capacity"),
        "exam": (30, "blocked_by_dependency"),
    }
    assert sessions_of(result, "exam") == []
    # The topic had to finish by Sunday 13 January, so the first week is overloaded.
    assert result.overloaded_weeks == [date(2030, 1, 7)]


def test_overload_is_reported_in_the_week_of_the_missed_deadline():
    data, windows = days(14, daily_limit_minutes=30)
    tasks = [
        WorkItem("fits", 30, 1, START + 2 * DAY),
        WorkItem("too-big", 400, 2, START + 9 * DAY),  # due Wednesday of week 2
        WorkItem("overdue", 30, 1, START - DAY),
    ]
    result = build_plan(tasks, windows, [], [], data, "UTC")
    assert {x.task_id: x.reason for x in result.unscheduled} == {
        "too-big": "insufficient_capacity",
        "overdue": "deadline_passed",
    }
    assert result.overloaded_weeks == [date(2030, 1, 14)]


def test_dependency_cycles_are_rejected():
    tasks = [WorkItem("a", 30, 1, at(180), depends_on=("b",)),
             WorkItem("b", 30, 1, at(180), depends_on=("a",))]
    with pytest.raises(CycleError):
        build_plan(tasks, [(at(0), at(180))], [], [], request(), "UTC")


def test_diff_reports_moved_added_and_dropped_tasks():
    old = [
        PlannedSession("kept", at(0), at(30)),
        PlannedSession("moved", at(30), at(60)),
        PlannedSession("dropped", at(60), at(90)),
    ]
    new = [
        PlannedSession("kept", at(0), at(30)),
        PlannedSession("moved", at(90), at(120)),
        PlannedSession("added", at(120), at(150)),
    ]
    change = diff(old, new)
    assert change.moved == ["moved"]
    assert change.added == ["added"]
    assert change.dropped == ["dropped"]
    assert diff(new, list(reversed(new))) == diff([], [])


def test_weekly_limit_counts_fixed_work_and_resets_next_week():
    from types import SimpleNamespace

    start = datetime(2030, 1, 7, 7, tzinfo=UTC)  # Monday
    windows = [
        (start + i * DAY, start + i * DAY + timedelta(hours=2))
        for i in range(10)
    ]
    limits = SimpleNamespace(
        starts_at=start,
        ends_at=start + 10 * DAY,
        max_session_minutes=60,
        min_session_minutes=15,
        daily_limit_minutes=60,
        weekly_limit_minutes=90,
    )
    fixed = [(start, start + timedelta(minutes=30))]  # 30m used in week 1
    result = build_plan(
        [WorkItem("course", 150, 1, start + 10 * DAY)],
        windows,
        [(start, start + timedelta(minutes=30))],
        fixed,
        limits,
        "UTC",
    )
    assert result.unscheduled == []
    week1_minutes = sum(
        minutes(entry.starts_at, entry.ends_at)
        for entry in result.entries
        if entry.starts_at < start + 7 * DAY
    )
    week2_minutes = sum(
        minutes(entry.starts_at, entry.ends_at)
        for entry in result.entries
        if entry.starts_at >= start + 7 * DAY
    )
    assert week1_minutes == 60
    assert week2_minutes == 90


def test_early_exit_preserves_future_slots_for_later_tasks():
    data, windows = days(60, daily_limit_minutes=120)
    tasks = [
        WorkItem("early", 30, 1, START + 2 * DAY, release_at=START + 1 * DAY),
        WorkItem("week8", 120, 2, START + 55 * DAY, release_at=START + 49 * DAY),
    ]
    result = build_plan(tasks, windows, [], [], data, "UTC")
    assert result.unscheduled == []
    assert [minutes(x.starts_at, x.ends_at) for x in sessions_of(result, "early")] == [30]
    assert sessions_of(result, "early")[0].starts_at >= START + 1 * DAY
    assert sum(minutes(x.starts_at, x.ends_at) for x in sessions_of(result, "week8")) == 120
    assert sessions_of(result, "week8")[0].starts_at >= START + 49 * DAY
