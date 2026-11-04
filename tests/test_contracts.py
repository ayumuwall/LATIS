"""規範APIの条項に沿った境界・状態・参照の検証。"""

import copy
import json
import os
import sqlite3
import subprocess
import sys
from unittest.mock import patch

from latis import Engine, storage
from latis.model import CONTENT, KINDS, LIMITS, NODE_KEYS, OPERATIONS, RELATIONS, STATES, canonical, now, reference, uid
from tests.support import ContractCase, ROOT, node, relation


class ContractTests(ContractCase):
    def plan(self, operations, **extra):
        return dict(proposal=dict(title="契約の確認", body="規範仕様を確認する。"), change_set=dict(operations=operations), **extra)

    def revise_relation(self, value, **extra):
        return dict(op="update_relation", id=value["id"], expected_revision_id=value["revision_id"], **extra)

    def relation_value(self, id_):
        return self.ok("relation-detail", dict(relation_id=id_))["relation"]

    def proof(self, subjects, **extra):
        value = dict(subject_refs=[reference(subject) for subject in subjects], method="契約テストでの観測", outcome="passed", observed_at=now(), actor="test:observer")
        value.update(extra)
        return value

    def test_common_null_unknown_types_and_envelope(self):
        meta = self.ok("meta", {})
        self.assertEqual(meta["limits"], LIMITS)
        self.assertEqual(meta["capabilities"], OPERATIONS)
        for field, value in (("query", None), ("kinds", None), ("kinds", []), ("kinds", ["x:rule"]), ("lifecycles", []),
                             ("scope_ids", None), ("include_unscoped", None), ("include_descendants", 1), ("limit", None),
                             ("cursor", ""), ("cursor", 1), ("query", 1.0)):
            with self.subTest(field=field, value=value):
                response = self.error("search", {field: value}, "INVALID_REQUEST")
                self.assertEqual(set(response), {"ok", "data", "meta", "errors"})
                self.assertIsNone(response["data"])
                self.assertIn(response["meta"]["graph_revision"], (None, meta["graph_revision"]))
        for operation, request in (("meta", {"extra": 1}), ("init", {"extra": 1}), ("search", {"mode": "hybrid"}),
                                   ("search", {"scope_ids": ["missing"]})):
            self.error(operation, request, "TARGET_NOT_FOUND" if "scope_ids" in request else "INVALID_REQUEST")
        value = self.create()
        self.error("search", dict(scope_ids=[value["id"]]), "INVALID_REQUEST")
        for field in ("scope_ids", "anchor_node_ids", "basis_refs", "exploration_note"):
            self.error("consult", self.plan([node()], context={field: None}), "INVALID_REQUEST")
        self.error("consult", self.plan([node()], options=None), "INVALID_REQUEST")
        self.error("consult", self.plan([node()], options=dict(max_related_items=True)), "INVALID_REQUEST")

    def test_wire_utf8_size_limits_and_json_errors(self):
        maximum = LIMITS["max_request_bytes"]
        accepted = self.cli("meta", None, raw=b"{}" + b" " * (maximum - 2))
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        rejected = self.cli("meta", None, raw=b"{}" + b" " * (maximum - 1))
        self.assertEqual(rejected.returncode, 1)
        self.assertEqual(json.loads(rejected.stdout)["errors"][0]["code"], "LIMIT_EXCEEDED")
        for raw in (b'\xff', b'{} {}', b'{"x":Infinity}', b'{"x":1,"x":2}', b'{"query":' + b'[' * 1500 + b'0' + b']' * 1500 + b'}'):
            result = self.cli("search", None, raw=raw)
            self.assertEqual(result.returncode, 1, (raw[:30], result.stderr))
            self.assertEqual(json.loads(result.stdout)["errors"][0]["code"], "INVALID_REQUEST")
            self.assertEqual(result.stderr, b"")
        result = self.cli("unknown-operation", {})
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["ok"])

    def test_scalar_and_byte_limits_preserve_original_text(self):
        title = "😀" * 240
        body = "😀" * (1048576 // 4)
        value = self.create(lifecycle="draft", title=title, body=body)
        self.assertEqual(value["title"], title)
        self.assertEqual(value["body"], body)
        for patch_ in (dict(title=title + "a"), dict(body=body + "a")):
            self.error("save-draft", dict(change_set=dict(operations=[self.update(value, **patch_)]), record=dict(actor="test", reason="境界検査"), idempotency_key=uid()), "LIMIT_EXCEEDED")
        self.assertEqual(self.current(value["id"]), value)
        self.save(*[node(f"n{i}", lifecycle="draft", body="") for i in range(100)])
        self.error("consult", self.plan([node(f"n{i}") for i in range(101)]), "LIMIT_EXCEEDED")
        locator = "file:" + "a" * 2043
        artifact = self.create(kind="artifact", lifecycle="draft", locator=locator)
        self.assertEqual(artifact["locator"], locator)
        self.error("consult", self.plan([node(kind="artifact", locator=locator + "a")]), "LIMIT_EXCEEDED")

    def test_uri_hash_and_untrusted_strings_are_data(self):
        marker = self.directory / "must-not-exist"
        artifact = self.create(kind="artifact", lifecycle="draft", locator="https://example.invalid/unknown", content_hash="sha256:" + "a" * 64,
                               evidence=self.proof([self.create()], method=f"touch {marker}"))
        self.assertEqual(artifact["evidence"]["method"], f"touch {marker}")
        self.assertFalse(marker.exists())
        for locator in ("relative.py", "", "file:a b", "file:a\n", "file:a\x00", "file:a\x7f"):
            self.error("consult", self.plan([node(kind="artifact", locator=locator)]), "INVALID_REQUEST" if not locator else "INVALID_CHANGE")
        for hash_ in ("SHA256:" + "a" * 64, "sha256:" + "A" * 64, "sha256:" + "a" * 63):
            self.error("consult", self.plan([node(kind="artifact", content_hash=hash_)]), "INVALID_CHANGE")
        ordinary = self.create(kind="artifact", lifecycle="draft", locator="file:a", content_hash="sha256:" + "0" * 64)
        self.save(self.update(ordinary, locator=None, content_hash=None))
        self.assertIsNone(self.current(ordinary["id"])["locator"])

    def test_node_kinds_and_lifecycle_matrix(self):
        for kind in sorted(KINDS):
            value = self.create(kind=kind, lifecycle="proposed", body="原文\n  ")
            self.assertEqual(set(value), NODE_KEYS)
            self.apply(self.update(value, lifecycle="accepted"))
            self.assertEqual(self.current(value["id"])["kind"], kind)
            self.error("consult", self.plan([self.update(self.current(value["id"]), lifecycle="draft")]), "INVALID_CHANGE")
        allowed = {"draft": {"draft", "proposed", "accepted", "rejected", "retired"},
                   "proposed": {"draft", "proposed", "accepted", "rejected", "retired"},
                   "accepted": {"accepted", "retired", "superseded"}, "rejected": {"rejected"}, "retired": {"retired"}, "superseded": {"superseded"}}
        for before in sorted(STATES):
            value = self.create(lifecycle=before if before in {"draft", "proposed", "accepted"} else "draft")
            if before == "superseded":
                self.apply(self.update(value, lifecycle="accepted"))
                value = self.current(value["id"])
                self.apply(node("replacement"), self.update(value, lifecycle="superseded"), relation("replace", "$replacement", value["id"], "supersedes"))
                value = self.current(value["id"])
            elif before in {"rejected", "retired"}:
                self.apply(self.update(value, lifecycle=before))
                value = self.current(value["id"])
            for after in sorted(STATES):
                with self.subTest(before=before, after=after):
                    ops = [self.update(value, lifecycle=after, body="変更後")]
                    if before == "accepted" and after == "superseded":
                        ops += [node("next"), relation("replace", "$next", value["id"], "supersedes")]
                    response = self.engine.execute("consult", self.plan(ops))
                    self.assertEqual(response["ok"], after in allowed[before], response)

    def test_immutable_node_fields_and_local_reference_validation(self):
        value = self.create()
        for key, replacement in (("id", "other"), ("kind", "artifact"), ("scope_ids", []), ("revision_id", "other"), ("evidence", None)):
            self.error("consult", self.plan([self.update(value, **{key: replacement})]), "INVALID_REQUEST")
        self.error("consult", self.plan([self.update(value, locator=None)]), "INVALID_CHANGE")
        for operations in ([node("same"), node("same")], [self.update(value, body="a"), self.update(value, body="b")],
                           [node("created"), dict(op="update_node", id="$created", expected_revision_id="unknown", set=dict(body="a"))],
                           [relation("bad", "$missing", value["id"], confirmation="candidate")],
                           [node("Bad")], [node("n" * 65)]):
            response = self.engine.execute("consult", self.plan(operations))
            self.assertFalse(response["ok"], response)
        self.assertEqual(self.current(value["id"]), value)

    def test_relation_kind_matrix_and_final_endpoint_versions(self):
        a, b = self.create(), self.create()
        code = self.create(kind="artifact", lifecycle="draft")
        proof = self.create(kind="artifact", lifecycle="draft", evidence=self.proof([code]))
        s, t = self.create(kind="scope"), self.create(kind="scope")
        endpoints = {"contains": (s, t), "scoped_to": (a, s), "implemented_by": (a, code), "verified_by": (a, proof)}
        self.error("consult", self.plan([relation("no_evidence", a["id"], code["id"], "verified_by")]), "INVALID_CHANGE")
        for kind in sorted(RELATIONS):
            left, right = endpoints.get(kind, (a, b))
            ops = [relation("rel", left["id"], right["id"], kind, qualifier="条件" if kind == "exception_to" else None)]
            if kind == "supersedes":
                old = self.create()
                ops = [self.update(old, lifecycle="superseded"), relation("rel", a["id"], old["id"], kind)]
            result = self.apply(*ops)
            rel = self.relation_value(result["created_refs"]["rel"]["id"])
            self.assertEqual(rel["relation_kind"], kind)
            if kind in CONTENT:
                self.assertTrue({rel["from_node_id"], rel["to_node_id"]} <= {ref["id"] for ref in rel["basis_refs"]})
            else:
                self.assertEqual(rel["basis_refs"], [])
            self.error("consult", self.plan([relation("self", left["id"], left["id"], kind)]), "INVALID_CHANGE")
        for kind in ("contains", "scoped_to", "implemented_by", "verified_by"):
            self.error("consult", self.plan([relation("wrong", a["id"], b["id"], kind)]), "INVALID_CHANGE")
        for kind in ("exception_to", "supersedes", "specializes", "conflicts_with"):
            self.error("consult", self.plan([relation("wrong", a["id"], code["id"], kind)]), "INVALID_CHANGE")

    def test_relation_confirmation_reconfirmation_and_additional_roots(self):
        a, b, extra = self.create(), self.create(), self.create(lifecycle="draft")
        created = self.apply(relation("dep", a["id"], b["id"], basis_targets=[extra["id"]]))
        rel = self.relation_value(created["created_refs"]["dep"]["id"])
        self.save(self.update(extra, body="根拠の変更"))
        self.error("consult", self.plan([self.revise_relation(rel, set=dict(qualifier="新条件"))]), "INVALID_CHANGE")
        self.apply(self.revise_relation(rel, set=dict(priority=100)))
        current = self.relation_value(rel["id"])
        self.assertEqual(current["basis_refs"], rel["basis_refs"])
        consulted = self.consult(self.revise_relation(current, reconfirm=True))
        self.assertEqual(consulted["normalized_request"]["change_set"]["operations"][0]["basis_targets"], [extra["id"]])
        self.ok("apply", self.application(consulted))
        current = self.relation_value(rel["id"])
        self.apply(self.update(a, body="同じcommitで改訂"), self.revise_relation(current, reconfirm=True, basis_targets=[]))
        final = self.relation_value(rel["id"])
        self.assertEqual(final["basis_refs"], sorted([reference(self.current(a["id"])), reference(b)], key=lambda x: x["id"]))
        for patch_ in (dict(confirmation="candidate"), dict(from_node_id=b["id"]), dict(origin="human")):
            response = self.engine.execute("consult", self.plan([self.revise_relation(final, set=patch_)]))
            self.assertFalse(response["ok"], response)
        candidate_id = self.save(relation("candidate", a["id"], b["id"], confirmation="candidate"))["created_refs"]["candidate"]["id"]
        candidate = self.relation_value(candidate_id)
        self.error("consult", self.plan([self.revise_relation(candidate, reconfirm=True)]), "INVALID_CHANGE")
        self.error("consult", self.plan([relation("duplicate", a["id"], b["id"])]), "INVALID_CHANGE")

    def test_supersedes_repair_and_existing_accepted_replacement(self):
        old, replacement = self.create(), self.create(body="置換先")
        result = self.apply(self.update(old, lifecycle="superseded"), relation("replace", replacement["id"], old["id"], "supersedes"))
        self.apply(node("restored", body=old["body"]), relation("origin", "$restored", old["id"], "originates_from"), self.update(replacement, lifecycle="retired"))
        self.assertEqual(self.current(old["id"])["lifecycle"], "superseded")
        self.assertEqual(self.relation_value(result["created_refs"]["replace"]["id"])["lifecycle"], "active")
        self.ok("export", dict(destination=str(self.directory / "repair.json")))

    def test_search_order_scope_or_and_summary_contract(self):
        exact = self.create(title="ログ 保持", body="先頭\n" + "😀" * 260)
        title_match = self.create(title="通常ログ 保持期間", body="")
        body_match = self.create(title="別の項目", body="ログを保持する。")
        self.create(kind="artifact", lifecycle="draft", title="ログ 保持")
        result = self.ok("search", dict(query="ログ 保持"))
        self.assertEqual([item["id"] for item in result["items"]], [exact["id"], title_match["id"], body_match["id"]])
        self.assertEqual(set(result["items"][0]), {"id", "revision_id", "kind", "lifecycle", "title", "excerpt", "scope_ids", "matched_fields"})
        self.assertEqual(result["items"][0]["excerpt"], exact["body"][:240])
        self.assertEqual(self.ok("search", dict(query="保持"))["page"]["returned_count"], 3)
        s, t = self.create(kind="scope"), self.create(kind="scope")
        self.apply(relation("one", exact["id"], s["id"], "scoped_to"), relation("two", body_match["id"], t["id"], "scoped_to"), relation("tree", s["id"], t["id"], "contains"))
        self.assertEqual([item["id"] for item in self.ok("search", dict(scope_ids=[s["id"]]))["items"]], [exact["id"]])
        result = self.ok("search", dict(scope_ids=[s["id"], t["id"], s["id"]]))
        self.assertEqual({item["id"] for item in result["items"]}, {exact["id"], body_match["id"]})
        self.assertEqual(result["applied_filters"]["expanded_scope_ids"], sorted([s["id"], t["id"]]))
        self.assertEqual(self.ok("search", dict(kinds=["scope"], scope_ids=[s["id"]]))["items"], [])

    def test_relations_filters_pages_history_and_retired_endpoint(self):
        a, b = self.create(), self.create()
        ids = []
        for i in range(3):
            ids.append(self.save(relation("candidate", a["id"], b["id"], "conflicts_with", "candidate", qualifier=str(i)))["created_refs"]["candidate"]["id"])
        self.assertEqual(self.ok("relations", dict(node_id=a["id"], direction="in"))["items"], [])
        self.assertEqual(len(self.ok("relations", dict(node_id=b["id"], direction="both"))["items"]), 3)
        found, cursor = [], None
        while True:
            result = self.ok("relations", dict(node_id=a["id"], limit=1, cursor=cursor))
            found.extend(item["relation"]["id"] for item in result["items"])
            cursor = result["page"]["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(found, sorted(ids))
        old = self.relation_value(ids[0])
        self.apply(self.revise_relation(old, set=dict(confirmation="confirmed")))
        self.apply(self.update(b, lifecycle="retired"))
        historical = self.ok("relation-detail", dict(relation_id=old["id"], revision_id=old["revision_id"]))
        self.assertEqual(historical["relation"], old)
        self.assertIsNone(historical["basis_status"])
        self.assertEqual(historical["diagnostics"], [])
        self.assertEqual(self.ok("relations", dict(node_id=a["id"], confirmations=["confirmed"]))["items"][0]["other_node_summary"]["lifecycle"], "retired")
        history = self.ok("history", dict(target_type="relation", target_id=old["id"], limit=1))
        self.assertTrue(history["page"]["has_more"])
        self.assertEqual(len(history["provenance"]), 1)
        self.error("relations", dict(node_id=a["id"], relation_kinds="conflicts_with"), "INVALID_REQUEST")

    def test_save_draft_permission_boundary_and_terminal_membership(self):
        scope = self.create(kind="scope")
        draft = self.create(lifecycle="draft")
        accepted = self.create()
        for operations in ([node()], [self.update(accepted, body="変更")], [self.update(scope, title="変更")],
                           [relation("scope", accepted["id"], scope["id"], "scoped_to")],
                           [self.update(draft, lifecycle="retired"), relation("scope", draft["id"], scope["id"], "scoped_to")]):
            self.error("save-draft", dict(change_set=dict(operations=operations), record=dict(actor="test", reason="許可範囲"), idempotency_key=uid()), "CONSULTATION_REQUIRED")
        self.save(node("new_scope", kind="scope"), relation("candidate", accepted["id"], draft["id"], confirmation="candidate"))
        result = self.save(relation("scope", draft["id"], scope["id"], "scoped_to"))
        rel = self.relation_value(result["created_refs"]["scope"]["id"])
        self.error("save-draft", dict(change_set=dict(operations=[self.revise_relation(rel, set=dict(priority=1))]), record=dict(actor="test", reason="確定判断"), idempotency_key=uid()), "CONSULTATION_REQUIRED")
        self.save(self.update(draft, lifecycle="retired"), self.revise_relation(rel, set=dict(lifecycle="retired")))

    def test_consult_new_evidence_additional_root_is_watched(self):
        a, b, code = self.create(), self.create(), self.create(kind="artifact", lifecycle="draft")
        consultation = self.consult(node("proof", kind="artifact", lifecycle="draft", evidence=self.proof([code])),
                                    relation("dep", a["id"], b["id"], basis_targets=["$proof"]), options=dict(max_related_items=1))
        expected = sorted([a["id"], b["id"], code["id"]])
        self.assertEqual(consultation["basis"]["watch"]["node_ids"], expected)
        self.assertEqual(sorted(r["id"] for r in consultation["basis"]["refs"]), expected)
        self.save(self.update(code, body="照合後のコード変更"))
        self.error("apply", self.application(consultation), "BASIS_CHANGED")

    def test_consult_evidence_expansion_is_one_level(self):
        a, b = self.create(), self.create()
        code = self.create(kind="artifact", lifecycle="draft")
        first = self.create(kind="artifact", lifecycle="draft", evidence=self.proof([code]))
        second = self.create(kind="artifact", lifecycle="draft", evidence=self.proof([first]))
        consultation = self.consult(relation("dep", a["id"], b["id"], basis_targets=[second["id"]]))
        self.assertEqual(set(consultation["basis"]["watch"]["node_ids"]), {a["id"], b["id"], first["id"], second["id"]})
        self.assertNotIn(code["id"], consultation["basis"]["watch"]["node_ids"])
        verified = self.apply(relation("verified", a["id"], second["id"], "verified_by"))["created_refs"]["verified"]["id"]
        rel = self.relation_value(verified)
        consulted = self.consult(self.update(b, body="変更"), context=dict(basis_refs=[reference(rel, "relation")]))
        self.assertIn(first["id"], consulted["basis"]["watch"]["node_ids"])

    def test_consult_scope_conflicts_and_inclusion_reasons(self):
        a, b = self.create(), self.create()
        scope = self.create(kind="scope")
        self.apply(relation("a_scope", a["id"], scope["id"], "scoped_to"), relation("b_scope", b["id"], scope["id"], "scoped_to"),
                   relation("conflict", a["id"], b["id"], "conflicts_with"))
        scoped = self.consult(node("new"), context=dict(scope_ids=[scope["id"]]))
        self.assertIn("recorded_conflict", [d["code"] for d in scoped["diagnostics"]])
        before = self.snapshot()
        full = self.consult(self.update(a, body="48時間"))
        self.assertEqual(self.snapshot(), before)
        by_id = {item["id"]: item for item in full["related_items"]}
        self.assertEqual(by_id[a["id"]]["inclusion_reasons"], ["seed", "same_scope"])
        self.assertEqual(by_id[b["id"]]["inclusion_reasons"], ["explicit_relation_neighbor", "same_scope"])
        self.assertEqual(by_id[scope["id"]]["inclusion_reasons"], ["explicit_relation_neighbor", "same_scope"])
        small = self.consult(self.update(a, body="48時間"), options=dict(max_related_items=1))
        self.assertEqual(small["basis"], full["basis"])
        self.assertTrue(small["related_page"]["has_more"])

    def test_opaque_ids_do_not_collide_with_planning_placeholders(self):
        old = self.create()
        data = self.snapshot()
        opaque_id = "pending:new_agreement"
        rewritten = canonical(data).replace(json.dumps(old["id"]), json.dumps(opaque_id))
        source = self.directory / "opaque.json"
        source.write_text(rewritten)
        restored = Engine(self.directory / "opaque.sqlite")
        self.ok("restore", dict(source=str(source), format="json"), restored)
        self.engine = restored
        old = self.current(opaque_id)
        result = self.apply(node("new_agreement"), self.update(old, lifecycle="superseded"), relation("replace", "$new_agreement", old["id"], "supersedes"))
        self.assertNotEqual(result["created_refs"]["new_agreement"]["id"], old["id"])
        self.assertEqual(self.current(old["id"])["lifecycle"], "superseded")

    def test_precondition_and_basis_error_precede_context_or_missing_delta(self):
        value, anchor = self.create(), self.create()
        consultation = self.consult(self.update(value, body="48時間"), context=dict(basis_refs=[reference(anchor)]))
        self.apply(self.update(anchor, body="根拠更新"))
        missing = self.ok("meta", {})["graph_revision"]
        self.create(title="別の更新")
        conn = sqlite3.connect(self.engine.path)
        conn.execute("DELETE FROM commits WHERE id=?", (missing,))
        conn.commit()
        conn.close()
        response = self.error("apply", self.application(consultation), "BASIS_CHANGED")
        self.assertEqual(response["errors"][0]["details"]["current_revision"], response["meta"]["graph_revision"])
        self.assertEqual(response["errors"][0]["details"]["next_action"], "reconsult")
        self.apply(self.update(value, body="対象の更新"))
        response = self.error("apply", self.application(consultation), "PRECONDITION_CHANGED")
        self.assertEqual(response["errors"][0]["details"]["current_revision"], response["meta"]["graph_revision"])

    def test_candidate_and_unrelated_scope_updates_do_not_block(self):
        values = self.seed()
        other_scope = self.create(kind="scope")
        separate = self.create()
        self.apply(relation("scope", separate["id"], other_scope["id"], "scoped_to"))
        consultation = self.consult(self.update(values["normal_retention"], body="48時間"))
        self.save(relation("candidate", values["normal_retention"]["id"], values["audit_retention"]["id"], "conflicts_with", "candidate"))
        self.apply(self.update(separate, body="別Scopeで更新"))
        result = self.ok("apply", self.application(consultation))
        self.assertGreater(result["validated_at_revision"], result["consulted_at_revision"])

    def test_explicit_relation_priority_change_is_basis_changed(self):
        a, b = self.create(), self.create()
        rel = self.relation_value(self.apply(relation("dep", a["id"], b["id"]))["created_refs"]["dep"]["id"])
        consultation = self.consult(self.update(a, body="48時間"), context=dict(basis_refs=[reference(rel, "relation")]))
        self.apply(self.revise_relation(rel, set=dict(priority=999)))
        self.error("apply", self.application(consultation), "BASIS_CHANGED")

    def test_idempotency_normalization_global_keys_and_execution_context(self):
        request = dict(change_set=dict(operations=[node(lifecycle="draft")]), record=dict(actor="test", reason="同じ保存", principal_refs=["human:z", "human:a", "human:a"]), idempotency_key="shared")
        first = self.engine.execute("save-draft", request)
        self.assertTrue(first["ok"], first)
        equivalent = copy.deepcopy(request)
        equivalent["record"].update(source_refs=[], principal_refs=["human:a", "human:z"])
        self.assertEqual(self.engine.execute("save-draft", equivalent), first)
        equivalent["record"]["execution_context"] = {}
        self.error("save-draft", equivalent, "IDEMPOTENCY_CONFLICT")
        application = self.application(self.consult(node()), key="shared")
        self.error("apply", application, "IDEMPOTENCY_CONFLICT")
        for invalid in ("", "has space", "x/1", "x" * 129, "日本語"):
            bad = copy.deepcopy(request)
            bad["idempotency_key"] = invalid
            self.error("save-draft", bad, "INVALID_REQUEST")

    def test_same_key_in_separate_cli_processes_commits_once(self):
        value = self.create()
        request = self.application(self.consult(self.update(value, body="48時間")), key="two-processes")
        command = [str(ROOT / "bin/latis"), "--db", str(self.engine.path), "apply"]
        raw = json.dumps(request).encode()
        first = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        second = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        first.stdin.write(raw)
        first.stdin.close()
        first.stdin = None
        out2, err2 = second.communicate(raw, timeout=15)
        out1, err1 = first.communicate(timeout=15)
        self.assertEqual((first.returncode, second.returncode), (0, 0), (err1, err2))
        self.assertEqual(json.loads(out1), json.loads(out2))
        self.assertEqual(len(self.ok("history", dict(target_type="node", target_id=value["id"]))["revisions"]), 2)

    def test_evidence_reference_shape_limits_and_explicit_immutability(self):
        code = self.create(kind="artifact", lifecycle="draft")
        original = code
        self.save(self.update(code, body="新しいコード"))
        code = self.current(code["id"])
        duplicate = self.proof([code, code])
        result = self.create(kind="artifact", lifecycle="draft", evidence=duplicate)
        self.assertEqual(result["evidence"]["subject_refs"], [reference(code)])
        for field, value, expected in (("subject_refs", [reference(code), reference(original)], "INVALID_REQUEST"),
                                       ("subject_refs", [reference(code)] * 101, "LIMIT_EXCEEDED"),
                                       ("subject_refs", [dict(type="node", id="$local", revision_id="unknown")], "INVALID_REQUEST"),
                                       ("subject_refs", [dict(type="relation", id=code["id"], revision_id=code["revision_id"])], "INVALID_REQUEST"),
                                       ("subject_refs", [dict(type="node", id=code["id"], revision_id="missing")], "REVISION_NOT_FOUND"),
                                       ("observed_at", "2026-11-04T12:00:00+09:00", "INVALID_REQUEST"),
                                       ("observed_at", "2026-02-30T00:00:00Z", "INVALID_REQUEST"),
                                       ("source_refs", None, "INVALID_REQUEST"), ("method", "", "INVALID_REQUEST")):
            ev = self.proof([code])
            ev[field] = value
            self.error("consult", self.plan([node(kind="artifact", evidence=ev)]), expected)
        accepted_result = self.current(result["id"])
        self.apply(self.update(accepted_result, lifecycle="accepted"))
        accepted_result = self.current(result["id"])
        for field in ("locator", "content_hash"):
            self.error("save-draft", dict(change_set=dict(operations=[self.update(accepted_result, **{field: None})]), record=dict(actor="test", reason="固定値の確認"), idempotency_key=uid()), "INVALID_CHANGE")

    def test_cli_db_precedence_and_missing_database_not_created(self):
        environment_db = self.directory / "environment.sqlite"
        self.ok("init", {}, Engine(environment_db))
        env = dict(os.environ, LATIS_DB=str(environment_db))
        command = [str(ROOT / "bin/latis"), "meta"]
        result = subprocess.run(command, input=b"{}", capture_output=True, env=env, cwd=self.directory)
        self.assertEqual(json.loads(result.stdout)["meta"]["database_id"], self.ok("meta", {}, Engine(environment_db))["database_id"])
        explicit = self.cli("meta", {}, env=env)
        self.assertEqual(json.loads(explicit.stdout)["meta"]["database_id"], self.ok("meta", {})["database_id"])
        child = self.directory / "nested"
        child.mkdir()
        env.pop("LATIS_DB")
        result = subprocess.run(command, input=b"{}", capture_output=True, env=env, cwd=child)
        self.assertEqual(result.returncode, 1)
        self.assertFalse((child / ".latis").exists())
        result = subprocess.run([str(ROOT / "bin/latis"), "init"], input=b"{}", capture_output=True, env=env, cwd=child)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((child / ".latis/latis.sqlite").is_file())

    def test_snapshot_rejects_types_provenance_and_success_response_mismatch(self):
        values = self.seed()
        self.apply(self.update(values["normal_retention"], body="48時間"))
        original = self.snapshot()
        def changed_node_commit(data):
            revision = next(r for r in data["revisions"] if r["target_id"] == values["logs_scope"]["id"])
            revision["snapshot"]["commit_revision"] = True
            next(n for n in data["nodes"] if n["id"] == revision["target_id"])["commit_revision"] = True
        def swap_response_partition(data):
            response = next(r for r in data["idempotency_records"] if r["response"]["data"]["updated_refs"])["response"]["data"]
            response["created_refs"]["fabricated"] = response["updated_refs"].pop()
        mutations = [changed_node_commit, swap_response_partition,
                     lambda d: d["provenance"][0].update(actor="別の実行者"),
                     lambda d: d["provenance"][0]["proposal"].update(unknown=True),
                     lambda d: d["provenance"][0]["change_set"]["operations"][0].update(unknown=True),
                     lambda d: d["provenance"][0]["decision"].update(semantic_review="needs_user_decision"),
                     lambda d: d["provenance"][0].update(validated_at_revision=False),
                     lambda d: d["commits"][0].update(snapshot_id=""),
                     lambda d: next(r for r in d["idempotency_records"] if r["response"]["meta"]["graph_revision"] == 1)["response"]["meta"].update(graph_revision=True)]
        for mutate in mutations:
            data = copy.deepcopy(original)
            mutate(data)
            source = self.directory / "invalid.json"
            source.write_text(json.dumps(data))
            destination = self.directory / (uid() + ".sqlite")
            self.error("restore", dict(format="json", source=str(source)), "INVALID_DATABASE", Engine(destination))
            self.assertFalse(destination.exists())

    def test_sqlite_duplicate_json_keys_and_invalid_scalar_are_not_discarded(self):
        self.create()
        for modify in (lambda raw: '{"database_id":"hidden",' + raw[1:],
                       lambda raw: raw.replace('"graph_revision":1', '"graph_revision":true')):
            source = self.directory / (uid() + ".sqlite")
            self.ok("backup", dict(destination=str(source)))
            conn = sqlite3.connect(source)
            raw = conn.execute("SELECT data FROM metadata").fetchone()[0]
            altered = modify(raw)
            self.assertNotEqual(altered, raw)
            conn.execute("UPDATE metadata SET data=?", (altered,))
            conn.commit()
            conn.close()
            self.error("restore", dict(format="sqlite", source=str(source)), "INVALID_DATABASE", Engine(self.directory / (uid() + ".sqlite")))

    def test_backup_wal_snapshot_and_publish_failure(self):
        self.create()
        conn = sqlite3.connect(self.engine.path)
        self.assertEqual(conn.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        conn.close()
        value = self.create(lifecycle="draft")
        source = self.directory / "wal.sqlite"
        self.ok("backup", dict(destination=str(source)))
        restored = Engine(self.directory / "restored-wal.sqlite")
        self.ok("restore", dict(source=str(source), format="sqlite"), restored)
        self.assertEqual(self.ok("detail", dict(node_id=value["id"]), restored)["node"], value)
        destination = self.directory / "unfinished.json"
        before = set(self.directory.iterdir())
        def failed_writer(path):
            with open(path, "w") as output:
                output.write("未完了")
            raise OSError("出力失敗を模擬")
        with self.assertRaises(OSError):
            storage.publish(destination, failed_writer)
        self.assertFalse(destination.exists())
        self.assertEqual(set(self.directory.iterdir()), before)

    def test_explicit_retired_judgment_reports_old_basis(self):
        a, b = self.create(), self.create()
        rel = self.relation_value(self.apply(relation("dep", a["id"], b["id"]))["created_refs"]["dep"]["id"])
        self.apply(self.revise_relation(rel, set=dict(lifecycle="retired")))
        retired = self.relation_value(rel["id"])
        self.apply(self.update(b, body="古い判断の根拠を改訂"))
        consulted = self.consult(self.update(a, body="48時間"), context=dict(basis_refs=[reference(retired, "relation")]))
        self.assertTrue(any(d["code"] == "basis_changed" and d["target_refs"] == [reference(retired, "relation")] for d in consulted["diagnostics"]))

    def test_maximum_evidence_subjects_are_not_limited_by_display_count(self):
        created = self.save(*[node(f"s{i}", kind="artifact", lifecycle="draft") for i in range(100)])
        subjects = [self.current(ref["id"]) for ref in created["created_refs"].values()]
        agreement = self.create()
        result = self.create(kind="artifact", lifecycle="draft", evidence=self.proof(subjects))
        consulted = self.consult(relation("verified", agreement["id"], result["id"], "verified_by"), options=dict(max_related_items=1))
        self.assertEqual(len(consulted["basis"]["refs"]), 102)
        self.assertEqual(len(consulted["basis"]["watch"]["node_ids"]), 102)
        self.assertEqual(consulted["related_page"]["returned_count"], 1)
        applied = self.ok("apply", self.application(consulted))
        self.assertEqual(len(self.relation_value(applied["created_refs"]["verified"]["id"])["basis_refs"]), 102)
        combined = self.consult(node("new_proof", kind="artifact", lifecycle="draft", evidence=self.proof(subjects)),
                                relation("new_verified", agreement["id"], "$new_proof", "verified_by"), options=dict(max_related_items=1))
        self.assertEqual(len(combined["basis"]["refs"]), 101)
        self.ok("apply", self.application(combined))
        self.snapshot()

    def test_execution_metadata_resolutions_and_source_order(self):
        source_refs = ["二番目\n", "一番目\t", "二番目\n"]
        request = self.plan([node()], context=dict(exploration_note="根拠の記録"))
        request["proposal"]["source_refs"] = source_refs
        consulted = self.ok("consult", request)
        self.assertEqual(consulted["normalized_request"]["proposal"]["source_refs"], source_refs)
        resolution = dict(issue="対象の確認", source_refs=["会話の指示"], resolution="通常ログだけを変更する", authority_ref="明示された指示")
        applied = self.ok("apply", self.application(consulted, principal_refs=["human:outside-node-table"],
                                                   execution_context=dict(model="申告したモデル", provider="申告した提供元"), resolutions=[resolution]))
        history = self.ok("history", dict(target_type="node", target_id=applied["created_refs"]["n"]["id"]))
        prov = history["provenance"][0]
        self.assertEqual(prov["source_refs"], source_refs)
        self.assertEqual(prov["decision"]["resolutions"], [resolution])
        self.assertNotIn("model_version", prov["execution_context"])
        for context_ in (None, dict(model=""), dict(unknown="x")):
            self.error("save-draft", dict(change_set=dict(operations=[node(lifecycle="draft")]), record=dict(actor="test", reason="実行情報", execution_context=context_), idempotency_key=uid()), "INVALID_REQUEST")

    def test_rfc3339_utc_forms_preserve_observation_time(self):
        subject = self.create()
        for observed in ("2026-11-04t12:00:00z", "2026-11-04T12:00:00.123456789+00:00", "2016-12-31T23:59:60Z"):
            result = self.create(kind="artifact", lifecycle="draft", evidence=self.proof([subject], observed_at=observed))
            self.assertEqual(result["evidence"]["observed_at"], observed)
        for observed in ("2026-11-04T12:00:60Z", "2026-11-04T23:59:60Z", "2026-11-04T24:00:00Z", "2026-13-01T00:00:00Z"):
            self.error("consult", self.plan([node(kind="artifact", evidence=self.proof([subject], observed_at=observed))]), "INVALID_REQUEST")

    def test_snapshot_record_times_need_not_be_identical(self):
        self.create()
        data = self.snapshot()
        data["provenance"][0]["created_at"] = "2026-11-04T00:00:00.123Z"
        source = self.directory / "independent-times.json"
        source.write_text(json.dumps(data))
        self.ok("restore", dict(source=str(source), format="json"), Engine(self.directory / "independent-times.sqlite"))

    def test_basis_metadata_digest_and_read_revision_errors(self):
        value, other = self.create(), self.create()
        consulted = self.consult(self.update(value, body="48時間"))
        original = self.application(consulted)
        for field, replacement, expected in (("database_id", "different-db", "INVALID_BASIS"),
                                               ("schema_version", "basis-unknown", "INVALID_BASIS"),
                                               ("rules_version", "other-rules", "RULES_CHANGED"),
                                               ("change_digest", "sha256:" + "0" * 64, "INVALID_BASIS"),
                                               ("snapshot_id", "different-snapshot", "BASIS_UNAVAILABLE"),
                                               ("graph_revision", 999, "BASIS_UNAVAILABLE")):
            request = copy.deepcopy(original)
            request["basis"][field] = replacement
            self.error("apply", request, expected)
        changed = copy.deepcopy(original)
        changed["change_set"]["operations"][0]["set"]["body"] = "別の変更"
        self.error("apply", changed, "INVALID_BASIS")
        self.error("detail", dict(node_id=value["id"], revision_id=other["revision_id"]), "REVISION_NOT_FOUND")
        self.error("consult", self.plan([node()], context=dict(basis_refs=[dict(type="node", id=value["id"], revision_id="missing")])), "REVISION_NOT_FOUND")
        self.error("consult", self.plan([node()], context=dict(scope_ids=[value["id"]])), "INVALID_REQUEST")
        self.error("consult", self.plan([node()], context=dict(anchor_node_ids=["missing"])), "TARGET_NOT_FOUND")
        self.assertEqual(self.ok("init", {})["snapshot_id"], self.ok("meta", {})["snapshot_id"])

    def test_cursor_detects_restored_fork_with_equal_revision(self):
        a, b = self.create(), self.create()
        baseline = self.directory / "baseline-cursor.json"
        self.ok("export", dict(destination=str(baseline)))
        self.apply(self.update(a, body="分岐A"))
        cursor = self.ok("search", dict(limit=1))["page"]["next_cursor"]
        original_meta = self.ok("meta", {})
        branch = Engine(self.directory / "cursor-branch.sqlite")
        self.ok("restore", dict(source=str(baseline), format="json"), branch)
        self.engine = branch
        self.apply(self.update(a, body="分岐B"))
        branch_meta = self.ok("meta", {})
        self.assertEqual(original_meta["database_id"], branch_meta["database_id"])
        self.assertEqual(original_meta["graph_revision"], branch_meta["graph_revision"])
        self.assertNotEqual(original_meta["snapshot_id"], branch_meta["snapshot_id"])
        self.error("search", dict(limit=1, cursor=cursor), "CURSOR_STALE")
