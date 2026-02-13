"""Pause the active Pomodoro interval."""

import typer

app = typer.Typer()


@app.command()
def pause() -> None:
    """Pause the active Pomodoro interval."""
    typer.echo("Not implemented yet.")
