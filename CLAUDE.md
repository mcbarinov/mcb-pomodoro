# AI Agent Start Guide

## Critical: Language
RESPOND IN ENGLISH. Always. No exceptions.
User's language does NOT determine your response language.
Only switch if user EXPLICITLY requests it (e.g., "respond in {language}").
Language switching applies ONLY to chat. All code, comments, commit messages, and files must ALWAYS be in English — no exceptions.

## Mandatory Rules (external)
These files are REQUIRED. Read them fully and follow all rules.
- `~/.claude/shared-rules/general.md`
- `~/.claude/shared-rules/python.md`

## Project Reading (context)
Required — read before every task:
- `README.md`
- `docs/timer-design.md`
- `docs/cli-architecture.md`
Reference — read when working on related areas:
- `docs/cli-commands.md` — command behavior, JSON format, error codes
- `docs/raycast.md` — Raycast script commands

## Preflight (mandatory)
Before your first response:
1. Read all required files listed above.
2. Do not answer until all are read.
3. In your first reply, list every file you have read from this document.

Failure to follow this protocol is considered an error.

## Testing the app

The user may have a real pomodoro timer running. NEVER run `mb-pomodoro` commands against the default data directory.
Always use `--data-dir /tmp/mb-pomodoro-test` (or similar) for any manual verification.
