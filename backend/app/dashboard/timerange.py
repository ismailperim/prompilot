"""Resolve Grafana-style time expressions into absolute datetimes.

Supported: ``now``, ``now-5m``, ``now+1h``, ``now/d`` (round to unit),
``now-1d/d``, ISO-8601 timestamps and epoch milliseconds.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from app.config import parse_duration
from app.dashboard.models import TimeRange

_RELATIVE = re.compile(
    r"^now(?:(?P<sign>[+-])(?P<amount>\d+(?:ms|s|m|h|d|w)))?(?:/(?P<unit>[smhdwMy]))?$"
)


class TimeRangeError(ValueError):
    pass


def _round(moment: datetime, unit: str, *, up: bool) -> datetime:
    floor = {
        "s": moment.replace(microsecond=0),
        "m": moment.replace(second=0, microsecond=0),
        "h": moment.replace(minute=0, second=0, microsecond=0),
        "d": moment.replace(hour=0, minute=0, second=0, microsecond=0),
        "w": (moment - timedelta(days=moment.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        ),
        "M": moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
        "y": moment.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
    }[unit]
    if not up:
        return floor
    match unit:
        case "s":
            return floor + timedelta(seconds=1)
        case "m":
            return floor + timedelta(minutes=1)
        case "h":
            return floor + timedelta(hours=1)
        case "d":
            return floor + timedelta(days=1)
        case "w":
            return floor + timedelta(weeks=1)
        case "M":
            return (floor + timedelta(days=32)).replace(day=1)
        case _:
            return floor.replace(year=floor.year + 1)


def parse_time(expr: str, *, now: datetime, round_up: bool = False) -> datetime:
    expr = expr.strip()
    if match := _RELATIVE.match(expr):
        moment = now
        if match.group("amount"):
            offset = parse_duration(match.group("amount"))
            moment = moment - offset if match.group("sign") == "-" else moment + offset
        if match.group("unit"):
            moment = _round(moment, match.group("unit"), up=round_up)
        return moment

    if expr.isdigit():
        millis = int(expr)
        # Treat 10-digit values as seconds for convenience; Grafana sends milliseconds.
        seconds = millis / 1000 if millis > 10_000_000_000 else millis
        return datetime.fromtimestamp(seconds, tz=UTC)

    try:
        parsed = datetime.fromisoformat(expr.replace("Z", "+00:00"))
    except ValueError:
        raise TimeRangeError(
            f"invalid time {expr!r}; expected e.g. 'now-1h', 'now/d', an ISO-8601 "
            "timestamp or epoch milliseconds"
        ) from None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def resolve(time_range: TimeRange, *, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return absolute ``(start, end)`` for a time range; raises if start >= end."""
    now = now or datetime.now(tz=UTC)
    start = parse_time(time_range.from_, now=now)
    end = parse_time(time_range.to, now=now, round_up=True)
    if start >= end:
        raise TimeRangeError(
            f"time range is empty: {time_range.from_!r} is not before {time_range.to!r}"
        )
    return start, end


def to_millis(moment: datetime) -> int:
    return round(moment.timestamp() * 1000)
