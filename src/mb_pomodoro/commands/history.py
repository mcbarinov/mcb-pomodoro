"""Show Pomodoro session history."""

import time
from typing import Annotated

import typer

from mb_pomodoro import db
from mb_pomodoro.app_context import use_context
from mb_pomodoro.output import DailyHistoryItem, DailyHistoryResult, HistoryItem, HistoryResult


def history(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option("--limit", "-n", min=1, help="Maximum number of entries to show.")] = 10,
    daily: Annotated[bool, typer.Option("--daily", "-d", help="Show completed count per day.")] = False,
) -> None:
    """Show Pomodoro session history."""
    app = use_context(ctx)

    if daily:
        rows = db.fetch_daily_completed(app.conn, limit)
        items = [DailyHistoryItem(date=date, completed=count) for date, count in rows]
        app.out.print_daily_history(DailyHistoryResult(days=items))
        return

    interval_rows = db.fetch_history(app.conn, limit)

    now = int(time.time())
    history_items: list[HistoryItem] = []
    for row in interval_rows:
        effective_worked = row.effective_worked(now)
        history_items.append(
            HistoryItem(
                interval_id=row.id,
                status=row.status,
                duration_sec=row.duration_sec,
                worked_sec=effective_worked,
                started_at=row.started_at,
            )
        )

    app.out.print_history(HistoryResult(intervals=history_items))
