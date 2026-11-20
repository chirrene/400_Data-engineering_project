"""DAG structure and end-to-end tests. Run: pytest tests/test_dag.py

Uses offline fixtures and a temporary SQLite database, so no network,
Docker or Postgres is needed.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

airflow = pytest.importorskip("airflow")
from airflow.models import DagBag  # noqa: E402
from airflow.utils.state import DagRunState  # noqa: E402


@pytest.fixture()
def offline_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NASA_OFFLINE", "1")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("APOD_START_DATE", "2020-01-01")
    return tmp_path


@pytest.fixture(scope="module")
def dag():
    bag = DagBag(dag_folder="dags", include_examples=False)
    assert not bag.import_errors, bag.import_errors
    return bag.get_dag("nasa_pipeline")


def test_dag_loads(dag):
    assert dag is not None
    assert len(dag.tasks) == 8


def test_dag_dependencies(dag):
    downstream = {t.task_id: {d.task_id for d in t.downstream_list} for t in dag.tasks}
    assert downstream["start_run"] == {"create_tables"}
    assert downstream["create_tables"] == {"extract_apod", "extract_library"}
    assert downstream["extract_apod"] == {"transform_load_apod"}
    assert downstream["extract_library"] == {"transform_load_library"}
    assert downstream["transform_load_apod"] == {"quality_checks"}
    assert downstream["transform_load_library"] == {"quality_checks"}
    assert downstream["quality_checks"] == {"finish_run"}
    assert downstream["finish_run"] == set()


def test_finish_run_always_runs(dag):
    assert dag.get_task("finish_run").trigger_rule == "all_done"


def _db_rows(tmp_path, sql):
    from sqlalchemy import create_engine

    with create_engine(f"sqlite:///{tmp_path / 'test.db'}").connect() as conn:
        return conn.execute(text(sql)).fetchall()


def _count(tmp_path, source_api):
    sql = f"SELECT COUNT(*) FROM nasa_records WHERE source_api = '{source_api}'"
    return _db_rows(tmp_path, sql)[0][0]


def test_end_to_end_offline_and_idempotent(dag, offline_env):
    first = dag.test()
    assert first.state == DagRunState.SUCCESS
    apod_count = _count(offline_env, "apod")
    lib_count = _count(offline_env, "nasa_library")
    assert apod_count > 0 and lib_count > 0

    # A second run must not create duplicates.
    second = dag.test()
    assert second.state == DagRunState.SUCCESS
    assert _count(offline_env, "apod") == apod_count
    assert _count(offline_env, "nasa_library") == lib_count

    runs = _db_rows(
        offline_env,
        "SELECT status, apod_loaded, library_loaded, duration_seconds, step_metrics "
        "FROM pipeline_runs ORDER BY started_at",
    )
    assert len(runs) == 2
    status, apod_loaded, library_loaded, duration, metrics = runs[-1]
    assert status == "success"
    assert apod_loaded == apod_count and library_loaded == lib_count
    assert duration is not None and duration >= 0
    assert "extract_apod" in json.loads(metrics)


def test_failed_step_is_recorded(dag, offline_env, monkeypatch):
    from src.pipeline import placeholders

    def broken(*_args, **_kwargs):
        raise RuntimeError("NASA API down")

    monkeypatch.setattr(placeholders, "fetch_apod", broken)
    for t in dag.tasks:  # don't wait through real retry delays in a test
        monkeypatch.setattr(t, "retries", 0)
    run = dag.test()
    assert run.state == DagRunState.FAILED
    status = _db_rows(offline_env, "SELECT status FROM pipeline_runs")[-1][0]
    assert status == "failed"
