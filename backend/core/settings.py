import os
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


def default_state_dir() -> Path:
    if getattr(sys, "frozen", False):
        xdg_data_home = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
        return base / "automation-toolbox"
    return ROOT_DIR


def default_workers() -> int:
    return min(4, max(1, (os.cpu_count() or 2) // 2))


def available_cpu_count() -> int:
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except AttributeError:
        return max(1, os.cpu_count() or 1)


def recommended_parallel_workers(max_task_workers: int) -> int:
    return max(1, min(32, available_cpu_count() // max(1, max_task_workers)))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_prefix="TOOLBOX_",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    max_workers: int = Field(default_factory=default_workers, ge=1, le=32)
    parallel_workers: int = Field(default=0, ge=0, le=32)
    cancel_timeout: float = Field(default=5.0, ge=1.0, le=60.0)
    data_dir: Path = Field(default_factory=lambda: default_state_dir() / "data")
    log_dir: Path = Field(default_factory=lambda: default_state_dir() / "logs")
    database_path: Path | None = None
    auth_disabled: bool = True
    session_token: str | None = None

    @property
    def resolved_database_path(self) -> Path:
        return self.database_path or self.data_dir / "toolbox.sqlite3"


@lru_cache
def get_settings() -> Settings:
    return Settings()
