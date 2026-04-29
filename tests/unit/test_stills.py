"""time_range 파싱."""

from __future__ import annotations

from javstory.library.stills.time_range import parse_time_range


def test_parse_time_range_basic() -> None:
    a, b = parse_time_range("00:03:43.05 ~ 00:31:53.6")
    assert a is not None and b is not None
    assert a < b


def test_parse_time_range_swaps_if_reversed() -> None:
    a, b = parse_time_range("00:10:00 ~ 00:05:00")
    assert a is not None and b is not None
    assert a <= b


def test_parse_time_range_invalid() -> None:
    assert parse_time_range("") == (None, None)
    assert parse_time_range(None) == (None, None)
