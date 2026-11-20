"""
### NASA Space Explorer pipeline

API -> raw JSON -> clean -> database -> quality checks, measured start to finish.

```
start_run -> create_tables -> extract_apod    -> transform_load_apod    -> quality_checks -> finish_run
                           -> extract_library -> transform_load_library ->
```

* **start_run / finish_run** write one row per run to `pipeline_runs`
  (rows fetched and loaded, quality failures, per-step durations, status).
  `finish_run` runs even when a step fails, records the failure, then fails
  the DAG run so it shows red in the UI.
* Task bodies live in `src/pipeline/tasks.py`; which teammate module each
  step calls is set in `src/pipeline/contracts.py`.
* Settings come from environment variables; see `.env.example`.
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.decorators import dag, task
from airflow.exceptions import AirflowException
from airflow.utils.state import TaskInstanceState
from airflow.utils.trigger_rule import TriggerRule

# Make `src` importable when Airflow loads this file from dags/.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.pipeline import tasks  # noqa: E402

RESULT_TASKS = [
    "create_tables",
    "extract_apod",
    "extract_library",
    "transform_load_apod",
    "transform_load_library",
    "quality_checks",
]
FAILED_STATES = {TaskInstanceState.FAILED, TaskInstanceState.UPSTREAM_FAILED}

default_args = {
    "owner": "andy",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "retry_exponential_backoff": True,
    "execution_timeout": timedelta(minutes=30),
}


@dag(
    dag_id="nasa_pipeline",
    description="NASA APOD + Image Library: API -> database -> quality checks",
    schedule="@daily",
    start_date=pendulum.datetime(2026, 11, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["nasa", "mlds400"],
    doc_md=__doc__,
)
def nasa_pipeline():
    @task
    def start_run(run_id=None):
        return tasks.start_run(run_id)

    @task
    def create_tables():
        return tasks.create_tables()

    @task(retries=3)
    def extract_apod(run_id=None):
        return tasks.extract_apod(run_id)

    @task(retries=3)
    def extract_library(run_id=None):
        return tasks.extract_library(run_id)

    @task
    def transform_load_apod(extract_result: dict):
        return tasks.transform_load_apod(extract_result)

    @task
    def transform_load_library(extract_result: dict):
        return tasks.transform_load_library(extract_result)

    @task
    def quality_checks():
        return tasks.quality_checks()

    @task(trigger_rule=TriggerRule.ALL_DONE, retries=0)
    def finish_run(run_id=None, dag_run=None, ti=None):
        instances = {
            t.task_id: t for t in dag_run.get_task_instances() if t.task_id != ti.task_id
        }
        failed = sorted(tid for tid, t in instances.items() if t.state in FAILED_STATES)
        results = {tid: ti.xcom_pull(task_ids=tid) for tid in RESULT_TASKS}
        durations = {tid: t.duration for tid, t in instances.items()}
        summary = tasks.finish_run(
            run_id, "failed" if failed else "success", results, durations
        )
        if failed:
            raise AirflowException(f"Pipeline failed at: {', '.join(failed)}")
        return summary

    started = start_run()
    tables = create_tables()
    apod_raw = extract_apod()
    library_raw = extract_library()
    apod_loaded = transform_load_apod(apod_raw)
    library_loaded = transform_load_library(library_raw)
    checks = quality_checks()
    finished = finish_run()

    started >> tables >> [apod_raw, library_raw]
    [apod_loaded, library_loaded] >> checks >> finished


nasa_pipeline()
