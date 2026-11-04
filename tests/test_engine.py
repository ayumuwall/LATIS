"""P0の受け入れ条件を、実DBとCLIで検証する。"""

import copy
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from latis import Engine
from latis.model import RULES, canonical, digest, now, uid
from latis import storage

ROOT = Path(__file__).resolve().parent.parent


def node(ref="n", kind="agreement", lifecycle="accepted", title="ログの保持期間", body="通常ログは24時間保持する。", **extra):
    return dict(op="create_node", ref=ref, kind=kind, lifecycle=lifecycle, title=title, body=body, **extra)


def relation(ref, a, b, kind="depends_on", confirmation="confirmed", **extra):
    return dict(op="create_relation", ref=ref, **{"from": a, "to": b}, relation_kind=kind, confirmation=confirmation, origin="agent", **extra)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.engine = Engine(self.directory / "data.sqlite")
        self.ok("init", {})

    def ok(self, operation, request, engine=None):
        response = (engine or self.engine).execute(operation, request)
        self.assertTrue(response["ok"], response)
        return response["data"]

    def error(self, operation, request, code, engine=None):
        response = (engine or self.engine).execute(operation, request)
        self.assertFalse(response["ok"], response)
        self.assertEqual(response["errors"][0]["code"], code, response)
        return response

    def save(self, *operations, key=None):
        return self.ok("save-draft", dict(change_set=dict(operations=list(operations)), record=dict(actor="agent:test", reason="受け入れ検査"), idempotency_key=key or uid()))

    def consult(self, *operations, context=None, **extra):
        return self.ok("consult", dict(proposal=dict(title="検査用変更", body="受け入れ条件を確認する。"),
                                       change_set=dict(operations=list(operations)), context=context or {}, **extra))

    def application(self, consultation, key=None, **decision):
        return dict(**consultation["normalized_request"], basis=consultation["basis"],
                    decision=dict(actor="agent:test", reason="受け入れ検査", authority_ref="このテストの指示", semantic_review="ready", **decision), idempotency_key=key or uid())

    def apply(self, *operations, context=None):
        return self.ok("apply", self.application(self.consult(*operations, context=context)))

    def create(self, **kwargs):
        op = node(**kwargs)
        result = self.save(op) if op["lifecycle"] in {"draft", "proposed"} else self.apply(op)
        return self.current(result["created_refs"][op["ref"]]["id"])

    def current(self, id_):
        return self.ok("detail", dict(node_id=id_))["node"]

    def update(self, value, **patch):
        return dict(op="update_node", id=value["id"], expected_revision_id=value["revision_id"], set=patch)

    def seed(self):
        request = json.loads((ROOT / "docs/v0.3.0/examples/seed_consult.request.json").read_text())
        result = self.ok("apply", self.application(self.ok("consult", request)))
        return {key: self.current(ref["id"]) for key, ref in result["created_refs"].items() if ref["type"] == "node"}

    def test_A01_A04_A07_unorganized_records_and_unrelated_questions(self):
        saved = self.save(node("memo", "artifact", "draft"), node("duplicate", "proposal", "proposed"), node("question", "question", "draft"))
        self.assertEqual(len(saved["created_refs"]), 3)
        self.assertEqual(self.ok("search", {})["items"], [])
        self.assertEqual(len(self.ok("search", dict(kinds=["artifact", "proposal", "question"], lifecycles=["draft", "proposed"]))["items"]), 3)
        self.create()
        self.assertEqual(len(self.ok("search", {})["items"]), 1)

    def test_A02_A03_A19_A20_search_normalization_scope_and_cursor(self):
        scope = self.create(kind="scope", title="ログ")
        first = self.create(title="保持", body="ＡＢＣ +[] 通常ログ")
        second = self.create(title="通常ログ保持", body="abc")
        self.apply(relation("membership", first["id"], scope["id"], "scoped_to"))
        result = self.ok("search", dict(query="保持 ABC", limit=1))
        expected = sorted([first["id"], second["id"]])
        self.assertEqual(result["items"][0]["id"], expected[0])
        self.assertEqual(self.ok("search", dict(query="保持"))["items"][0]["id"], first["id"])
        self.assertTrue(result["page"]["has_more"])
        next_request = dict(query="保持 ABC", limit=1, cursor=result["page"]["next_cursor"])
        self.assertEqual(self.ok("search", next_request)["items"][0]["id"], expected[1])
        self.assertEqual(len(self.ok("search", dict(query="+[]"))["items"]), 1)
        self.assertEqual(len(self.ok("search", dict(scope_ids=[scope["id"]]))["items"]), 1)
        self.assertEqual(len(self.ok("search", dict(scope_ids=[scope["id"]], include_unscoped=True))["items"]), 2)
        self.create(title="追加")
        self.error("search", next_request, "CURSOR_STALE")

    def test_A05_A06_A08_A18_accepted_change_and_verbatim_text(self):
        values = self.seed()
        normal, audit = values["normal_retention"], values["audit_retention"]
        self.apply(self.update(normal, body="通常ログは48時間保持する。"), context=dict(basis_refs=[dict(type="node", id=audit["id"], revision_id=audit["revision_id"])]))
        self.assertEqual(self.current(audit["id"]), audit)
        history = self.ok("history", dict(target_type="node", target_id=normal["id"]))
        self.assertEqual(len(history["revisions"]), 2)
        self.assertEqual(history["revisions"][1]["snapshot"], normal)
        prov = max(history["provenance"], key=lambda p: p["commit_revision"])
        self.assertIn("authority_ref", prov["decision"])
        self.assertEqual(prov["target_refs"][0]["revision_id"], self.current(normal["id"])["revision_id"])
        self.assertEqual(self.ok("search", dict(query="90日"))["items"][0]["id"], audit["id"])

    def test_A09_target_update_is_not_overwritten(self):
        value = self.create()
        request = self.application(self.consult(self.update(value, body="48時間")))
        self.apply(self.update(value, body="72時間"))
        self.error("apply", request, "PRECONDITION_CHANGED")
        self.assertEqual(self.current(value["id"])["body"], "72時間")

    def test_A10_scope_add_retire_and_move_out(self):
        for mutation in ("add", "retire", "move"):
            with self.subTest(mutation=mutation):
                values = self.seed()
                watched = self.consult(self.update(values["normal_retention"], body="48時間"))
                audit = values["audit_retention"]
                if mutation == "add":
                    self.apply(node("extra"), relation("scope", "$extra", values["logs_scope"]["id"], "scoped_to"))
                elif mutation == "retire":
                    self.apply(self.update(audit, lifecycle="retired"))
                else:
                    rel = self.ok("relations", dict(node_id=audit["id"], relation_kinds=["scoped_to"]))["items"][0]["relation"]
                    self.apply(dict(op="update_relation", id=rel["id"], expected_revision_id=rel["revision_id"], set=dict(lifecycle="retired")))
                self.error("apply", self.application(watched), "CONTEXT_CHANGED")

    def test_A11_A26_confirmed_relation_and_additional_basis(self):
        a, b, extra = self.create(), self.create(title="前提"), self.create(kind="artifact", lifecycle="draft")
        result = self.apply(relation("dependency", a["id"], b["id"], basis_targets=[extra["id"]]))
        rel_id = result["created_refs"]["dependency"]["id"]
        rel = self.ok("relation-detail", dict(relation_id=rel_id))["relation"]
        request = self.application(self.consult(self.update(a, body="48時間"), context=dict(basis_refs=[dict(type="relation", id=rel_id, revision_id=rel["revision_id"])])))
        self.save(self.update(extra, body="根拠更新"))
        self.error("apply", request, "BASIS_CHANGED")
        rel = self.ok("relation-detail", dict(relation_id=rel_id))["relation"]
        consult = self.consult(dict(op="update_relation", id=rel_id, expected_revision_id=rel["revision_id"], reconfirm=True))
        self.assertEqual(consult["normalized_request"]["change_set"]["operations"][0]["basis_targets"], [extra["id"]])
        self.ok("apply", self.application(consult))
        self.assertEqual(self.ok("relation-detail", dict(relation_id=rel_id))["basis_status"], "current")

    def test_A11_relation_only_change_in_watched_scope(self):
        values = self.seed()
        consultation = self.consult(self.update(values["normal_retention"], body="48時間"))
        self.apply(relation("newjudgment", values["audit_retention"]["id"], values["app_artifact"]["id"], "governs"))
        self.error("apply", self.application(consultation), "CONTEXT_CHANGED")

    def test_A12_A13_candidate_and_changed_basis_do_not_invalidate_agreement(self):
        a, b = self.create(), self.create(title="前提")
        result = self.save(relation("candidate", a["id"], b["id"], "conflicts_with", "candidate"))
        rel_id = result["created_refs"]["candidate"]["id"]
        self.assertEqual(self.ok("relation-detail", dict(relation_id=rel_id))["basis_status"], "untracked")
        consultation = self.consult(self.update(a, body="48時間"))
        self.assertIn("candidate_conflict", [d["code"] for d in consultation["diagnostics"]])
        rel = self.ok("relation-detail", dict(relation_id=rel_id))["relation"]
        self.apply(dict(op="update_relation", id=rel_id, expected_revision_id=rel["revision_id"], set=dict(confirmation="confirmed")))
        self.apply(self.update(b, body="前提改訂"))
        self.assertEqual(self.current(a["id"])["lifecycle"], "accepted")
        self.assertEqual(self.ok("relation-detail", dict(relation_id=rel_id))["basis_status"], "changed")

    def test_A14_atomic_failure_and_failed_key_reuse(self):
        request = dict(change_set=dict(operations=[node(lifecycle="draft"), relation("bad", "$n", "absent", confirmation="candidate")]),
                       record=dict(actor="test", reason="原子性確認"), idempotency_key="failed-key")
        before = self.ok("meta", {})["graph_revision"]
        self.error("save-draft", request, "TARGET_NOT_FOUND")
        self.assertEqual(self.ok("meta", {})["graph_revision"], before)
        request["change_set"]["operations"].pop()
        self.ok("save-draft", request)

    def test_A15_success_replay_precedes_stale_basis_and_key_conflict(self):
        value = self.create()
        request = self.application(self.consult(self.update(value, body="48時間")), key="same-key")
        first = self.engine.execute("apply", request)
        self.assertTrue(first["ok"], first)
        current = self.current(value["id"])
        self.apply(self.update(current, body="72時間"))
        self.assertEqual(self.engine.execute("apply", request), first)
        request["decision"]["reason"] = "異なる判断"
        self.error("apply", request, "IDEMPOTENCY_CONFLICT")

    def test_A15_concurrent_same_key_applies_once(self):
        value = self.create()
        request = self.application(self.consult(self.update(value, body="48時間")), key="parallel")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: Engine(self.engine.path).execute("apply", request), range(2)))
        self.assertTrue(all(result["ok"] for result in results), results)
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(self.ok("history", dict(target_type="node", target_id=value["id"]))["revisions"]), 2)

    def test_A16_deterministic_consult_and_display_limit_not_basis_limit(self):
        values = self.seed()
        op = self.update(values["normal_retention"], body="48時間")
        a = self.consult(op, options=dict(max_related_items=1))
        b = self.consult(op, options=dict(max_related_items=100))
        self.assertEqual(a["basis"], b["basis"])
        self.assertTrue(a["related_page"]["has_more"])
        self.assertEqual(self.consult(op, options=dict(max_related_items=1)), a)

    def test_A17_priority_only_change_does_not_stop_unreferenced_plan(self):
        a, b = self.create(), self.create(title="前提")
        rel_id = self.apply(relation("dependency", a["id"], b["id"]))["created_refs"]["dependency"]["id"]
        consultation = self.consult(self.update(a, body="48時間"))
        rel = self.ok("relation-detail", dict(relation_id=rel_id))["relation"]
        self.apply(dict(op="update_relation", id=rel_id, expected_revision_id=rel["revision_id"], set=dict(priority=999)))
        result = self.ok("apply", self.application(consultation))
        self.assertGreater(result["validated_at_revision"], result["consulted_at_revision"])

    def test_A21_P1_unknown_features_and_old_formats_are_rejected(self):
        self.error("search", dict(include_descendants=True), "UNSUPPORTED_FEATURE")
        self.error("search", dict(mode="hybrid"), "INVALID_REQUEST")
        self.error("export", dict(format="markdown", destination=str(self.directory / "view")), "UNSUPPORTED_FEATURE")
        self.error("export", dict(format="json", destination="x", node_ids=[]), "INVALID_REQUEST")
        data = storage.initial()
        data["format_version"] = 1
        source = self.directory / "old.json"
        source.write_text(json.dumps(data))
        self.error("restore", dict(format="json", source=str(source)), "UNSUPPORTED_FORMAT", Engine(self.directory / "new.sqlite"))

    def test_A22_draft_scope_changes_and_unrelated_updates(self):
        values = self.seed()
        consultation = self.consult(self.update(values["normal_retention"], body="48時間"))
        self.save(relation("draft_scope", values["unrelated_question"]["id"], values["logs_scope"]["id"], "scoped_to"))
        self.create(title="別Scope未分類合意")
        result = self.ok("apply", self.application(consultation))
        self.assertIn("unclassified_changes", [d["code"] for d in result["diagnostics"]])

    def test_A23_backup_export_restore_preserve_identity_and_replay(self):
        values = self.seed()
        request = self.application(self.consult(self.update(values["normal_retention"], body="48時間")), key="replay-restored")
        result = self.engine.execute("apply", request)
        for format_, operation, suffix in (("json", "export", ".json"), ("sqlite", "backup", ".sqlite")):
            with self.subTest(format=format_):
                destination = self.directory / ("backup" + suffix)
                req = dict(destination=str(destination))
                if operation == "export":
                    req["format"] = "json"
                self.ok(operation, req)
                restored = Engine(self.directory / ("restored" + suffix + ".sqlite"))
                self.ok("restore", dict(format=format_, source=str(destination)), restored)
                self.assertEqual(self.ok("meta", {}), self.ok("meta", {}, restored))
                self.assertEqual(restored.execute("apply", request), result)
                self.error(operation, req, "DESTINATION_EXISTS")
                self.error("restore", dict(format=format_, source=str(destination)), "DESTINATION_EXISTS", restored)

    def test_A24_cli_stdin_stdout_and_errors(self):
        def run(operation, raw, **kwargs):
            return subprocess.run([sys.executable, "-m", "latis", "--db", str(self.engine.path), operation], input=raw, capture_output=True, cwd=ROOT, **kwargs)
        result = run("meta", b"{}")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(json.loads(result.stdout)["data"]["rules_version"], RULES)
        for raw in (b'{"query":null}', b'{"query":"a","query":"b"}', b'{"query":NaN}', b'[]', b'{"query":"\\ud800"}'):
            result = run("search", raw)
            self.assertEqual(result.returncode, 1, result)
            self.assertFalse(json.loads(result.stdout)["ok"])

    def test_A25_restore_branch_detects_same_revision_different_snapshot(self):
        value = self.create()
        backup = self.directory / "baseline.json"
        self.ok("export", dict(destination=str(backup)))
        self.apply(self.update(value, body="分岐A"))
        current = self.current(value["id"])
        old_consult = self.consult(self.update(current, body="古い分岐からの変更"))
        restored = Engine(self.directory / "branch.sqlite")
        self.ok("restore", dict(source=str(backup), format="json"), restored)
        consultation = restored.execute("consult", dict(proposal=dict(title="分岐B", body="別履歴"), change_set=dict(operations=[self.update(value, body="分岐B")])))
        self.assertTrue(consultation["ok"], consultation)
        self.ok("apply", self.application(consultation["data"]), restored)
        self.error("apply", self.application(old_consult), "BASIS_UNAVAILABLE", restored)

    def evidence_setup(self, outcome="passed"):
        agreement = self.create()
        code = self.create(kind="artifact", lifecycle="draft", title="コード", locator="file:app.py", content_hash="sha256:" + "0" * 64)
        test = self.create(kind="artifact", lifecycle="draft", title="テスト", locator="file:test_app.py")
        ev = dict(subject_refs=[dict(type="node", id=x["id"], revision_id=x["revision_id"]) for x in (code, test)],
                  method="python -m unittest -v", outcome=outcome, observed_at=now(), actor="agent:test")
        result = self.create(kind="artifact", lifecycle="draft", title="検査結果", evidence=ev, locator="file:result.txt")
        return agreement, code, test, result

    def test_E01_E02_E03_E05_E10_E11_recorded_verification_and_physical_limit(self):
        agreement, code, test, result = self.evidence_setup()
        rel_id = self.apply(relation("verified", agreement["id"], result["id"], "verified_by"))["created_refs"]["verified"]["id"]
        detail = self.ok("relation-detail", dict(relation_id=rel_id))
        self.assertEqual(detail["basis_status"], "current")
        self.assertEqual({r["id"] for r in detail["relation"]["basis_refs"]}, {x["id"] for x in (agreement, code, test, result)})
        (self.directory / "app.py").write_text("現物の未登録変更")
        self.assertEqual(self.ok("relation-detail", dict(relation_id=rel_id))["basis_status"], "current")
        self.save(self.update(test, body="テストを更新"))
        detail = self.ok("relation-detail", dict(relation_id=rel_id))
        self.assertEqual(detail["basis_status"], "changed")
        self.assertEqual(detail["diagnostics"][0]["code"], "verification_basis_changed")
        self.assertEqual(self.current(agreement["id"])["lifecycle"], "accepted")
        self.assertIn("verification_basis_changed", [d["code"] for d in self.ok("detail", dict(node_id=agreement["id"]))["diagnostics"]])

    def test_E04_failed_or_inconclusive_never_confirmed(self):
        for outcome in ("failed", "inconclusive"):
            agreement, code, test, result = self.evidence_setup(outcome)
            self.save(relation("candidate", agreement["id"], result["id"], "verified_by", "candidate"))
            request = dict(proposal=dict(title="検証", body="確認"), change_set=dict(operations=[relation("bad", agreement["id"], result["id"], "verified_by")]))
            self.error("consult", request, "INVALID_CHANGE")

    def test_E06_E07_old_evidence_cannot_be_reconfirmed_or_retargeted(self):
        agreement, code, test, result = self.evidence_setup()
        rel_id = self.apply(relation("verified", agreement["id"], result["id"], "verified_by"))["created_refs"]["verified"]["id"]
        self.save(self.update(code, body="新しいコード"))
        rel = self.ok("relation-detail", dict(relation_id=rel_id))["relation"]
        for extra in ({}, {"basis_targets": []}, {"basis_targets": [code["id"]]}):
            op = dict(op="update_relation", id=rel_id, expected_revision_id=rel["revision_id"], reconfirm=True, **extra)
            self.error("consult", dict(proposal=dict(title="再確認", body="確認"), change_set=dict(operations=[op])), "EVIDENCE_SUBJECT_CHANGED")
        old_result = self.create(kind="artifact", lifecycle="draft", evidence=result["evidence"])
        self.assertEqual(old_result["evidence"], result["evidence"])

    def test_E08_subject_changes_between_consult_and_apply_or_in_batch(self):
        agreement, code, test, result = self.evidence_setup()
        consultation = self.consult(relation("verified", agreement["id"], result["id"], "verified_by"))
        self.save(self.update(code, body="変更"))
        before = self.ok("meta", {})["graph_revision"]
        self.error("apply", self.application(consultation), "BASIS_CHANGED")
        self.assertEqual(self.ok("meta", {})["graph_revision"], before)
        agreement, code, test, result = self.evidence_setup()
        self.error("consult", dict(proposal=dict(title="同時変更", body="検証"), change_set=dict(operations=[self.update(code, body="同じbatchで変更"), relation("verified", agreement["id"], result["id"], "verified_by")])), "EVIDENCE_SUBJECT_CHANGED")

    def test_E09_evidence_and_its_locator_and_hash_are_immutable(self):
        agreement, code, test, result = self.evidence_setup()
        for patch in (dict(locator=result["locator"]), dict(content_hash=None), dict(evidence=None)):
            self.error("save-draft", dict(change_set=dict(operations=[self.update(result, **patch)]), record=dict(actor="test", reason="訂正"), idempotency_key=uid()),
                       "INVALID_REQUEST" if "evidence" in patch else "INVALID_CHANGE")
        self.save(self.update(result, title="補足"))

    def test_E12_provenance_history_and_historical_views(self):
        values = self.seed()
        normal = values["normal_retention"]
        consultation = self.consult(self.update(normal, body="48時間"))
        request = self.application(consultation, principal_refs=["human:owner"], execution_context=dict(session_ref="session-002"))
        self.ok("apply", request)
        other = Engine(self.engine.path)
        history = self.ok("history", dict(target_type="node", target_id=normal["id"]), other)
        latest_prov = next(p for p in history["provenance"] if p["commit_revision"] == history["revisions"][0]["commit_revision"])
        self.assertEqual(latest_prov["principal_refs"], ["human:owner"])
        self.assertEqual(latest_prov["execution_context"], dict(session_ref="session-002"))
        self.assertEqual(latest_prov["consulted_basis"], consultation["basis"])
        historical = self.ok("detail", dict(node_id=normal["id"], revision_id=normal["revision_id"]), other)
        self.assertEqual(historical["node"], normal)
        self.assertIsNone(historical["scope_ids"])

    def test_supersession_exception_cycles_and_terminal_states(self):
        old = self.create()
        result = self.apply(node("replacement", body="48時間"), self.update(old, lifecycle="superseded"), relation("supersedes", "$replacement", old["id"], "supersedes"))
        rel_id = result["created_refs"]["supersedes"]["id"]
        rel = self.ok("relation-detail", dict(relation_id=rel_id))["relation"]
        self.error("consult", dict(proposal=dict(title="終了", body="訂正"), change_set=dict(operations=[dict(op="update_relation", id=rel_id, expected_revision_id=rel["revision_id"], set=dict(lifecycle="retired"))])), "INVALID_CHANGE")
        old = self.current(old["id"])
        self.error("consult", dict(proposal=dict(title="復活", body="再採択"), change_set=dict(operations=[self.update(old, lifecycle="accepted")])), "INVALID_CHANGE")
        a, b = self.create(kind="scope"), self.create(kind="scope")
        self.error("consult", dict(proposal=dict(title="循環", body="確認"), change_set=dict(operations=[relation("ab", a["id"], b["id"], "contains"), relation("ba", b["id"], a["id"], "contains")])), "INVALID_CHANGE")

    def test_basis_tampering_and_unresolved_decision(self):
        value = self.create()
        request = self.application(self.consult(self.update(value, body="48時間")))
        bad = copy.deepcopy(request)
        bad["basis"]["refs"] = []
        bad["basis"]["watch"]["node_ids"] = []
        self.error("apply", bad, "INVALID_BASIS")
        request["decision"]["semantic_review"] = "needs_user_decision"
        self.error("apply", request, "UNRESOLVED_DECISION")

    def test_restore_rejects_corruption_without_creating_destination(self):
        self.seed()
        source = self.directory / "export.json"
        self.ok("export", dict(destination=str(source)))
        original = json.loads(source.read_text())
        for mutate in (lambda data: data["nodes"][0].update(body="履歴と不一致"),
                       lambda data: data["revisions"].pop(),
                       lambda data: data["commits"][-1].update(membership_changes=[]),
                       lambda data: data["nodes"][0].update(unknown=True)):
            data = copy.deepcopy(original)
            mutate(data)
            source.write_text(json.dumps(data))
            destination = self.directory / (uid() + ".sqlite")
            self.error("restore", dict(source=str(source), format="json"), "INVALID_DATABASE", Engine(destination))
            self.assertFalse(destination.exists())

    def test_limits_unknown_fields_and_no_changes(self):
        self.error("save-draft", dict(change_set=dict(operations=[node(lifecycle="draft", title="x" * 241)]), record=dict(actor="t", reason="検査"), idempotency_key=uid()), "LIMIT_EXCEEDED")
        value = self.create()
        self.error("consult", dict(proposal=dict(title="変更なし", body="確認"), change_set=dict(operations=[self.update(value, body=value["body"])])), "NO_CHANGES")
        self.error("save-draft", dict(change_set=dict(operations=[self.update(value, body="48時間")]), record=dict(actor="t", reason="検査"), idempotency_key=uid()), "CONSULTATION_REQUIRED")
        self.error("search", dict(limit=True), "INVALID_REQUEST")
        self.error("meta", dict(unknown=True), "INVALID_REQUEST")

    def test_normalization_golden_fixture_matches_engine_and_cli(self):
        fixture = json.loads((ROOT / "tests/fixtures/normalization.json").read_text())
        direct = self.ok("consult", fixture["request"])
        result = subprocess.run([str(ROOT / "bin/latis"), "--db", str(self.engine.path), "consult"], input=json.dumps(fixture["request"]).encode(), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        cli = json.loads(result.stdout)["data"]
        for response in (direct, cli):
            self.assertEqual(response["normalized_request"], fixture["normalized_request"])
            self.assertEqual(response["basis"]["change_digest"], fixture["change_digest"])

    def test_concurrent_different_requests_never_lose_an_update(self):
        value = self.create()
        requests = [self.application(self.consult(self.update(value, body=body))) for body in ("48時間", "72時間")]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda request: Engine(self.engine.path).execute("apply", request), requests))
        self.assertEqual(sum(result["ok"] for result in results), 1)
        self.assertEqual(next(result for result in results if not result["ok"])["errors"][0]["code"], "PRECONDITION_CHANGED")

    def test_transaction_rolls_back_after_late_storage_failure(self):
        request = dict(change_set=dict(operations=[node(lifecycle="draft")]), record=dict(actor="test", reason="障害注入"), idempotency_key="storage-failure")
        original = storage.write_commit
        def fail_after_writes(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("commit直前の障害を模擬")
        with patch("latis.storage.write_commit", side_effect=fail_after_writes):
            with self.assertRaises(RuntimeError):
                self.engine.execute("save-draft", request)
        self.assertEqual(self.ok("meta", {})["graph_revision"], 0)
        self.assertEqual(self.ok("search", dict(lifecycles=["draft"]))["items"], [])
        self.ok("save-draft", request)

    def test_supersession_chain_priority_changes_survive_restore(self):
        original = self.create()
        first = self.apply(node("next"), self.update(original, lifecycle="superseded"), relation("replacement", "$next", original["id"], "supersedes"))
        next_node = self.current(first["created_refs"]["next"]["id"])
        self.apply(node("last"), self.update(next_node, lifecycle="superseded"), relation("replacement", "$last", next_node["id"], "supersedes"))
        rel = self.ok("relation-detail", dict(relation_id=first["created_refs"]["replacement"]["id"]))["relation"]
        self.apply(dict(op="update_relation", id=rel["id"], expected_revision_id=rel["revision_id"], set=dict(priority=10)))
        source = self.directory / "chain.json"
        self.ok("export", dict(destination=str(source)))
        self.ok("restore", dict(source=str(source), format="json"), Engine(self.directory / "chain.sqlite"))

    def test_exception_does_not_retire_base_and_requires_qualifier(self):
        a, b = self.create(), self.create(title="例外")
        request = dict(proposal=dict(title="例外", body="確認"), change_set=dict(operations=[relation("exception", b["id"], a["id"], "exception_to")]))
        self.error("consult", request, "INVALID_CHANGE")
        request["change_set"]["operations"][0]["qualifier"] = "試験環境に限る。"
        self.ok("apply", self.application(self.ok("consult", request)))
        self.assertEqual(self.current(a["id"]), a)
        self.error("consult", dict(proposal=dict(title="循環", body="確認"), change_set=dict(operations=[relation("reverse", a["id"], b["id"], "exception_to", qualifier="条件")])), "INVALID_CHANGE")

    def test_draft_retirement_and_scope_retirement_in_same_batch(self):
        scope = self.create(kind="scope")
        draft = self.create(lifecycle="draft")
        rel_id = self.save(relation("scope", draft["id"], scope["id"], "scoped_to"))["created_refs"]["scope"]["id"]
        rel = self.ok("relation-detail", dict(relation_id=rel_id))["relation"]
        self.save(self.update(draft, lifecycle="retired"), dict(op="update_relation", id=rel_id, expected_revision_id=rel["revision_id"], set=dict(lifecycle="retired")))

    def test_restore_preserves_old_evidence_and_rejects_broken_success_records(self):
        agreement, code, test, result = self.evidence_setup()
        self.apply(relation("verified", agreement["id"], result["id"], "verified_by"))
        self.save(self.update(code, body="変更後"))
        self.create(kind="artifact", lifecycle="draft", evidence=result["evidence"])
        source = self.directory / "old-evidence.json"
        self.ok("export", dict(destination=str(source)))
        self.ok("restore", dict(source=str(source), format="json"), Engine(self.directory / "old-evidence.sqlite"))
        original = json.loads(source.read_text())
        for mutate in (lambda data: data["idempotency_records"].pop(),
                       lambda data: data["idempotency_records"][0]["response"]["data"].update(commit_revision=999)):
            data = copy.deepcopy(original)
            mutate(data)
            source.write_text(json.dumps(data))
            destination = self.directory / (uid() + ".sqlite")
            self.error("restore", dict(source=str(source), format="json"), "INVALID_DATABASE", Engine(destination))
            self.assertFalse(destination.exists())

    def test_missing_database_invalid_existing_file_and_symlinks(self):
        missing = Engine(self.directory / "missing.sqlite")
        self.error("meta", {}, "TARGET_NOT_FOUND", missing)
        self.assertFalse(missing.path.exists())
        unrelated = self.directory / "unrelated.sqlite"
        unrelated.write_bytes("既存ファイル".encode())
        self.error("init", {}, "INVALID_DATABASE", Engine(unrelated))
        self.assertEqual(unrelated.read_bytes(), "既存ファイル".encode())
        link = self.directory / "dangling.json"
        link.symlink_to(self.directory / "never-created.json")
        self.error("export", dict(destination=str(link)), "DESTINATION_EXISTS")
        self.assertFalse((self.directory / "never-created.json").exists())

    def test_multiple_changes_to_same_watched_record_return_context_error(self):
        values = self.seed()
        consultation = self.consult(self.update(values["normal_retention"], body="48時間"))
        audit = values["audit_retention"]
        for body in ("監査の1回目の変更", "監査の2回目の変更"):
            self.apply(self.update(audit, body=body))
            audit = self.current(audit["id"])
        self.error("apply", self.application(consultation), "CONTEXT_CHANGED")

    def test_sqlite_restore_rejects_unknown_schema_without_discarding_data(self):
        source = self.directory / "backup.sqlite"
        self.ok("backup", dict(destination=str(source)))
        conn = sqlite3.connect(source)
        conn.execute("CREATE TABLE unknown_data(value TEXT)")
        conn.execute("INSERT INTO unknown_data VALUES ('保持する情報')")
        conn.commit()
        conn.close()
        destination = self.directory / "rejected.sqlite"
        self.error("restore", dict(source=str(source), format="sqlite"), "INVALID_DATABASE", Engine(destination))
        self.assertFalse(destination.exists())
        conn = sqlite3.connect(source)
        self.assertEqual(conn.execute("SELECT value FROM unknown_data").fetchone()[0], "保持する情報")
        conn.close()

    def test_missing_intermediate_history_requires_reconsultation(self):
        value = self.create()
        consultation = self.consult(self.update(value, body="48時間"))
        self.create(title="無関係の追加")
        missing = self.ok("meta", {})["graph_revision"]
        self.create(title="もう一つの追加")
        conn = sqlite3.connect(self.engine.path)
        conn.execute("DELETE FROM commits WHERE id=?", (missing,))
        conn.commit()
        conn.close()
        self.error("apply", self.application(consultation), "BASIS_UNAVAILABLE")

    def test_success_replay_survives_unavailable_baseline(self):
        value = self.create()
        consultation = self.consult(self.update(value, body="48時間"))
        request = self.application(consultation, key="retained-success")
        result = self.engine.execute("apply", request)
        self.assertTrue(result["ok"], result)
        conn = sqlite3.connect(self.engine.path)
        conn.execute("DELETE FROM commits WHERE id=?", (consultation["basis"]["graph_revision"],))
        conn.commit()
        conn.close()
        self.assertEqual(self.engine.execute("apply", request), result)

    def test_exclusive_database_lock_is_busy_and_does_not_consume_key(self):
        request = dict(change_set=dict(operations=[node(lifecycle="draft")]), record=dict(actor="test", reason="ロック検査"), idempotency_key="retry-after-busy")
        conn = sqlite3.connect(self.engine.path)
        conn.execute("BEGIN EXCLUSIVE")
        try:
            self.error("save-draft", request, "BUSY")
        finally:
            conn.rollback()
            conn.close()
        self.ok("save-draft", request)


if __name__ == "__main__":
    unittest.main()
