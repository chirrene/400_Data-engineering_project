# DAG & automation (`dags/nasa_pipeline.py`)

Owner: Andy

## What it does

```
start_run -> create_tables -> extract_apod    -> transform_load_apod    -> quality_checks -> finish_run
                           -> extract_library -> transform_load_library ->
```

| Task | What happens |
|---|---|
| `start_run` | Inserts a `running` row into `pipeline_runs` |
| `create_tables` | Creates tables if they don't exist |
| `extract_apod` | APOD posts since `APOD_START_DATE`, saved to `data/raw/<run_id>/apod.json` |
| `extract_library` | Image Library search for each of `LIBRARY_KEYWORDS`, saved to `library.json` |
| `transform_load_*` | Normalizes, validates (drops and counts invalid records) and upserts (re-running never creates duplicates) |
| `quality_checks` | Counts failing rows per check; failures are recorded, not fatal |
| `finish_run` | Always runs. Writes status, row counts, quality failures, total and per-step durations to `pipeline_runs`; if any step failed it records `failed` and fails the run |

Schedule: daily, no catch-up, one run at a time. API tasks retry 3 times with
exponential backoff, others 2 times.

### Measuring the pipeline

```sql
SELECT run_id, status, apod_fetched, apod_loaded, library_fetched, library_loaded,
       quality_failures, duration_seconds
FROM pipeline_runs ORDER BY started_at DESC;
```

`step_metrics` holds a JSON object with each task's duration and result
(including which module ran the step, so you can see placeholders vs real code).

## Interface with teammates

All records use the unified schema from Irene's `src/processing/normalize.py`
(`source_api, source_id, date, title, media_type, image_url, page_url,
explanation, credit, alt_text, center, location, keywords, asset_manifest_url`).
Image Library records also get `search_keyword`.

`src/pipeline/contracts.py` maps each step onto teammates' code through small
adapters, so nobody has to change their function signatures for the DAG. A
step whose code doesn't exist yet runs a placeholder from
`src/pipeline/placeholders.py`; the task log says `using placeholder` and
`pipeline_runs.step_metrics` records which module ran.

| Step | Calls | Owner | Status |
|---|---|---|---|
| fetch APOD | `src.apis.apod_client.fetch_apod` | Irene | Current version returns only the newest page, so the DAG pages back to `APOD_START_DATE` itself. Add a `start_date` parameter and the DAG uses it automatically |
| fetch Image Library | `src.apis.image_library_client.fetch_nasa_library_pages(query, max_pages, start_year, end_year)` | Irene | Used |
| normalize | `src.processing.normalize.normalize_apod(record)` per record, `normalize_nasa_library(raw)` per keyword | Irene | Used |
| validate | `src.processing.validate.validate_record`, `find_duplicate_records` | Irene | Used; invalid records are dropped and counted (`invalid_dropped`) |
| create tables | `src.database.db.create_tables()` | Lize | Placeholder: one `nasa_records` table, key `(source_api, source_id, search_keyword)` |
| load | `src.database.load_data.load_records(records) -> int` | Lize | Placeholder upsert |
| quality checks | `src.database.queries.run_quality_checks() -> dict[str, int]` | Lize | Placeholder SQL checks |

Rules that keep the DAG reliable:

* **Loads must be idempotent** (`INSERT ... ON CONFLICT DO UPDATE`): Airflow
  retries tasks, and the same day can be re-run.
* **Raise on real errors** (network down, bad SQL). Don't catch and return `[]`,
  or the run looks successful with no data.
* `pipeline_runs` is owned by the DAG (`src/pipeline/run_log.py`); please don't
  drop it in `schema.sql`.

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | unset | Overrides `DATABASE_PATH`, e.g. Postgres in Docker: `postgresql+psycopg2://nasa:nasa@postgres:5432/nasa` |
| `DATABASE_PATH` | `data/nasa.db` | SQLite file used when `DATABASE_URL` is unset |
| `APOD_START_DATE` | `2020-01-01` | Earliest APOD date to fetch |
| `LIBRARY_KEYWORDS` | `mars,jupiter,galaxy,nebula` | Comma-separated search terms |
| `LIBRARY_YEAR_START` / `_END` | `2020` / `2026` | Image Library year filter |
| `LIBRARY_MAX_PAGES` | `2` | Pages of 100 per keyword |
| `NASA_OFFLINE` | `0` | `1` replays `tests/fixtures/` instead of calling NASA |
| `DATA_DIR` | `data/` | Where raw JSON per run is written |

## Running

Tests (offline, temporary SQLite, no Docker needed):

```bash
pip install -r requirements-airflow.txt
pytest tests/
```

Run the whole DAG once without the scheduler or UI:

```bash
export AIRFLOW_HOME=$PWD/.airflow AIRFLOW__CORE__DAGS_FOLDER=$PWD/dags AIRFLOW__CORE__LOAD_EXAMPLES=False
airflow db migrate
airflow dags test nasa_pipeline
```

With the UI: `airflow standalone`, open http://localhost:8080, turn on
`nasa_pipeline` and click Trigger. In Docker, Irene's `docker-compose.yml`
should mount `dags/` and `src/` and set `PYTHONPATH=/opt/airflow` plus the
variables above.
