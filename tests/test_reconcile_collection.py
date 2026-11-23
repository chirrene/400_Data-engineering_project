"""Focused offline recovery and explicit partial-approval tests."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock

from src.processing import incremental_collection as base
from src.processing import reconcile_collection as recovery
from test_incremental_collection import raw, payload, image, relationship


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data, self.run = self.root / "data", self.root / "run"
        base.write_rows(self.data / base.NAMES[0], [image("preserved")])
        base.write_rows(self.data / base.NAMES[1], [relationship("preserved", "Mars")])
        # Four hits but only three unique NASA IDs, including a genuine ID collision.
        a, b = raw("collision"), raw("collision")
        a["href"], b["href"] = "asset/one", "asset/two"
        def fetch(**query):
            if query["query"] == "Earth":
                return payload([a, b, raw("other")], 4)
            return payload([], 1)
        base.Collector(self.run, fetch=fetch, delay=0, sleep=lambda _:None).collect()
        self.original = base.fingerprints(self.data)
        self.cached = {str(p.relative_to(self.run)):base.digest(p) for p in self.run.rglob("*.json")}
        self.add_evidence("mars", "Mars", [raw("preserved")])
        self.add_evidence("earth", "Earth", [raw("recovered")])

    def add_evidence(self, name, topic, items):
        data = payload(items)
        path = self.run / "reconciliation" / "pages" / (name + ".json")
        base.save_json(path, {"params":{"q":topic,"media_type":"image","page":1},
                              "payload":data,"sha256":base.Collector.payload_hash(data)})
        return path

    def test_audit_distinguishes_duplicate_assets_and_existing_missing_ids(self):
        report = recovery.audit(self.data, self.run)
        duplicate = report["topics"]["Earth"]["ranges"][0]["duplicates"][0]
        self.assertEqual(duplicate["source_id"], "collision")
        self.assertEqual(duplicate["distinct_asset_count"], 2)
        self.assertEqual(report["topics"]["Mars"]["original_topic_ids_absent_from_collection"][0]["source_id"], "preserved")

    def test_build_is_additive_preserves_caches_and_incomplete_status(self):
        report = recovery.build(self.data, self.run)
        self.assertEqual(report["status"], "incomplete")
        self.assertTrue(report["requires_partial_approval"])
        self.assertEqual(report["reconciled_unique_ids_by_topic"], {"Mars":1,"Earth":3})
        self.assertEqual(report["proposed_union"]["images"], 4)
        self.assertEqual(base.fingerprints(self.data), self.original)
        for name, digest in self.cached.items():
            self.assertEqual(base.digest(self.run / name), digest)

    def test_partial_prepare_requires_explicit_approval(self):
        recovery.build(self.data, self.run)
        with self.assertRaisesRegex(ValueError, "approve-partial-coverage"):
            base.prepare(self.data, self.run)
        report = base.prepare(self.data, self.run, approve_partial_coverage=True)
        self.assertEqual(report["collection_status"], "incomplete")
        self.assertTrue(report["partial_coverage_approved"])
        self.assertEqual(base.fingerprints(self.data), self.original)

    def test_partial_verify_and_merge_each_require_approval(self):
        recovery.build(self.data, self.run)
        base.prepare(self.data, self.run, True)
        with self.assertRaises(ValueError):
            base.verify(self.data, self.run)
        with self.assertRaises(ValueError):
            base.merge(self.data, self.run)
        self.assertEqual(base.fingerprints(self.data), self.original)
        report = base.verify(self.data, self.run, True)
        # Simulated merge only into temporary fixtures, never the project dataset.
        merged = base.merge(self.data, self.run, True)
        self.assertEqual(merged["collection_status"], "incomplete")
        self.assertEqual(base.fingerprints(Path(merged["backup"])), self.original)
        self.assertEqual(merged["candidate_sha256"], report["candidate_sha256"])

    def test_no_report_cannot_bypass_with_flag(self):
        with self.assertRaises(OSError):
            base.prepare(self.data, self.run, True)
        self.assertEqual(base.fingerprints(self.data), self.original)

    def test_new_evidence_invalidates_approval_snapshot(self):
        recovery.build(self.data, self.run)
        base.prepare(self.data, self.run, True)
        self.add_evidence("new", "Earth", [raw("later")])
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            base.verify(self.data, self.run, True)

    def test_changed_report_after_prepare_refuses_merge(self):
        recovery.build(self.data, self.run)
        base.prepare(self.data, self.run, True)
        path = self.run / "reconciliation_summary.json"
        report = base.read_json(path)
        report["limitations"].append("Another unresolved issue")
        base.save_json(path, report)
        with self.assertRaisesRegex(ValueError, "changed since prepare"):
            base.verify(self.data, self.run, True)

    def test_changed_reconciled_records_rejected(self):
        recovery.build(self.data, self.run)
        path = self.run / "reconciliation" / "reconciled_records.jsonl"
        with path.open("a") as stream:
            stream.write("{}\n")
        with self.assertRaisesRegex(ValueError, "checksum"):
            base.prepare(self.data, self.run, True)

    def test_corrupt_evidence_rejected(self):
        path = self.run / "reconciliation" / "pages" / "earth.json"
        saved = base.read_json(path)
        saved["payload"]["collection"]["items"] = []
        base.save_json(path, saved)
        with self.assertRaisesRegex(ValueError, "checksum"):
            recovery.build(self.data, self.run)

    def test_changed_original_rejected(self):
        recovery.build(self.data, self.run)
        base.write_rows(self.data / base.NAMES[0], [image("preserved", "Changed original")])
        with self.assertRaisesRegex(ValueError, "Original data changed"):
            base.prepare(self.data, self.run, True)

    def test_fetch_target_is_single_page_and_does_not_touch_cache(self):
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.return_value.json.return_value = payload([raw("target")])
        with patch.object(recovery, "create_retry_session", return_value=session), patch.object(recovery.time, "sleep"):
            result = recovery.fetch_target(self.run, "Earth", 2026, 2026, page=4)
        self.assertEqual(session.get.call_count, 1)
        self.assertEqual(base.read_json(Path(result["checkpoint"]))["params"]["page"], 4)
        for name, digest in self.cached.items():
            self.assertEqual(base.digest(self.run / name), digest)

    def test_fetch_refuses_page101_or_non_target_topic(self):
        with patch.object(recovery, "create_retry_session") as session:
            for args in (("Earth",2026,2026,101),("Venus",2026,2026,1)):
                with self.assertRaises(ValueError):
                    recovery.fetch_target(self.run, *args)
            session.assert_not_called()


if __name__ == "__main__":
    unittest.main()
