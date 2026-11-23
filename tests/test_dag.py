"""DAG structure and end-to-end tests. Run: pytest tests/test_dag.py

Structure tests need only Airflow. End-to-end tests replay offline fixtures
(no network) into a real PostgreSQL database given by TEST_DATABASE_URL, e.g.

    TEST_DATABASE_URL=postgresql+psycopg2://nasa:nasa@localhost:5432/nasa_test

They drop and recreate the pipeline tables there, so never point it at a
database you care about. Without TEST_DATABASE_URL they are skipped.
"""
from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import text

airflow = pytest.importorskip("airflow")
from airflow.models import DagBag  # noqa: E402
from airflow.utils.state import DagRunState  # noqa: E402


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
needs_postgres = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="set TEST_DATABASE_URL to a throwaway PostgreSQL database"
)


@pytest.fixture()
def offline_env(tmp_path, monkeypatch):
    from sqlalchemy import create_engine

    monkeypatch.setenv("NASA_OFFLINE", "1")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("APOD_START_DATE", "2020-01-01")
    monkeypatch.setenv("LIBRARY_KEYWORDS", "mars,jupiter,galaxy")
    with create_engine(TEST_DATABASE_URL).begin() as conn:
        conn.execute(
            text("DROP TABLE IF EXISTS nasa_search_matches, nasa_records, pipeline_runs")
        )
    return TEST_DATABASE_URL


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


def _db_rows(url, sql):
    from sqlalchemy import create_engine

    with create_engine(url).connect() as conn:
        return conn.execute(text(sql)).fetchall()


def _count(url, source_api):
    sql = f"SELECT COUNT(*) FROM nasa_records WHERE source_api = '{source_api}'"
    return _db_rows(url, sql)[0][0]


def test_missing_database_url_fails_clearly(monkeypatch):
    from src.pipeline import tasks
    from src.pipeline.config import MissingDatabaseURL

    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(MissingDatabaseURL, match="DATABASE_URL is not set"):
        tasks.start_run("manual__test")


@needs_postgres
def test_end_to_end_offline_and_idempotent(dag, offline_env):
    first = dag.test()
    assert first.state == DagRunState.SUCCESS
    apod_count = _count(offline_env, "apod")
    lib_count = _count(offline_env, "nasa_library")
    assert apod_count > 0 and lib_count > 0

    # A second run must not create duplicates, and APOD only re-fetches from
    # the newest stored date.
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
    assert [r[0] for r in runs] == ["success", "success"]
    # First run backfills every APOD post; the second only the newest day.
    assert runs[0][1] == apod_count
    assert runs[1][1] == 1
    assert all(r[2] == lib_count for r in runs)
    assert all(r[3] is not None and r[3] >= 0 for r in runs)
    assert json.loads(runs[0][4])["extract_apod"]["start_date"] == "2020-01-01"
    assert json.loads(runs[1][4])["extract_apod"]["start_date"] > "2020-01-01"
    # Topic links land in Lize's relationship table.
    topics = {
        row[0]
        for row in _db_rows(offline_env, "SELECT DISTINCT search_keyword FROM nasa_search_matches")
    }
    assert topics == {"mars", "jupiter", "galaxy"}


@needs_postgres
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
