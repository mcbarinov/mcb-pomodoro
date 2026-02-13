"""Show current Pomodoro timer status."""

import typer

app = typer.Typer()


@app.command()
def status() -> None:
    """Show current Pomodoro timer status."""
    typer.echo("Not implemented yet.")
