"""Tests for time_utils module."""

import re
from datetime import UTC, datetime

import pytest

from mb_pomodoro.time_utils import format_datetime, format_mmss, parse_duration, start_of_day


class TestParseDuration:
    """Tests for parse_duration function."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("25", 1500),
            ("1", 60),
            ("0", 0),
            ("120", 7200),
            ("25m", 1500),
            ("0m", 0),
            ("90s", 90),
            ("0s", 0),
            ("120s", 120),
            ("10m30s", 630),
            ("0m0s", 0),
            ("5m0s", 300),
            ("0m30s", 30),
            ("60m60s", 3660),
        ],
    )
    def test_valid(self, raw: str, expected: int):
        """Valid duration strings are parsed correctly."""
        assert parse_duration(raw) == expected

    @pytest.mark.parametrize("raw", ["", "abc", "-5", "2.5", "5m30", "m", "s", "ms", "30s10m", "10 m", "1h"])
    def test_invalid(self, raw: str):
        """Invalid duration strings return None."""
        assert parse_duration(raw) is None


class TestFormatMmss:
    """Tests for format_mmss function."""

    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (0, "00:00"),
            (45, "00:45"),
            (60, "01:00"),
            (1500, "25:00"),
            (630, "10:30"),
            (3661, "61:01"),
            (1, "00:01"),
        ],
    )
    def test_format(self, seconds: int, expected: str):
        """Seconds are formatted as MM:SS."""
        assert format_mmss(seconds) == expected


class TestFormatDatetime:
    """Tests for format_datetime function."""

    @pytest.mark.parametrize("ts", [0, 1_700_000_000, 1_234_567_890])
    def test_format(self, ts: int):
        """Output matches independently computed strftime result."""
        expected = datetime.fromtimestamp(ts, tz=UTC).astimezone().strftime("%Y-%m-%d %H:%M")
        assert format_datetime(ts) == expected

    def test_format_pattern(self):
        """Output matches YYYY-MM-DD HH:MM pattern."""
        result = format_datetime(1_700_000_000)
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", result)


class TestStartOfDay:
    """Tests for start_of_day function."""

    @pytest.mark.parametrize("ts", [0, 1_700_000_000, 1_234_567_890, 1_700_100_000])
    def test_result_is_midnight(self, ts: int):
        """Result converts back to midnight (h/m/s == 0)."""
        result = start_of_day(ts)
        dt = datetime.fromtimestamp(result, tz=UTC).astimezone()
        assert dt.hour == 0
        assert dt.minute == 0
        assert dt.second == 0

    @pytest.mark.parametrize("ts", [0, 1_700_000_000, 1_234_567_890, 1_700_100_000])
    def test_result_not_after_input(self, ts: int):
        """Start of day is never after the input timestamp."""
        assert start_of_day(ts) <= ts

    @pytest.mark.parametrize("ts", [0, 1_700_000_000, 1_234_567_890, 1_700_100_000])
    def test_idempotent(self, ts: int):
        """Applying start_of_day twice gives the same result."""
        assert start_of_day(start_of_day(ts)) == start_of_day(ts)

    def test_same_day_same_result(self):
        """Two timestamps hours apart on the same day produce the same start_of_day."""
        ts1 = 1_700_000_000
        ts2 = ts1 + 3600  # 1 hour later
        assert start_of_day(ts1) == start_of_day(ts2)

    def test_different_days_different_result(self):
        """Timestamps 24h apart produce different start_of_day values."""
        ts1 = 1_700_000_000
        ts2 = ts1 + 86400  # 24 hours later
        assert start_of_day(ts1) != start_of_day(ts2)
