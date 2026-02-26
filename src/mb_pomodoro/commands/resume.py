"""Resume a paused Pomodoro interval."""

import logging
import time

import typer
from mm_clikit import spawn_detached

from mb_pomodoro.app_context import use_context
from mb_pomodoro.db import IntervalStatus
from mb_pomodoro.output import ResumeResult

logger = logging.getLogger(__name__)


def resume(ctx: typer.Context) -> None:
    """Resume a paused Pomodoro interval."""
    app = use_context(ctx)

    row = app.db.fetch_latest_interval()
    if row is None or row.status not in (IntervalStatus.PAUSED, IntervalStatus.INTERRUPTED):
        app.out.print_interval_error_and_exit("NOT_RESUMABLE", "No paused or interrupted interval to resume.", row)

    now = int(time.time())

    if not app.db.resume_interval(row.id, now):
        logger.warning("Resume rejected: concurrent modification id=%s", row.id)
        app.out.print_error_and_exit("CONCURRENT_MODIFICATION", "Interval was modified concurrently.")

    spawn_detached([*app.cfg.cli_base_args(), "worker", str(row.id)])

    remaining = row.duration_sec - row.worked_sec
    logger.info("Interval resumed id=%s worked=%ds remaining=%ds", row.id, row.worked_sec, remaining)
    app.out.print_resumed(ResumeResult(interval_id=row.id, worked_sec=row.worked_sec, remaining_sec=remaining))
