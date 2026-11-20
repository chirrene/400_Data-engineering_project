"""Database connection shared by the pipeline (SQLAlchemy, Postgres or SQLite)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from src.pipeline.config import get_settings


@lru_cache(maxsize=4)
def _engine_for(url: str) -> Engine:
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, future=True)


def get_engine() -> Engine:
    return _engine_for(get_settings().database_url)
