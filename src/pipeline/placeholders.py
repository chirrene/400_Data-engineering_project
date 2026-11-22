"""Minimal working versions of teammates' steps.

These exist so the DAG can be built and demoed before the real modules land.
Each one is replaced automatically once the matching function in
``src.apis`` / ``src.processing`` / ``src.database`` exists (see contracts.py).
They are intentionally simple; the real modules own the full cleaning rules.
"""
from __future__ import annotations

import html
import json
import logging
import re
import time

import requests
from sqlalchemy import text

from src.pipeline.config import get_settings
from src.pipeline.db import get_engine

log = logging.getLogger(__name__)

APOD_URL = "https://science.nasa.gov/wp-json/wp/v2/apod-basic"
LIBRARY_URL = "https://images-api.nasa.gov/search"
HEADERS = {"User-Agent": "nasa-space-explorer-student-pipeline/0.1"}
REQUEST_PAUSE_S = 0.15


def _get_json(url: str, params: dict, attempts: int = 3) -> object:
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            if attempt == attempts:
                raise
            wait = 2**attempt
            log.warning("GET %s failed (%s), retry %d in %ss", url, exc, attempt, wait)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def _fixture(name: str) -> object:
    path = get_settings().fixtures_dir / name
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- extract
def fetch_apod(start_date: str) -> list[dict]:
    """All APOD posts on or after start_date (YYYY-MM-DD).

    apod-basic only honours ``page`` (25 posts, newest first), so we page
    back until we pass start_date.
    """
    if get_settings().offline:
        return [r for r in _fixture("apod_sample.json") if r["date"] >= start_date]

    records: list[dict] = []
    page = 1
    while True:
        batch = _get_json(APOD_URL, {"page": page})
        if not batch:
            break
        records.extend(r for r in batch if r.get("date", "") >= start_date)
        if min(r.get("date", "9999") for r in batch) < start_date:
            break
        page += 1
        time.sleep(REQUEST_PAUSE_S)
    log.info("APOD: %d posts since %s (%d pages)", len(records), start_date, page)
    return records


def fetch_library(keyword: str, year_start: int, year_end: int, max_pages: int) -> list[dict]:
    """Image Library search results (images only) for one keyword."""
    if get_settings().offline:
        return [r for r in _fixture("library_sample.json") if r.get("_keyword") == keyword]

    items: list[dict] = []
    for page in range(1, max_pages + 1):
        body = _get_json(
            LIBRARY_URL,
            {
                "q": keyword,
                "media_type": "image",
                "year_start": year_start,
                "year_end": year_end,
                "page": page,
                "page_size": 100,
            },
        )
        collection = body.get("collection", {})
        batch = collection.get("items", [])
        for item in batch:
            item["_keyword"] = keyword
        items.extend(batch)
        has_next = any(link.get("rel") == "next" for link in collection.get("links", []))
        if not batch or not has_next:
            break
        time.sleep(REQUEST_PAUSE_S)
    log.info("Library %r: %d items", keyword, len(items))
    return items


# -------------------------------------------------------------- transform
# Output uses the same unified record schema as src.processing.normalize.
_TAG = re.compile(r"<[^>]+>")


def _clean(value: object) -> str | None:
    if value is None:
        return None
    cleaned = html.unescape(_TAG.sub(" ", str(value))).replace("\xa0", " ")
    cleaned = " ".join(cleaned.split())
    return cleaned or None


