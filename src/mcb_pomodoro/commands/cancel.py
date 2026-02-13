"""Cancel the active Pomodoro interval."""

import typer

app = typer.Typer()


@app.command()
def cancel() -> None:
    """Cancel the active Pomodoro interval."""
    typer.echo("Not implemented yet.")
