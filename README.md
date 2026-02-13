# mcb-pomodoro

`mcb-pomodoro` is a macOS-focused Pomodoro timer with a CLI-first workflow.

This repository currently defines product scope and architecture decisions. Implementation details will be added later.

## Goals

- Provide a reliable Pomodoro workflow centered on work intervals.
- Keep CLI as the primary and guaranteed interface.
- Support optional UI integrations (tray icon and Raycast extension) on top of the same core logic.
- Persist timer state and history so progress is not lost across process crashes or machine restarts.

## Scope (Current)

### In Scope

- Work-interval timer only (no break intervals in current version).
- Default interval duration: 25 minutes.
- Custom interval duration via CLI, for example:
  - `mcb-pomodoro start 45`
- One active timer at a time.
- Timer controls:
  - `start`
  - `pause`
  - `resume`
  - `cancel`
- CLI history output.
- macOS notification when an interval completes.
- Persistent state and history in SQLite.
- Application data directory:
  - `~/.local/mcb-pomodoro`
- Background daemon process to own timer execution and state transitions.

### Explicit Behavior

- `pause` and `resume` are stored as explicit history events.
- If the system restarts or crashes during an active interval, timer execution does not auto-continue.
- After restart, the user must explicitly run `resume` to continue.

## Interfaces

### 1) CLI (Primary, Required)

CLI is the default and fully supported way to use the app.

### 2) Tray Icon (Optional)

Tray/menu bar UI is optional. Users can choose to run it, but the app must remain fully functional without it.

### 3) Raycast Extension (Required)

The app must be operable through a Raycast extension in addition to the CLI.

## Architecture Direction (Important to Account for Now)

- Use a single shared core service for timer logic.
  - CLI, tray, and Raycast must not duplicate timer behavior.
- Keep daemon as the source of truth for active timer state.
- Ensure safe concurrent access from multiple clients (CLI, tray, Raycast).
- Keep storage/event model explicit and auditable.

## Database Design (Detailed)

Storage engine: SQLite.
Root data directory: `~/.local/mcb-pomodoro`.

### Table: `intervals`

One row per work interval.

- `id` (TEXT PRIMARY KEY): interval UUID.
- `duration_sec` (INTEGER NOT NULL): requested interval duration in seconds.
- `status` (TEXT NOT NULL CHECK(status IN ('running', 'paused', 'completed', 'cancelled'))): current state.
- `started_at` (INTEGER NOT NULL): initial start timestamp (unix seconds).
- `finished_at` (INTEGER NULL): set when interval becomes `completed` or `cancelled`.
- `worked_sec` (INTEGER NOT NULL DEFAULT 0): accumulated active work time (pause time excluded).
- `run_started_at` (INTEGER NULL): timestamp of current active run; NULL when not running.

Purpose: fast status checks and history listing without replaying all events.

### Table: `interval_events`

Append-only state transition log.

- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `interval_id` (TEXT NOT NULL REFERENCES `intervals(id)`)
- `event_type` (TEXT NOT NULL CHECK(event_type IN ('started', 'paused', 'resumed', 'completed', 'cancelled', 'interrupted'))): state transition type.
- `event_at` (INTEGER NOT NULL): event timestamp (unix seconds)

Purpose: explicit timeline for audit/debug/history details, including pause/resume transitions.

### Constraints and Indexes

- Exactly one active interval:
  - `CREATE UNIQUE INDEX idx_one_active ON intervals((1)) WHERE status IN ('running', 'paused')`
- CHECK constraints on `status` and `event_type` (defined inline above).
- Recommended indexes:
  - `interval_events(interval_id, event_at)`
  - `intervals(started_at DESC)`

## Timer Business Logic

### Time Accounting Rule

- `worked_sec` stores accumulated completed running time.
- If interval is `running`, effective worked time is:
  - `worked_sec + (now - run_started_at)`
- If interval is `paused`, `completed`, or `cancelled`, effective worked time is:
  - `worked_sec`

### Command Semantics

- `start <minutes>`
  - Create `intervals` row with `status=running`, `worked_sec=0`, `run_started_at=now`.
  - Insert `started` event.
  - Fail if another active interval exists.
- `pause`
  - Allowed only from `running`.
  - Add elapsed segment to `worked_sec`.
  - Set `run_started_at=NULL`, `status=paused`.
  - Insert `paused` event.
- `resume`
  - Allowed only from `paused`.
  - Set `run_started_at=now`, `status=running`.
  - Insert `resumed` event.
- `cancel`
  - Allowed from `running` or `paused`.
  - If running, add elapsed segment to `worked_sec`.
  - Set `status=cancelled`, `finished_at=now`, `run_started_at=NULL`.
  - Insert `cancelled` event.
- Auto-complete (daemon-driven)
  - When effective worked time reaches `duration_sec`:
    - set `status=completed`, `finished_at=now`, `run_started_at=NULL`
    - insert `completed` event
    - trigger macOS completion notification

### Restart / Crash Recovery Rule

- On daemon startup, if an interval is still marked `running`:
  - set interval status to `paused`
  - set `run_started_at=NULL`
  - insert `interrupted` event
- **Known limitation**: work time accumulated between the last state transition and the crash is lost. The daemon cannot determine the actual crash time, so it does not update `worked_sec` during recovery.
- Interval does not continue automatically after restart.
- User must run `resume` explicitly.

## Out of Scope (for now)

- Automatic daemon startup with `launchd` (`LaunchAgent`).
- Break interval logic (short/long breaks).
- History export formats (`csv`, `json`).
- Multi-timer support.

## Status

This project is currently in planning/specification stage.
