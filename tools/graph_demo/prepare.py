#!/usr/bin/env python3
"""架空の展示データとbaseline/finalを、正規CLI経由で再生成する。"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from latis.model import uid
from scripts.rehearse import run as rehearse
from scripts.reset_demo import reset
from tools.graph_demo.requirements import normative_body, without_demo_note


class DemoCLI:
    def __init__(self, work):
        self.work = Path(work).resolve()
        self.db = self.work / "demo.sqlite"
        self.transcript = []

    def call(self, operation, request):
        result = subprocess.run([sys.executable, "-m", "latis", "--db", str(self.db), operation],
                                input=json.dumps(request, ensure_ascii=False).encode(), cwd=ROOT,
                                capture_output=True, timeout=30)
        response = json.loads(result.stdout)
        self.transcript.append(dict(operation=operation, request=request, response=response, exit_code=result.returncode))
        (self.work / "graph-cli-transcript.json").write_text(json.dumps(self.transcript, ensure_ascii=False, indent=2) + "\n")
        if result.returncode or not response["ok"]:
            raise RuntimeError(f"{operation}: {response}")
        print(f"CLI {operation}: 成功 / rev {response['meta']['graph_revision']}", flush=True)
        return response["data"]

    def change(self, operations, reason):
        consultation = self.call("consult", dict(proposal=dict(title=reason, body=reason,
                                    source_refs=["docs/v0.3.0/demo/", "架空の展示用データの準備指示"]),
                                    change_set=dict(operations=operations)))
        return self.call("apply", dict(**consultation["normalized_request"], basis=consultation["basis"],
                    decision=dict(actor="agent:graph-demo", authority_ref="11/7展示用の架空デモを準備・検証するユーザー指示",
                                  reason=reason, semantic_review="ready"), idempotency_key=uid()))

    def save(self, operations, reason):
        return self.call("save-draft", dict(change_set=dict(operations=operations),
                         record=dict(actor="agent:graph-demo", reason=reason), idempotency_key=uid()))

    def node(self, id_):
        return self.call("detail", dict(node_id=id_))["node"]

    def named(self, title, kind="agreement", lifecycle="accepted"):
        items = self.call("search", dict(query=title, kinds=[kind], lifecycles=[lifecycle], limit=100))["items"]
        exact = [n for n in items if n["title"] == title]
        if len(exact) != 1:
            raise ValueError(f"対象が一意でありません: {title}")
        return self.node(exact[0]["id"])


def node(ref, kind, title, body, lifecycle="accepted"):
    return dict(op="create_node", ref=ref, kind=kind, title=title,
                body=normative_body(body) if kind == "agreement" else without_demo_note(body), lifecycle=lifecycle)


def relation(ref, a, b, kind="scoped_to", confirmation="confirmed"):
    return dict(op="create_relation", ref=ref, **{"from": a, "to": b}, relation_kind=kind,
                confirmation=confirmation, origin="agent")


def enrich(cli, ids):
    operations = [node("normal_scope", "scope", "通常ログ", "通常ログに関する明示的な分類。架空の展示用。"),
                  node("audit_scope", "scope", "監査ログ", "監査ログに関する明示的な分類。架空の展示用。"),
                  node("incident_scope", "scope", "障害対応", "障害対応の分類。効力の継承を意味しない。"),
                  relation("contains_normal", ids["logs_scope"], "$normal_scope", "contains"),
                  relation("contains_audit", ids["logs_scope"], "$audit_scope", "contains"),
                  relation("contains_incident", ids["logs_scope"], "$incident_scope", "contains")]
    for key in ("normal_retention", "audit_retention"):
        agreement = cli.node(ids[key])
        body = normative_body(agreement["body"])
        if body != agreement["body"]:
            operations.append(dict(op="update_node", id=agreement["id"], expected_revision_id=agreement["revision_id"], set=dict(body=body)))
    for name, target in (("normal", "normal_retention"), ("audit", "audit_retention")):
        old = cli.call("relation-detail", dict(relation_id=ids[target + "_scope"]))["relation"]
        operations.append(dict(op="update_relation", id=old["id"], expected_revision_id=old["revision_id"], set=dict(lifecycle="retired")))
        operations.append(relation(name + "_membership", ids[target], "$" + name + "_scope"))
    operations.append(relation("normal_incident_membership", ids["normal_retention"], "$incident_scope"))
    fixtures = [
        ("privacy", "normal_scope", "個人情報のログ出力を避ける", "通常ログへ氏名やメールアドレスを直接出力しない。"),
        ("json", "normal_scope", "ログは1行JSONで記録する", "通常ログの各イベントを1行のJSONとして記録する。"),
        ("level", "normal_scope", "ログレベルを明示する", "通常ログにはイベントのログレベルを記録する。"),
        ("request", "normal_scope", "リクエストIDを記録する", "リクエスト処理の通常ログにはrequest_idを含める。"),
        ("secret", "audit_scope", "認証情報を記録しない", "監査ログへパスワードや認証トークンを出力しない。"),
        ("actor", "audit_scope", "監査の操作主体を記録する", "監査ログには操作主体の識別子を記録する。本人性の証明とは別である。"),
        ("action", "audit_scope", "監査の操作種別を記録する", "監査ログには操作対象と操作種別を記録する。"),
        ("trace", "incident_scope", "trace_idでログを突き合わせる", "障害調査ではtrace_idで関連するイベントを突き合わせる。"),
        ("retry", "incident_scope", "再試行の結果を区別する", "失敗と成功した再試行を区別して調査記録へ残す。"),
        ("handover", "incident_scope", "調査の判断理由を引き継ぐ", "引き継ぎには確認した内容と判断理由を残す。"),
    ]
    for ref, scope, title, body in fixtures:
        operations.extend([node(ref, "agreement", title, body), relation(ref + "_scope", "$" + ref, "$" + scope)])
    operations.extend([
        node("demo_only", "agreement", "展示は架空のデータで行う", "この台帳の設定値は説明用であり、実在サービスの運用規則ではない。"),
        node("audit_reason", "rationale", "監査の記録を独立して扱う理由", "通常ログと監査ログは目的が異なるため、保持期間を別々の合意として扱う。"),
        relation("audit_support", "$audit_reason", ids["audit_retention"], "supports"),
        node("trace_reason", "rationale", "調査対象を結び付ける理由", "関連する処理を取り違えず追跡するため。"),
        relation("trace_support", "$trace_reason", "$trace", "supports"),
        node("candidate", "proposal", "ログ形式を整理する案", "表示形式を整理する候補。まだ採択していない。", "proposed"),
        relation("candidate_support", "$candidate", "$json", "supports", "candidate"),
    ])
    return cli.change(operations, "固定列で階層・複数所属・未分類・候補を確認する架空の展示データを用意する")


def prepare(output):
    output = Path(output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    rehearse(output / "core-rehearsal", body_transform=without_demo_note)
    reset(output / "core-rehearsal", output / "work", state="baseline", format_="sqlite")
    cli = DemoCLI(output / "work")
    cli.call("meta", {})
    summary = json.loads((output / "core-rehearsal/summary.json").read_text())
    enrich(cli, summary["nodes"])
    from tools.graph_demo.scenario import add_utc, revise, verify_retention
    verify_retention(cli, "baseline")
    for operation, extension in (("backup", "sqlite"), ("export", "json")):
        request = dict(destination=str(output / f"baseline.{extension}"))
        if operation == "export": request["format"] = "json"
        cli.call(operation, request)
    shutil.copytree(output / "core-rehearsal/baseline-project", output / "baseline-project")
    for log in (output / "work").glob("check-*.log"):
        shutil.copyfile(log, output / log.name)
    add_utc(cli)
    revise(cli)
    for operation, extension in (("backup", "sqlite"), ("export", "json")):
        request = dict(destination=str(output / f"final.{extension}"))
        if operation == "export": request["format"] = "json"
        cli.call(operation, request)
    for source in [output / "work/retention.py", output / "work/test_retention.py", *(output / "work").glob("check-*.log")]:
        destination = output / source.name
        if destination.exists():
            if destination.read_bytes() != source.read_bytes():
                raise ValueError("既存の証拠ログが変更されています。")
        else:
            shutil.copyfile(source, destination)
    receipt = dict(output=str(output), baseline=str(output / "baseline.sqlite"), final=str(output / "final.sqlite"),
                   note="Pythonによる既定シナリオ。実LLMの受け入れとは別。", nodes=summary["nodes"])
    (output / "graph-demo.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False, indent=2), flush=True)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="まだ存在しない出力ディレクトリ")
    prepare(parser.parse_args().output)
