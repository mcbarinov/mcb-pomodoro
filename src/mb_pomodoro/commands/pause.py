"""Pause the active Pomodoro interval."""

import typer

from mb_pomodoro.app_context import use_context


def pause(ctx: typer.Context) -> None:
    """Pause the active Pomodoro interval."""
    app = use_context(ctx)
    result = app.pomodoro.pause()
    app.out.print_paused(result)
