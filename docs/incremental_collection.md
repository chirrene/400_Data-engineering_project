# Incremental Mars and Earth collection

Implementation only: no full collection, final export replacement, or database update
was performed during development. Existing collectors, normalizer, exporter, importer,
notebooks, application, and schema remain unchanged.

## Commands

Run from the repository root using the project's Python environment (with `requests`
and `python-dotenv` installed). On this machine `/opt/anaconda3/bin/python` has these
dependencies; the default `python3` does not.

```sh
cd /Users/zhuxumo/Desktop/400_Data-engineering_project
/opt/anaconda3/bin/python -m src.processing.incremental_collection collect
```

This command only writes `data/incremental/nasa_library/`. Repeat the same command to
resume after interruption. It never writes processed exports or contacts PostgreSQL.
The existing API client supplies request timeouts and HTTP retries; the new workflow
adds bounded attempts (`--attempts 3`), exponential backoff, and a default 0.5-second
pause before each request (`--delay 0.5`). Logs go to the terminal.

After collection finishes, inspect `data/incremental/nasa_library/collection_summary.json`.
A complete status requires both Mars and Earth to pass all coverage checks. Exit code
2 means incomplete coverage; exit code 1 means an operation failed; 0 means success.
Incomplete runs cannot prepare or merge by default. A documented reconciliation can
use an explicitly approved partial-coverage option; see [reconciliation](incremental_reconciliation.md). Successful page checkpoints remain available
when a request fails. Ctrl-C also preserves all previously saved pages; rerun collect
to regenerate the summary. An intermediate summary may lack a final overall status.

Prepare and verify candidate files before merging:

```sh
/opt/anaconda3/bin/python -m src.processing.incremental_collection prepare
/opt/anaconda3/bin/python -m src.processing.incremental_collection verify
cat data/incremental/nasa_library/validation_summary.json
```

`prepare` reads the original exports and the collected additions, and writes a fresh
candidate directory under `data/incremental/nasa_library/candidates/`. The validation
summary identifies the exact directory, counts before/after, additions, topic totals,
and SHA-256 checksums. Inspect its two JSONL files directly if desired. `verify`
performs offline checks again and makes no NASA requests. Existing export files are
still unchanged at this point. No existing raw topic files are needed.

Only after reviewing these results, explicitly replace the exports:

```sh
/opt/anaconda3/bin/python -m src.processing.incremental_collection merge
```

This revalidates, writes and verifies exact backups in
`data/processed/nasa_library/incremental_backups/<transaction>/`, saves a manifest,
and publishes the candidates. If the originals, candidate files, collection summary,
or additions changed since preparation, merge refuses to proceed.

After a successful merge, manually run the existing importer:

```sh
/opt/anaconda3/bin/python -m src.database.import_clean_exports data/processed/nasa_library
```

Only that last command updates PostgreSQL. It uses the existing configured database
connection and upsert pipeline. The incremental script never imports database code.
Do not run `export_clean_data.py` on intermediate data.

## Collection and coverage

Only Mars and Earth are requested. Each topic first gets an unfiltered first page to
record `total_hits`. Search uses the complete four-digit calendar-year span
`0001`–`9999`, including historical and future-dated archive metadata. Existing data
already includes dates in 2027. NASA documents year filters as `YYYY` and defaults to
100 items per page: [official NASA API documentation](https://images.nasa.gov/docs/images.nasa.gov_api_docs.pdf).
No narrow contemporary date cutoff is used.

Every filtered range is checked using `total_hits`. If its total exceeds 10,000,
the range is recursively split into disjoint inclusive ranges until accessible or
reduced to one year. Each leaf requests exactly `ceil(total_hits / 100)` pages, capped
at 100. No request ever goes to page 101. An oversized individual year collects up to
100 pages and reports its inaccessible remainder and incomplete status.

Checks include expected page lengths, stable totals within a range, valid image
metadata and dates, normalization losses, unique ID counts per range, and equality
of the overall unique record count and ranged totals to the unfiltered total. Missing
or unfilterable dates, count drift, unexpected short pages, duplicates across pages,
and malformed responses cannot be reported as complete.

The API has no snapshot token. A complete status describes the responses cached for
this run, not a guarantee of NASA's live catalog at a later time. Same-count catalog
changes cannot always be detected. Use a fresh `--run-dir` for a new catalog refresh.
This option must be passed consistently to all subsequent commands. If a saved page
is corrupted, it is refused. To repair a known corrupt or stale response, remove that
specific page checkpoint while no command is running, then rerun collect; alternatively
use a fresh run directory. Re-run prepare after any new collection.

## Data protection and replacement limits

Images are keyed by `(source_api, source_id)`; topics by
`(source_api, source_id, search_topic)`. All original rows and their full metadata win
on key collisions. Newly discovered relationships are added even for existing images.
The existing `normalize_nasa_library()` is reused; new images receive the existing
exporter's missing-title placeholder/flag. The existing `validate_record()` validates
required fields and dates. All nine topics are preserved; seven are never fetched.

Before publishing, validation reads both complete candidate JSONL files, rejects
invalid JSON/keys, duplicate keys and orphan relationships, and verifies every original
row is present with exactly the same values. Originals are hashed before preparation
and checked again at merge. Backups are byte-for-byte copies verified by SHA-256.

Each file is written to a same-directory temporary file, flushed with `fsync`, and
atomically renamed. Two fixed separate filenames **cannot** be replaced together in
one filesystem-atomic transaction. There is a brief interval between renames; stop
other readers/writers (including the importer) during merge. Caught failures trigger
rollback of both originals. A durable journal handles process kill or power loss:

```sh
/opt/anaconda3/bin/python -m src.processing.incremental_collection recover
```

Recovery restores both original files from the verified backup. Merge also attempts
recovery before proceeding. A pending journal blocks preparation/verification so an
interrupted pair cannot become the next baseline. If rollback itself fails, the
journal and backups remain for another recovery attempt. Never delete them manually
before recovery. Locks prevent concurrent incremental commands, but cannot coordinate
unrelated programs that ignore the locks. Original data remains untouched on validation
or backup failure. Successfully merged files and backups remain in place.

## Offline testing

```sh
/opt/anaconda3/bin/python -m unittest discover -s tests -p test_incremental_collection.py -v
```

Tests use temporary directories and mocked requests. This command avoids the existing
pytest/Airflow autouse fixture, which initializes an Airflow metadata database. Tests
cover deduplication, exact preservation, topic integrity, resumability, retries, malformed
responses/checkpoints, recursive splitting, single-year overflow, page 100/101 bounds,
candidate tampering, changed originals, backup failures, replacement rollback,
interrupted-transaction recovery, and locks. No test changes the project dataset or
PostgreSQL.
