# Timer Design

Core domain logic for the Pomodoro timer: state machine, time accounting, and persistence.

## Interval Statuses

An interval has one of seven statuses:

| Status | Meaning |
|---|---|
| `running` | Timer is actively counting. Worker is polling. |
| `paused` | Timer is suspended by the user. Worker is not running. |
| `interrupted` | Timer was forcibly stopped by a crash. Worker is not running. |
| `finished` | Full duration elapsed. Awaiting user resolution. |
| `completed` | User confirmed honest work was done. Terminal. |
| `abandoned` | User indicated they did not work. Terminal. |
| `cancelled` | User cancelled before duration elapsed. Terminal. |

## State Transitions

```
                          +-----------+
            start ------> |  running  | <--- resume (paused, interrupted)
                          +-----------+
                         /  |       |  \
                  pause /   |       |   \ cancel
                       v    |       |    v
                +---------+ |       | +-----------+
                | paused  | |       | | cancelled |
                +---------+ |       | +-----------+
                    |        |       |      ^
             cancel +--------+-------+------+
                             |       |
                       crash |       | auto-finish
                    recovery |       |
                             v       v
                     +-------------+ +-----------+
                     | interrupted | | finished  |
                     +-------------+ +-----------+
                                       /       \
                                finish/         \finish
                                     v           v
                               +-----------+ +-----------+
                               | completed | | abandoned |
                               +-----------+ +-----------+
```

Simplified:
- `running` -> `paused` (pause), `finished` (auto-finish by worker), `cancelled` (cancel), `interrupted` (crash recovery)
- `paused` -> `running` (resume), `cancelled` (cancel)
- `interrupted` -> `running` (resume), `cancelled` (cancel)
- `finished` -> `completed` (finish completed), `abandoned` (finish abandoned)
- `completed`, `abandoned`, `cancelled` — terminal, no further transitions.

## Time Accounting

Three fields track work time:

- **`worked_sec`** — accumulated completed running time (updated on pause, cancel, auto-finish).
- **`run_started_at`** — timestamp when the current running segment began. `NULL` when not running.
- **`heartbeat_at`** — last worker heartbeat timestamp (~10s interval). Used by crash recovery to credit worked time. `NULL` when not running.

**Effective worked time** (used in status, history, and completion checks):

- If `running`: `worked_sec + (now - run_started_at)`
- Otherwise: `worked_sec`

This design avoids updating the database every second. Only state transitions and periodic heartbeats (~10s) write to the DB.

## Auto-Finish (Timer Worker)

The timer worker is a background process spawned by `start` and `resume`. It polls the database every ~1 second:

1. Fetch the interval row. Exit if status is no longer `running`.
2. Compute effective worked time.
3. When `effective_worked >= duration_sec`:
   - Set `status=finished`, `worked_sec=duration_sec`, `ended_at=now`, `run_started_at=NULL`.
   - Show a macOS dialog (AppleScript) with "Completed" / "Abandoned" buttons (5-minute timeout).
   - If user responds: set `status=<choice>` (`completed` or `abandoned`).
   - If dialog times out or fails: interval stays `finished` — user resolves via `finish` command.
   - Exit worker.

Worker lifecycle:
- Tracked via PID file at `<data_dir>/timer_worker.pid`.
- Spawned as a detached process (`start_new_session=True`).
- Exits when: interval is no longer running, completion is detected, or an error occurs.
- PID file is removed on exit.

## Crash Recovery

The timer worker writes a heartbeat timestamp (`heartbeat_at`) to the database every ~10 seconds. This enables work time recovery after crashes.

On every CLI command, before executing, the system checks for stale intervals:

1. Fetch the latest interval.
2. If `status=running` but the worker process is not alive:
   - Credit worked time from the last heartbeat: `worked_sec += heartbeat_at - run_started_at` (capped at `duration_sec`).
   - Mark as `interrupted`, clear `run_started_at` and `heartbeat_at`.
   - Insert an `interrupted` event.
   - Remove stale PID file.
3. User must explicitly run `resume` to continue.

Worker liveness check: PID file exists + process is alive (`kill -0`) + process command contains "python" (`ps -p <pid> -o comm=`).

**Limitation**: work time between the last heartbeat and the crash is lost — at most ~10 seconds. If no heartbeat was written (crash within the first few seconds), the current run segment is lost entirely.

## Concurrency

