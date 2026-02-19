"""Structured output for CLI and JSON modes."""

# ruff: noqa: T201 — this module is the output layer; print() is its sole mechanism for producing CLI output.

import json
import logging
import sys
from dataclasses import asdict, dataclass
from typing import NoReturn

import typer

from mb_pomodoro.db import IntervalRow, IntervalStatus
from mb_pomodoro.time_utils import format_datetime, format_mmss

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StartResult:
    """Result of a successful interval start."""

    interval_id: str
    duration_sec: int
    started_at: int


@dataclass(frozen=True, slots=True)
class PauseResult:
    """Result of a successful interval pause."""

    interval_id: str
    worked_sec: int
    remaining_sec: int


@dataclass(frozen=True, slots=True)
class ResumeResult:
    """Result of a successful interval resume."""

    interval_id: str
    worked_sec: int
    remaining_sec: int


@dataclass(frozen=True, slots=True)
class CancelResult:
    """Result of a successful interval cancellation."""

    interval_id: str
    worked_sec: int


@dataclass(frozen=True, slots=True)
class FinishResult:
    """Result of resolving a finished interval."""

    interval_id: str
    resolution: IntervalStatus
    worked_sec: int


@dataclass(frozen=True, slots=True)
class StatusActiveResult:
    """Result of a status check when an interval is active."""

    interval_id: str
    status: IntervalStatus
    duration_sec: int
    worked_sec: int
    remaining_sec: int
    started_at: int
    today_completed: int


@dataclass(frozen=True, slots=True)
class StatusInactiveResult:
    """Result of a status check when no interval is active."""

    today_completed: int


@dataclass(frozen=True, slots=True)
class HistoryItem:
    """Single interval entry in history output."""

    interval_id: str
    status: IntervalStatus
    duration_sec: int
    worked_sec: int
    started_at: int


@dataclass(frozen=True, slots=True)
class HistoryResult:
    """Result of a history query."""

    intervals: list[HistoryItem]


@dataclass(frozen=True, slots=True)
class DailyHistoryItem:
    """Single day entry in daily history output."""

    date: str
    completed: int


@dataclass(frozen=True, slots=True)
class DailyHistoryResult:
    """Result of a daily history query."""

    days: list[DailyHistoryItem]


@dataclass(frozen=True, slots=True)
class TrayStartResult:
    """Result of launching the tray in background."""

    pid: int


@dataclass(frozen=True, slots=True)
class TrayStopResult:
    """Result of stopping the tray."""

    pid: int


class Output:
    """Handles all CLI output in JSON or human-readable format."""

    def __init__(self, *, json_mode: bool) -> None:
        """Initialize output handler.

        Args:
            json_mode: If True, output JSON envelopes; otherwise human-readable text.

        """
        self._json_mode = json_mode

    def _success(self, data: dict[str, object], message: str) -> None:
        """Print a success result in JSON or human-readable format."""
        if self._json_mode:
            print(json.dumps({"ok": True, "data": data}))
        else:
            print(message)

    def print_interval_error_and_exit(self, code: str, message: str, row: IntervalRow | None) -> NoReturn:
        """Print an interval status error with context and exit."""
        if row is not None:
            message = f"{message} Latest interval: id={row.id}, status={row.status}."
        self.print_error_and_exit(code, message)

    def print_error_and_exit(self, code: str, message: str) -> NoReturn:
        """Print an error in JSON or human-readable format and exit with code 1."""
        logger.error("Command error: [%s] %s", code, message)
        if self._json_mode:
            print(json.dumps({"ok": False, "error": code, "message": message}))
        else:
            print(f"Error: {message}", file=sys.stderr)
        raise typer.Exit(code=1)

    def print_started(self, result: StartResult) -> None:
        """Print interval start confirmation."""
        self._success(asdict(result), f"Pomodoro started: {format_mmss(result.duration_sec)}.")

    def print_paused(self, result: PauseResult) -> None:
        """Print interval pause confirmation."""
        self._success(
            asdict(result),
            f"Paused. Worked: {format_mmss(result.worked_sec)}, left: {format_mmss(result.remaining_sec)}.",
        )

    def print_resumed(self, result: ResumeResult) -> None:
        """Print interval resume confirmation."""
        self._success(
            asdict(result),
            f"Resumed. Worked: {format_mmss(result.worked_sec)}, left: {format_mmss(result.remaining_sec)}.",
        )

    def print_cancelled(self, result: CancelResult) -> None:
        """Print interval cancellation confirmation."""
        self._success(asdict(result), f"Cancelled. Worked: {format_mmss(result.worked_sec)}.")

    def print_finished(self, result: FinishResult) -> None:
        """Print interval resolution confirmation."""
        self._success(asdict(result), f"Interval marked as {result.resolution}. Worked: {format_mmss(result.worked_sec)}.")

    def print_history(self, result: HistoryResult) -> None:
        """Print interval history as a table or JSON."""
        if self._json_mode:
            print(json.dumps({"ok": True, "data": {"intervals": [asdict(item) for item in result.intervals]}}))
            return

        if not result.intervals:
            print("No intervals found.")
            return

        print(f"{'Date':<16}  {'Duration':>8}  {'Worked':>8}  {'Status':<9}")
        print(f"{'-' * 16}  {'-' * 8}  {'-' * 8}  {'-' * 9}")
        for item in result.intervals:
            print(
                f"{format_datetime(item.started_at):<16}  {format_mmss(item.duration_sec):>8}  "
                f"{format_mmss(item.worked_sec):>8}  {item.status:<9}"
            )

    def print_daily_history(self, result: DailyHistoryResult) -> None:
        """Print daily completed counts as a table or JSON."""
        if self._json_mode:
            print(json.dumps({"ok": True, "data": {"days": [asdict(item) for item in result.days]}}))
            return

        if not result.days:
            print("No completed intervals found.")
            return

        print(f"{'Date':<10}  {'Completed':>9}")
        print(f"{'-' * 10}  {'-' * 9}")
        for item in result.days:
            print(f"{item.date:<10}  {item.completed:>9}")

    def print_tray_started(self, result: TrayStartResult) -> None:
        """Print tray launch confirmation."""
        self._success(asdict(result), f"Tray started (pid {result.pid}).")

    def print_tray_stopped(self, result: TrayStopResult) -> None:
        """Print tray stop confirmation."""
        self._success(asdict(result), f"Tray stopped (pid {result.pid}).")

    def print_status(self, result: StatusActiveResult | StatusInactiveResult) -> None:
        """Print current timer status."""
        if isinstance(result, StatusInactiveResult):
            self._success(
                {"active": False, "today_completed": result.today_completed},
                f"No active interval. Today: {result.today_completed} completed.",
            )
            return

        self._success(
            {"active": True, **asdict(result)},
            f"Status:   {result.status}\n"
            f"Duration: {format_mmss(result.duration_sec)}\n"
            f"Worked:   {format_mmss(result.worked_sec)}\n"
            f"Left:     {format_mmss(result.remaining_sec)}\n"
            f"Today:    {result.today_completed} completed",
        )
