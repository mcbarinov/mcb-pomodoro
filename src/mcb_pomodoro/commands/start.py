"""Start a new Pomodoro interval."""

from typing import Annotated

import typer

app = typer.Typer()


@app.command()
def start(duration: Annotated[int, typer.Argument(help="Interval duration in minutes.")] = 25) -> None:
    """Start a new Pomodoro interval."""
    _ = duration
    typer.echo("Not implemented yet.")
