from datetime import UTC, datetime, timedelta

import pytest

from app.dashboard.models import TimeRange
from app.dashboard.timerange import TimeRangeError, parse_time, resolve, to_millis

NOW = datetime(2024, 3, 13, 14, 35, 27, 500_000, tzinfo=UTC)  # a Wednesday


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("now", NOW),
        ("now-5m", NOW - timedelta(minutes=5)),
        ("now-1h", NOW - timedelta(hours=1)),
        ("now-7d", NOW - timedelta(days=7)),
        ("now-2w", NOW - timedelta(weeks=2)),
        ("now+30s", NOW + timedelta(seconds=30)),
        ("now/d", datetime(2024, 3, 13, tzinfo=UTC)),
        ("now/h", datetime(2024, 3, 13, 14, tzinfo=UTC)),
        ("now/w", datetime(2024, 3, 11, tzinfo=UTC)),
        ("now/M", datetime(2024, 3, 1, tzinfo=UTC)),
        ("now/y", datetime(2024, 1, 1, tzinfo=UTC)),
        ("now-1d/d", datetime(2024, 3, 12, tzinfo=UTC)),
        ("1710340527000", datetime(2024, 3, 13, 14, 35, 27, tzinfo=UTC)),
        ("1710340527", datetime(2024, 3, 13, 14, 35, 27, tzinfo=UTC)),
        ("2024-03-13T10:00:00Z", datetime(2024, 3, 13, 10, tzinfo=UTC)),
        ("2024-03-13T10:00:00+02:00", datetime(2024, 3, 13, 8, tzinfo=UTC)),
        ("2024-03-13T10:00:00", datetime(2024, 3, 13, 10, tzinfo=UTC)),
    ],
)
def test_parse_time(expr: str, expected: datetime) -> None:
    assert parse_time(expr, now=NOW) == expected


def test_rounding_up_for_range_end() -> None:
    assert parse_time("now/d", now=NOW, round_up=True) == datetime(2024, 3, 14, tzinfo=UTC)
    assert parse_time("now/M", now=NOW, round_up=True) == datetime(2024, 4, 1, tzinfo=UTC)
    assert parse_time("now/y", now=NOW, round_up=True) == datetime(2025, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize("expr", ["yesterday", "now-", "now-1x", "now/q", "13/03/2024", ""])
def test_invalid_expressions(expr: str) -> None:
    with pytest.raises(TimeRangeError):
        parse_time(expr, now=NOW)


def test_resolve_today_so_far() -> None:
    start, end = resolve(TimeRange(from_="now/d", to="now"), now=NOW)
    assert start == datetime(2024, 3, 13, tzinfo=UTC)
    assert end == NOW


def test_resolve_full_yesterday() -> None:
    start, end = resolve(TimeRange(from_="now-1d/d", to="now-1d/d"), now=NOW)
    assert start == datetime(2024, 3, 12, tzinfo=UTC)
    assert end == datetime(2024, 3, 13, tzinfo=UTC)


def test_resolve_rejects_empty_range() -> None:
    with pytest.raises(TimeRangeError, match="empty"):
        resolve(TimeRange(from_="now", to="now-1h"), now=NOW)


def test_time_range_uses_from_alias() -> None:
    tr = TimeRange.model_validate({"from": "now-6h", "to": "now"})
    assert tr.from_ == "now-6h"
    assert tr.model_dump() == {"from": "now-6h", "to": "now"}


def test_to_millis() -> None:
    assert to_millis(datetime(2024, 3, 13, 14, 35, 27, 500_000, tzinfo=UTC)) == 1710340527500
