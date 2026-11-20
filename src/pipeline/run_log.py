"""pipeline_runs: one row per DAG run, so every run is measured start to finish."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import text

from src.pipeline.db import get_engine

DDL = """CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    status TEXT NOT NULL,
    apod_fetched INTEGER,
    apod_loaded INTEGER,
    library_fetched INTEGER,
    library_loaded INTEGER,
    invalid_dropped INTEGER,
    quality_failures INTEGER,
    duration_seconds REAL,
    step_metrics TEXT
)"""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_table() -> None:
    with get_engine().begin() as conn:
        conn.execute(text(DDL))


def start_run(run_id: str) -> None:
    ensure_table()
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO pipeline_runs (run_id, started_at, status) "
                "VALUES (:run_id, :started_at, 'running') "
                "ON CONFLICT (run_id) DO UPDATE SET started_at = excluded.started_at, "
                "status = 'running', finished_at = NULL"
            ),
            {"run_id": run_id, "started_at": _now()},
        )


def finish_run(run_id: str, status: str, summary: dict, step_metrics: dict) -> None:
    ensure_table()
    with get_engine().begin() as conn:
        started = conn.execute(
            text("SELECT started_at FROM pipeline_runs WHERE run_id = :run_id"),
            {"run_id": run_id},
        ).scalar()
        finished = _now()
        if isinstance(started, str):  # SQLite returns text
            started = datetime.fromisoformat(started)
        duration = (finished - started).total_seconds() if started else None
        conn.execute(
            text(
                "UPDATE pipeline_runs SET finished_at = :finished_at, status = :status, "
                "apod_fetched = :apod_fetched, apod_loaded = :apod_loaded, "
                "library_fetched = :library_fetched, library_loaded = :library_loaded, "
                "invalid_dropped = :invalid_dropped, quality_failures = :quality_failures, duration_seconds = :duration, "
                "step_metrics = :step_metrics WHERE run_id = :run_id"
            ),
            {
                "run_id": run_id,
                "finished_at": finished,
                "status": status,
                "apod_fetched": summary.get("apod_fetched"),
                "apod_loaded": summary.get("apod_loaded"),
                "library_fetched": summary.get("library_fetched"),
                "library_loaded": summary.get("library_loaded"),
                "invalid_dropped": summary.get("invalid_dropped"),
                "quality_failures": summary.get("quality_failures"),
                "duration": duration,
                "step_metrics": json.dumps(step_metrics, default=str),
            },
        )
