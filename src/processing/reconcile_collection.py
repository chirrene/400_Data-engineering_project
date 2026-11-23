"""Offline audit and additive targeted recovery; never replace original exports.

Recovery responses live separately from the immutable original page checkpoints.
Building recovery records preserves incomplete status and requires explicit partial
coverage approval in the existing prepare/verify/merge commands.
"""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
import uuid

from src.apis.image_library_client import (
    create_retry_session, NASA_LIBRARY_API_URL, REQUEST_TIMEOUT,
)
from src.processing import incremental_collection as base


def collected_rows(run_dir):
    summary = base.read_json(run_dir / "collection_summary.json")
    path = run_dir / "collected_records.jsonl"
    if base.digest(path) != summary["records_sha256"]:
        raise ValueError("Original collected-record checksum mismatch")
    rows = base.read_rows(path, topic=True)
    for row in rows.values():
        if row["search_topic"] not in base.TOPICS or row["source_api"] != "nasa_library":
            raise ValueError("Unexpected topic/source in collected records")
        if not base.validate_record(row)["is_valid"]:
            raise ValueError("Invalid collected record")
    return summary, rows


def evidence(run_dir):
    for path in sorted((run_dir / "reconciliation" / "pages").glob("*.json")):
        saved = base.read_json(path)
        params = saved["params"]
        if params.get("q") not in base.TOPICS or params.get("media_type") != "image":
            raise ValueError(f"Unexpected recovery query: {path}")
        if not 1 <= int(params.get("page", 1)) <= base.MAX_PAGES:
            raise ValueError("Recovery page must be in 1..100")
        if saved["sha256"] != base.Collector.payload_hash(saved["payload"]):
            raise ValueError(f"Recovery checksum mismatch: {path}")
        base.unpack(saved["payload"])
        yield path, saved


