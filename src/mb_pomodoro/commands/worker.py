"""Background timer worker CLI command."""

import logging
import os
import time
from typing import Annotated

import typer
from mm_clikit import write_pid_file

from mb_pomodoro.app_context import use_context
from mb_pomodoro.db import IntervalStatus
from mb_pomodoro.notification import send_notification

logger = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL_SEC = 10


def worker(
    ctx: typer.Context,
    interval_id: Annotated[int, typer.Argument(help="Interval ID to track.")],
) -> None:
    """Run background timer worker. Not intended for manual use."""
    app = use_context(ctx)
    cfg = app.cfg

    logger.info("Worker started for interval id=%s pid=%d", interval_id, os.getpid())
    try:
        write_pid_file(cfg.timer_worker_pid_path)
        try:
            last_heartbeat = 0  # Forces immediate heartbeat on first iteration
            while True:
                row = app.db.fetch_interval(interval_id)
                if row is None or row.status != IntervalStatus.RUNNING:
                    logger.info("Worker exiting: interval id=%s no longer running", interval_id)
                    break

                now = int(time.time())

                # Periodic heartbeat for crash recovery
                if now - last_heartbeat >= _HEARTBEAT_INTERVAL_SEC:
                    app.db.update_heartbeat(interval_id, now)
                    last_heartbeat = now

                effective_worked = row.effective_worked(now)
                if effective_worked >= row.duration_sec:
                    if app.db.finish_interval(interval_id, row.duration_sec, now):
                        logger.info("Interval finished id=%s duration=%ds", interval_id, row.duration_sec)
                        resolution = send_notification()
                        if resolution:
                            app.db.resolve_interval(interval_id, resolution, int(time.time()))
                            logger.info("Interval resolved id=%s resolution=%s", interval_id, resolution)
                    else:
                        logger.warning("Finish race lost for interval id=%s", interval_id)
                    break

                time.sleep(1)
        finally:
            cfg.timer_worker_pid_path.unlink(missing_ok=True)
            logger.debug("Worker cleanup: removed PID file")
    except Exception:
        logger.exception("Worker crashed for interval id=%s", interval_id)
        raise
