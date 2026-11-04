"""実DBを使う契約テストの共通準備。"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from latis import Engine
from latis.model import uid

ROOT = Path(__file__).resolve().parent.parent


def node(ref="n", kind="agreement", lifecycle="accepted", title="ログの保持期間", body="通常ログは24時間保持する。", **extra):
    return dict(op="create_node", ref=ref, kind=kind, lifecycle=lifecycle, title=title, body=body, **extra)


def relation(ref, a, b, kind="depends_on", confirmation="confirmed", **extra):
    return dict(op="create_relation", ref=ref, **{"from": a, "to": b}, relation_kind=kind, confirmation=confirmation, origin="agent", **extra)


class ContractCase(unittest.TestCase):
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

    def cli(self, operation, request, *, db=None, cwd=None, env=None, raw=None):
        return subprocess.run(
            [str(ROOT / "bin/latis"), "--db", str(db or self.engine.path), operation],
            input=raw if raw is not None else json.dumps(request, ensure_ascii=False).encode(),
            capture_output=True, cwd=cwd or ROOT, env=env,
        )

    def snapshot(self):
        destination = self.directory / (uid() + ".json")
        self.ok("export", dict(destination=str(destination)))
        return json.loads(destination.read_text())
