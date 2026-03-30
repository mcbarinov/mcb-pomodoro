"""Permanently delete an accidentally started interval."""

import time
from typing import Annotated

import typer

from mb_pomodoro.app_context import use_context
from mb_pomodoro.pomodoro import PomodoroError
from mb_pomodoro.time_utils import format_mmss


def undo_start(
    ctx: typer.Context,
    *,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompt.")] = False,
) -> None:
    """Permanently delete the active interval, as if it never existed."""
    app = use_context(ctx)

    if not yes:
        row = app.pomodoro.get_active_interval()
        if row is None:
            raise PomodoroError("NOT_RUNNING", "No running interval to undo.")

        if app.out.json_mode:
            raise PomodoroError("CONFIRMATION_REQUIRED", "Use --yes flag to confirm deletion in JSON mode.")

        now = int(time.time())
        elapsed = now - row.started_at
        worked = row.effective_worked(now)
        duration = format_mmss(row.duration_sec)
        typer.echo(
            f"Active interval: {duration}, {row.status}, worked {format_mmss(worked)} ({format_mmss(elapsed)} since start)."
        )
        answer = input("Type 'yes' to permanently delete this interval: ")
        if answer != "yes":
            raise PomodoroError("NOT_CONFIRMED", "Aborted: interval was not deleted.")

    result = app.pomodoro.undo_start()
    app.out.print_undo_start(result)
