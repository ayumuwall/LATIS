#!/usr/bin/env python3
"""意味レビュー済みの実Claude収録を、展示用の固定ファイルへまとめる。"""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil


def bundle(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    clips = []
    for stage, title in (("utc", "UTC合意を追加"), ("change", "通常ログを24時間から48時間へ改訂")):
        load = lambda name: json.loads((source / name).read_text())
        review = load(stage + "-semantic-review.json")
        check = load(stage + "-check.json")
        result = load(stage + "-result.json")
        launch = load(stage + "-launch.json")
        report = load(stage + "-browser/report.json")
        snapshot = load(stage + "-snapshot.json")
        if not (review.get("passed") is True and check.get("mechanical_pass") is True
                and result.get("exit_code") == 0 and not result.get("timed_out") and report.get("passed") is True):
            raise ValueError(stage + ": 受け入れ済みの実収録ではありません。")
        frames = report["frames"]
        if len(frames) < 2:
            raise ValueError("保存前後の画面記録がありません。")
        video = source / (stage + "-browser/demo.webm")
        clips.append(dict(title=title, file=stage + ".webm", sha256=sha256(video.read_bytes()).hexdigest(),
            database_id=snapshot["meta"]["database_id"],
            recorded_at=datetime.fromtimestamp(frames[0]["observed_ns"] / 1e9, timezone.utc).isoformat(),
            from_revision=int(frames[0]["revision"].split()[1]), to_revision=snapshot["meta"]["graph_revision"],
            snapshot_id=snapshot["meta"]["snapshot_id"], model=" / ".join(result["models"]), effort=launch["effort"],
            note="架空の専用DBに対する実保存と表示。収録時の画面を再生しています。現在のLIVE DBは変更しません。"))
    output.mkdir(parents=True, exist_ok=False)
    for stage in ("utc", "change"):
        shutil.copyfile(source / (stage + "-browser/demo.webm"), output / (stage + ".webm"))
        for suffix in ("-semantic-review.json", "-check.json", "-snapshot.json"):
            shutil.copyfile(source / (stage + suffix), output / (stage + suffix))
        shutil.copyfile(source / (stage + "-browser/report.json"), output / (stage + "-browser.json"))
    manifest = dict(mode="RECORDED", clips=clips)
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(output / "manifest.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="意味レビュー済みのliveディレクトリ")
    parser.add_argument("--output", required=True, help="未存在の保存先")
    args = parser.parse_args()
    bundle(args.source, args.output)
