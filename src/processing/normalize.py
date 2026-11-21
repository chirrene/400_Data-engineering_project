
import html
import re


def clean_html(text):
    """Convert HTML-formatted text to plain text."""
    if not text:
        return None

    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)

    return " ".join(text.split())


def normalize_apod(record):
    """Normalize a single NASA APOD record."""

    return {
        "source_api": "apod",
        "source_id": str(record["post_id"]),
        "date": record.get("date"),
        "title": record.get("title"),
        "media_type": record.get("media_type"),
        "image_url": record.get("hdurl"),
        "page_url": record.get("permalink"),
        "explanation": clean_html(record.get("explanation")),
        "credit": clean_html(record.get("credit")),
        "alt_text": clean_html(record.get("alt")),
        "center": None,
        "location": None,
        "keywords": [],
        "asset_manifest_url": None,}



def normalize_nasa_library(raw_data, search_topic=None):
    """Flatten and normalize NASA Image Library search results."""

    items = raw_data.get("collection", {}).get("items", [])
    normalized_records = []

    for item in items:
        metadata_list = item.get("data", [])

        if not metadata_list:
            continue

        metadata = metadata_list[0]
        links = item.get("links", [])

        image_url = next(
            (
                link.get("href")
                for link in links
                if link.get("render") == "image"
                and link.get("rel") == "preview"
            ),
            None,
        )

        if not image_url:
            image_url = next(
                (
                    link.get("href")
                    for link in links
                    if link.get("render") == "image"
                ),
                None,
            )

        nasa_id = metadata.get("nasa_id")
        date_created = metadata.get("date_created")

        record = {
            "source_api": "nasa_library",
            "source_id": nasa_id,
            "search_topic": search_topic,
            "date": date_created[:10] if date_created else None,
            "title": clean_html(metadata.get("title")),
            "media_type": metadata.get("media_type"),
            "image_url": image_url,
            "page_url": (
                f"https://images.nasa.gov/details/{nasa_id}"
                if nasa_id else None
            ),
            "asset_manifest_url": item.get("href"),
            "explanation": clean_html(metadata.get("description")),
            "credit": clean_html(metadata.get("photographer")),
            "alt_text": None,
            "center": metadata.get("center"),
            "location": metadata.get("location"),
            "keywords": metadata.get("keywords", []),
        }

        normalized_records.append(record)

    return normalized_records


def filter_records_by_year(records, start_year=None, end_year=None):
    """Filter records by optional year boundaries."""

    filtered_records = []

    for record in records:
        date = record.get("date")

        # Keep all records if no year filtering is requested.
        if start_year is None and end_year is None:
            filtered_records.append(record)
            continue

        if not date or not str(date)[:4].isdigit():
            continue

        year = int(str(date)[:4])

        if start_year is not None and year < start_year:
            continue

        if end_year is not None and year > end_year:
            continue

        filtered_records.append(record)

    return filtered_records


