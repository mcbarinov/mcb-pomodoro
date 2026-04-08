# mb-pomodoro

macOS-focused Pomodoro timer with a CLI-first workflow. Work intervals only — no break timers.

- CLI is the primary interface.
- Optional GUI integrations (tray icon, Raycast extension) invoke CLI commands as subprocesses with `--json`.
- Persistent state and history in SQLite.
- Background worker process tracks interval completion and sends macOS notifications.

## Configuration

Optional config file at `<data_dir>/config.toml`:

```toml
[timer]
default_duration = "25"  # same formats as CLI: "25", "25m", "90s", "10m30s"
```

### Data Directory

Default: `~/.local/mb-pomodoro`. Override with `--data-dir` flag or `MB_POMODORO_DATA_DIR` env variable.

| File | Purpose |
|---|---|
| `pomodoro.db` | SQLite database (intervals + events). |
| `timer_worker.pid` | PID of the active timer worker. Exists only while a worker is running. |
| `pomodoro.log` | Rotating log file (1 MB max, 3 backups). |
| `config.toml` | Optional configuration. |

## Documentation

Detailed docs in `docs/`:

- [Timer Design](docs/timer-design.md) — state machine, time accounting, crash recovery, database schema
- [CLI Commands](docs/cli-commands.md) — command reference with examples and JSON output format
- [CLI Architecture](docs/cli-architecture.md) — mm-clikit patterns and project structure conventions
- [Raycast Integration](docs/raycast.md) — Raycast script commands setup
