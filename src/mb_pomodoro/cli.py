"""CLI entry point for mb-pomodoro."""

import os
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from mb_pomodoro.app_context import AppContext
from mb_pomodoro.commands.cancel import cancel
from mb_pomodoro.commands.finish import finish
from mb_pomodoro.commands.history import history
from mb_pomodoro.commands.pause import pause
from mb_pomodoro.commands.resume import resume
from mb_pomodoro.commands.start import start
from mb_pomodoro.commands.status import status
from mb_pomodoro.commands.tray import tray
from mb_pomodoro.commands.worker import worker
from mb_pomodoro.config import DEFAULT_DATA_DIR, build_config
from mb_pomodoro.db import get_connection
from mb_pomodoro.log import setup_logging
from mb_pomodoro.output import Output
from mb_pomodoro.recovery import recover_stale_interval

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(version("mb-pomodoro"))
        raise typer.Exit


@app.callback()
def main(
    ctx: typer.Context,
    *,
    version: Annotated[
        bool | None, typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version and exit.")
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output results as JSON.")] = False,
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Application data directory (db, pid, log). Allows running multiple instances."),
    ] = None,
) -> None:
    """Pomodoro timer for macOS."""
    _ = version
    if data_dir is not None:
        resolved_dir = data_dir
    elif env_dir := os.environ.get("MB_POMODORO_DATA_DIR"):
        resolved_dir = Path(env_dir)
    else:
        resolved_dir = DEFAULT_DATA_DIR
    cfg = build_config(resolved_dir.resolve())
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(cfg.log_path)
    conn = get_connection(cfg.db_path)
    ctx.call_on_close(conn.close)
    if ctx.invoked_subcommand not in {"worker", "tray"}:
        recover_stale_interval(conn, cfg.timer_worker_pid_path)
    ctx.obj = AppContext(out=Output(json_mode=json_output), conn=conn, cfg=cfg)


app.command()(start)
app.command()(pause)
app.command()(resume)
app.command()(cancel)
app.command()(finish)
app.command()(history)
app.command()(status)
app.command()(tray)
app.command()(worker)
