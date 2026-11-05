"""既定シナリオから、DB・現物・証拠を新規復元する契約を検査する。"""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from latis.model import Error
from scripts.reset_demo import reset, sha
from scripts.test_support import run_unittest
from tests.support import ROOT


class ResetDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        cls.source = Path(temporary.name) / "rehearsal"
        result = subprocess.run([sys.executable, "scripts/rehearse.py", "--output", str(cls.source)], cwd=ROOT, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr.decode() + result.stdout.decode())

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def call(self, db, operation, request, *, error=None):
        result = subprocess.run([sys.executable, "-m", "latis", "--db", str(db), operation], cwd=ROOT,
                                input=json.dumps(request).encode(), capture_output=True, timeout=15)
        response = json.loads(result.stdout)
        self.assertEqual(result.returncode, 1 if error else 0, response)
        if error:
            self.assertEqual(response["errors"][0]["code"], error)
        else:
            self.assertTrue(response["ok"], response)
        return response["data"]

    def test_both_formats_restore_matching_code_evidence_and_complete_history(self):
        source_hashes = {str(path.relative_to(self.source)): sha(path) for path in self.source.rglob("*") if path.is_file()}
        for state in ("baseline", "final"):
            expected = json.loads((self.source / (state + ".json")).read_text())
            for format_ in ("sqlite", "json"):
                with self.subTest(state=state, format=format_):
                    destination = self.directory / (state + "-" + format_)
                    receipt = reset(self.source, destination, state=state, format_=format_)
                    self.assertEqual(json.loads((destination / "snapshot.json").read_text()), expected)
                    self.assertEqual(receipt["meta"], expected["meta"])
                    self.assertFalse(receipt["code_executed"])
                    self.assertFalse(receipt["new_test_evidence_registered"])
                    self.assertEqual(self.call(destination / "demo.sqlite", "meta", {})["snapshot_id"], expected["meta"]["snapshot_id"])
                    # 復元補助自体はコードを実行しない。この検査では自前の既知の素材だけを実行する。
                    tests = run_unittest(destination)
                    self.assertEqual(tests.returncode, 0, tests.stderr)
                    self.assertIn(b"Ran 3 tests", tests.stderr)
                    for artifact in expected["nodes"]:
                        if artifact["kind"] == "artifact" and artifact["locator"] and artifact["locator"].startswith("file:"):
                            self.assertEqual(sha(destination / artifact["locator"].removeprefix("file:")), artifact["content_hash"])
        self.assertEqual(source_hashes, {str(path.relative_to(self.source)): sha(path) for path in self.source.rglob("*") if path.is_file()})

    def test_rejects_wrong_pair_existing_destination_and_output_inside_source(self):
        broken = self.directory / "broken"
        shutil.copytree(self.source, broken)
        (broken / "baseline-project/retention.py").write_text("改変された素材")
        destination = self.directory / "new"
        with self.assertRaisesRegex(ValueError, "観測版"):
            reset(broken, destination)
        self.assertFalse(destination.exists())
        destination.mkdir()
        (destination / "keep.txt").write_text("保持")
        with self.assertRaises(Error) as caught:
            reset(self.source, destination)
        self.assertEqual(getattr(caught.exception, "code", None), "DESTINATION_EXISTS")
        self.assertEqual((destination / "keep.txt").read_text(), "保持")
        with self.assertRaisesRegex(ValueError, "復元元の中"):
            reset(self.source, self.source / "reset")
        self.assertFalse((self.source / "reset").exists())

    def test_rejects_changed_evidence_and_source_symlink_escape(self):
        broken = self.directory / "broken"
        shutil.copytree(self.source, broken)
        (broken / "check-initial.log").write_text("元の結果と異なるログ")
        with self.assertRaisesRegex(ValueError, "固定証拠"):
            reset(broken, self.directory / "bad-log")
        (broken / "baseline-project/retention.py").unlink()
        outside = self.directory / "outside.py"
        outside.write_text("ダミー")
        (broken / "baseline-project/retention.py").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "外側を参照"):
            reset(broken, self.directory / "bad-link")
        duplicate = self.directory / "duplicate"
        shutil.copytree(self.source, duplicate)
        snapshot = duplicate / "baseline.json"
        snapshot.write_text('{"format_version":3,' + snapshot.read_text().lstrip()[1:])
        with self.assertRaises((Error, ValueError)):
            reset(duplicate, self.directory / "bad-json")
        self.assertFalse((self.directory / "bad-json").exists())

    def test_actual_cli_rejects_basis_and_cursor_from_different_restored_fork(self):
        a, b = self.directory / "a", self.directory / "b"
        reset(self.source, a, format_="sqlite")
        reset(self.source, b, format_="json")
        database_a, database_b = a / "demo.sqlite", b / "demo.sqlite"
        target = json.loads((self.source / "summary.json").read_text())["nodes"]["normal_retention"]
        def plan(database, body):
            current = self.call(database, "detail", dict(node_id=target))["node"]
            return self.call(database, "consult", dict(proposal=dict(title="復元後の分岐", body=body),
                change_set=dict(operations=[dict(op="update_node", id=target, expected_revision_id=current["revision_id"], set=dict(body=body))])))
        def application(consulted, key):
            return dict(**consulted["normalized_request"], basis=consulted["basis"], idempotency_key=key,
                        decision=dict(actor="test:reset", reason="復元後の別履歴を区別する", authority_ref="この検査", semantic_review="ready"))
        self.call(database_a, "apply", application(plan(database_a, "通常ログは48時間保持する。"), "fork-a"))
        basis_a = application(plan(database_a, "通常ログは72時間保持する。"), "future-a")
        cursor = self.call(database_a, "search", dict(limit=1))["page"]["next_cursor"]
        self.call(database_b, "apply", basis_a, error="BASIS_UNAVAILABLE")
        self.call(database_b, "apply", application(plan(database_b, "通常ログは96時間保持する。"), "fork-b"))
        meta_a, meta_b = self.call(database_a, "meta", {}), self.call(database_b, "meta", {})
        self.assertEqual(meta_a["database_id"], meta_b["database_id"])
        self.assertEqual(meta_a["graph_revision"], meta_b["graph_revision"])
        self.assertNotEqual(meta_a["snapshot_id"], meta_b["snapshot_id"])
        self.call(database_b, "apply", basis_a, error="BASIS_UNAVAILABLE")
        self.call(database_b, "search", dict(limit=1, cursor=cursor), error="CURSOR_STALE")
