"""展示の正規CLI生成と、四通りの復元を実データ・実検査で確認する。"""

import json
from pathlib import Path
import tempfile
import unittest

from scripts.rehearse import sha
from scripts.reset_demo import reset
from scripts.test_support import run_unittest
from tools.graph_demo.prepare import prepare
from tools.graph_demo.projection import project, read_snapshot


class GraphDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / "source"
        prepare(cls.source)

    def test_baseline_contains_real_hierarchy_candidates_and_normative_agreements(self):
        snapshot = read_snapshot(self.source / "baseline.sqlite")
        view = project(self.source / "baseline.sqlite")
        agreements = [n for n in snapshot["nodes"] if n["kind"] == "agreement"]
        self.assertEqual(len(agreements), 13)
        self.assertTrue(all("なければならない" in n["body"] or "してはならない" in n["body"] for n in agreements))
        normal = next(n for n in agreements if n["title"] == "通常ログの保持期間")
        self.assertIn("24時間保持しなければならない", normal["body"])
        self.assertEqual(len(view["scope_ids"][normal["id"]]), 2)
        self.assertTrue(any(n["id"] not in {ref for values in view["scope_ids"].values() for ref in values} and not view["scope_ids"][n["id"]] for n in agreements))
        self.assertEqual(len([r for r in snapshot["relations"] if r["relation_kind"] == "contains"]), 3)
        self.assertTrue(any(r["confirmation"] == "candidate" for r in snapshot["relations"]))
        self.assertFalse(any("UTC" in n["body"] for n in agreements))
        self.assertTrue(all(r["response"]["ok"] for r in snapshot["idempotency_records"]))

    def test_demo_note_is_absent_from_every_saved_revision_and_provenance(self):
        for state in ("baseline", "final"):
            snapshot = read_snapshot(self.source / (state + ".sqlite"))
            text = json.dumps(snapshot,ensure_ascii=False)
            self.assertNotIn("（架空の展示設定）",text)
            self.assertNotIn("これは展示用の架空設定である。",text)
            self.assertNotIn("架空の展示設定。",text)
            for revision in range(snapshot["meta"]["graph_revision"]+1):
                self.assertFalse(any("（架空の展示設定）" in n["body"] for n in project(self.source / (state + ".sqlite"),revision)["nodes"]))

    def test_actual_new_evidence_tracks_same_id_change_and_preserves_audit(self):
        before, after = (read_snapshot(self.source / (name + ".sqlite")) for name in ("baseline", "final"))
        old = {n["id"]: n for n in before["nodes"]}
        new = {n["id"]: n for n in after["nodes"]}
        normal = next(n for n in old.values() if n["title"] == "通常ログの保持期間")
        audit = next(n for n in old.values() if n["title"] == "監査ログの保持期間")
        self.assertIn("48時間保持しなければならない", new[normal["id"]]["body"])
        self.assertEqual(new[audit["id"]], audit)
        self.assertTrue(any(n["kind"] == "agreement" and "UTCで統一しなければならない" in n["body"] for n in new.values()))
        self.assertTrue(all(new[n["id"]] == n for n in old.values() if n.get("evidence")))
        for name in ("baseline", "final"):
            view = project(self.source / (name + ".sqlite"))
            links = [r for r in view["relations"] if r["lifecycle"] == "active" and r["relation_kind"] == "verified_by"]
            self.assertEqual(len(links), 2)
            self.assertTrue(all(view["basis_status"][r["id"]] == "current" for r in links))

    def test_all_four_restores_keep_source_and_match_complete_snapshots_and_files(self):
        hashes = {str(p.relative_to(self.source)): sha(p) for p in self.source.rglob("*") if p.is_file()}
        for state in ("baseline", "final"):
            for format_ in ("sqlite", "json"):
                with self.subTest(state=state, format=format_):
                    work = self.root / f"{state}-{format_}"
                    receipt = reset(self.source, work, state=state, format_=format_)
                    self.assertFalse(receipt["new_test_evidence_registered"])
                    self.assertEqual(read_snapshot(work / "demo.sqlite"), json.loads((self.source / f"{state}.json").read_text()))
                    self.assertEqual(run_unittest(work).returncode, 0)
        self.assertEqual({str(p.relative_to(self.source)): sha(p) for p in self.source.rglob("*") if p.is_file()}, hashes)


if __name__ == "__main__":
    unittest.main()
