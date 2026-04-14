"""CLI app definition and initialization."""

from pathlib import Path
from typing import Annotated

import typer
from mm_clikit import CoreContext, TyperPlus, setup_logging

from mb_pomodoro.cli.commands.cancel import cancel
from mb_pomodoro.cli.commands.delete import delete
from mb_pomodoro.cli.commands.finish import finish
from mb_pomodoro.cli.commands.history import history
from mb_pomodoro.cli.commands.pause import pause
from mb_pomodoro.cli.commands.re_resolve import re_resolve
from mb_pomodoro.cli.commands.resume import resume
from mb_pomodoro.cli.commands.start import start
from mb_pomodoro.cli.commands.status import status
from mb_pomodoro.cli.commands.tray import tray
from mb_pomodoro.cli.commands.worker import worker
from mb_pomodoro.cli.output import Output
from mb_pomodoro.config import Config
from mb_pomodoro.core.core import Core

app = TyperPlus(package_name="mb-pomodoro")


@app.callback()
def main(
    ctx: typer.Context,
    *,
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Data directory. Env: MB_POMODORO_DATA_DIR."),
    ] = None,
) -> None:
    """Pomodoro timer for macOS."""
    config = Config.build(data_dir)
    setup_logging("mb_pomodoro", file_path=config.log_path)
    core = Core(config)
    ctx.call_on_close(core.close)
    if ctx.invoked_subcommand not in {"worker", "tray"}:
        core.service.recover_stale()
    ctx.obj = CoreContext(core=core, out=Output())


app.command()(start)
app.command(aliases=["p"])(pause)
app.command(aliases=["r"])(resume)
app.command()(cancel)
app.command()(finish)
app.command()(delete)
app.command(name="re-resolve")(re_resolve)
app.command(aliases=["h"])(history)
app.command(aliases=["s"])(status)
app.command()(tray)
app.command()(worker)
