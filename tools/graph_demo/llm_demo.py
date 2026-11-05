#!/usr/bin/env python3
"""既存の必須隔離を使い、展示データの追加・改訂・独立引き継ぎを確認する。"""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import llm_acceptance as h
from scripts.reset_demo import reset
from tools.graph_demo.projection import read_snapshot, project
from tools.graph_demo.labels import DisplayLog, updating_index


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def reviewed(directory, stage):
    review = h.load_json(directory / (stage + "-semantic-review.json"))
    require(review.get("passed") is True and review.get("notes"), "実記録の意味レビューが未完了です。")
    return review


def display_prompt(directory):
    """送信前に確認できる、オブジェクトID付きデモ利用の指示。"""
    directory = Path(directory).resolve()
    index = directory / "workspace/latis-display-numbers.json"
    prompt = h.prompt_for(directory) + "\n\n補足: Bashで実行できるのは上記の固定CLI、observe、checkだけです。wc、cat、ls、find、シェル変数への代入、パイプ等も使ってはなりません。文書の確認にはRead・Glob・Grepを使ってください。合意や範囲の本文に展示用の注記を付けないでください。"
    prompt += f"\n最初のmetaも例外ではありません。Writeで{directory}/workspace/request-meta.jsonへ {{}} を保存してから、Bashで `{directory}/tool/latis --db {directory}/workspace/demo.sqlite meta < {directory}/workspace/request-meta.json` と実行してください。echoやprintf、パイプは禁止です。要求JSONの新規作成は許可されています。"
    prompt += f"\n\nオブジェクトID対応表: {index}\nユーザーへの提示にはA-1等のオブジェクトIDとタイトルを使ってください。操作には対応する内部idとrevision_idを使います。対応表は同じDBから実行中も更新されます。metaのdatabase_id・graph_revision・snapshot_idと対応表のmetaが一致することを確認し、書込み後の報告前にも表を読み直してください。不一致なら表を再読し、未確認の番号を推測してはなりません。対応表を編集してはいけません。"
    prompt += "\nオブジェクトIDで十分な場面ではオブジェクトIDを使う原則を全動作に適用してください。途中の説明・ツールのdescriptionにもオブジェクトIDと名称を使い、人がログから対象と動作を追えるようにしてください。"
    return prompt


def prepare(output, source):
    output.mkdir(parents=True, exist_ok=False)
    live = h.prepare_case(output / "live", "explicit")
    # 試験基盤が最初に作った組を保持し、正規CLIで準備済みの展示baselineを新規復元する。
    (live / "workspace").rename(live / "bootstrap-workspace")
    reset(source, live / "workspace", state="baseline", format_="json")
    before = read_snapshot(live / "workspace/demo.sqlite")
    ids = h.load_json(Path(source) / "graph-demo.json")["nodes"]
    ids["baseline_evidence"] = next(n["id"] for n in before["nodes"] if n.get("evidence") and n["locator"] == "file:check-baseline.log")
    facts = dict(case="explicit", ids=ids, before=before,
        task="このデモプロジェクトで、通常ログのタイムスタンプをUTCで統一する仕様を追加してください。理由は、時差による障害調査の取り違えを防ぐためです。既存の決定と整合するか確認し、必要な内容と理由を記録してください。今回はコードとテストは変更しないでください。合意本文の義務は「しなければならない」、禁止は「してはならない」で表してください。",
        files_before={p.name: h.sha(p) for p in (live / "workspace").glob("*.py")})
    h.write_json(live / "fixture.json", facts)
    h.write_json(output / "sources.json", {str(p.relative_to(ROOT)): h.sha(p) for p in sorted([
        *ROOT.glob("latis/*.py"), ROOT / "tools/graph_demo/labels.py", ROOT / "tools/graph_demo/llm_demo.py", ROOT / "scripts/llm_acceptance.py", ROOT / "scripts/claude_sandbox.py",
        ROOT / "scripts/test_support.py", ROOT / "docs/v0.3.0/LATIS_LLM_Guide.md", ROOT / "docs/v0.3.0/LATIS_API.md"] )})
    print("展示baselineを復元しました。実ClaudeのUTC追加から開始できます。", flush=True)


