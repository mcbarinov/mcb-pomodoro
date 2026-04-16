"""Core business logic."""

import logging
import time

from mm_clikit import CliError, is_process_running

from mb_pomodoro.config import Config
from mb_pomodoro.core.db import ACTIVE_STATUSES, Db, IntervalRow, IntervalStatus
from mb_pomodoro.core.results import (
    CancelResult,
    DailyHistoryItem,
    DailyHistoryResult,
    DeleteResult,
    FinishResult,
    HistoryItem,
    HistoryResult,
    PauseResult,
    ReResolveResult,
    RestartResult,
    ResumeResult,
    StartResult,
    StatusActiveResult,
    StatusInactiveResult,
)
from mb_pomodoro.time_utils import parse_duration

logger = logging.getLogger(__name__)

# Grace period for worker startup: covers Python interpreter launch, imports,
# config loading, and first heartbeat write. Skips recovery for fresh intervals
# where the worker may not have written its PID file yet.
_STARTUP_GRACE_SEC = 15


class Service:
    """Main application service."""

    def __init__(self, db: Db, cfg: Config) -> None:
        """Initialize with database and configuration."""
        self._db = db
        self._cfg = cfg

    def start(self, duration: str | None = None) -> StartResult:
        """Start a new work interval.

        Args:
            duration: Duration string (e.g. '25', '25m', '90s', '10m30s'). Falls back to config default.

        Returns:
            Start result with interval ID, duration, and start time.

        Raises:
            CliError: On invalid duration, active interval exists, or concurrent race.

        """
        if duration is None:
            duration = self._cfg.default_duration
        duration_sec = parse_duration(duration)
        if duration_sec is None or duration_sec <= 0:
            raise CliError(f"Invalid duration: {duration}. Examples: 25, 25m, 90s, 10m30s.", "INVALID_DURATION")

        latest = self._db.fetch_latest_interval()
        if latest and latest.status in ACTIVE_STATUSES:
            raise CliError(
                f"An active interval already exists. Latest interval: id={latest.id}, status={latest.status}.",
                "ACTIVE_INTERVAL_EXISTS",
            )

        now = int(time.time())
        interval_id = self._db.insert_interval(duration_sec, now)
        if interval_id is None:
            raise CliError("Another interval was started concurrently.", "ACTIVE_INTERVAL_EXISTS")

        logger.info("Interval started id=%d duration=%ds", interval_id, duration_sec)
        return StartResult(interval_id=interval_id, duration_sec=duration_sec, started_at=now)

    def pause(self) -> PauseResult:
        """Pause the running interval.

        Returns:
            Pause result with worked and remaining time.

        Raises:
            CliError: If no running interval or concurrent modification.

        """
        row = self._db.fetch_latest_interval()
        if row is None or row.status != IntervalStatus.RUNNING or row.run_started_at is None:
            msg = "No running interval to pause."
            if row is not None:
                msg = f"{msg} Latest interval: id={row.id}, status={row.status}."
            raise CliError(msg, "NOT_RUNNING")

        now = int(time.time())
        new_worked = row.effective_worked(now)

        if not self._db.pause_interval(row.id, new_worked, now):
            logger.warning("Pause rejected: concurrent modification id=%s", row.id)
            raise CliError("Interval was modified concurrently.", "CONCURRENT_MODIFICATION")

        remaining = row.duration_sec - new_worked
        logger.info("Interval paused id=%s worked=%ds remaining=%ds", row.id, new_worked, remaining)
        return PauseResult(interval_id=row.id, worked_sec=new_worked, remaining_sec=remaining)

    def resume(self) -> ResumeResult:
        """Resume a paused or interrupted interval.

        Returns:
            Resume result with worked and remaining time.

        Raises:
            CliError: If no resumable interval or concurrent modification.

        """
        row = self._db.fetch_latest_interval()
        if row is None or row.status not in (IntervalStatus.PAUSED, IntervalStatus.INTERRUPTED):
            msg = "No paused or interrupted interval to resume."
            if row is not None:
                msg = f"{msg} Latest interval: id={row.id}, status={row.status}."
            raise CliError(msg, "NOT_RESUMABLE")

        now = int(time.time())
        if not self._db.resume_interval(row.id, now):
            logger.warning("Resume rejected: concurrent modification id=%s", row.id)
            raise CliError("Interval was modified concurrently.", "CONCURRENT_MODIFICATION")

        remaining = row.duration_sec - row.worked_sec
        logger.info("Interval resumed id=%s worked=%ds remaining=%ds", row.id, row.worked_sec, remaining)
        return ResumeResult(interval_id=row.id, worked_sec=row.worked_sec, remaining_sec=remaining)

    def cancel(self) -> CancelResult:
        """Cancel the active interval.

        Returns:
            Cancel result with worked time.

        Raises:
            CliError: If no active interval or concurrent modification.

        """
        row = self._db.fetch_latest_interval()
        if row is None or row.status not in (IntervalStatus.RUNNING, IntervalStatus.PAUSED, IntervalStatus.INTERRUPTED):
            msg = "No active interval to cancel."
            if row is not None:
                msg = f"{msg} Latest interval: id={row.id}, status={row.status}."
            raise CliError(msg, "NO_ACTIVE_INTERVAL")

        now = int(time.time())
        new_worked = row.effective_worked(now)

        if not self._db.cancel_interval(row.id, new_worked, now):
            logger.warning("Cancel rejected: concurrent modification id=%s", row.id)
            raise CliError("Interval was modified concurrently.", "CONCURRENT_MODIFICATION")

        logger.info("Interval cancelled id=%s worked=%ds", row.id, new_worked)
        return CancelResult(interval_id=row.id, worked_sec=new_worked)

    def finish(self, resolution: str) -> FinishResult:
        """Resolve a finished interval as completed or abandoned.

        Args:
            resolution: 'completed' or 'abandoned'.

        Returns:
            Finish result with resolution and worked time.

        Raises:
            CliError: On invalid resolution, no finished interval, or concurrent modification.

        """
        if resolution not in (IntervalStatus.COMPLETED, IntervalStatus.ABANDONED):
            raise CliError("Resolution must be 'completed' or 'abandoned'.", "INVALID_RESOLUTION")

        resolved_status = IntervalStatus(resolution)

        row = self._db.fetch_latest_interval()
        if row is None or row.status != IntervalStatus.FINISHED:
            msg = "No finished interval to resolve."
            if row is not None:
                msg = f"{msg} Latest interval: id={row.id}, status={row.status}."
            raise CliError(msg, "NOT_FINISHED")

        now = int(time.time())
        if not self._db.resolve_interval(row.id, resolved_status, now):
            logger.warning("Finish rejected: concurrent modification id=%s", row.id)
            raise CliError("Interval was modified concurrently.", "CONCURRENT_MODIFICATION")

        logger.info("Interval resolved id=%s resolution=%s", row.id, resolved_status)
        return FinishResult(interval_id=row.id, resolution=resolved_status, worked_sec=row.worked_sec)

    def delete_interval(self, interval_id: int) -> DeleteResult:
        """Permanently delete an interval.

        Args:
            interval_id: Interval ID to delete.

        Returns:
            Delete result with deleted interval metadata.

        Raises:
            CliError: If interval not found.

        """
        row = self._db.fetch_interval(interval_id)
        if row is None:
            raise CliError(f"No interval with id {interval_id}.", "INTERVAL_NOT_FOUND")

        now = int(time.time())
        worked = row.effective_worked(now)
        # No need to kill the worker: it polls fetch_interval() every ~1s,
        # gets None for the deleted row, and exits cleanly. All worker writes
        # (heartbeat, finish) target a specific id+status, so they no-op on a missing row.
        self._db.delete_interval(row.id)
        logger.info("Interval deleted id=%s status=%s worked=%ds", row.id, row.status, worked)
        return DeleteResult(
            interval_id=row.id,
            status=row.status,
            duration_sec=row.duration_sec,
            worked_sec=worked,
            started_at=row.started_at,
        )

    def restart(self) -> RestartResult:
        """Reset a running interval's counters in place, keeping the same id.

        Only valid when status is ``running``. The existing worker sees the new values
        on its next poll and keeps counting down -- no respawn, no PID churn.

        Raises:
            CliError: If there is no running interval or a concurrent race lost.

        """
        row = self._db.fetch_latest_interval()
        if row is None or row.status != IntervalStatus.RUNNING:
            msg = "No running interval to restart."
            if row is not None:
                msg = f"{msg} Latest interval: id={row.id}, status={row.status}."
            raise CliError(msg, "NOT_RUNNING")

        now = int(time.time())
        if not self._db.restart_interval(row.id, now):
            logger.warning("Restart rejected: concurrent modification id=%s", row.id)
            raise CliError("Interval was modified concurrently.", "CONCURRENT_MODIFICATION")

        logger.info("Interval restarted id=%s", row.id)
        return RestartResult(interval_id=row.id, duration_sec=row.duration_sec, started_at=now)

    def re_resolve(self, interval_id: int, resolution: str) -> ReResolveResult:
        """Change the resolution of a completed or abandoned interval.

        Args:
            interval_id: Interval ID to re-resolve.
            resolution: New resolution: 'completed' or 'abandoned'.

        Returns:
            Re-resolve result with old and new resolution.

        Raises:
            CliError: On invalid resolution, wrong status, same status, or concurrent modification.

        """
        if resolution not in (IntervalStatus.COMPLETED, IntervalStatus.ABANDONED):
            raise CliError("Resolution must be 'completed' or 'abandoned'.", "INVALID_RESOLUTION")
        new_status = IntervalStatus(resolution)

        row = self._db.fetch_interval(interval_id)
        if row is None:
            raise CliError(f"No interval with id {interval_id}.", "INTERVAL_NOT_FOUND")
        if row.status not in (IntervalStatus.COMPLETED, IntervalStatus.ABANDONED):
            raise CliError(
                f"Interval {interval_id} has status '{row.status}'; only completed or abandoned intervals can be re-resolved.",
                "NOT_RE_RESOLVABLE",
            )
        if row.status == new_status:
            raise CliError(f"Interval {interval_id} is already {resolution}.", "ALREADY_RESOLVED")

        now = int(time.time())
        if not self._db.re_resolve_interval(row.id, new_status, now):
            logger.warning("Re-resolve rejected: concurrent modification id=%s", row.id)
            raise CliError("Interval was modified concurrently.", "CONCURRENT_MODIFICATION")

        logger.info("Interval re-resolved id=%s from %s to %s", row.id, row.status, new_status)
        return ReResolveResult(
            interval_id=row.id,
            old_resolution=row.status,
            new_resolution=new_status,
            worked_sec=row.worked_sec,
        )

    def get_running_interval(self) -> IntervalRow:
        """Return the currently running interval.

        Raises:
            CliError: If no running interval exists.

        """
        row = self._db.fetch_latest_interval()
        if row is None or row.status != IntervalStatus.RUNNING:
            msg = "No running interval."
            if row is not None:
                msg = f"{msg} Latest interval: id={row.id}, status={row.status}."
            raise CliError(msg, "NOT_RUNNING")
        return row

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

    # --- Recovery ---

    def recover_stale(self) -> None:
        """Detect a running interval with a dead worker and mark it as interrupted."""
        row = self._db.fetch_latest_interval()
        if row is None or row.status != IntervalStatus.RUNNING:
            return

        pid_path = self._cfg.timer_worker_pid_path
        if is_process_running(pid_path, command_contains="mb-pomodoro"):
            return

        # Worker may still be starting -- skip recovery for fresh intervals without a heartbeat
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
