"""Start a new Pomodoro interval."""

from typing import Annotated

import typer
from mm_clikit import spawn_daemon

from mb_pomodoro.app_context import use_context


def start(
    ctx: typer.Context,
    duration: Annotated[str | None, typer.Argument(help="Duration: 25 (minutes), 25m, 90s, 10m30s. Default from config.")] = None,
) -> None:
    """Start a new Pomodoro interval."""
    app = use_context(ctx)
    result = app.pomodoro.start(duration)
    spawn_daemon([*app.cfg.cli_base_args(), "worker", str(result.interval_id)])
    app.out.print_started(result)
