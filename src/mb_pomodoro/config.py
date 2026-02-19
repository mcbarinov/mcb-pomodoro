"""Centralized application configuration."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from mb_pomodoro.time_utils import parse_duration

DEFAULT_DATA_DIR = Path.home() / ".local" / "mb-pomodoro"
_DEFAULT_DURATION = "25"


@dataclass(frozen=True, slots=True)
class Config:
    """Application-wide configuration."""

    data_dir: Path
    db_path: Path
    timer_worker_pid_path: Path
    tray_pid_path: Path
    log_path: Path
    config_path: Path
    default_duration: str


def build_config(data_dir: Path) -> Config:
    """Build a Config instance from defaults and optional config.toml."""
    config_path = data_dir / "config.toml"
    default_duration = _DEFAULT_DURATION

    if config_path.is_file():
        with config_path.open("rb") as f:
            toml_data = tomllib.load(f)
        timer = toml_data.get("timer", {})
        if isinstance(timer, dict):
            val = timer.get("default_duration")
            if isinstance(val, str) and parse_duration(val) is not None:
                default_duration = val

    return Config(
        data_dir=data_dir,
        db_path=data_dir / "pomodoro.db",
        timer_worker_pid_path=data_dir / "timer_worker.pid",
        tray_pid_path=data_dir / "tray.pid",
        log_path=data_dir / "pomodoro.log",
        config_path=config_path,
        default_duration=default_duration,
    )
