"""Process liveness, PID file utilities, and process spawning."""

import contextlib
import os
import subprocess  # nosec B404
import tempfile
from pathlib import Path


def read_pid(pid_path: Path) -> int | None:
    """Read PID from file, returning None if missing or invalid."""
    if not pid_path.exists():
        return None
    try:
        return int(pid_path.read_text().strip())
    except ValueError, OSError:
        return None


def is_alive(pid_path: Path) -> bool:
    """Check whether a process is running by PID file and process liveness."""
    pid = read_pid(pid_path)
    if pid is None:
        return False

    # Check process exists
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass

    # Verify process is a Python process
    try:
        # S603/S607: args are controlled literals, "ps" is a standard system utility
        result = subprocess.run(["ps", "-p", str(pid), "-o", "comm="], capture_output=True, text=True, check=False)  # noqa: S603, S607  # nosec B603, B607
        return "python" in result.stdout.lower()
    except OSError:
        return False


def write_pid_file(pid_path: Path) -> None:
    """Write current PID to a PID file atomically."""
    fd, tmp_path = tempfile.mkstemp(dir=pid_path.parent, prefix=".worker.pid.")
    tmp = Path(tmp_path)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        tmp.replace(pid_path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def spawn_timer_worker(interval_id: str, data_dir: Path) -> None:
    """Launch the timer worker as a detached background process."""
    # S603/S607: args are controlled literals, "mb-pomodoro" is our own CLI entry point
    subprocess.Popen(  # noqa: S603  # nosec B603, B607
        ["mb-pomodoro", "--data-dir", str(data_dir), "worker", interval_id],  # noqa: S607
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def spawn_tray(data_dir: Path) -> int:
    """Launch the tray process in background and return its PID."""
    # S603/S607: args are controlled literals, "mb-pomodoro" is our own CLI entry point
    proc = subprocess.Popen(  # noqa: S603  # nosec B603, B607
        ["mb-pomodoro", "--data-dir", str(data_dir), "tray", "--run"],  # noqa: S607
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    return proc.pid
