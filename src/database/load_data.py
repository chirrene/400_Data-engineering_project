import json

from sqlalchemy import text

from src.database.db import get_engine


COLUMNS = (
    "source_api", "source_id", "date", "title", "media_type",
    "image_url", "page_url", "asset_manifest_url", "explanation",
    "credit", "alt_text", "center", "location", "keywords",
)
KEY_COLUMNS = ("source_api", "source_id")

column_names = ", ".join(COLUMNS)
parameters = ", ".join(
    "CAST(:keywords AS JSONB)" if column == "keywords" else f":{column}"
    for column in COLUMNS
)
updates = ", ".join(
    f"{column} = EXCLUDED.{column}"
    for column in COLUMNS
    if column not in KEY_COLUMNS
)

UPSERT = text(f"""
    INSERT INTO nasa_records ({column_names})
    VALUES ({parameters})
    ON CONFLICT (source_api, source_id) DO UPDATE
    SET {updates}
""")

INSERT_SEARCH_MATCH = text("""
    INSERT INTO nasa_search_matches (source_api, source_id, search_keyword)
    VALUES (:source_api, :source_id, :search_keyword)
    ON CONFLICT (source_api, source_id, search_keyword) DO NOTHING
""")


def load_records(records):
    """Insert or update NASA records and save their search matches."""
    rows_by_key = {}
    search_matches = set()

    for record in records:
        row = {column: record.get(column) for column in COLUMNS}
        row["keywords"] = json.dumps(row["keywords"] or [])
        key = (row["source_api"], row["source_id"])
        rows_by_key[key] = row

        keyword = (record.get("search_keyword") or "").strip().lower()
        if keyword:
            search_matches.add((*key, keyword))

    if not rows_by_key:
        return 0

    with get_engine().begin() as connection:
        connection.execute(UPSERT, list(rows_by_key.values()))

        if search_matches:
            connection.execute(
                INSERT_SEARCH_MATCH,
                [
                    {"source_api": source, "source_id": record_id, "search_keyword": keyword}
                    for source, record_id, keyword in sorted(search_matches)
                ],
            )

    return len(rows_by_key)