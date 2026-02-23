"""Menu bar status icon for the Pomodoro timer."""

import contextlib
import os
import signal
import subprocess  # nosec B404
import threading
import time
from typing import Annotated

import typer
from mm_pymac import MenuItem, MenuSeparator, TrayApp

from mb_pomodoro.app_context import use_context
from mb_pomodoro.config import Config
from mb_pomodoro.db import ACTIVE_STATUSES, Db, IntervalRow, IntervalStatus
from mb_pomodoro.output import TrayStartResult, TrayStopResult
from mb_pomodoro.process import build_cli_args, is_alive, read_pid, spawn_tray, write_pid_file
from mb_pomodoro.time_utils import format_mmss, parse_duration

_POLL_INTERVAL_SEC = 2.0
_STOP_TIMEOUT_SEC = 2.0
_LAUNCH_VERIFY_SEC = 0.5

# Visible action items per interval status (None = no active interval)
_VISIBLE_ACTIONS: dict[IntervalStatus | None, frozenset[str]] = {
    None: frozenset({"start"}),
    IntervalStatus.RUNNING: frozenset({"pause"}),
    IntervalStatus.PAUSED: frozenset({"resume"}),
    IntervalStatus.INTERRUPTED: frozenset({"resume"}),
    IntervalStatus.FINISHED: frozenset(),
}


def _format_title(row: IntervalRow | None, today_completed: int) -> str:
    """Build the menu bar title string from the latest interval and today's count."""
    if row is None or row.status not in ACTIVE_STATUSES:
        icon = "\u25c7"
    elif row.status == IntervalStatus.FINISHED:
        icon = "\u2713"
    elif row.status in {IntervalStatus.PAUSED, IntervalStatus.INTERRUPTED}:
        icon = "\u23f8"
    else:
        icon = "\u25b6"
    if today_completed > 0:
        return f"{icon} {today_completed}"
    return icon


class _TrayController:
    """Manages tray app lifecycle: menu items, polling, and CLI actions."""

    def __init__(self, db: Db, cfg: Config) -> None:
        self._db = db
        self._cfg = cfg
        self._app = TrayApp(title="\u25c7")

        # Action items (keyed by command name for visibility lookup)
        self._actions: dict[str, MenuItem] = {
            "start": MenuItem("Start", callback=lambda _: self._run_action("start")),
            "pause": MenuItem("Pause", callback=lambda _: self._run_action("pause"), hidden=True),
            "resume": MenuItem("Resume", callback=lambda _: self._run_action("resume"), hidden=True),
        }

        # Info items
        self._status_item = MenuItem("No active interval", enabled=False)
        self._duration_item = MenuItem("Duration: --:--", enabled=False, hidden=True)
        self._worked_item = MenuItem("Worked: --:--", enabled=False, hidden=True)
        self._left_item = MenuItem("Left: --:--", enabled=False, hidden=True)
        self._today_item = MenuItem("Today: 0 completed", enabled=False, hidden=True)

        self._app.set_menu(
            [
                self._actions["start"],
                self._actions["pause"],
                self._actions["resume"],
                MenuSeparator(),
                self._status_item,
                self._duration_item,
                self._worked_item,
                self._left_item,
                self._today_item,
                MenuSeparator(),
                MenuItem("Quit", callback=lambda _: self._app.quit()),
            ]
        )

    def run(self) -> None:
        """Start the poll timer and enter the event loop."""
        self._app.start_timer(_POLL_INTERVAL_SEC, self._refresh)
        self._app.run()

    def _refresh(self) -> None:
        """Poll DB and update menu bar title and menu items."""
        row = self._db.fetch_latest_interval()
        now = int(time.time())
        today_completed = self._db.count_today_completed(now)

        self._app.title = _format_title(row, today_completed)

        # Today's completed count
        if today_completed > 0:
            self._today_item.title = f"Today: {today_completed} completed"
            self._today_item.hidden = False
        else:
            self._today_item.hidden = True

        # Action items visibility + re-enable after CLI execution
        status_key = row.status if row is not None and row.status in ACTIVE_STATUSES else None
        if status_key is None:
            duration_sec = parse_duration(self._cfg.default_duration) or 0
            self._actions["start"].title = f"Start ({format_mmss(duration_sec)})"
        visible = _VISIBLE_ACTIONS[status_key]
        for name, item in self._actions.items():
            item.hidden = name not in visible
            item.enabled = True

        # Info items
        if row is not None and row.status in ACTIVE_STATUSES:
            effective = row.effective_worked(now)
            remaining = max(0, row.duration_sec - effective)
            self._status_item.title = f"Status: {row.status}"
            self._duration_item.title = f"Duration: {format_mmss(row.duration_sec)}"
            self._duration_item.hidden = False
            self._worked_item.title = f"Worked: {format_mmss(effective)}"
            self._worked_item.hidden = False
            self._left_item.title = f"Left: {format_mmss(remaining)}"
            self._left_item.hidden = False
        else:
            self._status_item.title = "No active interval"
            self._duration_item.hidden = True
            self._worked_item.hidden = True
            self._left_item.hidden = True

    def _run_action(self, command: str) -> None:
        """Disable action items and run CLI command in a background thread."""
        for item in self._actions.values():
            item.enabled = False

        def task() -> None:
            # S603: args are controlled literals, "mb-pomodoro" is our own CLI entry point
            subprocess.run(  # noqa: S603  # nosec B603, B607
                [*build_cli_args(self._cfg.data_dir), "--json", command],
                capture_output=True,
                check=False,
            )
            self._app.run_on_main_thread(self._refresh)

        threading.Thread(target=task, daemon=True).start()


