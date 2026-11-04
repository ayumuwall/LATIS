#!/usr/bin/env python3
"""既定リハーサルのDB・コード・証拠を、新しい場所へ一組で復元する。"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from latis import storage
from latis.model import Error, decode_json


def sha(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reset(source, destination, *, state="baseline", format_="sqlite"):
    source, destination = Path(source).resolve(), Path(destination).absolute()
    if state not in {"baseline", "final"} or format_ not in {"sqlite", "json"}:
        raise ValueError("状態はbaseline/final、形式はsqlite/jsonを指定してください。")
    if destination.resolve().is_relative_to(source):
        raise ValueError("復元元の中へは出力できません。元の記録を保持してください。")
    observed = {}
    def checked(relative):
        path = source / relative
        if not path.resolve().is_relative_to(source) or not path.is_file():
            raise ValueError(f"復元元の必要なファイルがないか、外側を参照しています: {relative}")
        observed[str(relative)] = sha(path)
        return path
    snapshot_path = checked(state + ".json")
    snapshot = decode_json(snapshot_path.read_bytes())
    storage.validate_snapshot(snapshot)
    database_source = checked(state + "." + format_)
    project = Path("baseline-project") if state == "baseline" else Path(".")
    files = {name: checked(project / name) for name in ("retention.py", "test_retention.py")}
    for name, path in files.items():
        artifacts = [item for item in snapshot["nodes"] if item["kind"] == "artifact" and item["locator"] == "file:" + name]
        if len(artifacts) != 1 or artifacts[0]["content_hash"] != sha(path):
            raise ValueError(f"DBの観測版とコード・テストが一致しません: {name}")
    for artifact in snapshot["nodes"]:
        if artifact["kind"] != "artifact" or artifact["evidence"] is None:
            continue
        locator = artifact["locator"] or ""
        name = locator.removeprefix("file:")
        if not locator.startswith("file:") or not name or Path(name).name != name:
            raise ValueError("証拠ログの所在は復元元直下のファイル名である必要があります。")
        path = checked(name)
        if artifact["content_hash"] != sha(path):
            raise ValueError(f"DBの固定証拠とログの内容が一致しません: {name}")
        files[name] = path

    def call(db, operation, request):
        result = subprocess.run([sys.executable, "-m", "latis", "--db", str(db), operation], cwd=ROOT,
                                input=json.dumps(request).encode(), capture_output=True, timeout=30)
        response = json.loads(result.stdout)
        if result.returncode or not response["ok"]:
            raise RuntimeError(f"復元検査のCLIが失敗しました: {response}")
        return response["data"]

    def writer(staging):
        db = staging / "demo.sqlite"
        restored = call(db, "restore", dict(format=format_, source=str(database_source)))
        for name, path in files.items():
            shutil.copyfile(path, staging / name)
        call(db, "export", dict(format="json", destination=str(staging / "snapshot.json")))
        if json.loads((staging / "snapshot.json").read_text()) != snapshot:
            raise ValueError("選択したDBとJSONの全履歴・来歴・再試行記録が一致しません。")
        if any(sha(source / relative) != digest for relative, digest in observed.items()):
            raise ValueError("復元の準備中に復元元が変更されました。公開しません。")
        if any(sha(staging / name) != sha(path) for name, path in files.items()):
            raise ValueError("コード・証拠ログの複写が一致しません。公開しません。")
        receipt = dict(source=str(source), destination=str(destination), state=state, format=format_,
                       database=str(destination / "demo.sqlite"), meta={key: restored[key] for key in snapshot["meta"]},
                       source_hashes=observed, files={name: sha(staging / name) for name in files},
                       code_executed=False, new_test_evidence_registered=False)
        (staging / "reset.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    storage.publish_directory(str(destination), writer)
    return json.loads((destination / "reset.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="scripts/rehearse.pyが作った出力先")
    parser.add_argument("--destination", required=True, help="まだ存在しない専用ディレクトリ")
    parser.add_argument("--state", choices=("baseline", "final"), default="baseline")
    parser.add_argument("--format", choices=("sqlite", "json"), default="sqlite")
    args = parser.parse_args()
    try:
        print(json.dumps(reset(args.source, args.destination, state=args.state, format_=args.format), ensure_ascii=False, indent=2))
    except (Error, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"復元の準備に失敗しました: {error}", file=sys.stderr)
        raise SystemExit(1)
