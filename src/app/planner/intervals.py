"""Half-open time intervals [start, end) and the set operations the planner needs."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

Interval = tuple[datetime, datetime]


def minutes(start: datetime, end: datetime) -> int:
    return max(0, int((end - start).total_seconds() // 60))


def merge(intervals: list[Interval]) -> list[Interval]:
    result: list[Interval] = []
    for start, end in sorted(intervals):
        if start >= end:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def subtract(windows: list[Interval], occupied: list[Interval]) -> list[Interval]:
    result = merge(windows)
    for busy_start, busy_end in merge(occupied):
        next_result = []
        for start, end in result:
            if busy_end <= start or busy_start >= end:
                next_result.append((start, end))
                continue
            if start < busy_start:
                next_result.append((start, busy_start))
            if busy_end < end:
                next_result.append((busy_end, end))
        result = next_result
    return result


def intersect(left: list[Interval], right: list[Interval]) -> list[Interval]:
    result = []
    a, b = merge(left), merge(right)
    i = j = 0
    while i < len(a) and j < len(b):
        start, end = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if start < end:
            result.append((start, end))
        if a[i][1] <= b[j][1]:
            i += 1
        else:
            j += 1
    return result


def split_days(interval: Interval, zone: ZoneInfo) -> list[Interval]:
    start, end = interval
    result = []
    while start < end:
        tomorrow = start.astimezone(zone).date() + timedelta(days=1)
        midnight = datetime.combine(tomorrow, time.min, zone).astimezone(start.tzinfo)
        boundary = min(midnight, end)
        result.append((start, boundary))
        start = boundary
    return result
