"""CLI entry point for mb-pomodoro."""

import os
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer
from mm_clikit import TyperPlus

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
from mb_pomodoro.config import Config
from mb_pomodoro.db import Db
from mb_pomodoro.log import setup_logging
from mb_pomodoro.output import Output
from mb_pomodoro.recovery import recover_stale_interval

app = TyperPlus(package_name="mb-pomodoro")


@app.callback()
def main(
    ctx: typer.Context,
    *,
    json_output: Annotated[bool, typer.Option("--json", help="Output results as JSON.")] = False,
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Application data directory (db, pid, log). Allows running multiple instances."),
    ] = None,
) -> None:
    """Pomodoro timer for macOS."""
    _ = version
    if data_dir is not None:
        resolved_dir: Path | None = data_dir.resolve()
    elif env_dir := os.environ.get("MB_POMODORO_DATA_DIR"):
        resolved_dir = Path(env_dir).resolve()
    else:
        resolved_dir = None
    cfg = Config.build(resolved_dir)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(cfg.log_path)
    db = Db(cfg.db_path)
    ctx.call_on_close(db.close)
    if ctx.invoked_subcommand not in {"worker", "tray"}:
        recover_stale_interval(db, cfg.timer_worker_pid_path)
    ctx.obj = AppContext(out=Output(json_mode=json_output), db=db, cfg=cfg)


app.command()(start)
app.command(aliases=["p"])(pause)
app.command(aliases=["r"])(resume)
app.command()(cancel)
app.command()(finish)
app.command(aliases=["h"])(history)
app.command(aliases=["s"])(status)
app.command()(tray)
app.command()(worker)
