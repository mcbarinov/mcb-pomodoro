"""Cancel the active Pomodoro interval."""

import typer

from mb_pomodoro.app_context import use_context


def cancel(ctx: typer.Context) -> None:
    """Cancel the active Pomodoro interval."""
    app = use_context(ctx)
    result = app.pomodoro.cancel()
    app.out.print_cancelled(result)