def launch(output, stage, browser_python, capture=False):
    output = Path(output).resolve()
    directory = output / ("handover" if stage == "handover" else "live")
    for relative, digest in h.load_json(output / "sources.json").items():
        require(h.sha(ROOT / relative) == digest, "検査対象ソースが変わりました: " + relative)
    require(not (directory / (stage + "-result.json")).exists(), "同じ実行記録は上書きしません。")
    if stage == "change":
        reviewed(directory, "utc")
        facts = h.load_json(directory / "fixture.json")
        facts.update(before=read_snapshot(directory / "workspace/demo.sqlite"),
                     task="障害調査の時間を確保するため、通常ログだけ24時間から48時間へ変更してください。監査ログの90日という決定は維持してください。過去の保持期間の理由を確認し、合意、コード、テストを更新してください。現物を観測して実テストの結果を新しい証拠へ記録し、実装・検証の対応も整えてください。義務は「しなければならない」、禁止は「してはならない」で表してください。")
        h.write_json(directory / "fixture.json", facts)
    before = read_snapshot(directory / "workspace/demo.sqlite")
    frames = directory / (stage + "-browser")
    stop_file, ready_file = directory / (stage + "-stop"), directory / (stage + "-ready.json")
    watcher = None
    if capture:
        watcher = subprocess.Popen([browser_python, str(ROOT / "tools/graph_demo/watch_browser.py"),
            "--db", str(directory / "workspace/demo.sqlite"), "--output", str(frames),
            "--stop-file", str(stop_file), "--ready-file", str(ready_file)])
    try:
        started = time.monotonic()
        while watcher is not None and not ready_file.exists():
            require(watcher.poll() is None, "ブラウザー収録を起動できません。")
            require(time.monotonic() - started < 40, "ブラウザーの準備が完了しません。")
            time.sleep(.1)
        prompt = display_prompt(directory)
        index = directory / "workspace/latis-display-numbers.json"
        print(f"[表示用ログ・再実行不可] オブジェクトIDと名称で表示します。実コマンド・応答の原記録: {directory / (stage + '-events.json')} / {directory / 'calls.jsonl'}", flush=True)
        with updating_index(directory / "workspace/demo.sqlite",index):
            h.run_claude(directory, turn=stage, prompt=prompt,
                         event_renderer=DisplayLog(directory / "workspace/demo.sqlite",h.render_event))
    finally:
        if watcher is not None:
            stop_file.touch()
            try:
                code = watcher.wait(timeout=30)
            except subprocess.TimeoutExpired:
                watcher.terminate()
                watcher.wait(timeout=10)
                raise RuntimeError("ブラウザー収録が終了しませんでした。")
            require(code == 0, "ブラウザー収録が不合格です。")
    after = read_snapshot(directory / "workspace/demo.sqlite")
    h.write_json(directory / (stage + "-snapshot.json"), after)
    if stage == "utc":
        old = {n["id"]: n for n in before["nodes"]}
        created = [n for n in after["nodes"] if n["id"] not in old]
        utc = [n for n in created if n["kind"] == "agreement" and n["lifecycle"] == "accepted" and "UTC" in n["body"]]
        calls = h.read_calls(directory)
        checks = dict(actual_cli=bool(calls), meta=any(c["operation"] == "meta" for c in calls),
            utc_agreement=len(utc) == 1, old_nodes_preserved=all(n == old[n["id"]] for n in after["nodes"] if n["id"] in old),
            files_preserved=h.load_json(directory / "fixture.json")["files_before"] == {p.name:h.sha(p) for p in (directory / "workspace").glob("*.py")},
            reason_recorded=bool(utc) and any(r["relation_kind"] == "supports" and r["to_node_id"] == utc[0]["id"] and r["confirmation"] == "confirmed" and r["lifecycle"] == "active" for r in after["relations"]))
        check = dict(mechanical_pass=all(checks.values()), checks=checks)
    else:
        check = h.evaluate(directory)
    view = project(directory / "workspace/demo.sqlite")
    h.write_json(directory / (stage + "-projection.json"), view)
    h.write_json(directory / (stage + "-check.json"), check)
    require(check["mechanical_pass"], "機械判定が不合格です。後続へ進みません。")
    print("実応答とDB・ブラウザーの記録をレビューし、" + stage + "-semantic-review.jsonへ判断を残してください。", flush=True)


def handover(output, browser_python, capture=False):
    live = output / "live"
    reviewed(live, "change")
    directory = h.prepare_case(output / "handover", "handover", handover_source=live)
    before = read_snapshot(directory / "workspace/demo.sqlite")
    for n in before["nodes"]:
        if n.get("evidence") and n.get("locator", "").startswith("file:"):
            name = n["locator"][5:]
            if Path(name).name == name and (live / "workspace" / name).is_file():
                shutil.copyfile(live / "workspace" / name, directory / "workspace" / name)
    facts = h.load_json(directory / "fixture.json")
    facts["task"] += "通常ログのタイムスタンプについても、現在の決定と理由を調べてください。"
    h.write_json(directory / "fixture.json", facts)
    launch(output, "handover", browser_python, capture)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--stage", required=True, choices=("prepare", "utc", "change", "handover"))
    parser.add_argument("--source")
    parser.add_argument("--browser-python", default="/tmp/latis-playwright-env/bin/python")
    parser.add_argument("--capture", action="store_true", help="任意の実画面収録。既定では起動しない")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if args.stage == "prepare":
        require(args.source, "展示baselineの復元元を指定してください。")
        prepare(output, Path(args.source).resolve())
    elif args.stage == "handover":
        handover(output, args.browser_python, args.capture)
    else:
        launch(output, args.stage, args.browser_python, args.capture)
