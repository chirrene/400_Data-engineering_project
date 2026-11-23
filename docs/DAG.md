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
| `DATABASE_URL` | set by Compose | PostgreSQL URL. Required outside Docker, e.g. `postgresql+psycopg2://nasa:nasa@localhost:5433/nasa` |
| `APOD_START_DATE` | `2020-01-01` | First run backfills APOD from here; later runs fetch only new days |
| `LIBRARY_KEYWORDS` | the 9 team topics | Comma-separated search topics |
| `LIBRARY_YEAR_START` / `_END` | blank | Image Library year filter; blank = all years |
| `LIBRARY_MAX_PAGES` | `2` | Pages of 100 per topic per run |
| `NASA_OFFLINE` | `0` | `1` replays `tests/fixtures/` instead of calling NASA |
| `DATA_DIR` | `data/` | Where raw JSON per run is written |

## Running with Docker Compose (recommended)

Needs only [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
cp .env.example .env          # optional, defaults work as-is
docker compose up --build
```

| Service | URL | Notes |
|---|---|---|
| Airflow | http://localhost:8080 | Log in with `admin` / `admin` (change in `.env`). Unpause `nasa_pipeline`, then click Trigger |
| Dashboard | http://localhost:8501 | Reads the local database, so it fills up as the DAG runs |
| PostgreSQL | `localhost:5433` | `nasa` / `nasa`, database `nasa`; tables come from `sql/schema.sql` |

* The first run backfills APOD from 2020 (about 100 API pages, a few minutes).
  Daily runs after that fetch only new days.
* Each run pulls `LIBRARY_MAX_PAGES` pages per topic. The full collection
  (up to 100 pages per topic) is the one-off backfill in `src/apis/collect_planets.py`.
* Compose never uses the `DATABASE_URL` from `.env`, so it can't write to the
  team's cloud database by accident.
* Stop with `Ctrl+C`; `docker compose down -v` also deletes the local database.

Check what each run did:

```bash
docker compose exec postgres psql -U nasa -d nasa -c "SELECT run_id, status, apod_loaded, library_loaded, quality_failures, round(duration_seconds) FROM pipeline_runs ORDER BY started_at DESC;"
```

## Running without Docker

Python 3.11 and a PostgreSQL database are needed.

```bash
pip install -r requirements-airflow.txt \
  --constraint https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.11.txt
export DATABASE_URL=postgresql+psycopg2://nasa:nasa@localhost:5432/nasa
export AIRFLOW_HOME=$PWD/.airflow AIRFLOW__CORE__DAGS_FOLDER=$PWD/dags AIRFLOW__CORE__LOAD_EXAMPLES=False
airflow db migrate
airflow dags test nasa_pipeline      # one full run, no scheduler or UI
```

## Tests

```bash
pytest tests/test_dag.py tests/test_pipeline_tasks.py
```

Structure and adapter tests need no database. The two end-to-end tests replay
offline fixtures into PostgreSQL and run only when `TEST_DATABASE_URL` points
at a **throwaway** database (they drop and recreate the tables):

```bash
TEST_DATABASE_URL=postgresql+psycopg2://nasa:nasa@localhost:5433/nasa_test pytest tests/test_dag.py
```
