"""Show current Pomodoro timer status."""

import time

import typer

from mb_pomodoro import db
from mb_pomodoro.app_context import use_context
from mb_pomodoro.db import ACTIVE_STATUSES
from mb_pomodoro.output import StatusActiveResult, StatusInactiveResult


def status(ctx: typer.Context) -> None:
    """Show current Pomodoro timer status."""
    app = use_context(ctx)

    now = int(time.time())
    row = db.fetch_latest_interval(app.conn)
    today_completed = db.count_today_completed(app.conn, now)

    if row is None or row.status not in ACTIVE_STATUSES:
        app.out.print_status(StatusInactiveResult(today_completed=today_completed))
        return

    effective_worked = row.effective_worked(now)
    remaining = max(0, row.duration_sec - effective_worked)

    app.out.print_status(
        StatusActiveResult(
            interval_id=row.id,
            status=row.status,
            duration_sec=row.duration_sec,
            worked_sec=effective_worked,
            remaining_sec=remaining,
            started_at=row.started_at,
            today_completed=today_completed,
        )
    )