def _stop_tray(ctx: typer.Context) -> None:
    """Stop a running tray process via SIGTERM with SIGKILL fallback."""
    app = use_context(ctx)
    pid_path = app.cfg.tray_pid_path

    pid = read_pid(pid_path)
    if pid is None or not is_alive(pid_path):
        pid_path.unlink(missing_ok=True)
        app.out.print_error_and_exit("TRAY_NOT_RUNNING", "Tray is not running.")

    # SIGTERM — installMachInterrupt() converts this into clean NSApplication termination
    os.kill(pid, signal.SIGTERM)

    # Wait for process to exit
    deadline = time.monotonic() + _STOP_TIMEOUT_SEC
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        # SIGKILL fallback
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)

    pid_path.unlink(missing_ok=True)
    app.out.print_tray_stopped(TrayStopResult(pid=pid))


def _run_foreground(ctx: typer.Context) -> None:
    """Run the tray in foreground (blocking). Used by the background spawner."""
    app = use_context(ctx)
    cfg = app.cfg
    tray_pid_path = cfg.tray_pid_path

    if is_alive(tray_pid_path):
        app.out.print_error_and_exit("TRAY_ALREADY_RUNNING", "Tray is already running.")

    # Separate DB connection — the tray outlives the CLI context lifecycle
    tray_db = Db(cfg.db_path)
    write_pid_file(tray_pid_path)
    try:
        _TrayController(tray_db, cfg).run()
    finally:
        tray_pid_path.unlink(missing_ok=True)
        tray_db.close()


def _launch_background(ctx: typer.Context) -> None:
    """Spawn tray in background, verify it started, print PID."""
    app = use_context(ctx)
    cfg = app.cfg

    if is_alive(cfg.tray_pid_path):
        pid = read_pid(cfg.tray_pid_path)
        app.out.print_error_and_exit("TRAY_ALREADY_RUNNING", f"Tray is already running (pid {pid}).")

    pid = spawn_tray(cfg.data_dir)

    # Brief wait to verify the process is alive
    time.sleep(_LAUNCH_VERIFY_SEC)
    if not is_alive(cfg.tray_pid_path):
        app.out.print_error_and_exit("TRAY_LAUNCH_FAILED", "Tray process failed to start.")

    app.out.print_tray_started(TrayStartResult(pid=pid))


def tray(
    ctx: typer.Context,
    *,
    stop: Annotated[bool, typer.Option("--stop", help="Stop the running tray process.")] = False,
    run: Annotated[bool, typer.Option("--run", hidden=True, help="Run tray in foreground (internal).")] = False,
) -> None:
    """Run menu bar status icon that displays current timer state."""
    if stop:
        _stop_tray(ctx)
    elif run:
        _run_foreground(ctx)
    else:
        _launch_background(ctx)
