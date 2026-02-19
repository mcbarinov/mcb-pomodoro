"""Database connection, schema management, and query/mutation functions."""

import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from mb_pomodoro.time_utils import start_of_day

logger = logging.getLogger(__name__)

# --- Migrations ---


def _migrate_v1(conn: sqlite3.Connection) -> None:
    """Create initial schema: intervals + interval_events tables and indexes."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS intervals (
            id TEXT PRIMARY KEY,
            duration_sec INTEGER NOT NULL,
            status TEXT NOT NULL
                CHECK(status IN ('running','paused','finished','completed','abandoned','cancelled','interrupted')),
            started_at INTEGER NOT NULL,
            ended_at INTEGER,
            worked_sec INTEGER NOT NULL DEFAULT 0,
            run_started_at INTEGER,
            heartbeat_at INTEGER
        ) STRICT;

        CREATE TABLE IF NOT EXISTS interval_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            interval_id TEXT NOT NULL REFERENCES intervals(id),
            event_type TEXT NOT NULL
                CHECK(event_type IN ('started','paused','resumed','finished','completed','abandoned','cancelled','interrupted')),
            event_at INTEGER NOT NULL
        ) STRICT;

        CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active
            ON intervals((1)) WHERE status IN ('running','paused','finished','interrupted');
        CREATE INDEX IF NOT EXISTS idx_events_interval_at
            ON interval_events(interval_id, event_at);
        CREATE INDEX IF NOT EXISTS idx_intervals_started_desc
            ON intervals(started_at DESC);
    """)


