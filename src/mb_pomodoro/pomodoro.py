"""High-level API for pomodoro timer operations."""

import logging
import time

from mm_clikit import CliError, is_process_running

from mb_pomodoro.config import Config
from mb_pomodoro.db import ACTIVE_STATUSES, Db, IntervalRow, IntervalStatus
from mb_pomodoro.output import (
    CancelResult,
    DailyHistoryItem,
    DailyHistoryResult,
    FinishResult,
    HistoryItem,
    HistoryResult,
    PauseResult,
    ResumeResult,
    StartResult,
    StatusActiveResult,
    StatusInactiveResult,
    UndoStartResult,
)
from mb_pomodoro.time_utils import parse_duration

logger = logging.getLogger(__name__)

# Grace period for worker startup: covers Python interpreter launch, imports,
# config loading, and first heartbeat write. Skips recovery for fresh intervals
# where the worker may not have written its PID file yet.
_STARTUP_GRACE_SEC = 15


class PomodoroError(CliError):
    """Application-level error with machine-readable code.

    Caught automatically by TyperPlus error handler — formats JSON/display and exits.
    """

    def __init__(self, code: str, message: str) -> None:
        """Initialize with error code and human-readable message.

        Args:
            code: Machine-readable error code (e.g. 'NOT_RUNNING').
            message: Human-readable error description.

        """
        super().__init__(message, error_code=code)


