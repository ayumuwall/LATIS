#!/usr/bin/env python3
"""展示の既定シナリオを実CLI・実テストで再現する。対話LLMの試験とは区別する。"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.test_support import run_unittest


def sha(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def run(output, *, body_transform=None):
    output = Path(output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    source = ROOT / "docs/v0.3.0/examples"
    for name in ("retention.py", "test_retention.py"):
        shutil.copyfile(source / "demo_project" / name, output / name)
    shutil.copytree(source / "demo_project", output / "baseline-project", ignore=shutil.ignore_patterns("__pycache__"))
    database = output / "demo.sqlite"
    transcript = []
    counter = 0

    def call(operation, request, *, db=database, expected_error=None):
        result = subprocess.run([sys.executable, "-m", "latis", "--db", str(db), operation], input=json.dumps(request, ensure_ascii=False).encode(),
                                cwd=ROOT, capture_output=True)
        response = json.loads(result.stdout)
        transcript.append(dict(operation=operation, request=request, response=response, exit_code=result.returncode))
        if expected_error:
            assert result.returncode == 1 and response["errors"][0]["code"] == expected_error, response
            return response
        assert result.returncode == 0 and response["ok"] and not result.stderr, (response, result.stderr.decode())
        return response["data"]

    def apply(request, reason):
        nonlocal counter
        counter += 1
        if body_transform is not None:
            for operation in request["change_set"]["operations"]:
                values = operation if operation["op"] == "create_node" else operation.get("set", {})
                if "body" in values:
                    values["body"] = body_transform(values["body"])
        consultation = call("consult", request)
        return call("apply", dict(**consultation["normalized_request"], basis=consultation["basis"],
                                  decision=dict(actor="agent:rehearsal", principal_refs=["human:demo-owner"],
                                                authority_ref="LATIS_Demo_Guideに従う架空の展示シナリオの準備・検証指示", reason=reason,
                                                semantic_review="ready", resolutions=[], execution_context=dict(session_ref="scripted-rehearsal")),
                                  idempotency_key=f"rehearsal-apply-{counter}"))

    def change(operations, reason):
        return apply(dict(proposal=dict(title=reason, body=reason, source_refs=["docs/v0.3.0/LATIS_Demo_Guide.md"]),
                          change_set=dict(operations=operations)), reason)

    def current(id_, *, db=database):
        return call("detail", dict(node_id=id_), db=db)["node"]

    def save(operations, reason):
        nonlocal counter
        counter += 1
        return call("save-draft", dict(change_set=dict(operations=operations), record=dict(actor="agent:rehearsal", reason=reason),
                                       idempotency_key=f"rehearsal-save-{counter}"))

    def rel(ref, a, b):
        return dict(op="create_relation", ref=ref, **{"from": a, "to": b}, relation_kind="verified_by", confirmation="confirmed", origin="agent")

    def verify(label):
        log = output / f"check-{label}.log"
        before = {name: sha(output / name) for name in ("retention.py", "test_retention.py")}
        result = run_unittest(output)
        log.write_bytes(result.stdout + result.stderr)
        assert before == {name: sha(output / name) for name in before}, "検査中に対象ファイルが変更されました。"
        subject_nodes = [current(ids[name]) for name in ("app_artifact", "test_artifact", "normal_retention", "audit_retention")]
        evidence = dict(subject_refs=[dict(type="node", id=n["id"], revision_id=n["revision_id"]) for n in subject_nodes],
                        method=f"作業場所 {output} でバイトコードキャッシュを分離し、{sys.executable} -m unittest -v を実行。終了コード={result.returncode}",
                        outcome="passed" if result.returncode == 0 else "failed", observed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                        actor="agent:rehearsal", source_refs=[str(log)])
        response = save([dict(op="create_node", ref="result", kind="artifact", title=f"実検査結果 {label}", body="実際のアプリ・テストの版に対する結果。",
                              lifecycle="draft", locator=f"file:{log.name}", content_hash=sha(log), evidence=evidence)], "実行結果を一回の観測として保存")
        assert result.returncode == 0, log.read_text()
        print(f"実テスト {label}: passed（3ケース）", flush=True)
        return response["created_refs"]["result"]["id"]

    call("init", {"project_name":"ログ管理サービス"})
    seed = json.loads((source / "seed_consult.request.json").read_text())
    for op in seed["change_set"]["operations"]:
        if op.get("content_hash"):
            assert op["content_hash"] == sha(output / op["locator"].removeprefix("file:")), "初期素材のハッシュ不一致"
    seeded = apply(seed, "架空の初期条件を正規の照合・採択経路で登録")
    ids = {name: ref["id"] for name, ref in seeded["created_refs"].items()}
    initial_evidence = verify("initial")
    initial_links = change([rel("normal_verified", ids["normal_retention"], initial_evidence), rel("audit_verified", ids["audit_retention"], initial_evidence)], "初期アプリ・テストの実結果を両合意へ結ぶ")
    call("backup", dict(destination=str(output / "baseline.sqlite")))
    call("export", dict(format="json", destination=str(output / "baseline.json")))
    normal = current(ids["normal_retention"])
    audit_before = current(ids["audit_retention"])
    call("search", dict(query="ログ 保持", kinds=["agreement"], lifecycles=["accepted"]))
    change([dict(op="update_node", id=normal["id"], expected_revision_id=normal["revision_id"],
                 set=dict(body="通常ログは48時間保持する。監査ログはこの合意の対象に含めない。これは展示用の架空設定である。"))],
           "障害調査の時間を確保するため、通常ログだけ48時間へ変更し監査ログ90日は維持する")
    for name, old, new in (("retention.py", '"normal": 24', '"normal": 48'),
                           ("test_retention.py", 'retention_hours("normal"), 24', 'retention_hours("normal"), 48')):
        path = output / name
        text = path.read_text()
        assert text.count(old) == 1
        path.write_text(text.replace(old, new))
    observe = []
    for key, name in (("app_artifact", "retention.py"), ("test_artifact", "test_retention.py")):
        artifact = current(ids[key])
        observe.append(dict(op="update_node", id=artifact["id"], expected_revision_id=artifact["revision_id"], set=dict(content_hash=sha(output / name))))
    save(observe, "変更したコード・テストの現物を再観測")
    old_link = call("relation-detail", dict(relation_id=initial_links["created_refs"]["normal_verified"]["id"]))
    assert old_link["basis_status"] == "changed"
    call("consult", dict(proposal=dict(title="古い証拠の再利用拒否を確認", body="検査対象版を付け替えない。"),
                         change_set=dict(operations=[dict(op="update_relation", id=old_link["relation"]["id"], expected_revision_id=old_link["relation"]["revision_id"], reconfirm=True, basis_targets=[])])),
         expected_error="EVIDENCE_SUBJECT_CHANGED")
    updated_evidence = verify("updated")
    operations = [rel("normal_verified", ids["normal_retention"], updated_evidence), rel("audit_verified", ids["audit_retention"], updated_evidence)]
    for item in initial_links["created_refs"].values():
        old = call("relation-detail", dict(relation_id=item["id"]))["relation"]
        operations.append(dict(op="update_relation", id=old["id"], expected_revision_id=old["revision_id"], set=dict(lifecycle="retired")))
    for name in ("normal_implementation", "audit_implementation"):
        old = call("relation-detail", dict(relation_id=ids[name]))["relation"]
        operations.append(dict(op="update_relation", id=old["id"], expected_revision_id=old["revision_id"], reconfirm=True))
    final_links = change(operations, "新しい実検査の結果へ結び、旧証拠を履歴として保持")
    assert current(ids["audit_retention"]) == audit_before
    for item in final_links["created_refs"].values():
        assert call("relation-detail", dict(relation_id=item["id"]))["basis_status"] == "current"
    call("export", dict(format="json", destination=str(output / "final.json")))
    call("backup", dict(destination=str(output / "final.sqlite")))
    restored_db = output / "restored.sqlite"
    call("restore", dict(format="json", source=str(output / "final.json")), db=restored_db)
    # 各呼び出しは新しいCLIプロセス。会話記憶を使わず、DBから読み直す。
    fresh_search = call("search", dict(query="ログ 保持"), db=restored_db)
    fresh_history = call("history", dict(target_type="node", target_id=ids["normal_retention"]), db=restored_db)
    assert any("48時間" in item["excerpt"] for item in fresh_search["items"])
    assert len(fresh_history["revisions"]) == 2
    assert any("障害調査" in prov["reason"] for prov in fresh_history["provenance"])
    for key, name in (("app_artifact", "retention.py"), ("test_artifact", "test_retention.py")):
        assert current(ids[key], db=restored_db)["content_hash"] == sha(output / name)
    summary = dict(output=str(output), database=str(database), restored_database=str(restored_db), nodes=ids,
                   normal_retention_hours=48, audit_retention_hours=2160, initial_evidence_id=initial_evidence, updated_evidence_id=updated_evidence,
                   real_tests_passed=True, old_evidence_reconfirmation_rejected=True, backup_restore_verified=True, fresh_cli_reuse_verified=True,
                   independent_llm_session_verified=False, note="既定シナリオの自動再現。対話LLMの自発的探索・打診と、別LLMセッションは手動受け入れ対象。")
    (output / "responses.json").write_text(json.dumps(transcript, ensure_ascii=False, indent=2) + "\n")
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="展示の既定シナリオを実CLIで再現（出力先は新しいディレクトリ）")
    parser.add_argument("--output", required=True)
    run(parser.parse_args().output)
