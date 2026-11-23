"""Database connection for the pipeline's own tables (pipeline_runs).

Uses the same DATABASE_URL as src/database, so run logs and NASA records live
in the same PostgreSQL database.
"""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from src.pipeline.config import get_settings


@lru_cache(maxsize=4)
def _engine_for(url: str) -> Engine:
    return create_engine(url, future=True, pool_pre_ping=True)


def get_engine() -> Engine:
    return _engine_for(get_settings().require_database_url())