def audit(folder, run_dir):
    """Read all cached evidence; zero API requests and no file changes."""
    summary, collected = collected_rows(run_dir)
    images, matches = base.read_pair(folder)
    report = {"status": "incomplete" if summary["status"] != "complete" else "complete",
              "original_sha256": base.fingerprints(folder),
              "collection_summary_sha256": base.digest(run_dir / "collection_summary.json"),
              "topics": {}, "checkpoint_count": 0, "recovery_responses": []}
    groups = defaultdict(list)
    nodes = {}
    for path in sorted((run_dir / "pages").glob("*.json")):
        saved = base.read_json(path)
        query, payload = saved["query"], saved["payload"]
        if saved["sha256"] != base.Collector.payload_hash(payload):
            raise ValueError(f"Original checkpoint checksum mismatch: {path}")
        topic = query["query"]
        if topic not in base.TOPICS or not 1 <= query["page"] <= base.MAX_PAGES:
            raise ValueError(f"Unexpected original query: {path}")
        total, _ = base.unpack(payload)
        start, end = query["start_year"], query["end_year"]
        group = (topic, int(start) if start is not None else None,
                 int(end) if end is not None else None)
        groups[group].append((query["page"], payload, path.name))
        if query["page"] == 1:
            nodes[group] = total
        report["checkpoint_count"] += 1
    for topic in base.TOPICS:
        topic_keys = {k[:2] for k in collected if k[2] == topic}
        original_keys = {k[:2] for k in matches if k[2] == topic}
        missing = original_keys - topic_keys
        entry = {"original_api_total_hits": summary["topics"][topic]["unfiltered_total_hits"],
                 "collected_unique_ids": len(topic_keys),
                 "collected_ids_already_in_original_images": len(topic_keys & images.keys()),
                 "collected_topic_relationships_already_present": len(topic_keys & original_keys),
                 "original_topic_ids_absent_from_collection": [
                     {"source_api": k[0], "source_id": k[1], "date": images[k].get("date"),
                      "title": images[k].get("title"), "image_already_preserved": True,
                      "topic_relationship_already_preserved": True} for k in sorted(missing)],
                 "ranges": [], "split_total_discrepancies": []}
        for leaf in summary["topics"][topic]["ranges"]:
            start, end, total = leaf["start_year"], leaf["end_year"], leaf["total_hits"]
            occurrences = defaultdict(list)
            anomalies = []
            count = 0
            pages = groups.get((topic, start, end), [])
            for number, payload, filename in sorted(pages):
                current, items = base.unpack(payload)
                count += len(items)
                expected = max(0, min(base.PAGE_SIZE, total - (number - 1) * base.PAGE_SIZE))
                if current != total or len(items) != expected:
                    anomalies.append({"page": number, "checkpoint": filename,
                                      "reported_total_hits": current, "range_total_hits": total,
                                      "returned_items": len(items), "expected_items": expected})
                for index, item in enumerate(items):
                    metadata = item.get("data", [{}])[0]
                    occurrences[metadata.get("nasa_id")].append({
                        "page": number, "index": index, "asset_manifest_url": item.get("href"),
                        "date_created": metadata.get("date_created"), "title": metadata.get("title")})
            duplicates = [{"source_id": identifier, "occurrences": found,
                           "distinct_asset_count": len({v["asset_manifest_url"] for v in found}),
                           "image_already_in_original": ("nasa_library", identifier) in images,
                           "topic_already_in_original": ("nasa_library", identifier, topic) in matches}
                          for identifier, found in occurrences.items() if len(found) > 1]
            entry["ranges"].append({"start_year": start, "end_year": end, "total_hits": total,
                                    "raw_items": count, "unique_ids": len(occurrences),
                                    "duplicates": duplicates, "page_anomalies": anomalies})
        for (name, start, end), total in nodes.items():
            if name != topic or start is None:
                continue
            middle = (start + end) // 2
            children = [nodes.get((topic, a, b)) for a, b in ((start, middle), (middle + 1, end))]
            if all(v is not None for v in children) and total != sum(children):
                entry["split_total_discrepancies"].append({"start_year": start, "end_year": end,
                                                           "parent_total": total, "child_totals": children})
        report["topics"][topic] = entry
    recovery_groups = {}
    for path, saved in evidence(run_dir):
        total, items = base.unpack(saved["payload"])
        report["recovery_responses"].append({"file": path.name, "params": saved["params"],
                                            "total_hits": total, "returned_items": len(items)})
        params = saved["params"]
        query_key = (params["q"], params.get("year_start"), params.get("year_end"), params.get("nasa_id"))
        group = recovery_groups.setdefault(query_key, {
            "topic": params["q"], "start_year": params.get("year_start"),
            "end_year": params.get("year_end"), "source_id_filter": params.get("nasa_id"),
            "pages": [], "reported_totals": set(), "raw_items": 0, "ids": set()})
        group["pages"].append(int(params.get("page", 1)))
        group["reported_totals"].add(total)
        group["raw_items"] += len(items)
        group["ids"].update(item.get("data", [{}])[0].get("nasa_id") for item in items)
    report["recovery_query_groups"] = []
    for group in recovery_groups.values():
        ids = group.pop("ids")
        group["unique_ids"] = len(ids)
        group["reported_totals"] = sorted(group["reported_totals"])
        group["pages"].sort()
        group["new_ids_vs_collected"] = sorted(identifier for identifier in ids if
            ("nasa_library", identifier, group["topic"]) not in collected)
        report["recovery_query_groups"].append(group)
    return report


