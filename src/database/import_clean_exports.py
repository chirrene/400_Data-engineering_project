import argparse
import json
from collections import defaultdict
from pathlib import Path

from src.database.db import create_tables
from src.database.load_data import load_records


def read_jsonl(path):
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def record_key(row):
    return row["source_api"], row["source_id"]


def import_exports(folder):
    images = read_jsonl(folder / "clean_images.jsonl")
    relationships = read_jsonl(folder / "image_topics.jsonl")
    image_keys = {record_key(image) for image in images}
    topics = defaultdict(set)

    for relationship in relationships:
        key = record_key(relationship)
        keyword = relationship["search_topic"].strip().lower()
        if key not in image_keys or not keyword:
            raise ValueError(f"Invalid topic relationship: {relationship}")
        topics[key].add(keyword)

    create_tables()
    image_count = 0
    for start in range(0, len(images), 1000):
        rows = [
            {**image, "search_keyword": keyword}
            for image in images[start:start + 1000]
            for keyword in topics.get(record_key(image), ("",))
        ]
        image_count += load_records(rows)

    print(f"Images upserted: {image_count:,}")
    print(f"Distinct topic relationships processed: {sum(map(len, topics.values())):,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    import_exports(parser.parse_args().folder)
