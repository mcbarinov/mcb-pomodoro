"""Centralized application configuration."""

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from mb_pomodoro.time_utils import parse_duration

DEFAULT_DATA_DIR = Path.home() / ".local" / "mb-pomodoro"


class Config(BaseModel):
    """Application-wide configuration."""

    model_config = ConfigDict(frozen=True)

    data_dir: Path = Field(description="Base directory for all application data")
    default_duration: str = Field(default="25", description="Default timer duration (e.g. '25', '25m', '90s', '10m30s')")

    @computed_field(description="SQLite database file")
    @property
    def db_path(self) -> Path:
        """SQLite database file."""
        return self.data_dir / "pomodoro.db"

    @computed_field(description="Timer worker PID file")
    @property
    def timer_worker_pid_path(self) -> Path:
        """Timer worker PID file."""
        return self.data_dir / "timer_worker.pid"

    @computed_field(description="Menu bar tray PID file")
    @property
    def tray_pid_path(self) -> Path:
        """Menu bar tray PID file."""
        return self.data_dir / "tray.pid"

    @computed_field(description="Rotating log file")
    @property
    def log_path(self) -> Path:
        """Rotating log file."""
        return self.data_dir / "pomodoro.log"

    @computed_field(description="Optional TOML configuration file")
    @property
    def config_path(self) -> Path:
        """Optional TOML configuration file."""
        return self.data_dir / "config.toml"

    def cli_base_args(self) -> list[str]:
        """Build CLI base args, including --data-dir only when non-default."""
        args: list[str] = ["mb-pomodoro"]
        if self.data_dir != DEFAULT_DATA_DIR:
            args.extend(["--data-dir", str(self.data_dir)])
        return args

    @staticmethod
    def build(data_dir: Path | None = None) -> Config:
        """Build a Config instance from defaults and optional config.toml."""
        resolved_dir = data_dir if data_dir is not None else DEFAULT_DATA_DIR
        config_path = resolved_dir / "config.toml"

        kwargs: dict[str, Any] = {"data_dir": resolved_dir}
        if config_path.is_file():
            with config_path.open("rb") as f:
                toml_data = tomllib.load(f)
            timer = toml_data.get("timer", {})
            if isinstance(timer, dict):
                val = timer.get("default_duration")
                if isinstance(val, str) and parse_duration(val) is not None:
                    kwargs["default_duration"] = val

        return Config(**kwargs)
