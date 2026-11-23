"""Plain-Python bodies of the DAG tasks.

Kept free of Airflow imports so they can be unit-tested and run by hand
by hand. Large data moves between tasks as
JSON files under DATA_DIR/raw/<run_id>/; only small dicts go through XCom.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from src.pipeline import run_log
from src.pipeline.config import get_settings
from src.pipeline.contracts import resolve

log = logging.getLogger(__name__)


def _safe(run_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", run_id)


def _run_dir(run_id: str) -> Path:
    path = get_settings().data_dir / "raw" / _safe(run_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write(path: Path, records: list[dict]) -> None:
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")


def _read(path: str | Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def start_run(run_id: str) -> dict:
    # Fail on the first task with a clear message instead of a KeyError deep
    # inside src/database when DATABASE_URL is missing.
    get_settings().require_database_url()
    run_log.start_run(run_id)
    return {"run_id": run_id}


def create_tables() -> dict:
    func, source = resolve("create_tables")
    func()
    run_log.ensure_table()
    return {"source": source}


def _latest_apod_date() -> str | None:
    from sqlalchemy import text

    from src.pipeline.db import get_engine

    with get_engine().connect() as conn:
        latest = conn.execute(
            text("SELECT MAX(date) FROM nasa_records WHERE source_api = 'apod'")
        ).scalar()
    return str(latest)[:10] if latest else None


def extract_apod(run_id: str) -> dict:
    """Fetch APOD posts we don't have yet.

    The first run backfills from APOD_START_DATE; later runs start from the
    newest APOD date already stored (re-fetching that day in case it changed),
    so a daily run makes one or two requests instead of ~100.
    """
    settings = get_settings()
    latest = _latest_apod_date()
    start_date = max(settings.apod_start_date, latest) if latest else settings.apod_start_date
    func, source = resolve("fetch_apod")
    records = func(start_date)
    path = _run_dir(run_id) / "apod.json"
    _write(path, records)
    return {"path": str(path), "fetched": len(records), "start_date": start_date, "source": source}


def extract_library(run_id: str) -> dict:
    settings = get_settings()
    func, source = resolve("fetch_library")
    records: list[dict] = []
    per_keyword = {}
    for keyword in settings.library_keywords:
        batch = func(
            keyword,
            settings.library_year_start,
            settings.library_year_end,
            settings.library_max_pages,
        )
        per_keyword[keyword] = len(batch)
        records.extend(batch)
    path = _run_dir(run_id) / "library.json"
    _write(path, records)
    return {"path": str(path), "fetched": len(records), "per_keyword": per_keyword, "source": source}


def _transform_load(extract_result: dict, normalize_step: str) -> dict:
    normalize, n_source = resolve(normalize_step)
    validate, v_source = resolve("validate_records")
    load, l_source = resolve("load_records")
    rows = normalize(_read(extract_result["path"]))
    valid, validation = validate(rows)
    loaded = load(valid)
    return {
        "normalized": len(rows),
        **validation,
        "loaded": loaded,
        "source": {"normalize": n_source, "validate": v_source, "load": l_source},
    }


def transform_load_apod(extract_result: dict) -> dict:
    return _transform_load(extract_result, "normalize_apod")


def transform_load_library(extract_result: dict) -> dict:
    return _transform_load(extract_result, "normalize_library")


def quality_checks() -> dict:
    func, source = resolve("run_quality_checks")
    results = func()
    failures = sum(results.values())
    for name, count in results.items():
        log.info("quality check %-28s %s", name, "OK" if count == 0 else f"{count} failing rows")
    # Failing rows are recorded, not fatal: NASA data has known gaps and we
    # want the run to finish and report them. Broken code still fails the task.
    return {"checks": results, "failures": failures, "source": source}


def finish_run(run_id: str, status: str, results: dict[str, dict | None], durations: dict) -> dict:
    """Write the run summary row. ``results`` maps task_id -> its return value."""

    def get(task: str, key: str):
        return (results.get(task) or {}).get(key)

    summary = {
        "apod_fetched": get("extract_apod", "fetched"),
        "apod_loaded": get("transform_load_apod", "loaded"),
        "library_fetched": get("extract_library", "fetched"),
        "library_loaded": get("transform_load_library", "loaded"),
        "quality_failures": get("quality_checks", "failures"),
        "invalid_dropped": sum(
            get(t, "invalid_dropped") or 0
            for t in ("transform_load_apod", "transform_load_library")
        ),
    }
    step_metrics = {
        task: {"duration_s": durations.get(task), **(res or {})} for task, res in results.items()
    }
    run_log.finish_run(run_id, status, summary, step_metrics)
    log.info("run %s finished: %s %s", run_id, status, summary)
    return {"status": status, **summary}
