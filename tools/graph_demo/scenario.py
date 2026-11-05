#!/usr/bin/env python3
"""実CLIから追加・改訂・実検査を行う。LLMによる実演とは区別する。"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.rehearse import sha
from scripts.test_support import run_unittest
from tools.graph_demo.prepare import DemoCLI, node, relation


def add_utc(cli):
    normal = cli.named("通常ログの保持期間")
    scopes = cli.call("detail", dict(node_id=normal["id"]))["scope_ids"]
    normal_scope = next(id_ for id_ in scopes if cli.node(id_)["title"] == "通常ログ")
    return cli.change([
        node("utc", "agreement", "通常ログのタイムスタンプはUTC", "通常ログのタイムスタンプはUTCで統一する。"),
        node("utc_reason", "rationale", "時差による調査の取り違えを防ぐ", "時差による障害調査の取り違えを防ぐため、通常ログの時刻表現を統一する。"),
        relation("utc_scope", "$utc", normal_scope), relation("utc_support", "$utc_reason", "$utc", "supports"),
    ], "時差による障害調査の取り違えを防ぐため、通常ログにUTC記録の合意を追加する")


def revise(cli):
    normal, audit = cli.named("通常ログの保持期間"), cli.named("監査ログの保持期間")
    if "24時間" not in normal["body"]:
        raise ValueError("通常ログ24時間のbaselineから開始してください。")
    cli.change([dict(op="update_node", id=normal["id"], expected_revision_id=normal["revision_id"],
                     set=dict(body=normal["body"].replace("24時間", "48時間")))],
               "障害調査の時間を確保するため、通常ログだけ24時間から48時間へ改訂し、監査ログ90日は維持する")
    for name, old, new in (("retention.py", '"normal": 24', '"normal": 48'),
                           ("test_retention.py", 'retention_hours("normal"), 24', 'retention_hours("normal"), 48')):
        path = cli.work / name
        text = path.read_text()
        if text.count(old) != 1: raise ValueError(f"初期素材と一致しません: {name}")
        path.write_text(text.replace(old, new))
    artifacts = []
    for title, name in (("展示アプリの観測対象", "retention.py"), ("展示テストの観測対象", "test_retention.py")):
        a = cli.named(title, "artifact", "draft")
        cli.save([dict(op="update_node", id=a["id"], expected_revision_id=a["revision_id"], set=dict(content_hash=sha(cli.work / name)))],
                 "実物のコード・テストを再観測する")
        artifacts.append(cli.node(a["id"]))
    verify_retention(cli)
    if cli.node(audit["id"]) != audit: raise ValueError("監査ログの合意が変わりました。")
    print("実テスト3件成功、通常ログは同一IDで48時間、監査ログの合意は不変。", flush=True)


def verify_retention(cli, label="updated"):
    """現物を実検査し、現在の合意版へ新しい結果を結ぶ。過去の証拠は変更しない。"""
    normal, audit = cli.named("通常ログの保持期間"), cli.named("監査ログの保持期間")
    artifacts = [cli.named(title, "artifact", "draft") for title in ("展示アプリの観測対象", "展示テストの観測対象")]
    for artifact, name in zip(artifacts, ("retention.py", "test_retention.py")):
        if artifact["content_hash"] != sha(cli.work / name):
            raise ValueError("記録された観測版と現物が一致しません。")
    log = cli.work / f"check-{label}.log"
    if log.exists():
        raise ValueError("過去の証拠ログは上書きできません。")
    observed = {name: sha(cli.work / name) for name in ("retention.py", "test_retention.py")}
    result = run_unittest(cli.work)
    if observed != {name: sha(cli.work / name) for name in observed}: raise ValueError("実検査中に対象が変わりました。")
    log.write_bytes(result.stdout + result.stderr)
    subjects = [*artifacts, cli.node(normal["id"]), audit]
    evidence = dict(subject_refs=[dict(type="node", id=n["id"], revision_id=n["revision_id"]) for n in subjects],
                    method=f"{cli.work} でキャッシュを分離し {sys.executable} -m unittest -v を実行。終了コード={result.returncode}",
                    outcome="passed" if result.returncode == 0 else "failed", actor="agent:graph-demo",
                    observed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), source_refs=[str(log)])
    saved = cli.save([dict(op="create_node", ref="check", kind="artifact", title=f"展示の実検査 {label}", body="通常・監査ログの境界値と未知種類の拒否を実検査。",
                           lifecycle="draft", locator=f"file:{log.name}", content_hash=sha(log), evidence=evidence)], "今回の実検査を新しい証拠として保存する")
    if result.returncode: raise RuntimeError(log.read_text())
    operations = []
    for ref, agreement in (("normal", normal), ("audit", audit)):
        old_relations = cli.call("relations", dict(node_id=agreement["id"], direction="out", relation_kinds=["verified_by", "implemented_by"], limit=100))["items"]
        for item in old_relations:
            r = item["relation"]
            operations.append(dict(op="update_relation", id=r["id"], expected_revision_id=r["revision_id"], **(
                dict(set=dict(lifecycle="retired")) if r["relation_kind"] == "verified_by" else dict(reconfirm=True))))
        operations.append(relation(ref + "_verified", agreement["id"], saved["created_refs"]["check"]["id"], "verified_by"))
    cli.change(operations, "変更後のコード・テストの新しい実検査を結び、旧証拠を履歴として残す")
    print(f"実テスト3件成功 / 新しい証拠: {saved['created_refs']['check']['id']}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True)
    parser.add_argument("--action", choices=("utc", "revise"), required=True)
    args = parser.parse_args()
    cli = DemoCLI(args.work)
    cli.call("meta", {})
    (add_utc if args.action == "utc" else revise)(cli)
