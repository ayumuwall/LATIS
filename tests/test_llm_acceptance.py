"""LLMを呼ばず、利用試験の記録・判定と障害注入自体を検査する。"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from uuid import uuid4

from scripts.llm_acceptance import Fixture, evaluate, load_json, prepare_case, read_calls


class AcceptanceHarnessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def cli(self, directory, operation, request):
        return subprocess.run([str(directory / "tool/latis"), "--db", str(directory / "workspace/demo.sqlite"), operation],
                              input=json.dumps(request).encode(), capture_output=True, cwd=directory / "workspace")

    def plan(self, directory):
        fixture = Fixture(directory / "workspace")
        fixture.ids = load_json(directory / "fixture.json")["ids"]
        return dict(proposal=dict(title="通常ログの改訂", body="監査ログは維持する。"),
                    change_set=dict(operations=[fixture.update("normal_retention", body="通常ログは48時間保持する。")]))

    def application(self, consultation):
        return dict(**consultation["normalized_request"], basis=consultation["basis"],
                    decision=dict(actor="test:harness", reason="検査", authority_ref="この検査の指示", semantic_review="ready"), idempotency_key=uuid4().hex)

    def test_self_report_without_cli_does_not_pass(self):
        directory = prepare_case(self.directory / "smoke", "smoke")
        before = Fixture(directory / "workspace").snapshot()
        self.assertFalse(evaluate(directory)["mechanical_pass"])
        response = self.cli(directory, "meta", {})
        self.assertEqual(response.returncode, 0, response.stderr)
        report = evaluate(directory)
        self.assertTrue(report["mechanical_pass"])
        self.assertEqual(report["semantic_review"], "pending")
        self.assertEqual(Fixture(directory / "workspace").snapshot(), before)

    def test_wrapper_rejects_database_and_export_outside_workspace(self):
        directory = prepare_case(self.directory / "scope", "smoke")
        outside = self.directory / "outside.sqlite"
        result = subprocess.run([str(directory / "tool/latis"), "--db", str(outside), "init"], input=b"{}", capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(outside.exists())
        response = self.cli(directory, "export", dict(format="markdown", destination=str(self.directory / "outside-view")))
        self.assertEqual(response.returncode, 1)
        self.assertFalse((self.directory / "outside-view").exists())
        self.assertEqual(read_calls(directory), [])

    def test_runtime_uses_only_identical_dedicated_source_copies(self):
        directory = prepare_case(self.directory / "runtime", "smoke")
        manifest = load_json(directory / "runtime-sources.json")
        self.assertTrue(all(value["source"] == value["copy"] for value in manifest.values()))
        self.assertIn("latis/engine.py", manifest)
        self.assertIn("scripts/claude_sandbox.py", manifest)
        self.assertNotIn("docs/M3_VERIFICATION.ja.md", manifest)
        self.assertIn(str(directory / "tool/runtime"), (directory / "tool/latis").read_text())
        for name in ("latis", "observe", "check"):
            self.assertEqual((directory / "tool" / name).read_text().splitlines()[0],
                             f"#!{Path(sys.executable).resolve()}")
        response = self.cli(directory, "meta", {})
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertTrue(json.loads(response.stdout)["ok"])

    def test_handover_does_not_copy_previous_requests_or_notes(self):
        source = prepare_case(self.directory / "explicit", "explicit")
        workspace = source / "workspace"
        (workspace / "previous-request.json").write_text('{"answer":"秘密の前会話"}')
        (workspace / "notes").mkdir()
        (workspace / "notes/reason.md").write_text("前セッションの回答")
        directory = prepare_case(self.directory / "handover", "handover", handover_source=source)
        copied = {path.name for path in (directory / "workspace").iterdir()}
        self.assertEqual(copied, {"demo.sqlite", "retention.py", "test_retention.py", "baseline-test.log"})
        self.assertEqual(Fixture(directory / "workspace").snapshot(), Fixture(workspace).snapshot())

    def test_handover_accepts_current_full_summary_but_not_truncated_body(self):
        source = prepare_case(self.directory / "explicit", "explicit")
        directory = prepare_case(self.directory / "handover", "handover", handover_source=source)
        ids = load_json(directory / "fixture.json")["ids"]
        self.cli(directory, "meta", {})
        self.cli(directory, "search", {})
        for key in ("app_artifact", "test_artifact", "baseline_evidence"):
            self.cli(directory, "detail", dict(node_id=ids[key]))
        self.cli(directory, "history", dict(target_type="node", target_id=ids["normal_retention"]))
        self.cli(directory, "relations", dict(node_id=ids["normal_retention"]))
        result = subprocess.run([str(directory / "tool/observe")], capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(evaluate(directory)["mechanical_pass"])
        calls = read_calls(directory)
        for call in calls:
            if call["operation"] == "search":
                for item in call["response"]["data"]["items"]:
                    if item["id"] == ids["audit_retention"]:
                        item["excerpt"] = item["excerpt"][:1]
        (directory / "calls.jsonl").write_text(''.join(json.dumps(call) + '\n' for call in calls))
        self.assertFalse(evaluate(directory)["mechanical_pass"])

    def test_observation_and_test_helpers_accept_no_arbitrary_arguments(self):
        directory = prepare_case(self.directory / "helpers", "retry")
        result = subprocess.run([str(directory / "tool/observe")], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        hashes = json.loads(result.stdout)["content_hashes"]
        self.assertEqual(set(hashes), {"retention.py", "test_retention.py"})
        for tool in ("observe", "check"):
            result = subprocess.run([str(directory / "tool" / tool), "arbitrary.py"], capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, b"")
        result = subprocess.run([str(directory / "tool/check")], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"Ran 3 tests", result.stdout)
        self.assertTrue((directory / "workspace/test-result-1.log").is_file())

    def test_concurrent_target_change_occurs_after_consult(self):
        directory = prepare_case(self.directory / "target", "rebase-target")
        consultation = json.loads(self.cli(directory, "consult", self.plan(directory)).stdout)["data"]
        self.assertTrue((directory / "injected.json").is_file())
        response = self.cli(directory, "apply", self.application(consultation))
        data = json.loads(response.stdout)
        self.assertEqual(response.returncode, 1)
        self.assertEqual(data["errors"][0]["code"], "PRECONDITION_CHANGED")
        fixture = Fixture(directory / "workspace")
        fixture.ids = load_json(directory / "fixture.json")["ids"]
        self.assertIn("並行更新", fixture.current("normal_retention")["title"])
        self.assertIn("24時間", fixture.current("normal_retention")["body"])
        self.assertEqual([call["operation"] for call in read_calls(directory)], ["consult", "apply"])

    def test_lost_success_response_is_replayed_without_second_commit(self):
        directory = prepare_case(self.directory / "retry", "retry")
        consultation = json.loads(self.cli(directory, "consult", self.plan(directory)).stdout)["data"]
        application = self.application(consultation)
        response = self.cli(directory, "apply", application)
        self.assertEqual(response.returncode, 2)
        self.assertEqual(response.stdout, b"")
        self.assertTrue(response.stderr)
        before_retry = Fixture(directory / "workspace").snapshot()
        response = self.cli(directory, "apply", application)
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertEqual(Fixture(directory / "workspace").snapshot(), before_retry)
        applied = [call for call in read_calls(directory) if call["operation"] == "apply"]
        self.assertEqual(len(applied), 2)
        self.assertEqual(applied[0]["response"], applied[1]["response"])

    def test_basis_scope_and_relation_changes_reject_stale_plan_but_unrelated_does_not(self):
        from latis.model import reference
        for name in ("rebase-basis", "rebase-scope", "rebase-relation", "unrelated"):
            with self.subTest(case=name):
                directory = prepare_case(self.directory / name, name)
                plan = self.plan(directory)
                if name == "rebase-basis":
                    fixture = Fixture(directory / "workspace")
                    fixture.ids = load_json(directory / "fixture.json")["ids"]
                    plan["context"] = dict(basis_refs=[reference(fixture.current("app_artifact"))])
                consultation = json.loads(self.cli(directory, "consult", plan).stdout)["data"]
                response = self.cli(directory, "apply", self.application(consultation))
                data = json.loads(response.stdout)
                self.assertEqual(data["ok"], name == "unrelated", data)
                self.assertEqual(response.returncode, 0 if name == "unrelated" else 1)
                self.assertTrue((directory / "injected.json").is_file())

    def test_discovery_requires_memo_target_and_candidate_observations(self):
        directory = prepare_case(self.directory / "discovery", "discovery")
        ids = load_json(directory / "fixture.json")["ids"]
        self.cli(directory, "meta", {})
        self.cli(directory, "detail", dict(node_id=ids["limit"]))
        incomplete = evaluate(directory)
        self.assertFalse(incomplete["mechanical_pass"])
        self.assertFalse(incomplete["checks"]["memo_read"])
        self.cli(directory, "search", dict(kinds=["artifact", "proposal"], lifecycles=["draft", "proposed"]))
        self.cli(directory, "detail", dict(node_id=ids["memo"]))
        self.cli(directory, "relations", dict(node_id=ids["limit"]))
        report = evaluate(directory)
        self.assertTrue(report["mechanical_pass"])
        self.assertEqual(report["semantic_review"], "pending")
