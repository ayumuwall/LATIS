"""代表データの条件と、未レビュー・無関係な変更を受け入れないことを確認する。"""

from pathlib import Path
import tempfile
import unittest

from scripts import llm_acceptance as acceptance
from scripts import verify_representative as representative


class RepresentativeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name) / "representative"
        representative.prepare(self.output)
        self.facts = acceptance.load_json(self.output / "explicit/fixture.json")

    def test_representative_has_mixed_records_without_adopting_candidates(self):
        snapshot = self.facts["before"]
        ids = self.facts["ids"]
        nodes = {node["id"]: node for node in snapshot["nodes"]}
        relations = {rel["id"]: rel for rel in snapshot["relations"]}
        self.assertEqual(len(nodes), 100)
        self.assertEqual(nodes[ids["proposal"]]["lifecycle"], "proposed")
        self.assertEqual(relations[ids["candidate"]]["confirmation"], "candidate")
        self.assertEqual(relations[ids["exception_link"]]["confirmation"], "confirmed")
        self.assertEqual(nodes[ids["question"]]["lifecycle"], "draft")
        scopes = {rel["to_node_id"] for rel in snapshot["relations"]
                  if rel["relation_kind"] == "scoped_to" and rel["from_node_id"] == ids["normal_retention"]}
        self.assertEqual(len(scopes), 2)
        self.assertFalse(any(rel["relation_kind"] == "scoped_to" and rel["from_node_id"] == ids["memo"]
                             for rel in snapshot["relations"]))
        self.assertTrue(nodes[ids["baseline_evidence"]]["evidence"])

    def test_handover_requires_a_recorded_semantic_review(self):
        with self.assertRaises(FileNotFoundError):
            representative.handover(self.output)
        acceptance.write_json(self.output / "explicit/semantic-review.json", dict(passed=False, notes="未確認"))
        with self.assertRaisesRegex(RuntimeError, "意味レビュー"):
            representative.handover(self.output)
        self.assertFalse((self.output / "json-restored").exists())

    def test_report_rejects_changes_to_unrelated_records(self):
        fixture = acceptance.Fixture(self.output / "explicit/workspace")
        fixture.ids = self.facts["ids"]
        fixture.save(fixture.update("memo", body="今回の依頼と無関係の書き換え"))
        acceptance.write_json(self.output / "explicit/after.json", fixture.snapshot())
        with self.assertRaisesRegex(RuntimeError, "無関係"):
            representative.report(self.output)


if __name__ == "__main__":
    unittest.main()