def fetch_target(run_dir, topic, start=None, end=None, page=1, source_id=None, delay=.5):
    """Fetch one explicit page into a new checkpoint, preserving prior versions."""
    if topic not in base.TOPICS or not 1 <= page <= base.MAX_PAGES:
        raise ValueError("Only Mars/Earth pages 1..100 are allowed")
    if (start is None) != (end is None) or (
        start is not None and not 1 <= start <= end <= 9999
    ):
        raise ValueError("Supply valid start/end years together")
    params = {"q": topic, "media_type": "image", "page": page}
    if start is not None:
        params.update(year_start=f"{start:04d}", year_end=f"{end:04d}")
    if source_id:
        params["nasa_id"] = source_id
    time.sleep(delay)
    with create_retry_session() as session:
        response = session.get(f"{NASA_LIBRARY_API_URL.rstrip('/')}/search",
                               params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    total, items = base.unpack(payload)
    path = run_dir / "reconciliation" / "pages" / f"{topic}_{start}_{end}_{page}_{uuid.uuid4().hex}.json"
    base.save_json(path, {"params": params, "payload": payload,
                          "sha256": base.Collector.payload_hash(payload),
                          "fetched_at": datetime.now(timezone.utc).isoformat()})
    return {"checkpoint": str(path), "total_hits": total, "returned_items": len(items)}


def build(folder, run_dir):
    """Union validated recovery records with collected records; never claim full coverage."""
    report = audit(folder, run_dir)
    _, records = collected_rows(run_dir)
    originals, original_topics = base.read_pair(folder)
    before = set(records)
    evidence_hashes = {}
    for path, saved in evidence(run_dir):
        evidence_hashes[str(path.relative_to(run_dir))] = base.digest(path)
        topic = saved["params"]["q"]
        normalized = base.normalize_nasa_library(saved["payload"], search_topic=topic)
        if len(normalized) != len(saved["payload"]["collection"]["items"]):
            raise ValueError(f"Recovery normalization skipped items: {path}")
        for row in normalized:
            missing = not bool(str(row.get("title") or "").strip())
            row["title_missing_original"] = missing
            if missing:
                row["title"] = "Untitled NASA Image"
            if row["source_api"] != "nasa_library" or row.get("media_type") != "image":
                raise ValueError("Invalid recovery source/media")
            if not base.validate_record(row)["is_valid"]:
                raise ValueError("Invalid recovery image")
            records.setdefault(base.key(row, topic=True), row)
    output = run_dir / "reconciliation" / "reconciled_records.jsonl"
    base.write_rows(output, records.values())
    union_images = set(originals) | {k[:2] for k in records}
    union_topics = set(original_topics) | set(records)
    report["proposed_union"] = {
        "images": len(union_images), "added_images": len(union_images) - len(originals),
        "relationships": len(union_topics), "added_relationships": len(union_topics) - len(original_topics),
        "relationships_by_topic": dict(Counter(k[2] for k in union_topics)),
        "note": "Preview only: original exports have not been changed."}
    report.update({"status": "incomplete", "requires_partial_approval": True,
                   "collected_records_sha256": base.digest(run_dir / "collected_records.jsonl"),
                   "records_sha256": base.digest(output), "evidence_sha256": evidence_hashes,
                   "limitations": [
                       "API hit counts are not unique NASA ID counts; distinct assets sharing one NASA ID remain collapsed under the required key.",
                       "Year filters and page responses show inconsistencies; unavailable results cannot be certified as collected.",
                       "Recovery preserves a union of cached responses, not a point-in-time or 100-percent coverage guarantee."],
                   "recovered_relationships": [
                       {"source_api": k[0], "source_id": k[1], "search_topic": k[2],
                        "image_already_in_original": k[:2] in originals,
                        "topic_already_in_original": k in original_topics} for k in sorted(set(records) - before)],
                   "reconciled_unique_ids_by_topic": {topic: sum(k[2] == topic for k in records)
                                                       for topic in base.TOPICS}})
    base.save_json(run_dir / "reconciliation_summary.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("audit", "fetch", "build"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed/nasa_library"))
    parser.add_argument("--run-dir", type=Path, default=Path("data/incremental/nasa_library"))
    parser.add_argument("--topic", choices=base.TOPICS)
    parser.add_argument("--start-year", type=int)
    parser.add_argument("--end-year", type=int)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--source-id")
    args = parser.parse_args()
    folder, run_dir = args.data_dir.resolve(), args.run_dir.resolve()
    if folder == run_dir or folder in run_dir.parents:
        parser.error("run-dir must be outside processed exports")
    logging.basicConfig(level=logging.INFO)
    if args.action == "fetch" and not args.topic:
        parser.error("fetch requires --topic")
    try:
        with base.locked(run_dir):
            if args.action == "audit":
                report = audit(folder, run_dir)
            elif args.action == "build":
                report = build(folder, run_dir)
            else:
                report = fetch_target(run_dir, args.topic, args.start_year, args.end_year,
                                      args.page, args.source_id)
        print(json.dumps(report, indent=2))
        return 0
    except (OSError, ValueError, KeyError, base.requests.RequestException) as error:
        logging.error("Reconciliation stopped safely: %s", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
