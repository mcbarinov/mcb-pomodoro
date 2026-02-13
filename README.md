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

## Data & History

SQLite stores both:

- Timer session records.
- State transition events (for example: `started`, `paused`, `resumed`, `cancelled`, `completed`).

This design makes it possible to reconstruct a session timeline and provide reliable CLI history output.

## Out of Scope (for now)

- Automatic daemon startup with `launchd` (`LaunchAgent`).
- Break interval logic (short/long breaks).
- History export formats (`csv`, `json`).
- Multi-timer support.

## Status

This project is currently in planning/specification stage.
