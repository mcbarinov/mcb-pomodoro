"""Start a new Pomodoro interval."""

import logging
import time
from typing import Annotated

import typer
from mm_clikit import spawn_detached

from mb_pomodoro.app_context import use_context
from mb_pomodoro.db import ACTIVE_STATUSES
from mb_pomodoro.output import StartResult
from mb_pomodoro.time_utils import parse_duration

logger = logging.getLogger(__name__)


def start(
    ctx: typer.Context,
    duration: Annotated[str | None, typer.Argument(help="Duration: 25 (minutes), 25m, 90s, 10m30s. Default from config.")] = None,
) -> None:
    """Start a new Pomodoro interval."""
    app = use_context(ctx)

    if duration is None:
        duration = app.cfg.default_duration
    duration_sec = parse_duration(duration)
    if duration_sec is None or duration_sec <= 0:
        logger.warning("Invalid duration input: %s", duration)
        app.out.print_error_and_exit("INVALID_DURATION", f"Invalid duration: {duration}. Examples: 25, 25m, 90s, 10m30s.")

    # Check for an existing active interval
    latest = app.db.fetch_latest_interval()
    if latest and latest.status in ACTIVE_STATUSES:
        app.out.print_interval_error_and_exit("ACTIVE_INTERVAL_EXISTS", "An active interval already exists.", latest)

    # Create new interval
    now = int(time.time())

    interval_id = app.db.insert_interval(duration_sec, now)
    if interval_id is None:
        logger.warning("Start rejected: concurrent interval creation race")
        app.out.print_error_and_exit("ACTIVE_INTERVAL_EXISTS", "Another interval was started concurrently.")

    spawn_detached([*app.cfg.cli_base_args(), "worker", str(interval_id)])

    logger.info("Interval started id=%d duration=%ds", interval_id, duration_sec)
    app.out.print_started(StartResult(interval_id=interval_id, duration_sec=duration_sec, started_at=now))
