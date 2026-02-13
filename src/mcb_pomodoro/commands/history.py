"""Show Pomodoro session history."""

import typer

app = typer.Typer()


@app.command()
def history() -> None:
    """Show Pomodoro session history."""
    typer.echo("Not implemented yet.")