class Pomodoro:
    """High-level API for pomodoro timer operations, wrapping DB and time logic."""

    def __init__(self, db: Db, cfg: Config) -> None:
        """Initialize the pomodoro service.

        Args:
            db: Database access object.
            cfg: Application configuration.

        """
        self._db = db
        self._cfg = cfg

    def start(self, duration: str | None = None) -> StartResult:
        """Start a new work interval.

        Args:
            duration: Duration string (e.g. '25', '25m', '90s', '10m30s'). Falls back to config default.

        Returns:
            Start result with interval ID, duration, and start time.

        Raises:
            PomodoroError: On invalid duration, active interval exists, or concurrent race.

        """
        if duration is None:
            duration = self._cfg.default_duration
        duration_sec = parse_duration(duration)
        if duration_sec is None or duration_sec <= 0:
            raise PomodoroError("INVALID_DURATION", f"Invalid duration: {duration}. Examples: 25, 25m, 90s, 10m30s.")

        latest = self._db.fetch_latest_interval()
        if latest and latest.status in ACTIVE_STATUSES:
            raise PomodoroError(
                "ACTIVE_INTERVAL_EXISTS",
                f"An active interval already exists. Latest interval: id={latest.id}, status={latest.status}.",
            )

        now = int(time.time())
        interval_id = self._db.insert_interval(duration_sec, now)
        if interval_id is None:
            raise PomodoroError("ACTIVE_INTERVAL_EXISTS", "Another interval was started concurrently.")

        logger.info("Interval started id=%d duration=%ds", interval_id, duration_sec)
        return StartResult(interval_id=interval_id, duration_sec=duration_sec, started_at=now)

    def pause(self) -> PauseResult:
        """Pause the running interval.

        Returns:
            Pause result with worked and remaining time.

        Raises:
            PomodoroError: If no running interval or concurrent modification.

        """
        row = self._db.fetch_latest_interval()
        if row is None or row.status != IntervalStatus.RUNNING or row.run_started_at is None:
            msg = "No running interval to pause."
            if row is not None:
                msg = f"{msg} Latest interval: id={row.id}, status={row.status}."
            raise PomodoroError("NOT_RUNNING", msg)

        now = int(time.time())
        new_worked = row.effective_worked(now)

        if not self._db.pause_interval(row.id, new_worked, now):
            logger.warning("Pause rejected: concurrent modification id=%s", row.id)
            raise PomodoroError("CONCURRENT_MODIFICATION", "Interval was modified concurrently.")

        remaining = row.duration_sec - new_worked
        logger.info("Interval paused id=%s worked=%ds remaining=%ds", row.id, new_worked, remaining)
        return PauseResult(interval_id=row.id, worked_sec=new_worked, remaining_sec=remaining)

    def resume(self) -> ResumeResult:
        """Resume a paused or interrupted interval.

        Returns:
            Resume result with worked and remaining time.

        Raises:
            PomodoroError: If no resumable interval or concurrent modification.

        """
        row = self._db.fetch_latest_interval()
        if row is None or row.status not in (IntervalStatus.PAUSED, IntervalStatus.INTERRUPTED):
            msg = "No paused or interrupted interval to resume."
            if row is not None:
                msg = f"{msg} Latest interval: id={row.id}, status={row.status}."
            raise PomodoroError("NOT_RESUMABLE", msg)

        now = int(time.time())
        if not self._db.resume_interval(row.id, now):
            logger.warning("Resume rejected: concurrent modification id=%s", row.id)
            raise PomodoroError("CONCURRENT_MODIFICATION", "Interval was modified concurrently.")

        remaining = row.duration_sec - row.worked_sec
        logger.info("Interval resumed id=%s worked=%ds remaining=%ds", row.id, row.worked_sec, remaining)
        return ResumeResult(interval_id=row.id, worked_sec=row.worked_sec, remaining_sec=remaining)

    def cancel(self) -> CancelResult:
        """Cancel the active interval.

        Returns:
            Cancel result with worked time.

        Raises:
            PomodoroError: If no active interval or concurrent modification.

        """
        row = self._db.fetch_latest_interval()
        if row is None or row.status not in (IntervalStatus.RUNNING, IntervalStatus.PAUSED, IntervalStatus.INTERRUPTED):
            msg = "No active interval to cancel."
            if row is not None:
                msg = f"{msg} Latest interval: id={row.id}, status={row.status}."
            raise PomodoroError("NO_ACTIVE_INTERVAL", msg)

        now = int(time.time())
        new_worked = row.effective_worked(now)

        if not self._db.cancel_interval(row.id, new_worked, now):
            logger.warning("Cancel rejected: concurrent modification id=%s", row.id)
            raise PomodoroError("CONCURRENT_MODIFICATION", "Interval was modified concurrently.")

        logger.info("Interval cancelled id=%s worked=%ds", row.id, new_worked)
        return CancelResult(interval_id=row.id, worked_sec=new_worked)

    def finish(self, resolution: str) -> FinishResult:
        """Resolve a finished interval as completed or abandoned.

        Args:
            resolution: 'completed' or 'abandoned'.

        Returns:
            Finish result with resolution and worked time.

        Raises:
            PomodoroError: On invalid resolution, no finished interval, or concurrent modification.

        """
        if resolution not in (IntervalStatus.COMPLETED, IntervalStatus.ABANDONED):
            raise PomodoroError("INVALID_RESOLUTION", "Resolution must be 'completed' or 'abandoned'.")

        resolved_status = IntervalStatus(resolution)

        row = self._db.fetch_latest_interval()
        if row is None or row.status != IntervalStatus.FINISHED:
            msg = "No finished interval to resolve."
            if row is not None:
                msg = f"{msg} Latest interval: id={row.id}, status={row.status}."
            raise PomodoroError("NOT_FINISHED", msg)

        now = int(time.time())
        if not self._db.resolve_interval(row.id, resolved_status, now):
            logger.warning("Finish rejected: concurrent modification id=%s", row.id)
            raise PomodoroError("CONCURRENT_MODIFICATION", "Interval was modified concurrently.")

        logger.info("Interval resolved id=%s resolution=%s", row.id, resolved_status)
        return FinishResult(interval_id=row.id, resolution=resolved_status, worked_sec=row.worked_sec)

    def undo_start(self) -> UndoStartResult:
        """Permanently delete the active running interval.

        Returns:
            Undo-start result with deleted interval ID.

        Raises:
            PomodoroError: If no running interval.

        """
        row = self._db.fetch_latest_interval()
        if row is None or row.status != IntervalStatus.RUNNING:
            msg = "No running interval to undo."
            if row is not None:
                msg = f"{msg} Latest interval: id={row.id}, status={row.status}."
            raise PomodoroError("NOT_RUNNING", msg)

        self._db.delete_interval(row.id)
        logger.info("Interval deleted (undo-start) id=%s worked=%ds", row.id, row.effective_worked(int(time.time())))
        return UndoStartResult(interval_id=row.id)

    def get_active_interval(self) -> IntervalRow | None:
        """Return the latest active interval, or None if no interval is active."""
        row = self._db.fetch_latest_interval()
        if row is not None and row.status in ACTIVE_STATUSES:
            return row
        return None

    def status(self) -> StatusActiveResult | StatusInactiveResult:
        """Get current timer status.

        Returns:
            Active or inactive status result.

        """
        now = int(time.time())
        row = self._db.fetch_latest_interval()
        today_completed = self._db.count_today_completed(now)

        if row is None or row.status not in ACTIVE_STATUSES:
            return StatusInactiveResult(today_completed=today_completed)

        effective_worked = row.effective_worked(now)
        remaining = max(0, row.duration_sec - effective_worked)
        return StatusActiveResult(
            interval_id=row.id,
            status=row.status,
            duration_sec=row.duration_sec,
            worked_sec=effective_worked,
            remaining_sec=remaining,
            started_at=row.started_at,
            today_completed=today_completed,
        )

    def history(self, limit: int) -> HistoryResult:
        """Get recent interval history.

        Args:
            limit: Maximum number of intervals to return.

        Returns:
            History result with interval items.

        """
        interval_rows = self._db.fetch_history(limit)
        now = int(time.time())
        items = [
            HistoryItem(
                interval_id=row.id,
                status=row.status,
                duration_sec=row.duration_sec,
                worked_sec=row.effective_worked(now),
                started_at=row.started_at,
            )
            for row in interval_rows
        ]
        return HistoryResult(intervals=items)

    def daily_history(self, limit: int) -> DailyHistoryResult:
        """Get daily completed counts.

        Args:
            limit: Maximum number of days to return.

        Returns:
            Daily history result with day items.

        """
        rows = self._db.fetch_daily_completed(limit)
        items = [DailyHistoryItem(date=date, completed=count) for date, count in rows]
        return DailyHistoryResult(days=items)

    # --- Worker methods ---

    def fetch_interval(self, interval_id: int) -> IntervalRow | None:
        """Fetch an interval by ID. Used by the timer worker.

        Args:
            interval_id: Interval row ID.

        """
        return self._db.fetch_interval(interval_id)

    def finish_running(self, interval_id: int, duration_sec: int, now: int) -> bool:
        """Mark a running interval as finished. Used by the timer worker.

        Args:
            interval_id: Interval row ID.
            duration_sec: Full duration for worked_sec.
            now: Current unix timestamp.

        """
        return self._db.finish_interval(interval_id, duration_sec, now)

    def resolve(self, interval_id: int, resolution: IntervalStatus, now: int) -> bool:
        """Resolve a finished interval. Used by the timer worker after notification.

        Args:
            interval_id: Interval row ID.
            resolution: COMPLETED or ABANDONED.
            now: Current unix timestamp.

        """
        return self._db.resolve_interval(interval_id, resolution, now)

    def update_heartbeat(self, interval_id: int, now: int) -> None:
        """Update heartbeat timestamp for crash recovery. Used by the timer worker.

        Args:
            interval_id: Interval row ID.
            now: Current unix timestamp.

        """
        self._db.update_heartbeat(interval_id, now)

    # --- Tray methods ---

    def fetch_latest_interval(self) -> IntervalRow | None:
        """Return the most recently started interval. Used by the tray for display."""
        return self._db.fetch_latest_interval()

    def count_today_completed(self, now: int) -> int:
        """Count intervals completed today. Used by the tray for display.

        Args:
            now: Current unix timestamp.

        """
        return self._db.count_today_completed(now)

    # --- Recovery ---

    def recover_stale(self) -> None:
        """Detect a running interval with a dead worker and mark it as interrupted."""
        row = self._db.fetch_latest_interval()
        if row is None or row.status != IntervalStatus.RUNNING:
            return

        pid_path = self._cfg.timer_worker_pid_path
        if is_process_running(pid_path, command_contains="mb-pomodoro"):
            return

        # Worker may still be starting — skip recovery for fresh intervals without a heartbeat
        now = int(time.time())
        if row.heartbeat_at is None and row.run_started_at is not None and now - row.run_started_at < _STARTUP_GRACE_SEC:
            logger.debug(
                "Skipping recovery for fresh interval id=%s (age=%ds): worker may still be starting",
                row.id,
                now - row.run_started_at,
            )
            return

        self._db.recover_running_interval(row.id, now)
        logger.warning("Recovered stale interval id=%s: marked as interrupted", row.id)

        pid_path.unlink(missing_ok=True)
