"""Pipeline settings, read from environment variables (see .env.example).

Nothing is hard-coded so the same code runs locally, in Docker, and years
from now with a different date range or keyword list.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# The nine topics the team collects (README, data collection report).
DEFAULT_TOPICS = "mercury,venus,earth,mars,jupiter,saturn,uranus,neptune,galaxy"


class MissingDatabaseURL(RuntimeError):
    pass


def _env_list(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "y"}


def _env_int(name: str, default: str = "") -> int | None:
    """Integer from the environment; blank or unset means 'no limit'."""
    raw = os.getenv(name, default).strip()
    return int(raw) if raw else None


@dataclass(frozen=True)
class Settings:
    # PostgreSQL, e.g. postgresql+psycopg2://nasa:nasa@localhost:5432/nasa.
    # Docker Compose sets this to its own postgres service. Required: the
    # database code (src/database) uses PostgreSQL features such as JSONB.
    database_url: str | None = field(default_factory=lambda: os.getenv("DATABASE_URL"))
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("DATA_DIR", str(REPO_ROOT / "data")))
    )
    apod_start_date: str = field(
        default_factory=lambda: os.getenv("APOD_START_DATE", "2020-01-01")
    )
    library_keywords: list[str] = field(
        default_factory=lambda: _env_list("LIBRARY_KEYWORDS", DEFAULT_TOPICS)
    )
    # Blank = all years, matching the team's collection.
    library_year_start: int | None = field(
        default_factory=lambda: _env_int("LIBRARY_YEAR_START")
    )
    library_year_end: int | None = field(default_factory=lambda: _env_int("LIBRARY_YEAR_END"))
    # Pages of 100 results per topic for each scheduled run. The full
    # collection (up to 100 pages per topic) is Irene's one-off backfill.
    library_max_pages: int = field(
        default_factory=lambda: int(os.getenv("LIBRARY_MAX_PAGES", "2"))
    )
    # Offline mode replays tests/fixtures instead of calling NASA, so the
    # pipeline still runs if the APIs change or there is no network.
    offline: bool = field(default_factory=lambda: _env_bool("NASA_OFFLINE"))
    fixtures_dir: Path = REPO_ROOT / "tests" / "fixtures"

    def require_database_url(self) -> str:
        if not self.database_url:
            raise MissingDatabaseURL(
                "DATABASE_URL is not set. Use docker compose (it sets it for you) or "
                "export DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST:5432/DB"
            )
        return self.database_url


def get_settings() -> Settings:
    return Settings()