# Indexed by position: _MIGRATIONS[0] = v1, _MIGRATIONS[1] = v2, etc.
# user_version=0 means no migrations applied.
_MIGRATIONS: tuple[Callable[[sqlite3.Connection], None], ...] = (_migrate_v1,)


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Run all pending schema migrations based on PRAGMA user_version."""
    current_version: int = conn.execute("PRAGMA user_version").fetchone()[0]
    for i, migrate_fn in enumerate(_MIGRATIONS):
        target_version = i + 1
        if current_version < target_version:
            migrate_fn(conn)
            conn.execute(f"PRAGMA user_version = {target_version}")
            logger.info("Applied migration v%d (%s)", target_version, migrate_fn.__doc__)


class IntervalStatus(StrEnum):
    """Interval lifecycle status."""

    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


ACTIVE_STATUSES = frozenset(
    {
        IntervalStatus.RUNNING,
        IntervalStatus.PAUSED,
        IntervalStatus.INTERRUPTED,
        IntervalStatus.FINISHED,
    }
)


class EventType(StrEnum):
    """Interval event type for the audit log."""

    STARTED = "started"
    PAUSED = "paused"
    RESUMED = "resumed"
    FINISHED = "finished"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


def _insert_event(conn: sqlite3.Connection, interval_id: str, event_type: EventType, event_at: int) -> None:
    """Insert a row into interval_events."""
    conn.execute(
        "INSERT INTO interval_events (interval_id, event_type, event_at) VALUES (?, ?, ?)", (interval_id, event_type, event_at)
    )


@dataclass(frozen=True, slots=True)
class IntervalRow:
    """Interval row projection."""

    id: str
    status: IntervalStatus
    duration_sec: int
    worked_sec: int
    run_started_at: int | None
    started_at: int
    heartbeat_at: int | None

    def effective_worked(self, now: int) -> int:
        """Compute actual worked time including the current running segment."""
        if self.status == IntervalStatus.RUNNING and self.run_started_at is not None:
            return min(self.worked_sec + (now - self.run_started_at), self.duration_sec)
        return self.worked_sec


# --- Queries ---

_SELECT_INTERVAL = "SELECT id, status, duration_sec, worked_sec, run_started_at, started_at, heartbeat_at FROM intervals"


def _to_interval_row(row: tuple[str, str, int, int, int | None, int, int | None]) -> IntervalRow:
    """Convert a raw SQL row tuple to an IntervalRow with enum conversion."""
    return IntervalRow(
        id=row[0],
        status=IntervalStatus(row[1]),
        duration_sec=row[2],
        worked_sec=row[3],
        run_started_at=row[4],
        started_at=row[5],
        heartbeat_at=row[6],
    )


def fetch_latest_interval(conn: sqlite3.Connection) -> IntervalRow | None:
    """Return the most recently started interval, or None."""
    row = conn.execute(_SELECT_INTERVAL + " ORDER BY started_at DESC LIMIT 1").fetchone()
    return _to_interval_row(row) if row else None


def fetch_interval(conn: sqlite3.Connection, interval_id: str) -> IntervalRow | None:
    """Return an interval by id, or None."""
    row = conn.execute(_SELECT_INTERVAL + " WHERE id = ?", (interval_id,)).fetchone()
    return _to_interval_row(row) if row else None


def fetch_history(conn: sqlite3.Connection, limit: int) -> list[IntervalRow]:
    """Return the most recent intervals ordered by started_at DESC."""
    rows = conn.execute(_SELECT_INTERVAL + " ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
    return [_to_interval_row(row) for row in rows]


def fetch_daily_completed(conn: sqlite3.Connection, limit: int) -> list[tuple[str, int]]:
    """Return daily completed counts (date, count) ordered by date DESC, days with >0 only."""
    rows = conn.execute(
        "SELECT date(started_at, 'unixepoch', 'localtime') AS day, COUNT(*) AS cnt"
        " FROM intervals WHERE status = 'completed'"
        " GROUP BY day ORDER BY day DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [(row[0], row[1]) for row in rows]


# --- Mutations ---


def insert_interval(conn: sqlite3.Connection, interval_id: str, duration_sec: int, now: int) -> bool:
    """Create a new running interval with 'started' event. Return False on IntegrityError."""
    try:
        conn.execute(
            "INSERT INTO intervals (id, duration_sec, status, started_at, worked_sec, run_started_at)"
            " VALUES (?, ?, 'running', ?, 0, ?)",
            (interval_id, duration_sec, now, now),
        )
        _insert_event(conn, interval_id, EventType.STARTED, now)
        conn.commit()
    except sqlite3.IntegrityError:
        return False
    return True


def finish_interval(conn: sqlite3.Connection, interval_id: str, duration_sec: int, now: int) -> bool:
    """Mark running interval as finished (awaiting resolution). Return False if rowcount == 0."""
    cursor = conn.execute(
        "UPDATE intervals SET status = 'finished', worked_sec = ?, ended_at = ?,"
        " run_started_at = NULL, heartbeat_at = NULL WHERE id = ? AND status = 'running'",
        (duration_sec, now, interval_id),
    )
    if cursor.rowcount == 0:
        conn.rollback()
        return False
    _insert_event(conn, interval_id, EventType.FINISHED, now)
    conn.commit()
    return True


def resolve_interval(conn: sqlite3.Connection, interval_id: str, resolution: IntervalStatus, now: int) -> bool:
    """Resolve a finished interval as 'completed' or 'abandoned'. Return False if rowcount == 0.

    Note: does not update ended_at — that records when the timer elapsed (set by finish_interval),
    not when the user made a resolution decision.
    """
    cursor = conn.execute(
        "UPDATE intervals SET status = ? WHERE id = ? AND status = 'finished'",
        (resolution, interval_id),
    )
    if cursor.rowcount == 0:
        conn.rollback()
        return False
    _insert_event(conn, interval_id, EventType(resolution), now)
    conn.commit()
    return True


def pause_interval(conn: sqlite3.Connection, interval_id: str, worked_sec: int, now: int) -> bool:
    """Pause a running interval. Return False if no running interval was updated."""
    cursor = conn.execute(
        "UPDATE intervals SET status = 'paused', worked_sec = ?, run_started_at = NULL, heartbeat_at = NULL"
        " WHERE id = ? AND status = 'running'",
        (worked_sec, interval_id),
    )
    if cursor.rowcount == 0:
        conn.rollback()
        return False
    _insert_event(conn, interval_id, EventType.PAUSED, now)
    conn.commit()
    return True


def resume_interval(conn: sqlite3.Connection, interval_id: str, now: int) -> bool:
    """Resume a paused interval. Return False if no paused interval was updated."""
    cursor = conn.execute(
        "UPDATE intervals SET status = 'running', run_started_at = ? WHERE id = ? AND status IN ('paused', 'interrupted')",
        (now, interval_id),
    )
    if cursor.rowcount == 0:
        conn.rollback()
        return False
    _insert_event(conn, interval_id, EventType.RESUMED, now)
    conn.commit()
    return True


def cancel_interval(conn: sqlite3.Connection, interval_id: str, worked_sec: int, now: int) -> bool:
    """Cancel a running or paused interval. Return False if no active interval was updated."""
    cursor = conn.execute(
        "UPDATE intervals SET status = 'cancelled', worked_sec = ?, ended_at = ?,"
        " run_started_at = NULL, heartbeat_at = NULL WHERE id = ? AND status IN ('running', 'paused', 'interrupted')",
        (worked_sec, now, interval_id),
    )
    if cursor.rowcount == 0:
        conn.rollback()
        return False
    _insert_event(conn, interval_id, EventType.CANCELLED, now)
    conn.commit()
    return True


def update_heartbeat(conn: sqlite3.Connection, interval_id: str, now: int) -> None:
    """Update heartbeat timestamp for a running interval."""
    conn.execute("UPDATE intervals SET heartbeat_at = ? WHERE id = ? AND status = 'running'", (now, interval_id))
    conn.commit()


def recover_running_interval(conn: sqlite3.Connection, interval_id: str, now: int) -> bool:
    """Mark running interval as interrupted, credit worked time from heartbeat, and insert 'interrupted' event.

    Uses heartbeat_at to recover work time accumulated before the crash.
    Falls back to no credit if heartbeat_at is NULL (no heartbeat was written).
    Return False if no running interval was updated.
    """
    cursor = conn.execute(
        "UPDATE intervals SET status = 'interrupted',"
        " worked_sec = CASE"
        "   WHEN heartbeat_at IS NOT NULL AND run_started_at IS NOT NULL"
        "   THEN MIN(worked_sec + (heartbeat_at - run_started_at), duration_sec)"
        "   ELSE worked_sec END,"
        " run_started_at = NULL, heartbeat_at = NULL"
        " WHERE id = ? AND status = 'running'",
        (interval_id,),
    )
    if cursor.rowcount == 0:
        conn.rollback()
        return False
    _insert_event(conn, interval_id, EventType.INTERRUPTED, now)
    conn.commit()
    return True


def count_today_completed(conn: sqlite3.Connection, now: int) -> int:
    """Count intervals completed today (local midnight to now)."""
    today_start = start_of_day(now)
    row = conn.execute(
        "SELECT COUNT(*) FROM intervals WHERE started_at >= ? AND status = 'completed'",
        (today_start,),
    ).fetchone()
    return int(row[0])


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode, busy timeout, and foreign keys enabled."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    _run_migrations(conn)
    return conn
