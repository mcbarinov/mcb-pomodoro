"""Resume a paused Pomodoro interval."""

import typer

app = typer.Typer()


@app.command()
def resume() -> None:
    """Resume a paused Pomodoro interval."""
    typer.echo("Not implemented yet.")
