
import json
from collections import Counter
from pathlib import Path

from src.processing.validate import validate_record


INPUT_DIR = Path("data/processed/nasa_library")

IMAGES_PATH = INPUT_DIR / "clean_images.jsonl"
TOPICS_PATH = INPUT_DIR / "image_topics.jsonl"
SUMMARY_PATH = INPUT_DIR / "clean_export_summary.json"


def export_clean_data():
    """Clean, deduplicate, and export NASA records for PostgreSQL."""

    unique_images = {}
    image_topic_pairs = set()

    total_records = 0
    missing_titles_fixed = 0
    missing_ids = 0
    conflicting_duplicates = 0

    for input_path in sorted(INPUT_DIR.glob("*.jsonl")):
        # Exclude previously generated export files.
        if input_path.name in {
            IMAGES_PATH.name,
            TOPICS_PATH.name,
        }:
            continue

        with input_path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue

                record = json.loads(line)
                total_records += 1

                source_api = record.get("source_api")
                source_id = record.get("source_id")
                topic = record.get("search_topic")

                # Do not merge unrelated records without IDs.
                if not source_api or not source_id:
                    missing_ids += 1
                    continue

                # Preserve whether the original title was missing.
                title_missing = not bool(
                    str(record.get("title") or "").strip()
                )

                if title_missing:
                    record["title"] = "Untitled NASA Image"
                    missing_titles_fixed += 1

                record["title_missing_original"] = title_missing

                # Keep the topic relationship separately.
                if topic:
                    image_topic_pairs.add(
                        (source_api, source_id, topic)
                    )

                # One image per unique NASA source key.
                image_key = (source_api, source_id)

                # Remove search_topic from the image table.
                image_record = {
                    key: value
                    for key, value in record.items()
                    if key != "search_topic"
                }

                if image_key not in unique_images:
                    unique_images[image_key] = image_record
                else:
                    existing = unique_images[image_key]

                    # Preserve the original missing-title flag
                    # if any occurrence had a missing title.
                    existing["title_missing_original"] = (
                        existing["title_missing_original"]
                        or title_missing
                    )

                    # Prefer an actual title over the placeholder.
                    if (
                        existing.get("title") == "Untitled NASA Image"
                        and not title_missing
                    ):
                        existing["title"] = record["title"]

                    # Count differing metadata for later review.
                    if (
                        existing.get("date") != record.get("date")
                        or existing.get("media_type")
                        != record.get("media_type")
                    ):
                        conflicting_duplicates += 1

    # Export unique images.
    with IMAGES_PATH.open("w", encoding="utf-8") as file:
        for record in unique_images.values():
            file.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )

    # Export distinct image-topic relationships.
    with TOPICS_PATH.open("w", encoding="utf-8") as file:
        for source_api, source_id, topic in sorted(
            image_topic_pairs
        ):
            relationship = {
                "source_api": source_api,
                "source_id": source_id,
                "search_topic": topic,
            }
            file.write(
                json.dumps(
                    relationship,
                    ensure_ascii=False,
                ) + "\n"
            )

    # Check final exported records.
    invalid_after_cleaning = sum(
        not validate_record(record)["is_valid"]
        for record in unique_images.values()
    )

    summary = {
        "input_records": total_records,
        "unique_images": len(unique_images),
        "duplicate_occurrences_removed": (
            total_records - missing_ids - len(unique_images)
        ),
        "unique_image_topic_relationships": len(
            image_topic_pairs
        ),
        "missing_title_occurrences_fixed": missing_titles_fixed,
        "records_missing_source_keys_skipped": missing_ids,
        "conflicting_duplicate_occurrences": conflicting_duplicates,
        "invalid_images_after_cleaning": invalid_after_cleaning,
    }

    with SUMMARY_PATH.open("w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2)

    print("\nCLEAN DATA EXPORT SUMMARY")
    print("-" * 45)

    for key, value in summary.items():
        print(f"{key}: {value:,}")

    print(f"\nImages exported to: {IMAGES_PATH}")
    print(f"Topic relationships exported to: {TOPICS_PATH}")
    print(f"Summary exported to: {SUMMARY_PATH}")

    return summary


if __name__ == "__main__":
    export_clean_data()
