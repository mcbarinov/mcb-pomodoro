# CLI Commands

All commands support the `--json` flag for machine-readable output.

## Global Options

| Option | Description |
|---|---|
| `--version` | Print version and exit. |
| `--json` | Output results as JSON envelopes. |
| `--data-dir PATH` | Override data directory (default: `~/.local/mb-pomodoro`). Env: `MB_POMODORO_DATA_DIR`. Each directory is an independent instance with its own DB and worker, allowing multiple timers to run simultaneously. |

## `start [duration]`

Start a new work interval.

- `duration` — optional. Formats: `25` (minutes), `25m`, `90s`, `10m30s`. Default: 25 minutes (configurable via `config.toml`).
- Fails if an active interval (running, paused, or finished) already exists.
- Spawns a background timer worker to track completion.

```
$ mb-pomodoro start
Pomodoro started: 25:00.

$ mb-pomodoro start 45
Pomodoro started: 45:00.

$ mb-pomodoro start 10m30s
Pomodoro started: 10:30.
```

## `pause`

Pause the running interval.

- Only valid when status is `running`.
- Accumulates elapsed work time into `worked_sec`, clears `run_started_at`.
- Timer worker exits (no polling while paused).

```
$ mb-pomodoro pause
Paused. Worked: 12:30, left: 12:30.
```

## `resume`

Resume a paused or interrupted interval.

- Only valid when status is `paused` or `interrupted`.
- Sets `run_started_at` to current time, spawns a new timer worker.

```
$ mb-pomodoro resume
Resumed. Worked: 12:30, left: 12:30.
```

## `cancel`

Cancel the active interval.

- Valid from `running`, `paused`, or `interrupted`.
- If running, accumulates the current work segment before cancelling.

```
$ mb-pomodoro cancel
Cancelled. Worked: 08:15.
```

## `finish <resolution>`

Manually resolve a finished interval. Fallback for when the macOS completion dialog was missed or timed out.

- `resolution` — required: `completed` (honest work) or `abandoned` (did not work).
- Only valid when status is `finished`.

```
$ mb-pomodoro finish completed
Interval marked as completed. Worked: 25:00.
```

## `status`

Show current timer status.

```
$ mb-pomodoro status
Status:   running
Duration: 25:00
Worked:   12:30
Left:     12:30

$ mb-pomodoro status
No active interval.
```

## `history [--limit N]`

Show recent intervals. Default limit: 10.

```
$ mb-pomodoro history -n 5
Date              Duration    Worked  Status
----------------  --------  --------  ---------
2026-02-17 14:00     25:00     25:00  completed
2026-02-17 10:30     25:00     15:20  cancelled
2026-02-16 09:00     45:00     45:00  abandoned
```

## `edit` — off-plan state edits

Group of non-standard operations for manipulating interval state outside the normal flow. Use these when something went off-plan.

### `edit restart`

Reset a running interval's counters in place, keeping the same id. Useful when you started a Pomodoro, got distracted, and want a fresh timer without losing the row.

- Only valid when status is `running`. For any other status (paused, interrupted, finished, or terminal), cancel and start a new interval instead.
- Resets `worked_sec` to 0, sets `started_at` and `run_started_at` to now, clears `heartbeat_at`. Appends a new `started` event to the audit log.
- Duration is preserved — restart does not accept a new duration. To change duration, `cancel` + `start <duration>`.
- The existing timer worker keeps polling and picks up the reset values on its next tick. No worker respawn, no PID churn.
- Requires interactive confirmation (type "yes") unless `--yes`/`-y` is provided.
- In `--json` mode, `--yes` is required.

```
$ mb-pomodoro edit restart
Interval 42: 25:00, worked 01:30, started 2026-04-08 14:00.
Type 'yes' to restart this interval: yes
Interval 42 restarted. Duration: 25:00.

$ mb-pomodoro edit restart -y
Interval 42 restarted. Duration: 25:00.
```

### `edit delete <interval_id>`

Permanently delete an interval from history.

- `interval_id` — required. The interval to delete.
- Requires interactive confirmation (type "yes") unless `--yes`/`-y` is provided.
- In `--json` mode, `--yes` is required.
- Completely removes the interval and all its events from the database.

```
$ mb-pomodoro edit delete 42
Interval 42: 25:00, running, worked 01:30, started 2026-04-08 14:00.
Type 'yes' to permanently delete this interval: yes
Interval 42 deleted (was running, 01:30 worked).

$ mb-pomodoro edit delete 38 -y
Interval 38 deleted (was completed, 25:00 worked).
```

### `edit re-resolve <interval_id> <resolution>`

Change the resolution of a completed or abandoned interval.

- `interval_id` — required. The interval to re-resolve.
- `resolution` — required: `completed` or `abandoned`.
- Only valid when status is `completed` or `abandoned`.
- Requires interactive confirmation (type "yes") unless `--yes`/`-y` is provided.
- In `--json` mode, `--yes` is required.

```
$ mb-pomodoro edit re-resolve 42 abandoned
Interval 42: currently completed, worked 25:00, started 2026-04-08 14:00.
Will change to: abandoned.
Type 'yes' to confirm: yes
Interval 42 changed from completed to abandoned.

$ mb-pomodoro edit re-resolve 42 completed -y
Interval 42 changed from abandoned to completed.
```

## JSON Output Format

All commands support `--json` for machine-readable output. Envelope:

- Success: `{"ok": true, "data": {<command-specific>}}`
- Error: `{"ok": false, "error": "<error_code>", "message": "<human-readable>"}`

Error codes: `INVALID_DURATION`, `ACTIVE_INTERVAL_EXISTS`, `NOT_RUNNING`, `NOT_RESUMABLE`, `NO_ACTIVE_INTERVAL`, `NOT_FINISHED`, `INVALID_RESOLUTION`, `CONCURRENT_MODIFICATION`, `INTERVAL_NOT_FOUND`, `CONFIRMATION_REQUIRED`, `NOT_CONFIRMED`, `ALREADY_RESOLVED`, `NOT_RE_RESOLVABLE`.
