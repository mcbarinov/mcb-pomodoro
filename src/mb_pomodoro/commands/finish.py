"""Resolve a finished Pomodoro interval as completed or abandoned.

Fallback for when the completion dialog was missed or failed.
"""

from typing import Annotated

import typer

from mb_pomodoro.app_context import use_context

_RESOLUTION_HELP = "Resolution: 'completed' (honest work) or 'abandoned' (did not work)."


def finish(ctx: typer.Context, resolution: Annotated[str, typer.Argument(help=_RESOLUTION_HELP)]) -> None:
    """Resolve a finished interval. Fallback for when the completion dialog was missed or failed."""
    app = use_context(ctx)
    result = app.pomodoro.finish(resolution)
    app.out.print_finished(result)
