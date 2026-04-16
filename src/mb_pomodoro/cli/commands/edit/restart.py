"""Restart a running interval in place, keeping the same ID."""

import time
from typing import Annotated

import typer
from mm_clikit import CliError

from mb_pomodoro.cli.context import use_context
from mb_pomodoro.time_utils import format_datetime, format_mmss


def restart(
    ctx: typer.Context,
    *,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompt.")] = False,
) -> None:
    """Reset a running interval's counters. Same ID, fresh timer."""
    app = use_context(ctx)

    if not yes:
        row = app.core.service.get_running_interval()

        if app.out.json_mode:
            raise CliError("Use --yes flag to confirm restart in JSON mode.", "CONFIRMATION_REQUIRED")

        now = int(time.time())
        worked = row.effective_worked(now)
        typer.echo(
            f"Interval {row.id}: {format_mmss(row.duration_sec)}, "
            f"worked {format_mmss(worked)}, started {format_datetime(row.started_at)}.",
        )
        answer = input("Type 'yes' to restart this interval: ")
        if answer != "yes":
            raise CliError("Aborted: interval was not restarted.", "NOT_CONFIRMED")

    result = app.core.service.restart()
    app.out.print_restarted(result)
