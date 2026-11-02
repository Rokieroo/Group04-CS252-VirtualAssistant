from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.planner import (
    WorkItem,
    build_plan,
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
