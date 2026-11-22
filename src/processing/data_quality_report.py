
import json
from collections import Counter, defaultdict
from pathlib import Path

from src.processing.validate import (
    validate_record,
    find_duplicate_records,
)

INPUT_DIR = Path("data/processed/nasa_library")
REPORT_PATH = INPUT_DIR / "data_quality_report.json"


def generate_data_quality_report():
    """Generate a data quality report for normalized NASA records."""

    all_records = []
    topic_records = defaultdict(list)

    # 1. Load all normalized JSONL files
    for path in sorted(INPUT_DIR.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue

                record = json.loads(line)
                all_records.append(record)

                topic = record.get("search_topic") or path.stem
                topic_records[topic].append(record)

    if not all_records:
        raise ValueError("No normalized NASA records found.")

    # 2. Validate records
    validation_results = [
        validate_record(record)
        for record in all_records
    ]

    valid_count = sum(
        result["is_valid"]
        for result in validation_results
    )

    invalid_count = len(all_records) - valid_count

    missing_required = Counter()
    invalid_dates = 0
    missing_values = Counter()
    year_distribution = defaultdict(Counter)

    for record, result in zip(all_records, validation_results):
        missing_required.update(result["missing_fields"])

        if not result["date_is_valid"]:
            invalid_dates += 1

        for field, value in record.items():
            if value is None or value == "" or value == []:
                missing_values[field] += 1

        date = record.get("date")
        topic = record.get("search_topic") or "Unknown"

        if result["date_is_valid"]:
            year_distribution[topic][date[:4]] += 1

    # 3. Find duplicate source IDs across all topics
    duplicates = find_duplicate_records(all_records)

    duplicate_counts_by_topic = Counter(
        record.get("search_topic") or "Unknown"
        for record in duplicates
    )

    # 4. Summarize each topic
    topic_summary = {}

    for topic, records in topic_records.items():
        years = year_distribution.get(topic, {})
        sorted_years = sorted(years.keys())

        topic_summary[topic] = {
            "total_records": len(records),
            "valid_records": sum(
                validate_record(record)["is_valid"]
                for record in records
            ),
            "duplicate_occurrences": duplicate_counts_by_topic[topic],
            "earliest_year": sorted_years[0] if sorted_years else None,
            "latest_year": sorted_years[-1] if sorted_years else None,
            "year_distribution": dict(sorted(years.items())),
        }

    # 5. Build report
    report = {
        "total_records": len(all_records),
        "valid_records": valid_count,
        "invalid_records": invalid_count,
        "invalid_or_missing_dates": invalid_dates,
        "duplicate_occurrences": len(duplicates),
        "unique_source_ids_estimate": len(all_records) - len(duplicates),
        "missing_required_fields": dict(missing_required),
        "missing_values_by_field": dict(missing_values),
        "topics": topic_summary,
    }

    with REPORT_PATH.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)

    # 6. Print summary
    print("\nNASA DATA QUALITY REPORT")
    print("-" * 45)
    print(f"Total records: {len(all_records):,}")
    print(f"Valid records: {valid_count:,}")
    print(f"Invalid records: {invalid_count:,}")
    print(f"Invalid/missing dates: {invalid_dates:,}")
    print(f"Duplicate occurrences: {len(duplicates):,}")
    print(
        "Distinct source keys (estimated): "
        f"{len(all_records) - len(duplicates):,}"
    )

    print("\nBY TOPIC")
    print("-" * 45)

    for topic, summary in topic_summary.items():
        print(
            f"{topic}: "
            f"{summary['total_records']:,} records, "
            f"{summary['valid_records']:,} valid, "
            f"years {summary['earliest_year']}–"
            f"{summary['latest_year']}"
        )

    print(f"\nReport saved to: {REPORT_PATH}")

    return report


if __name__ == "__main__":
    generate_data_quality_report()
