from sqlalchemy import text

from src.database.db import get_engine


QUALITY_CHECKS = {
    "blank_title": """
        SELECT COUNT(*)
        FROM nasa_records
        WHERE TRIM(title) = ''
    """,
    "image_without_url": """
        SELECT COUNT(*)
        FROM nasa_records
        WHERE media_type = 'image'
          AND (image_url IS NULL OR TRIM(image_url) = '')
    """,
}


def run_quality_checks():
    """Return the number of records that fail each quality check."""
    with get_engine().connect() as connection:
        return {
            name: connection.execute(text(sql)).scalar_one()
            for name, sql in QUALITY_CHECKS.items()
        }


def get_apod_by_date(selected_date):
    """Return the APOD record for a date, or None if it is unavailable."""
    query = text("""
        SELECT source_id, date, title, media_type, image_url,
               page_url, explanation, credit, alt_text
        FROM nasa_records
        WHERE source_api = 'apod'
          AND date = CAST(:selected_date AS DATE)
        ORDER BY source_id
        LIMIT 1
    """)

    with get_engine().connect() as connection:
        row = connection.execute(
            query, {"selected_date": selected_date}
        ).mappings().first()

    return dict(row) if row is not None else None


def search_library(keyword, year=None):
    """Find NASA Image Library records by search keyword and optional year."""
    query = text("""
        SELECT r.source_api, r.source_id, r.date, r.title,
               r.media_type, r.image_url, r.page_url, r.credit
        FROM nasa_records AS r
        JOIN nasa_search_matches AS m
          ON r.source_api = m.source_api
         AND r.source_id = m.source_id
        WHERE r.source_api = 'nasa_library'
          AND m.search_keyword = :keyword
          AND (
              CAST(:year AS INTEGER) IS NULL
              OR EXTRACT(YEAR FROM r.date) = CAST(:year AS INTEGER)
          )
        ORDER BY r.date DESC, r.source_id
    """)

    with get_engine().connect() as connection:
        rows = connection.execute(
            query, {"keyword": keyword.strip().lower(), "year": year}
        ).mappings()
        return [dict(row) for row in rows]

def get_record_details(source_api, source_id):
    """Return one NASA record, or None if it does not exist."""
    query = text("""
        SELECT source_api, source_id, date, title, media_type,
               image_url, page_url, asset_manifest_url,
               explanation, credit, alt_text, center, location, keywords
        FROM nasa_records
        WHERE source_api = :source_api AND source_id = :source_id
    """)

    with get_engine().connect() as connection:
        row = connection.execute(
            query, {"source_api": source_api, "source_id": source_id}
        ).mappings().one_or_none()

    return dict(row) if row is not None else None

def list_apod_dates():
    """Return the dates with stored APOD records, newest first."""
    query = text("""
        SELECT DISTINCT date
        FROM nasa_records
        WHERE source_api = 'apod'
        ORDER BY date DESC
    """)

    with get_engine().connect() as connection:
        return list(connection.execute(query).scalars())