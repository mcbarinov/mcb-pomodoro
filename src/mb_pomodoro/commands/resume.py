"""Resume a paused Pomodoro interval."""

import typer
from mm_clikit import spawn_daemon

from mb_pomodoro.app_context import use_context


def resume(ctx: typer.Context) -> None:
    """Resume a paused Pomodoro interval."""
    app = use_context(ctx)
    result = app.pomodoro.resume()
    spawn_daemon([*app.cfg.cli_base_args(), "worker", str(result.interval_id)])
    app.out.print_resumed(result)
