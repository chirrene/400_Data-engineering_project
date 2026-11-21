
import json
from pathlib import Path

from src.processing.normalize import normalize_nasa_library


RAW_DIR = Path("data/raw/nasa_library")
OUTPUT_DIR = Path("data/processed/nasa_library")

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


def process_nasa_data():
    """Flatten and normalize all collected NASA Library records."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    summary = {}

    for topic in SEARCH_TOPICS:
        input_path = RAW_DIR / f"{topic.lower()}.json"
        output_path = OUTPUT_DIR / f"{topic.lower()}.jsonl"

        if not input_path.exists():
            raise FileNotFoundError(
                f"Missing raw data file: {input_path}"
            )

        with input_path.open("r", encoding="utf-8") as file:
            raw_data = json.load(file)

        raw_count = len(
            raw_data.get("collection", {}).get("items", [])
        )

        normalized_records = normalize_nasa_library(
            raw_data,
            search_topic=topic,
        )

        # JSON Lines: one normalized record per line
        with output_path.open("w", encoding="utf-8") as file:
            for record in normalized_records:
                file.write(
                    json.dumps(record, ensure_ascii=False) + "\n"
                )

        summary[topic] = {
            "raw_records": raw_count,
            "normalized_records": len(normalized_records),
        }

        print(
            f"{topic}: {raw_count:,} raw -> "
            f"{len(normalized_records):,} normalized"
        )

    summary_path = OUTPUT_DIR / "processing_summary.json"

    with summary_path.open("w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2)

    print("\nPROCESSING SUMMARY")
    print("-" * 45)

    total_raw = sum(
        item["raw_records"] for item in summary.values()
    )
    total_normalized = sum(
        item["normalized_records"] for item in summary.values()
    )

    print(f"Total raw records: {total_raw:,}")
    print(f"Total normalized records: {total_normalized:,}")
    print(f"Records skipped: {total_raw - total_normalized:,}")

    return summary


if __name__ == "__main__":
    process_nasa_data()