def normalize_apod(records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        title = _clean(r.get("title")) or ""
        title = re.sub(r"^APOD:\s*\d{4} \w+ \d{1,2}\s*[-–]\s*", "", title)
        explanation = re.sub(r"^Explanation:\s*", "", _clean(r.get("explanation")) or "")
        out.append(
            {
                "source_api": "apod",
                "source_id": str(r.get("post_id") or r.get("date")),
                "date": r.get("date"),
                "title": title or None,
                "media_type": r.get("media_type"),
                "image_url": r.get("hdurl"),
                "page_url": r.get("permalink"),
                "explanation": explanation or None,
                "credit": _clean(r.get("credit")),
                "alt_text": _clean(r.get("alt")),
                "center": None,
                "location": None,
                "keywords": [],
                "asset_manifest_url": None,
            }
        )
    return out


def normalize_library(records: list[dict]) -> list[dict]:
    out = []
    for item in records:
        data = (item.get("data") or [{}])[0]
        if not data.get("nasa_id"):
            continue
        thumb = next(
            (l.get("href") for l in item.get("links", []) if l.get("rel") == "preview"), None
        )
        keywords = data.get("keywords") or []
        if len(keywords) == 1 and "," in keywords[0]:
            keywords = [k.strip() for k in keywords[0].split(",")]
        out.append(
            {
                "source_api": "nasa_library",
                "source_id": data["nasa_id"],
                "date": (data.get("date_created") or "")[:10] or None,
                "title": _clean(data.get("title")),
                "media_type": data.get("media_type"),
                "image_url": thumb,
                "page_url": f"https://images.nasa.gov/details/{data['nasa_id']}",
                "explanation": _clean(data.get("description")),
                "credit": data.get("photographer"),
                "alt_text": None,
                "center": data.get("center"),
                "location": data.get("location"),
                "keywords": keywords,
                "asset_manifest_url": item.get("href"),
                "search_keyword": item.get("_keyword"),
            }
        )
    return out


def validate_records(records: list[dict]) -> tuple[list[dict], dict]:
    """Drop records missing required fields; return (valid, metrics)."""
    required = ("source_api", "source_id", "title")
    valid = [r for r in records if all(r.get(f) for f in required)]
    keys = [(r["source_api"], r["source_id"], r.get("search_keyword")) for r in valid]
    return valid, {
        "invalid_dropped": len(records) - len(valid),
        "duplicates_in_batch": len(keys) - len(set(keys)),
    }


# ------------------------------------------------------------------- load
COLUMNS = [
    "source_api", "source_id", "search_keyword", "date", "title", "media_type",
    "image_url", "page_url", "explanation", "credit", "alt_text", "center",
    "location", "keywords", "asset_manifest_url",
]
KEY = ["source_api", "source_id", "search_keyword"]

DDL = """CREATE TABLE IF NOT EXISTS nasa_records (
    source_api TEXT NOT NULL,
    source_id TEXT NOT NULL,
    search_keyword TEXT NOT NULL DEFAULT '',
    date DATE,
    title TEXT,
    media_type TEXT,
    image_url TEXT,
    page_url TEXT,
    explanation TEXT,
    credit TEXT,
    alt_text TEXT,
    center TEXT,
    location TEXT,
    keywords TEXT,
    asset_manifest_url TEXT,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_api, source_id, search_keyword)
)"""


def create_tables() -> None:
    with get_engine().begin() as conn:
        conn.execute(text(DDL))


def load_records(records: list[dict]) -> int:
    """Upsert unified records; re-running never creates duplicates."""
    rows = {}
    for r in records:
        row = {c: r.get(c) for c in COLUMNS}
        row["search_keyword"] = row["search_keyword"] or ""
        row["keywords"] = json.dumps(row["keywords"] or [])
        rows[tuple(row[k] for k in KEY)] = row  # last one wins within a batch
    if not rows:
        return 0
    updates = ", ".join(f"{c} = excluded.{c}" for c in COLUMNS if c not in KEY)
    sql = text(
        f"INSERT INTO nasa_records ({', '.join(COLUMNS)}) "
        f"VALUES ({', '.join(':' + c for c in COLUMNS)}) "
        f"ON CONFLICT ({', '.join(KEY)}) DO UPDATE SET {updates}, "
        f"loaded_at = CURRENT_TIMESTAMP"
    )
    with get_engine().begin() as conn:
        conn.execute(sql, list(rows.values()))
    return len(rows)


# --------------------------------------------------------------- quality
QUALITY_CHECKS = {
    "missing_title": "SELECT COUNT(*) FROM nasa_records WHERE title IS NULL",
    "missing_date": "SELECT COUNT(*) FROM nasa_records WHERE date IS NULL",
    "apod_unknown_media_type": (
        "SELECT COUNT(*) FROM nasa_records WHERE source_api = 'apod' "
        "AND (media_type IS NULL OR media_type NOT IN ('image', 'video'))"
    ),
    "image_without_url": (
        "SELECT COUNT(*) FROM nasa_records WHERE media_type = 'image' AND image_url IS NULL"
    ),
    "apod_duplicate_dates": (
        "SELECT COUNT(*) FROM (SELECT date FROM nasa_records WHERE source_api = 'apod' "
        "GROUP BY date HAVING COUNT(*) > 1) d"
    ),
}


def run_quality_checks() -> dict[str, int]:
    with get_engine().connect() as conn:
        return {name: int(conn.execute(text(sql)).scalar()) for name, sql in QUALITY_CHECKS.items()}