CLI and timer worker may race on writes (e.g., `pause` vs auto-finish). Both use conditional `UPDATE ... WHERE status = 'running'` inside transactions. SQLite serializes these — only one succeeds (`rowcount = 1`), the other gets `rowcount = 0` and handles accordingly.

At most one active interval exists at any time, enforced by a partial unique index.

## Database

Storage engine: SQLite in STRICT mode. Database file: `<data_dir>/pomodoro.db`.

### Connection Setup

Every connection sets these PRAGMAs before any queries:

```sql
PRAGMA journal_mode = WAL;    -- concurrent CLI + worker access without reader/writer blocking
PRAGMA busy_timeout = 5000;   -- retry on SQLITE_BUSY instead of failing immediately
PRAGMA foreign_keys = ON;     -- enforce foreign key constraints
```

### Schema Migrations

Schema changes are managed via SQLite's built-in `PRAGMA user_version`. Each migration is a Python function in `db.py`, indexed sequentially. On every connection, the app compares the DB's `user_version` to the target version and runs any pending migrations automatically.

### Table: `intervals`

One row per work interval. Source of truth for current state.

```sql
CREATE TABLE intervals (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    duration_sec   INTEGER NOT NULL,           -- requested duration in seconds
    status         TEXT NOT NULL               -- current lifecycle status
        CHECK(status IN ('running','paused','finished','completed','abandoned','cancelled','interrupted')),
    started_at     INTEGER NOT NULL,           -- initial start time (unix seconds)
    ended_at    INTEGER,                    -- set when finished/cancelled (unix seconds)
    worked_sec     INTEGER NOT NULL DEFAULT 0, -- accumulated active work time (seconds)
    run_started_at INTEGER,                    -- current run segment start (unix seconds), NULL when not running
    heartbeat_at  INTEGER                     -- last worker heartbeat (unix seconds), NULL when not running
) STRICT;
```

| Column | Description |
|---|---|
| `id` | Autoincrement integer, assigned on `start`. |
| `duration_sec` | Requested interval length in seconds (e.g., 1500 for 25 minutes). |
| `status` | Current lifecycle status. See [Interval Statuses](#interval-statuses). |
| `started_at` | Unix timestamp when the interval was first created. Never changes. |
| `ended_at` | Unix timestamp when the interval ended (timer elapsed or cancelled). `NULL` while running/paused. |
| `worked_sec` | Total seconds of actual work. Updated on pause, cancel, and auto-finish. Excludes paused time. |
| `run_started_at` | Unix timestamp of the current running segment's start. Set on `start` and `resume`, cleared (`NULL`) on `pause`, `cancel`, `finish`, and crash recovery. |
| `heartbeat_at` | Unix timestamp of the last worker heartbeat (~10s interval). Used by crash recovery to credit worked time. Cleared on `pause`, `cancel`, `finish`, and crash recovery. |

### Table: `interval_events`

Append-only audit log. One row per state transition.

```sql
CREATE TABLE interval_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    interval_id   INTEGER NOT NULL REFERENCES intervals(id),
    event_type    TEXT NOT NULL
        CHECK(event_type IN ('started','paused','resumed','finished','completed','abandoned','cancelled','interrupted')),
    event_at      INTEGER NOT NULL             -- event time (unix seconds)
) STRICT;
```

Event types map to state transitions:

| Event Type | Trigger |
|---|---|
| `started` | `start` command creates a new interval. |
| `paused` | `pause` command suspends a running interval. |
| `resumed` | `resume` command continues a paused interval. |
| `finished` | Timer worker detects duration elapsed. |
| `completed` | User resolves finished interval as honest work (dialog or `finish` command). |
| `abandoned` | User resolves finished interval as not-worked (dialog or `finish` command). |
| `cancelled` | `cancel` command terminates an active interval. |
| `interrupted` | Crash recovery detects a running interval with a dead worker. |

### Indexes

```sql
-- Enforce at most one active (non-terminal) interval at any time.
CREATE UNIQUE INDEX idx_one_active
    ON intervals((1)) WHERE status IN ('running','paused','finished','interrupted');

-- Fast event lookup by interval, ordered by time.
CREATE INDEX idx_events_interval_at
    ON interval_events(interval_id, event_at);

-- Fast history queries (most recent first).
CREATE INDEX idx_intervals_started_desc
    ON intervals(started_at DESC);
```
