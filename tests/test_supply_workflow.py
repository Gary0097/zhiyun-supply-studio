import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from supply_workflow import SupplyWorkflowStore


class SupplyWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SupplyWorkflowStore(Path(self.tmp.name) / "supply.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_artifact_lifecycle(self):
        created = self.store.create_artifact("supplier", "供应商评估", {}) if False else self.store.create_artifact(
            "supplier", "供应商评估", {"suppliers": []})
        self.assertEqual(created["status"], "pending_review")
        self.assertEqual(created["kind"], "supplier")
        reviewed = self.store.review_artifact(created["id"], "accept", "王经理", "业绩达标")
        self.assertEqual(reviewed["status"], "accepted")
        self.assertEqual(len(reviewed["reviews"]), 1)

    def test_reviewer_required(self):
        created = self.store.create_artifact("risk", "风险监控", {"records": []})
        with self.assertRaises(ValueError):
            self.store.review_artifact(created["id"], "accept", "")

    def test_export_only_accepted(self):
        created = self.store.create_artifact("replenishment", "补货建议", {"items": []})
        with self.assertRaises(ValueError):
            self.store.export_artifact(created["id"])
        self.store.review_artifact(created["id"], "accept", "王经理")
        content, media_type = self.store.export_artifact(created["id"])
        self.assertEqual(media_type, "application/json")
        self.assertIn("replenishment", content)

    def test_invalid_kind(self):
        with self.assertRaises(ValueError):
            self.store.create_artifact("bogus", "标题", {})


if __name__ == "__main__":
    unittest.main()
