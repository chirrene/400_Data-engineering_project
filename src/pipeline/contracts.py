"""The functions the DAG calls, and how they map onto teammates' code.

The DAG never imports teammates' modules directly. For each step it asks
``resolve(step)``, which returns:

* an **adapter** around the teammate's function when it exists (adapters
  translate between the DAG's batch-oriented calls and each module's own
  signature), or
* a working **placeholder** from ``placeholders.py`` until it does,

so the DAG runs end to end at every stage of the project.

Record schema: the unified dict produced by Irene's ``src.processing.normalize``
(source_api, source_id, date, title, media_type, image_url, page_url,
explanation, credit, alt_text, center, location, keywords,
asset_manifest_url). Image Library records also carry ``search_keyword``.

Current mapping (see docs/DAG.md):

  Step               | Uses                                                  | Owner
  -------------------|-------------------------------------------------------|------
  fetch_apod         | src.apis.apod_client.fetch_apod                       | Irene
  fetch_library      | src.apis.image_library_client.fetch_nasa_library_pages| Irene
  normalize_apod     | src.processing.normalize.normalize_apod  (per record) | Irene
  normalize_library  | src.processing.normalize.normalize_nasa_library       | Irene
  validate_records   | src.processing.validate.validate_record,              | Irene
                     |   find_duplicate_records                              |
  create_tables      | src.database.db.create_tables()                       | Lize
  load_records       | src.database.load_data.load_records(records) -> int   | Lize
  run_quality_checks | src.database.queries.run_quality_checks() -> dict     | Lize
"""
from __future__ import annotations

import importlib
import inspect
import logging
from typing import Callable

from src.pipeline import placeholders
from src.pipeline.config import get_settings

log = logging.getLogger(__name__)

PLACEHOLDER = "src.pipeline.placeholders"


def _find(module_name: str, func_name: str) -> Callable | None:
    """Return a teammate's function, or None if it doesn't exist yet."""
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        # Fall back only when the teammate module itself is missing, not when
        # one of *its* imports is broken; that should fail loudly.
        if exc.name and module_name.startswith(exc.name):
            return None
        raise
    return getattr(module, func_name, None)


def _accepts(func: Callable, param: str) -> bool:
    try:
        return param in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


# ------------------------------------------------------------- adapters
def _fetch_apod() -> tuple[Callable, str]:
    func = _find("src.apis.apod_client", "fetch_apod")
    if func is None or get_settings().offline:
        return placeholders.fetch_apod, PLACEHOLDER
    if _accepts(func, "start_date"):
        return (lambda start_date: func(start_date=start_date)), "src.apis.apod_client"
    # Irene's current fetch_apod() returns only the newest page, so it can't
    # backfill from APOD_START_DATE. Use the DAG's paging until it can.
    log.warning(
        "src.apis.apod_client.fetch_apod() has no start_date parameter; "
        "using placeholder paging for the APOD backfill"
    )
    return placeholders.fetch_apod, PLACEHOLDER


def _fetch_library() -> tuple[Callable, str]:
    func = _find("src.apis.image_library_client", "fetch_nasa_library_pages")
    if func is None or get_settings().offline:
        return placeholders.fetch_library, PLACEHOLDER

    def adapter(keyword: str, year_start: int, year_end: int, max_pages: int) -> list[dict]:
        body = func(query=keyword, max_pages=max_pages, start_year=year_start, end_year=year_end)
        items = body.get("collection", {}).get("items", [])
        for item in items:
            item["_keyword"] = keyword
        return items

    return adapter, "src.apis.image_library_client"


def _normalize_apod() -> tuple[Callable, str]:
    func = _find("src.processing.normalize", "normalize_apod")
    if func is None:
        return placeholders.normalize_apod, PLACEHOLDER
    # Irene's normalize_apod takes one record; the DAG passes a batch.
    return (lambda records: [func(r) for r in records]), "src.processing.normalize"


def _normalize_library() -> tuple[Callable, str]:
    func = _find("src.processing.normalize", "normalize_nasa_library")
    if func is None:
        return placeholders.normalize_library, PLACEHOLDER

    def adapter(records: list[dict]) -> list[dict]:
        # Irene's function takes the API's {"collection": {"items": [...]}}
        # shape and drops our search keyword, so normalise per keyword.
        by_keyword: dict[str | None, list[dict]] = {}
        for item in records:
            by_keyword.setdefault(item.get("_keyword"), []).append(item)
        out = []
        for keyword, items in by_keyword.items():
            for row in func({"collection": {"items": items}}):
                row["search_keyword"] = keyword
                out.append(row)
        return out

    return adapter, "src.processing.normalize"


def _validate_records() -> tuple[Callable, str]:
    validate = _find("src.processing.validate", "validate_record")
    duplicates = _find("src.processing.validate", "find_duplicate_records")
    if validate is None:
        return placeholders.validate_records, PLACEHOLDER

    def adapter(records: list[dict]) -> tuple[list[dict], dict]:
        valid = [r for r in records if validate(r)["is_valid"]]
        dupes = len(duplicates(valid)) if duplicates else 0
        return valid, {
            "invalid_dropped": len(records) - len(valid),
            "duplicates_in_batch": dupes,
        }

    return adapter, "src.processing.validate"


def _by_name(module_name: str, func_name: str, step: str) -> Callable[[], tuple[Callable, str]]:
    def resolver() -> tuple[Callable, str]:
        func = _find(module_name, func_name)
        if func is None:
            return getattr(placeholders, step), PLACEHOLDER
        return func, module_name

    return resolver


RESOLVERS: dict[str, Callable[[], tuple[Callable, str]]] = {
    "fetch_apod": _fetch_apod,
    "fetch_library": _fetch_library,
    "normalize_apod": _normalize_apod,
    "normalize_library": _normalize_library,
    "validate_records": _validate_records,
    "create_tables": _by_name("src.database.db", "create_tables", "create_tables"),
    "load_records": _by_name("src.database.load_data", "load_records", "load_records"),
    "run_quality_checks": _by_name(
        "src.database.queries", "run_quality_checks", "run_quality_checks"
    ),
}


def resolve(step: str) -> tuple[Callable, str]:
    """Return (function, source module) for a pipeline step."""
    func, source = RESOLVERS[step]()
    if source == PLACEHOLDER:
        log.warning("Step %s: using placeholder (teammate code not available yet)", step)
    return func, source
