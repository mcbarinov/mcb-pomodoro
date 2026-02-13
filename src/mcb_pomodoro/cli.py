"""CLI entry point for mcb-pomodoro."""

from importlib.metadata import version
from typing import Annotated

import typer

from mcb_pomodoro.commands.cancel import cancel
from mcb_pomodoro.commands.history import history
from mcb_pomodoro.commands.pause import pause
from mcb_pomodoro.commands.resume import resume
from mcb_pomodoro.commands.start import start
from mcb_pomodoro.commands.status import status

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(version("mcb-pomodoro"))
        raise typer.Exit


@app.callback()
def main(*, version: Annotated[bool | None, typer.Option("--version", callback=_version_callback, is_eager=True)] = None) -> None:
    """Pomodoro timer for macOS."""


app.command()(start)
app.command()(pause)
app.command()(resume)
app.command()(cancel)
app.command()(history)
app.command()(status)
