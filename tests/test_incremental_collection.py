"""Offline tests: python -m unittest discover -s tests -p test_incremental_collection.py"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests

from src.processing import incremental_collection as workflow


def raw(identifier, year=2020, title="NASA image"):
    return {"data": [{"nasa_id": identifier, "date_created": f"{year:04d}-01-01T00:00:00Z",
                      "media_type": "image", "title": title}],
            "links": [{"render": "image", "rel": "preview", "href": "https://example.test/a.jpg"}]}


def payload(items, total=None):
    return {"collection": {"metadata": {"total_hits": len(items) if total is None else total},
                           "items": items}}


def image(identifier, title="NASA image"):
    row = workflow.normalize_nasa_library(payload([raw(identifier, title=title)]))[0]
    row.pop("search_topic")
    row["title_missing_original"] = False
    return row


def relationship(identifier, topic):
    return dict(source_api="nasa_library", source_id=identifier, search_topic=topic)


class IncrementalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "processed"
        self.run = self.root / "run"
        workflow.write_rows(self.data / workflow.NAMES[0], [image("old", "Preserve this metadata")])
        workflow.write_rows(self.data / workflow.NAMES[1], [relationship("old", "Galaxy")])
        self.original = workflow.fingerprints(self.data)

    def collector(self, fetch, attempts=1):
        return workflow.Collector(self.run, fetch=fetch, delay=0, attempts=attempts, sleep=lambda _: None)

    def collect_small(self):
        def fetch(**query):
            return payload([raw("old", title="Changed API metadata"), raw("new", title=None)])
        return self.collector(fetch).collect()

    def test_preserves_existing_images_and_all_topics_and_deduplicates(self):
        self.collect_small()
        report = workflow.prepare(self.data, self.run)
        self.assertEqual(workflow.fingerprints(self.data), self.original)
        self.assertEqual(report["images"], 2)
        self.assertEqual(report["relationships"], 5)
        images, topics = workflow.read_pair(Path(report["candidate"]))
        self.assertEqual(images[("nasa_library", "old")]["title"], "Preserve this metadata")
        self.assertEqual(images[("nasa_library", "new")]["title"], "Untitled NASA Image")
        self.assertTrue(images[("nasa_library", "new")]["title_missing_original"])
        self.assertIn(("nasa_library", "old", "Galaxy"), topics)
        self.assertEqual(workflow.verify(self.data, self.run), report)

    def test_resume_uses_cached_pages_and_only_requested_topics(self):
        calls = []
        def fetch(**query):
            calls.append(query)
            return payload([raw("id")])
        self.collector(fetch).collect()
        count = len(calls)
        self.collector(fetch).collect()
        self.assertEqual(len(calls), count)
        self.assertEqual({q["query"] for q in calls}, {"Mars", "Earth"})
        self.assertEqual({q["start_year"] for q in calls}, {None, "0001"})
        self.assertEqual({q["end_year"] for q in calls}, {None, "9999"})

    def test_resume_after_failed_page(self):
        calls = []
        fail = True
        def fetch(**q):
            calls.append(q)
            if fail and q["page"] == 2:
                raise requests.Timeout("temporary outage")
            return payload([raw(str(q["page"]))], total=2)
        with patch.object(workflow, "PAGE_SIZE", 1):
            self.assertEqual(self.collector(fetch).collect()["status"], "incomplete")
            cached = sum(q["page"] == 1 for q in calls)
            fail = False
            self.assertEqual(self.collector(fetch).collect()["status"], "complete")
            self.assertEqual(sum(q["page"] == 1 for q in calls), cached)

    def test_retries_then_succeeds(self):
        calls = []
        def fetch(**query):
            calls.append(query)
            if len(calls) < 3:
                raise requests.ConnectionError("offline")
            return payload([])
        self.collector(fetch, attempts=3).page("Mars", 2020, 2020)
        self.assertEqual(len(calls), 3)

    def test_failed_api_is_incomplete_and_cannot_prepare(self):
        def fail(**query):
            raise requests.HTTPError("400 Bad Request")
        summary = self.collector(fail).collect()
        self.assertEqual(summary["status"], "incomplete")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            workflow.prepare(self.data, self.run)
        self.assertEqual(workflow.fingerprints(self.data), self.original)

    def test_never_requests_page_101(self):
        with self.assertRaises(ValueError):
            self.collector(lambda **q: self.fail("network called")).page("Mars", page=101)

    def test_refuses_other_topics(self):
        with self.assertRaises(ValueError):
            self.collector(lambda **q: self.fail("network called")).page("Venus")

    def test_recursive_split_and_exact_page_boundary(self):
        calls = []
        def fetch(**q):
            calls.append(q)
            years = [2020, 2021]
            if q["start_year"]:
                years = [y for y in years if int(q["start_year"]) <= y <= int(q["end_year"])]
            items = [raw(f"{year}-{index}", year) for year in years for index in range(4)]
            start = (q["page"] - 1) * 2
            return payload(items[start:start + 2], total=len(items))
        with patch.object(workflow, "PAGE_SIZE", 2), patch.object(workflow, "MAX_PAGES", 2):
            summary = self.collector(fetch).collect()
        self.assertEqual(summary["status"], "complete")
        self.assertTrue(all(q["page"] <= 2 for q in calls))
        self.assertTrue(any(r["required_pages"] == 2 for r in summary["topics"]["Mars"]["ranges"]))

    def test_single_year_overflow_is_reported(self):
        calls = []
        def fetch(**q):
            calls.append(q)
            hit = not q["start_year"] or int(q["start_year"]) <= 2020 <= int(q["end_year"])
            return payload([raw(f"{q['page']}-{i}") for i in range(2)] if hit else [], 5 if hit else 0)
        with patch.object(workflow, "PAGE_SIZE", 2), patch.object(workflow, "MAX_PAGES", 2):
            summary = self.collector(fetch).collect()
        self.assertEqual(summary["status"], "incomplete")
        ranges = summary["topics"]["Mars"]["ranges"]
        overflow = next(r for r in ranges if r["total_hits"] == 5)
        self.assertEqual((overflow["start_year"], overflow["end_year"]), (2020, 2020))
        self.assertIn("Single year", " ".join(overflow["problems"]))
        self.assertTrue(all(q["page"] <= 2 for q in calls))

    def test_duplicate_page_ids_mark_incomplete(self):
        with patch.object(workflow, "PAGE_SIZE", 1):
            summary = self.collector(lambda **q: payload([raw("same")], 2)).collect()
        self.assertEqual(summary["status"], "incomplete")

    def test_missing_metadata_retried_and_rejected(self):
        calls = []
        def fetch(**q):
            calls.append(q)
            return {"collection": {"items": []}}
        summary = self.collector(fetch, attempts=2).collect()
        self.assertEqual(summary["status"], "incomplete")
        self.assertEqual(len(calls), 4)

    def test_skipped_normalization_marks_incomplete(self):
        self.assertEqual(self.collector(lambda **q: payload([{}])).collect()["status"], "incomplete")

    def test_date_range_drift_and_short_page_mark_incomplete(self):
        def fetch(**q):
            return payload([raw("id")], 2 if q["start_year"] else 3)
        self.assertEqual(self.collector(fetch).collect()["status"], "incomplete")

    def test_checkpoint_tampering_rejected(self):
        self.collect_small()
        checkpoint = next((self.run / "pages").glob("*.json"))
        value = workflow.read_json(checkpoint)
        value["payload"]["collection"]["metadata"]["total_hits"] = 999
        workflow.save_json(checkpoint, value)
        self.assertEqual(self.collector(lambda **q: self.fail("network called")).collect()["status"], "incomplete")

    def test_changed_original_or_candidate_refuses_merge(self):
        self.collect_small()
        report = workflow.prepare(self.data, self.run)
        candidate = Path(report["candidate"]) / workflow.NAMES[0]
        with candidate.open("a") as stream:
            stream.write("{}\n")
        with self.assertRaises(ValueError):
            workflow.merge(self.data, self.run)
        self.assertEqual(workflow.fingerprints(self.data), self.original)
        workflow.prepare(self.data, self.run)
        workflow.write_rows(self.data / workflow.NAMES[0], [image("old", "Edited outside collector")])
        changed = workflow.fingerprints(self.data)
        with self.assertRaisesRegex(ValueError, "changed since"):
            workflow.merge(self.data, self.run)
        self.assertEqual(workflow.fingerprints(self.data), changed)

    def test_orphan_and_duplicate_rows_rejected(self):
        workflow.write_rows(self.data / workflow.NAMES[1], [relationship("absent", "Galaxy")])
        with self.assertRaisesRegex(ValueError, "Orphan"):
            workflow.read_pair(self.data)
        workflow.write_rows(self.data / workflow.NAMES[0], [image("old"), image("old")])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            workflow.read_pair(self.data)

    def test_successful_merge_has_exact_verified_backup(self):
        self.collect_small()
        workflow.prepare(self.data, self.run)
        report = workflow.merge(self.data, self.run)
        self.assertEqual(workflow.fingerprints(Path(report["backup"])), self.original)
        self.assertEqual(workflow.fingerprints(self.data), report["candidate_sha256"])
        self.assertFalse((self.data / ".incremental_merge.json").exists())

    def test_second_replace_failure_rolls_back_both(self):
        self.collect_small()
        workflow.prepare(self.data, self.run)
        original_replace = workflow.os.replace
        failed = False
        def replace(source, destination):
            nonlocal failed
            if Path(destination) == self.data / workflow.NAMES[1] and not failed:
                failed = True
                raise OSError("simulated second rename failure")
            return original_replace(source, destination)
        with patch.object(workflow.os, "replace", side_effect=replace):
            with self.assertRaises(OSError):
                workflow.merge(self.data, self.run)
        self.assertEqual(workflow.fingerprints(self.data), self.original)

    def test_interrupted_transaction_recovery(self):
        self.collect_small()
        workflow.prepare(self.data, self.run)
        report = workflow.merge(self.data, self.run)
        workflow.save_json(self.data / ".incremental_merge.json", {
            "backup": report["backup"], "original_sha256": self.original})
        workflow.recover(self.data)
        self.assertEqual(workflow.fingerprints(self.data), self.original)

    def test_validation_failure_preserves_original(self):
        self.collect_small()
        with patch.object(workflow, "validate_preservation", side_effect=ValueError("bad candidate")):
            with self.assertRaises(ValueError):
                workflow.prepare(self.data, self.run)
        self.assertEqual(workflow.fingerprints(self.data), self.original)

    def test_exact_hundred_pages_stops_at_100(self):
        calls = []
        def fetch(**q):
            calls.append(q)
            return payload([raw(str(q["page"]))], total=100)
        with patch.object(workflow, "PAGE_SIZE", 1):
            summary = self.collector(fetch).collect()
        self.assertEqual(summary["status"], "complete")
        self.assertEqual(max(q["page"] for q in calls), 100)
        self.assertEqual(summary["topics"]["Mars"]["unique_records"], 100)

    def test_backup_failure_leaves_originals_unchanged(self):
        self.collect_small()
        workflow.prepare(self.data, self.run)
        original_write = workflow.atomic_write
        def write(path, content):
            if "incremental_backups" in str(path):
                raise OSError("backup disk full")
            return original_write(path, content)
        with patch.object(workflow, "atomic_write", side_effect=write):
            with self.assertRaises(OSError):
                workflow.merge(self.data, self.run)
        self.assertEqual(workflow.fingerprints(self.data), self.original)

    def test_unfinished_journal_blocks_preparation(self):
        self.collect_small()
        workflow.save_json(self.data / ".incremental_merge.json", {})
        with self.assertRaisesRegex(ValueError, "recover"):
            workflow.prepare(self.data, self.run)
        self.assertEqual(workflow.fingerprints(self.data), self.original)

    def test_lock_contention(self):
        with workflow.locked(self.run):
            with self.assertRaisesRegex(ValueError, "Another incremental"):
                with workflow.locked(self.run):
                    pass


if __name__ == "__main__":
    unittest.main()
