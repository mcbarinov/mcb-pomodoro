# Raycast Integration

The `raycast/` directory contains [Script Commands](https://github.com/raycast/script-commands) for controlling the timer from Raycast's search bar.

## Available Commands

| Command | Description |
|---|---|
| Start Pomodoro | Start with default duration |
| Start Pomodoro... | Start with custom duration (prompts for input) |
| Pause Pomodoro | Pause the running interval |
| Resume Pomodoro | Resume a paused or interrupted interval |
| Cancel Pomodoro | Cancel the active interval |
| Pomodoro Status | Show current timer status |

## Setup

1. Ensure `mb-pomodoro` is in `~/.local/bin/` (installed via `uv tool install`).
2. In Raycast, open Preferences > Extensions > Script Commands > Add Directories.
3. Add the `raycast/` directory from this repository.

The commands will appear in Raycast's search bar. Action commands (start, pause, resume, cancel) show a brief HUD notification with the result. Status shows a compact single-line summary.
