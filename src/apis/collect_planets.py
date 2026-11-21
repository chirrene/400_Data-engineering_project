
import json
import math
import time
from pathlib import Path

import requests

from src.apis.image_library_client import fetch_nasa_library


SEARCH_TOPICS = [
    "Mercury",
    "Venus",
    "Earth",
    "Mars",
    "Jupiter",
    "Saturn",
    "Uranus",
    "Neptune",
    "Galaxy",
]

MAX_PAGES = 100
PAGE_SIZE = 100
OUTPUT_DIR = Path("data/raw/nasa_library")

MAX_PAGE_ATTEMPTS = 3
RETRY_DELAY = 3


def save_checkpoint(path, items):
    """Atomically save collected records to avoid corrupt files."""
    temp_path = path.with_suffix(".json.tmp")

    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(
            {"collection": {"items": items}},
            file,
            ensure_ascii=False,
        )

    temp_path.replace(path)


def load_checkpoint(path):
    """Load previously saved records if available."""
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    return data.get("collection", {}).get("items", [])


def fetch_page_with_retries(topic, page):
    """Retry temporary API failures while preserving progress."""
    for attempt in range(1, MAX_PAGE_ATTEMPTS + 1):
        try:
            return fetch_nasa_library(
                query=topic,
                page=page,
                start_year=None,
                end_year=None,
            )
        except requests.RequestException as error:
            print(
                f"[{topic}] Page {page} failed "
                f"(attempt {attempt}/{MAX_PAGE_ATTEMPTS}): {error}"
            )

            if attempt == MAX_PAGE_ATTEMPTS:
                raise

            time.sleep(RETRY_DELAY * attempt)


def collect_nasa_topics(max_pages=MAX_PAGES):
    """Collect NASA images with per-page checkpointing and resume."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = {}

    for topic in SEARCH_TOPICS:
        output_path = OUTPUT_DIR / f"{topic.lower()}.json"
        items = load_checkpoint(output_path)

        print(f"\nStarting: {topic}")
        print(f"Existing saved records: {len(items)}")

        # Retrieve the current total search-result count.
        try:
            first_page = fetch_page_with_retries(topic, 1)
        except requests.RequestException:
            print(f"[{topic}] Metadata request failed. Skipping.")
            summary[topic] = len(items)
            continue

        total_hits = (
            first_page.get("collection", {})
            .get("metadata", {})
            .get("total_hits")
        )

        target_records = (
            min(total_hits, max_pages * PAGE_SIZE)
            if isinstance(total_hits, int)
            else max_pages * PAGE_SIZE
        )

        # Skip topics that have already reached the collection target.
        if len(items) >= target_records:
            print(f"[{topic}] Already complete. Skipping.")
            summary[topic] = len(items)
            continue

        # A previously saved partial final page indicates completion
        # only when the API's total hit count supports it.
        start_page = len(items) // PAGE_SIZE + 1

        if len(items) % PAGE_SIZE != 0:
            print(
                f"[{topic}] Existing checkpoint ends mid-page. "
                "Re-fetching the last partial page."
            )
            start_page = len(items) // PAGE_SIZE + 1
            items = items[:(start_page - 1) * PAGE_SIZE]

        print(f"[{topic}] Resuming from page {start_page}/{max_pages}")

        for page in range(start_page, max_pages + 1):
            try:
                if page == 1:
                    data = first_page
                else:
                    data = fetch_page_with_retries(topic, page)

            except requests.RequestException:
                print(
                    f"[{topic}] Stopped at page {page}. "
                    "Saved progress is preserved."
                )
                break

            new_items = (
                data.get("collection", {}).get("items", [])
            )

            if not new_items:
                print(f"[{topic}] No more results.")
                break

            items.extend(new_items)
            save_checkpoint(output_path, items)

            print(
                f"[{topic}] Page {page}/{max_pages}: "
                f"{len(new_items)} fetched, "
                f"{len(items)} total saved."
            )

            if len(new_items) < PAGE_SIZE:
                print(f"[{topic}] Reached final partial page.")
                break

            time.sleep(0.5)

        summary[topic] = len(items)
        print(f"[{topic}] Saved: {len(items)} records")

    print("\nFINAL COLLECTION SUMMARY")
    print("-" * 35)

    for topic, count in summary.items():
        print(f"{topic}: {count:,} saved records")

    print("-" * 35)
    print(f"Total: {sum(summary.values()):,} records")

    return summary


if __name__ == "__main__":
    collect_nasa_topics(max_pages=MAX_PAGES)
