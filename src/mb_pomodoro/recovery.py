"""Stale interval recovery after crashes or restarts."""

import logging
import time
from pathlib import Path

from mm_clikit import is_process_running

from mb_pomodoro.db import Db, IntervalStatus

logger = logging.getLogger(__name__)

# Grace period for worker startup: covers Python interpreter launch, imports,
# config loading, and first heartbeat write. Skips recovery for fresh intervals
# where the worker may not have written its PID file yet.
_STARTUP_GRACE_SEC = 15


def recover_stale_interval(db: Db, timer_worker_pid_path: Path) -> None:
    """Detect a running interval with a dead worker and mark it as interrupted."""
    row = db.fetch_latest_interval()
    if row is None or row.status != IntervalStatus.RUNNING:
        return

    if is_process_running(timer_worker_pid_path, command_contains="mb-pomodoro"):
        return

    # Worker may still be starting — skip recovery for fresh intervals without a heartbeat
    now = int(time.time())
    if row.heartbeat_at is None and row.run_started_at is not None and now - row.run_started_at < _STARTUP_GRACE_SEC:
        logger.debug(
            "Skipping recovery for fresh interval id=%s (age=%ds): worker may still be starting", row.id, now - row.run_started_at
        )
        return

    db.recover_running_interval(row.id, now)
    logger.warning("Recovered stale interval id=%s: marked as interrupted", row.id)

    # Remove stale PID file
    timer_worker_pid_path.unlink(missing_ok=True)
