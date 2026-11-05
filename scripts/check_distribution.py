#!/usr/bin/env python3
"""新しいPython環境の配布物を、ソースツリーの外から実CLIで検査する。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parent.parent


def sha(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(python, output, wheel):
    python, output, wheel = Path(python).absolute(), Path(output).absolute(), Path(wheel).resolve()
    output.mkdir(parents=True, exist_ok=False)
    inspect = '''import importlib.metadata as m, json, latis, platform, sqlite3, sys, sysconfig, unicodedata
print(json.dumps(dict(module=latis.__file__, data=sysconfig.get_path("data"), python=sys.version.split()[0],
    unicode=unicodedata.unidata_version, sqlite=sqlite3.sqlite_version, platform=platform.platform(),
    version=m.version("latis"), dependencies=m.requires("latis") or [])))'''
    result = subprocess.run([str(python), "-I", "-c", inspect], cwd=output, capture_output=True, check=True, text=True)
    environment = json.loads(result.stdout)
    package = Path(environment["module"]).parent
    if package.resolve().is_relative_to(ROOT) or environment["dependencies"]:
        raise RuntimeError("配布物の外からの実行か、実行依存なしの条件を満たしません。")
    if environment["unicode"] != "15.0.0" or not environment["python"].startswith("3.12."):
        raise RuntimeError("この実装にはPython 3.12 / Unicode 15.0.0が必要です。")
    if environment["version"] != tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]:
        raise RuntimeError("導入した配布物とプロジェクトの版が一致しません。")
    bundled = Path(environment["data"]) / "share/latis/docs/v0.3.0"
    files = {}
    for path in sorted([*ROOT.glob("latis/*.py"), *ROOT.glob("docs/v0.3.0/*.md"),
                        *ROOT.glob("docs/v0.3.0/examples/*.json"), ROOT / "docs/v0.3.0/examples/README.md",
                        *ROOT.glob("docs/v0.3.0/examples/demo_project/*.py")]):
        relative = path.relative_to(ROOT)
        installed = package / path.name if relative.parts[0] == "latis" else bundled / path.relative_to(ROOT / "docs/v0.3.0")
        if not installed.is_file() or sha(path) != sha(installed):
            raise RuntimeError(f"配布物の同梱ファイルがソースと一致しません: {relative}")
        files[str(relative)] = sha(installed)
    database = output / "demo.sqlite"
    calls = []
    def call(operation, request, *, db=database):
        result = subprocess.run([str(python.parent / "latis"), "--db", str(db), operation], cwd=output,
                                input=json.dumps(request).encode(), capture_output=True, timeout=30,
                                env=dict(PATH=str(python.parent) + os.pathsep + "/usr/bin:/bin", FORCE_COLOR="1", PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1"))
        response = json.loads(result.stdout)
        calls.append(dict(operation=operation, request=request, response=response, exit_code=result.returncode))
        if result.returncode or not response["ok"]:
            raise RuntimeError(f"配布物のCLIが失敗しました: {response}")
        return response["data"]
    def apply(request, key):
        consulted = call("consult", request)
        return call("apply", dict(**consulted["normalized_request"], basis=consulted["basis"], idempotency_key=key,
            decision=dict(actor="test:distribution", reason="配布物を専用データで検査する", authority_ref="M4の配布検査指示", semantic_review="ready")))
    initialized = call("init", {"project_name":"配布物検査"})
    assert {"search_descendants", "markdown_export"} <= set(initialized["capabilities"])
    seed = json.loads((bundled / "examples/seed_consult.request.json").read_text())
    refs = apply(seed, "distribution-seed")["created_refs"]
    call("meta", {})
    agreement = refs["normal_retention"]["id"]
    scope = refs["logs_scope"]["id"]
    assert call("search", dict(query="ログ"))["items"]
    call("detail", dict(node_id=agreement))
    relation = call("relations", dict(node_id=agreement))["items"][0]["relation"]["id"]
    call("relation-detail", dict(relation_id=relation))
    history = call("history", dict(target_type="node", target_id=agreement))
    draft = dict(change_set=dict(operations=[dict(op="create_node", ref="memo", kind="question", lifecycle="draft", title="配布検査", body="専用の架空データ")]),
                 record=dict(actor="test:distribution", reason="配布物の保存経路"), idempotency_key="distribution-draft")
    assert call("save-draft", draft) == call("save-draft", draft)
    operations = [dict(op="create_node", ref="child", kind="scope", lifecycle="accepted", title="配布検査の子Scope", body="検査専用"),
                  dict(op="create_node", ref="descendant", kind="agreement", lifecycle="accepted", title="配布検査の子合意", body="検査専用")]
    for ref, a, b, kind in (("contains", scope, "$child", "contains"), ("membership", "$descendant", "$child", "scoped_to")):
        operations.append(dict(op="create_relation", ref=ref, **{"from": a, "to": b}, relation_kind=kind, origin="agent", confirmation="confirmed"))
    descendants = apply(dict(proposal=dict(title="子孫検索の配布検査", body="専用の構造を追加する"), change_set=dict(operations=operations)), "distribution-descendant")["created_refs"]
    direct = call("search", dict(scope_ids=[scope]))
    expanded = call("search", dict(scope_ids=[scope], include_descendants=True))
    child_agreement = descendants["descendant"]["id"]
    assert child_agreement not in {item["id"] for item in direct["items"]}
    assert child_agreement in {item["id"] for item in expanded["items"]}
    call("export", dict(format="markdown", destination=str(output / "view"), node_ids=[agreement, child_agreement]))
    assert len(list((output / "view/agreement").glob("*.md"))) == 2
    assert "読み取り専用" in (output / "view/index.md").read_text()
    call("backup", dict(destination=str(output / "backup.sqlite")))
    call("export", dict(format="json", destination=str(output / "snapshot.json")))
    snapshot = json.loads((output / "snapshot.json").read_text())
    for format_, source in (("sqlite", "backup.sqlite"), ("json", "snapshot.json")):
        restored = output / ("restored-" + format_ + ".sqlite")
        assert call("restore", dict(format=format_, source=str(output / source)), db=restored)["snapshot_id"] == snapshot["meta"]["snapshot_id"]
        assert call("history", dict(target_type="node", target_id=agreement), db=restored) == history
        call("export", dict(format="json", destination=str(output / ("restored-" + format_ + ".json"))), db=restored)
        assert json.loads((output / ("restored-" + format_ + ".json")).read_text()) == snapshot
    project = output / "project"
    shutil.copytree(bundled / "examples/demo_project", project, ignore=shutil.ignore_patterns("__pycache__"))
    tests = subprocess.run([str(python), "-I", "-B", "-X", "pycache_prefix=" + str(output / "cache"), "-m", "unittest", "-v"], cwd=project, capture_output=True)
    (output / "material-test.log").write_bytes(tests.stdout + tests.stderr)
    assert tests.returncode == 0 and b"Ran 3 tests" in tests.stderr
    required = {"meta", "search", "detail", "relations", "relation-detail", "history", "save-draft", "consult", "apply"}
    assert required <= {item["operation"] for item in calls}
    report = dict(passed=True, environment=environment, wheel=dict(path=str(wheel), sha256=sha(wheel)),
                  files=files, operations=sorted({item["operation"] for item in calls}), calls=len(calls), material_tests=3,
                  capabilities=["search_descendants", "markdown_export"], sqlite_and_json_restore=True)
    (output / "calls.json").write_text(json.dumps(calls, ensure_ascii=False, indent=2) + "\n")
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, help="配布物だけを導入した新しい環境のPython")
    parser.add_argument("--wheel", required=True, help="検査対象として導入したwheel")
    parser.add_argument("--output", required=True, help="まだ存在しない検査出力先")
    args = parser.parse_args()
    verify(args.python, args.output, args.wheel)
