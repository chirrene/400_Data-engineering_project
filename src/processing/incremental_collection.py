"""Resumable Mars/Earth collection; explicit prepare, verify and merge steps.

Run from the repository root: python -m src.processing.incremental_collection --help
NASA API reference: https://images.nasa.gov/docs/images.nasa.gov_api_docs.pdf
"""

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import tempfile
import time
import uuid

import requests

from src.apis.image_library_client import fetch_nasa_library
from src.processing.normalize import normalize_nasa_library
from src.processing.validate import validate_record

TOPICS = ("Mars", "Earth")
NAMES = ("clean_images.jsonl", "image_topics.jsonl")
PAGE_SIZE = 100
MAX_PAGES = 100
LOG = logging.getLogger(__name__)


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path, content):
    """Durably write a file on the same filesystem, then atomically rename it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_json(path, value):
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def read_json(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


@contextmanager
def locked(folder):
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / ".incremental.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(f"Another incremental operation holds {folder}") from error
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def key(row, topic=False):
    fields = ("source_api", "source_id", "search_topic") if topic else ("source_api", "source_id")
    if not isinstance(row, dict) or any(
        not isinstance(row.get(field), str) or not row[field].strip() for field in fields
    ):
        raise ValueError(f"Invalid source/topic key: {row!r}")
    return tuple(row[field] for field in fields)


def read_rows(path, topic=False):
    rows = {}
    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row_key = key(row, topic)
            if row_key in rows:
                raise ValueError(f"Duplicate key at {path}:{line_number}: {row_key}")
            if not topic and not validate_record(row)["is_valid"]:
                raise ValueError(f"Invalid image at {path}:{line_number}")
            rows[row_key] = row
    return rows


def read_pair(folder):
    if (folder / ".incremental_merge.json").exists():
        raise ValueError("Interrupted merge detected; run the recover command first")
    images = read_rows(folder / NAMES[0])
    topics = read_rows(folder / NAMES[1], topic=True)
    if any(k[:2] not in images for k in topics):
        raise ValueError(f"Orphan topic relationship in {folder}")
    return images, topics


def write_rows(path, rows):
    atomic_write(path, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode())


def unpack(payload):
    try:
        collection = payload["collection"]
        total = collection["metadata"]["total_hits"]
        items = collection["items"]
    except (KeyError, TypeError) as error:
        raise ValueError("Missing collection, total_hits, or items") from error
    if type(total) is not int or total < 0 or not isinstance(items, list) or len(items) > PAGE_SIZE:
        raise ValueError("Malformed NASA search response")
    return total, items


class Collector:
    def __init__(self, run_dir, fetch=None, delay=0.5, attempts=3, sleep=time.sleep):
        self.run_dir = Path(run_dir)
        self.fetch = fetch or fetch_nasa_library
        self.delay = delay
        self.attempts = attempts
        self.sleep = sleep

    def page(self, topic, start=None, end=None, page=1):
        if topic not in TOPICS or not 1 <= page <= MAX_PAGES:
            raise ValueError("Only Mars/Earth and pages 1..100 are allowed")
        query = dict(query=topic, page=page,
                     start_year=f"{start:04d}" if start is not None else None,
                     end_year=f"{end:04d}" if end is not None else None)
        path = self.run_dir / "pages" / f"{topic}_{start}_{end}_{page}.json"
        if path.exists():
            checkpoint = read_json(path)
            if checkpoint["query"] != query:
                raise ValueError(f"Checkpoint query mismatch: {path}")
            payload = checkpoint["payload"]
            if checkpoint["sha256"] != self.payload_hash(payload):
                raise ValueError(f"Checkpoint checksum mismatch: {path}")
            unpack(payload)
            return payload
        for attempt in range(self.attempts):
            self.sleep(self.delay)
            try:
                payload = self.fetch(**query)
                unpack(payload)
                save_json(path, {"query": query, "payload": payload,
                                 "sha256": self.payload_hash(payload)})
                LOG.info("%s years=%s..%s page=%s saved", topic, start, end, page)
                return payload
            except (requests.RequestException, ValueError) as error:
                LOG.warning("Request %s failed (%s/%s): %s", query, attempt + 1, self.attempts, error)
                if attempt + 1 == self.attempts:
                    raise
                self.sleep(2 ** attempt)

    @staticmethod
    def payload_hash(payload):
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def topic(self, topic):
        result = {"status": "incomplete", "ranges": [], "errors": []}
        records = {}
        try:
            baseline, _ = unpack(self.page(topic))
            result["unfiltered_total_hits"] = baseline

            def visit(start, end):
                first = self.page(topic, start, end)
                total, _ = unpack(first)
                if total > MAX_PAGES * PAGE_SIZE and start < end:
                    middle = (start + end) // 2
                    visit(start, middle)
                    visit(middle + 1, end)
                    return
                info = {"start_year": start, "end_year": end, "total_hits": total,
                        "required_pages": math.ceil(total / PAGE_SIZE), "pages_saved": 0,
                        "unique_records": 0, "status": "incomplete"}
                result["ranges"].append(info)
                seen = set()
                problems = []
                for number in range(1, min(MAX_PAGES, math.ceil(total / PAGE_SIZE)) + 1):
                    payload = first if number == 1 else self.page(topic, start, end, number)
                    current_total, items = unpack(payload)
                    expected = min(PAGE_SIZE, total - (number - 1) * PAGE_SIZE)
                    if current_total != total or len(items) != expected:
                        problems.append(f"Page {number}: total/count changed or short page")
                    normalized = normalize_nasa_library(payload, search_topic=topic)
                    if len(normalized) != len(items):
                        problems.append(f"Page {number}: normalization skipped items")
                    for row in normalized:
                        missing = not bool(str(row.get("title") or "").strip())
                        row["title_missing_original"] = missing
                        if missing:
                            row["title"] = "Untitled NASA Image"
                        row_key = key(row)
                        if row["source_api"] != "nasa_library" or row.get("media_type") != "image":
                            raise ValueError("Unexpected source or media type")
                        if not validate_record(row)["is_valid"]:
                            raise ValueError(f"Invalid normalized image: {row_key}")
                        if not start <= int(row["date"][:4]) <= end:
                            raise ValueError(f"API returned date outside requested range: {row_key}")
                        seen.add(row_key)
                        records.setdefault(row_key, row)
                    info["pages_saved"] += 1
                    info["unique_records"] = len(seen)
                if total > MAX_PAGES * PAGE_SIZE:
                    problems.append("Single year exceeds 10,000 accessible results; coverage incomplete")
                if len(seen) != total:
                    problems.append(f"Unique IDs {len(seen)} differ from total_hits {total}")
                info["problems"] = problems
                info["status"] = "complete" if not problems else "incomplete"

            # All four-digit calendar years, including future-dated archive records.
            visit(1, 9999)
            ranged_total = sum(r["total_hits"] for r in result["ranges"])
            result["range_total_hits"] = ranged_total
            if ranged_total != baseline or len(records) != baseline:
                result["errors"].append("Year-filtered unique records/counts differ from unfiltered total; "
                                        "undated records, API drift, or inaccessible results may remain")
            if not result["errors"] and all(r["status"] == "complete" for r in result["ranges"]):
                result["status"] = "complete"
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            result["errors"].append(str(error))
            LOG.error("%s incomplete: %s", topic, error)
        result["unique_records"] = len(records)
        return result, records

    def collect(self):
        summary = {"version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                   "year_bounds": [1, 9999], "topics": {},
                   "coverage_note": "Counts describe cached API responses, not a point-in-time NASA snapshot."}
        additions = []
        for topic in TOPICS:
            report, records = self.topic(topic)
            summary["topics"][topic] = report
            additions.extend(records.values())
            # Persist per topic, too. Raw page checkpoints survive any interruption.
            save_json(self.run_dir / "collection_summary.json", summary)
        write_rows(self.run_dir / "collected_records.jsonl", additions)
        summary["records_sha256"] = digest(self.run_dir / "collected_records.jsonl")
        summary["status"] = "complete" if all(
            t["status"] == "complete" for t in summary["topics"].values()) else "incomplete"
        save_json(self.run_dir / "collection_summary.json", summary)
        return summary


def coverage_state(run_dir, approve_partial_coverage=False):
    """Bind explicit partial approval to a reviewed, checksummed reconciliation."""
    summary = read_json(run_dir / "collection_summary.json")
    if set(summary.get("topics", {})) != set(TOPICS):
        raise ValueError("Missing topic coverage reports")
    if digest(run_dir / "collected_records.jsonl") != summary["records_sha256"]:
        raise ValueError("Collected-record checksum mismatch")
    complete = summary.get("status") == "complete" and all(
        t.get("status") == "complete" for t in summary["topics"].values())
    if complete:
        return {"collection_status": "complete", "partial_coverage_approved": False,
                "records_path": str(run_dir / "collected_records.jsonl")}
    if not approve_partial_coverage:
        raise ValueError("Collection coverage incomplete; inspect reconciliation_summary.json and "
                         "explicitly pass --approve-partial-coverage to use partial recovery records")
    report_path = run_dir / "reconciliation_summary.json"
    report = read_json(report_path)
    if report.get("status") != "incomplete" or report.get("requires_partial_approval") is not True:
        raise ValueError("Missing explicit incomplete-coverage reconciliation report")
    if not report.get("limitations"):
        raise ValueError("Partial coverage limitations must be documented")
    if report["collection_summary_sha256"] != digest(run_dir / "collection_summary.json") or (
        report["collected_records_sha256"] != summary["records_sha256"]
    ):
        raise ValueError("Reconciliation is stale; run reconciliation build again")
    actual_evidence = {str(path.relative_to(run_dir)): digest(path) for path in
                       (run_dir / "reconciliation" / "pages").glob("*.json")}
    if actual_evidence != report["evidence_sha256"]:
        raise ValueError("Recovery evidence changed; run reconciliation build again")
    path = run_dir / "reconciliation" / "reconciled_records.jsonl"
    if digest(path) != report["records_sha256"]:
        raise ValueError("Reconciled-record checksum mismatch")
    return {"collection_status": "incomplete", "partial_coverage_approved": True,
            "reconciliation_summary_sha256": digest(report_path),
            "reconciliation_original_sha256": report["original_sha256"],
            "coverage_limitations": report["limitations"], "records_path": str(path)}


def additions(run_dir, approve_partial_coverage=False):
    state = coverage_state(run_dir, approve_partial_coverage)
    with Path(state["records_path"]).open(encoding="utf-8") as stream:
        seen = set()
        for line in stream:
            row = json.loads(line)
            row_key = key(row, topic=True)
            if row_key in seen:
                raise ValueError("Duplicate collected topic relationship")
            seen.add(row_key)
            if row["search_topic"] not in TOPICS or row["source_api"] != "nasa_library":
                raise ValueError("Unexpected topic/source in additions")
            if not validate_record(row)["is_valid"]:
                raise ValueError("Invalid collected record")
            yield row


def fingerprints(folder):
    return {name: digest(folder / name) for name in NAMES}


def validate_preservation(original, candidate):
    before = read_pair(original)
    after = read_pair(candidate)
    for old, new in zip(before, after):
        if any(new.get(k) != row for k, row in old.items()):
            raise ValueError("Candidate lost or changed existing records/relationships")
    return {"original_images": len(before[0]), "images": len(after[0]),
            "added_images": len(after[0]) - len(before[0]),
            "original_relationships": len(before[1]), "relationships": len(after[1]),
            "added_relationships": len(after[1]) - len(before[1]),
            "relationships_by_topic": dict(Counter(k[2] for k in after[1])),
            "preservation": "all original rows preserved exactly", "validation": "passed"}


def prepare(folder, run_dir, approve_partial_coverage=False):
    baseline = fingerprints(folder)
    coverage = coverage_state(run_dir, approve_partial_coverage)
    if coverage.get("reconciliation_original_sha256", baseline) != baseline:
        raise ValueError("Original data changed since reconciliation; build again")
    images, topics = read_pair(folder)
    for row in additions(run_dir, approve_partial_coverage):
        image_key = key(row)
        images.setdefault(image_key, {k: v for k, v in row.items() if k != "search_topic"})
        topics.setdefault(key(row, topic=True), dict(zip(
            ("source_api", "source_id", "search_topic"), key(row, topic=True))))
    # A fresh immutable candidate directory avoids mixing generations after a failed prepare.
    candidate = run_dir / "candidates" / uuid.uuid4().hex
    for name, rows in zip(NAMES, (images.values(), topics.values())):
        write_rows(candidate / name, rows)
    report = validate_preservation(folder, candidate)
    if fingerprints(folder) != baseline:
        raise ValueError("Original data changed during preparation; run prepare again")
    report.update(coverage)
    report.update({"candidate": str(candidate.resolve()), "baseline_sha256": baseline,
                   "candidate_sha256": fingerprints(candidate),
                   "collection_summary_sha256": digest(run_dir / "collection_summary.json")})
    save_json(run_dir / "validation_summary.json", report)
    return report


def verify(folder, run_dir, approve_partial_coverage=False):
    report = read_json(run_dir / "validation_summary.json")
    # Recheck completeness and the additions checksum without contacting NASA.
    state = coverage_state(run_dir, approve_partial_coverage)
    if any(report.get(field) != value for field, value in state.items()):
        raise ValueError("Coverage approval/report changed since prepare; run prepare again")
    list(additions(run_dir, approve_partial_coverage))
    if digest(run_dir / "collection_summary.json") != report["collection_summary_sha256"]:
        raise ValueError("Collection changed since prepare; run prepare again")
    candidate = Path(report["candidate"])
    if fingerprints(folder) != report["baseline_sha256"]:
        raise ValueError("Original data changed since prepare; run prepare again")
    if fingerprints(candidate) != report["candidate_sha256"]:
        raise ValueError("Candidate checksum mismatch")
    validate_preservation(folder, candidate)
    return report


def recover(folder):
    """Roll back an interrupted two-file replacement before any further merge."""
    journal = folder / ".incremental_merge.json"
    if not journal.exists():
        return
    transaction = read_json(journal)
    backup = Path(transaction["backup"])
    if fingerprints(backup) != transaction["original_sha256"]:
        raise ValueError(f"Recovery backup damaged: {backup}; manual recovery required")
    for name in NAMES:
        atomic_write(folder / name, (backup / name).read_bytes())
    journal.unlink()
    sync_directory(folder)
    LOG.warning("Recovered original pair from %s", backup)


def merge(folder, run_dir, approve_partial_coverage=False):
    with locked(folder):
        recover(folder)
        report = verify(folder, run_dir, approve_partial_coverage)
        candidate = Path(report["candidate"])
        backup = folder / "incremental_backups" / uuid.uuid4().hex
        backup.mkdir(parents=True)
        for name in NAMES:
            atomic_write(backup / name, (folder / name).read_bytes())
        if fingerprints(backup) != report["baseline_sha256"]:
            raise ValueError("Backup verification failed; originals untouched")
        # Validate again after backup, immediately before publishing.
        verify(folder, run_dir, approve_partial_coverage)
        save_json(backup / "manifest.json", report)
        journal = folder / ".incremental_merge.json"
        save_json(journal, {"backup": str(backup.resolve()),
                            "original_sha256": report["baseline_sha256"]})
        try:
            for name in NAMES:
                atomic_write(folder / name, (candidate / name).read_bytes())
            if fingerprints(folder) != report["candidate_sha256"]:
                raise ValueError("Published checksums differ")
            journal.unlink()
            sync_directory(folder)
        except BaseException:
            recover(folder)
            raise
        return {"status": "merged", "backup": str(backup.resolve()), **report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("collect", "prepare", "verify", "merge", "recover"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed/nasa_library"))
    parser.add_argument("--run-dir", type=Path, default=Path("data/incremental/nasa_library"))
    parser.add_argument("--approve-partial-coverage", action="store_true",
                        help="Explicitly accept documented incomplete coverage for prepare/verify/merge")
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args()
    if args.delay < 0 or args.attempts < 1:
        parser.error("delay must be nonnegative and attempts positive")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args.data_dir = args.data_dir.resolve()
    args.run_dir = args.run_dir.resolve()
    if args.run_dir == args.data_dir or args.data_dir in args.run_dir.parents:
        parser.error("run-dir must be outside processed exports (the old exporter scans JSONL files)")
    try:
        with locked(args.run_dir):
            if args.action == "collect":
                report = Collector(args.run_dir, delay=args.delay, attempts=args.attempts).collect()
            elif args.action == "prepare":
                report = prepare(args.data_dir, args.run_dir, args.approve_partial_coverage)
            elif args.action == "verify":
                report = verify(args.data_dir, args.run_dir, args.approve_partial_coverage)
            elif args.action == "merge":
                report = merge(args.data_dir, args.run_dir, args.approve_partial_coverage)
            else:
                with locked(args.data_dir):
                    recover(args.data_dir)
                report = {"status": "recovery checked"}
        print(json.dumps(report, indent=2))
        return 2 if report.get("status") == "incomplete" else 0
    except (OSError, ValueError, KeyError) as error:
        LOG.error("Stopped safely: %s", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
