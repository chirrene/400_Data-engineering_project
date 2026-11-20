"""Pipeline settings, read from environment variables (see .env.example).

Nothing is hard-coded so the same code runs locally, in Docker, and years
from now with a different date range or keyword list.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _env_list(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "y"}


@dataclass(frozen=True)
class Settings:
    # Postgres in Docker, e.g. postgresql+psycopg2://nasa:nasa@postgres:5432/nasa
    # Falls back to a local SQLite file so the DAG can run without Docker.
    # DATABASE_PATH (a SQLite file, from the team .env.example) is used when
    # DATABASE_URL is not set.
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL")
        or f"sqlite:///{REPO_ROOT / os.getenv('DATABASE_PATH', 'data/nasa.db')}"
    )
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("DATA_DIR", str(REPO_ROOT / "data")))
    )
    # Team decision: keep the scope to 2020 onward.
    apod_start_date: str = field(
        default_factory=lambda: os.getenv("APOD_START_DATE", "2020-01-01")
    )
    library_keywords: list[str] = field(
        default_factory=lambda: _env_list("LIBRARY_KEYWORDS", "mars,jupiter,galaxy,nebula")
    )
    library_year_start: int = field(
        default_factory=lambda: int(os.getenv("LIBRARY_YEAR_START", "2020"))
    )
    library_year_end: int = field(
        default_factory=lambda: int(os.getenv("LIBRARY_YEAR_END", "2026"))
    )
    # Pages of 100 results per keyword; keeps a run short.
    library_max_pages: int = field(
        default_factory=lambda: int(os.getenv("LIBRARY_MAX_PAGES", "2"))
    )
    # Offline mode replays tests/fixtures instead of calling NASA, so the
    # pipeline still runs if the APIs change or there is no network.
    offline: bool = field(default_factory=lambda: _env_bool("NASA_OFFLINE"))
    fixtures_dir: Path = REPO_ROOT / "tests" / "fixtures"


def get_settings() -> Settings:
    return Settings()
