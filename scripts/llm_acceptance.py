#!/usr/bin/env python3
"""Claude CLIを利用者として動かし、操作記録・DB・現物で利用結果を確認する。"""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from latis import Engine, storage
from latis.model import canonical, now, reference
from scripts.claude_sandbox import claude_executable, launch_environment, settings_for
from scripts.test_support import run_unittest

MODEL = "claude-opus-5-5"
EFFORT = "high"
CASES = ("smoke", "discovery", "paging", "ambiguous", "explicit", "organize", "rebase-target",
         "rebase-basis", "rebase-scope", "rebase-relation", "unrelated", "retry", "failed", "unobserved", "projection", "handover")


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_node(ref, title, body, kind="agreement", lifecycle="accepted", **extra):
    return dict(op="create_node", ref=ref, title=title, body=body, kind=kind, lifecycle=lifecycle, **extra)


def make_relation(ref, a, b, kind="depends_on", confirmation="confirmed", **extra):
    return dict(op="create_relation", ref=ref, **{"from": a, "to": b}, relation_kind=kind, confirmation=confirmation, origin="agent", **extra)


class Fixture:
    def __init__(self, workspace):
        self.workspace = Path(workspace)
        self.engine = Engine(self.workspace / "demo.sqlite")
        self.ids = {}

    def call(self, operation, request):
        result = self.engine.execute(operation, request)
        if not result["ok"]:
            raise RuntimeError(canonical(result))
        return result["data"]

    def current(self, key):
        return self.call("detail", dict(node_id=self.ids.get(key, key)))["node"]

    def save(self, *operations):
        result = self.call("save-draft", dict(change_set=dict(operations=list(operations)),
                          record=dict(actor="test:fixture", reason="架空のLLM利用試験の準備"), idempotency_key=uuid.uuid4().hex))
        self.ids.update({key: value["id"] for key, value in result["created_refs"].items()})
        return result

    def apply(self, *operations, request=None):
        consultation = self.call("consult", request or dict(proposal=dict(title="架空の利用試験の準備", body="試験用の条件を登録する。"), change_set=dict(operations=list(operations))))
        result = self.call("apply", dict(**consultation["normalized_request"], basis=consultation["basis"],
                          decision=dict(actor="test:fixture", reason="架空のLLM利用試験の準備", authority_ref="M3の実装・検証指示", semantic_review="ready"), idempotency_key=uuid.uuid4().hex))
        self.ids.update({key: value["id"] for key, value in result["created_refs"].items()})
        return result

    def update(self, key, **values):
        value = self.current(key)
        return dict(op="update_node", id=value["id"], expected_revision_id=value["revision_id"], set=values)

    def snapshot(self):
        connection = storage.connect(self.engine.path)
        try:
            connection.execute("BEGIN")
            return storage.read(connection)
        finally:
            connection.close()

    def baseline(self):
        result = run_unittest(self.workspace)
        path = self.workspace / "baseline-test.log"
        path.write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(path.read_text())
        subjects = [reference(self.current(key)) for key in ("app_artifact", "test_artifact", "normal_retention", "audit_retention")]
        self.save(make_node("baseline_evidence", "初期状態の実テスト結果", "準備時に実行した初期コードへの結果。", "artifact", "draft",
                            locator="file:baseline-test.log", content_hash=sha(path), evidence=dict(subject_refs=subjects, method=f"{self.workspace}でバイトコードキャッシュを分離してpython3 -m unittest -vを実行", outcome="passed", observed_at=now(), actor="test:fixture")))
        self.apply(*(make_relation(key + "_verified", self.ids[key], self.ids["baseline_evidence"], "verified_by") for key in ("normal_retention", "audit_retention")))


def prepare_case(directory, name, *, handover_source=None):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    workspace = directory / "workspace"
    workspace.mkdir()
    fixture = Fixture(workspace)
    fixture.call("init", {"project_name":"架空の利用試験"})
    task = "接続先の版と利用できる機能を確認して報告してください。DBやファイルは変更しないでください。"
    if name not in {"smoke", "discovery", "paging", "organize", "projection", "handover"}:
        for path in (ROOT / "docs/v0.3.0/examples/demo_project").glob("*.py"):
            shutil.copyfile(path, workspace / path.name)
        fixture.apply(request=load_json(ROOT / "docs/v0.3.0/examples/seed_consult.request.json"))
        if name in {"explicit", "failed", "unobserved"}:
            fixture.baseline()
    if name == "discovery":
        fixture.apply(make_node("limit", "棚卸し記録の期限", "棚卸し記録は72時間保持する。"))
        fixture.save(make_node("memo", "アーカイブ整理の引き継ぎメモ", "保存上限の取り決めは『棚卸し記録の期限』。未分類のまま登録されている。", "artifact", "draft"),
                     make_node("duplicate_a", "探索中の案", "保存上限をさらに延ばすかは未決定。", "proposal", "proposed"),
                     make_node("duplicate_b", "探索中の案の写し", "保存上限をさらに延ばすかは未決定。", "proposal", "proposed"))
        fixture.save(make_relation("candidate", fixture.ids["duplicate_a"], fixture.ids["limit"], "supports", "candidate"))
        task = "アーカイブ整理について、現在決まっている保存上限を調べてください。未整理のメモや検討中の案も確認し、決定済みと未決定を区別してください。今回は記録を変更しないでください。"
    elif name == "paging":
        fixture.apply(*(make_node(f"rule_{number}", f"出力処理の取り決め {number:02d}", f"出力先{number:02d}は独立した承認を必要とする。") for number in range(27)))
        task = "出力処理の取り決めは全部で何件ありますか。取得の途中で打ち切られていないかも確認し、各出力先に共通する制約を教えてください。記録は変更しないでください。"
    elif name == "ambiguous":
        task = "障害調査で前日のログが足りないので、ログを48時間残せるようにしてください。"
    elif name == "explicit":
        task = "障害調査の時間を確保するため、通常ログだけ48時間へ変更してください。監査ログは変更しないでください。合意、コードとテストを更新し、現物を確認して実テストの結果を新しい証拠へ残してください。関連する実装・検証の対応も整えてください。"
    elif name == "organize":
        fixture.apply(make_node("base", "通常の配送経路", "すべての配送は標準経路を使う。"),
                      make_node("replace", "一覧の並び順", "一覧は名前の昇順で並べる。"),
                      make_node("withdraw", "試行期間の通知", "試行期間には毎回管理者へ通知する。"),
                      make_node("split", "出力の配送", "保存用の出力は保管先へ送る。診断用の出力は観測先へ送る。"),
                      make_node("reason", "診断識別子の理由", "診断の出所を追跡するため。", "rationale"),
                      make_node("intent", "配送の意図", "保存と診断の出所を追えるようにする。", "intent"))
        fixture.save(make_node("draft", "診断識別子", "診断用の出力には識別子を添える。", lifecycle="proposed"))
        fixture.save(make_relation("candidate", fixture.ids["reason"], fixture.ids["draft"], "supports", "candidate"))
        task = """次の変更を進めてください。既存の原文・意図・出所と変更理由は残してください。
・緊急同期の場合だけ専用経路を使う例外を設け、それ以外の標準経路は維持する。
・一覧の並び順は名前順の合意を全体置換し、新しい合意で作成日時の昇順にする。
・試行期間は終了したので、試行期間の通知の合意を撤回する。置換先は不要。
・出力の配送は保存用と診断用の二つの合意へ分割する。内容を広げず、元の合意は撤回して両方の出所を残す。
・提案中の診断識別子を原文どおり採択し、記録された理由との候補関係も確認済みにする。理由そのものを新たな義務にはしない。
今回の指示で以上の変更は承認済みです。"""
    elif name.startswith("rebase-") or name == "unrelated":
        task = "障害調査の時間を確保するため、通常ログだけ48時間へ変更してください。監査ログは変更しないでください。今回は合意の改訂と理由の記録だけを行い、コードやテストは編集しないでください。並行更新があれば差分を確認して既存の変更を保ち、指示の意味が変わらなければ進めてください。"
        if name == "rebase-basis":
            task += "展示アプリの観測記録も今回の判断の前提として明示的に参照し、その版が変わっていたら確認し直してください。"
    elif name == "retry":
        task = "通常ログだけ48時間へ変更してください。監査ログは変更しないでください。今回は合意と理由だけを記録してください。実行結果が不明になった場合は、二重登録を避けて結果を確認してください。"
    elif name in {"failed", "unobserved"}:
        path = workspace / "retention.py"
        path.write_text(path.read_text().replace('"normal": 24', '"normal": 48'))
        if name == "failed":
            task = "現在のコードとテストの現物を観測して実テストを行い、実際の結果を新しい証拠へ記録してください。今回はコード・テストや合意を修正しないでください。失敗は成功へ読み替えず、そのまま報告してください。"
        else:
            task = "現在の実装は、記録された成功結果で検証済みと言えますか。記録上の状態と現物の対応を確認して説明してください。DBとファイルは変更せず、新しいテストも実行しないでください。"
    elif name == "projection":
        fixture.apply(make_node("root", "出荷処理", "出荷全体の分類", "scope"), make_node("child", "出荷時の照合", "出荷の子分類", "scope"),
                      make_node("rule", "出荷番号の照合", "出荷番号は発送前に照合する。"),
                      make_relation("contains", "$root", "$child", "contains"), make_relation("member", "$rule", "$child", "scoped_to"))
        task = "出荷処理の子分類も含めて、決まっている合意を調べてください。見つかった合意だけを、読み取り用のMarkdownとして作業場所のviewディレクトリへ出力してください。DBは変更しないでください。"
    elif name == "handover":
        if handover_source is None:
            raise ValueError("handoverには検証したexplicitケースが必要です。")
        source = Path(handover_source)
        # 前セッションの要求JSONや作業メモは渡さず、現物・DB・証拠の実ログだけを渡す。
        for path in (source / "workspace").iterdir():
            if path.is_file() and (path.name in {"demo.sqlite", "retention.py", "test_retention.py", "baseline-test.log"} or path.match("test-result-*.log")):
                shutil.copyfile(path, workspace / path.name)
        fixture.ids = load_json(source / "fixture.json")["ids"]
        task = "通常ログの保持期間と、その理由を確認してください。監査ログの扱いと、現在のコードを何で確認したかも教えてください。現在のファイルと証拠の対象版が対応しているかも確認してください。記録やファイルは変更しないでください。"
    facts = dict(case=name, ids=fixture.ids, before=fixture.snapshot(), task=task,
                 files_before={path.name: sha(path) for path in workspace.glob("*.py")})
    write_json(directory / "fixture.json", facts)
    tool = directory / "tool" / "latis"
    tool.parent.mkdir()
    runtime = prepare_runtime(directory)
    tool.write_text(f'#!{Path(sys.executable).resolve()}\nimport sys\nsys.path.insert(0, {str(runtime)!r})\nfrom scripts.llm_acceptance import audited_cli\nraise SystemExit(audited_cli({str(directory)!r}))\n')
    tool.chmod(0o755)
    for name_ in ("observe", "check"):
        helper = tool.parent / name_
        helper.write_text(f'#!{Path(sys.executable).resolve()}\nimport sys\nsys.path.insert(0, {str(runtime)!r})\nfrom scripts.llm_acceptance import workspace_command\nraise SystemExit(workspace_command({str(directory)!r}, {name_!r}))\n')
        helper.chmod(0o755)
    return directory


def prepare_runtime(directory):
    """元リポジトリの一覧読取を許可せず、実行に必要なソースだけを複写する。"""
    runtime = Path(directory) / "tool/runtime"
    sources = [ROOT / "bin/latis", *ROOT.glob("latis/*.py"),
               *(ROOT / "scripts" / name for name in ("__init__.py", "llm_acceptance.py", "claude_sandbox.py", "test_support.py"))]
    manifest = {}
    for source in sorted(sources):
        relative = source.relative_to(ROOT)
        destination = runtime / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        manifest[str(relative)] = dict(source=sha(source), copy=sha(destination))
        if manifest[str(relative)]["source"] != manifest[str(relative)]["copy"]:
            raise RuntimeError("実行ソースの複写中に内容が変わりました。試験を起動しません。")
    (runtime / "bin/latis").chmod(0o755)
    write_json(Path(directory) / "runtime-sources.json", manifest)
    return runtime


def workspace_command(directory, operation):
    """任意コードの引数を受けず、指定コピーの観測と実テストだけを提供する。"""
    if len(sys.argv) != 1:
        print("この試験補助コマンドに引数は指定できません。", file=sys.stderr)
        return 1
    workspace = Path(directory) / "workspace"
    files = ("retention.py", "test_retention.py")
    hashes = {name: sha(workspace / name) for name in files if (workspace / name).is_file()}
    if operation == "observe":
        observed = dict(operation=operation, observed_at=now(), content_hashes=hashes)
        with (Path(directory) / "helpers.jsonl").open("a") as stream:
            stream.write(canonical(observed) + "\n")
        print(canonical(observed))
        return 0
    existing = list(workspace.glob("test-result-*.log"))
    path = workspace / f"test-result-{len(existing) + 1}.log"
    print(f"実行: {sys.executable} -m unittest -v / 作業場所: {workspace} / バイトコードキャッシュを毎回分離", flush=True)
    result = run_unittest(workspace)
    path.write_bytes(result.stdout + result.stderr)
    sys.stdout.buffer.write(result.stdout + result.stderr)
    unchanged = hashes == {name: sha(workspace / name) for name in hashes}
    observed = dict(operation=operation, log=str(path), content_hash=sha(path), content_hashes=hashes,
                    observed_at=now(), exit_code=result.returncode, subjects_unchanged=unchanged, bytecode_cache="isolated")
    with (Path(directory) / "helpers.jsonl").open("a") as stream:
        stream.write(canonical(observed) + "\n")
    print(canonical(observed), flush=True)
    return result.returncode if unchanged else 2


def inject(directory, fixture_data, request):
    name = fixture_data["case"]
    if not (name.startswith("rebase-") or name == "unrelated") or (directory / "injected.json").exists():
        return
    if not any(op.get("op") == "update_node" and op.get("id") == fixture_data["ids"]["normal_retention"] for op in request.get("change_set", {}).get("operations", [])):
        return
    fixture = Fixture(directory / "workspace")
    fixture.ids = fixture_data["ids"]
    if name == "rebase-target":
        fixture.apply(fixture.update("normal_retention", title="通常ログの保持期間（並行更新で補記）"))
    elif name == "rebase-basis":
        # 明示的な根拠参照がある場合は個別版検査、ない場合もScopeの関係検査の対象になる。
        fixture.save(fixture.update("app_artifact", body=fixture.current("app_artifact")["body"] + "\n並行して観測メモを追記。"))
    elif name == "rebase-scope":
        fixture.apply(make_node("concurrent", "補足の保存規則", "通常ログの期間変更は監査ログへ波及させない。"),
                      make_relation("concurrent_scope", "$concurrent", fixture.ids["logs_scope"], "scoped_to"))
    elif name == "rebase-relation":
        relation = fixture.call("relation-detail", dict(relation_id=fixture.ids["normal_support"]))["relation"]
        fixture.apply(dict(op="update_relation", id=relation["id"], expected_revision_id=relation["revision_id"], set=dict(qualifier="通常ログと監査ログを分ける理由。並行して記録を補足。"), reconfirm=True))
    else:
        fixture.save(make_node("unrelated", "別作業の未整理メモ", "今回の保存期間には関係しない。", "question", "draft"))
    write_json(directory / "injected.json", dict(case=name, meta=fixture.call("meta", {})))


def audited_cli(directory):
    directory = Path(directory)
    raw = sys.stdin.buffer.read()
    # 許可したCLIを経由しても、試験コピー外のDBや退避元・出力先には触れない。
    args = sys.argv[1:]
    workspace = (directory / "workspace").resolve()
    if len(args) != 3 or args[0] != "--db" or Path(args[1]).resolve() != workspace / "demo.sqlite" or args[2] not in {"meta", "search", "detail", "relations", "relation-detail", "history", "save-draft", "consult", "apply", "export"}:
        print("この試験CLIは指定された専用DBと日常操作・exportだけを扱います。", file=sys.stderr)
        return 1
    if args[2] == "export":
        try:
            destination = Path(json.loads(raw)["destination"]).resolve()
            if not destination.is_relative_to(workspace):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            print("試験の出力先は作業コピー内に限定します。", file=sys.stderr)
            return 1
    started = time.time_ns()
    # PATH上の別版やHomebrewの中継symlinkを経由せず、同じPythonでCLIを実行する。
    result = subprocess.run([sys.executable, str(ROOT / "bin/latis"), *sys.argv[1:]], input=raw, capture_output=True)
    request, response = None, None
    try:
        request = json.loads(raw)
        response = json.loads(result.stdout)
    except ValueError:
        pass
    operation = next((value for value in reversed(sys.argv[1:]) if value in {"meta", "search", "detail", "relations", "relation-detail", "history", "save-draft", "consult", "apply", "export", "backup", "restore", "init"}), None)
    data = load_json(directory / "fixture.json")
    with (directory / "calls.jsonl").open("a", encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.write(canonical(dict(started=started, operation=operation, request=request, response=response, exit_code=result.returncode)) + "\n")
        stream.flush()
        if operation == "consult" and response and response["ok"]:
            inject(directory, data, request)
        lose = data["case"] == "retry" and operation == "apply" and response and response["ok"] and not (directory / "lost-response.json").exists()
        if lose:
            write_json(directory / "lost-response.json", dict(idempotency_key=request["idempotency_key"]))
    if lose:
        print("試験用の通信断：この操作の結果を受信できませんでした。", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    return result.returncode


def prompt_for(directory):
    data = load_json(directory / "fixture.json")
    return f'''日本語で作業・回答してください。架空のプロジェクトに対するLATIS利用試験です。
作業場所: {directory}/workspace
Guide: {ROOT}/docs/v0.3.0/LATIS_LLM_Guide.md
API仕様: {ROOT}/docs/v0.3.0/LATIS_API.md
CLI: {directory}/tool/latis
DB: {directory}/workspace/demo.sqlite
DBは初期化・準備済みです。Guideを読み、最初にmetaの版・capabilitiesを確認してください。CLIはJSONを標準入力へ渡します（metaも{{}}が必要）。
未解決の判断がある場合だけ質問し、既存の指示・授権を再利用してください。異なる種類の合意があるのに対象の種類が未指定なら、値や理由から対象を決めず、対象への回答を得るまで合意・コード・テストは変更しないでください。
同じ既存合意の期間・条件値などの変更は、同じIDの改訂を既定にします。全体置換の意図が明示されていなければ、別IDの合意とsupersedesを自分で選ばないでください。
作業やDB更新は指定した作業場所だけで行ってください。LATISの操作は指定CLIへ --db の絶対パスと操作名を渡し、DBの直接編集やEngineの直接呼出しは行わないでください。
ファイルの参照・探索はRead/Glob/Grep、作業コピー内の編集とJSON要求ファイルの作成はWrite/Editを使えます。作ったJSONは指定CLIの標準入力へファイルから渡せます。
Bashで許可されるのは指定CLIと次の二つの引数なし補助コマンドだけです。任意のPythonやシェルスクリプトの実行は許可していません。
すべてのBashと子プロセスにはOSサンドボックスを適用します。拒否された操作を隔離外で再実行したり、設定変更で回避したりしないでください。
{directory}/tool/observe : 作業コピーのコード・テストの実バイトのSHA-256と観測時刻を取得する外部観測コマンド。
{directory}/tool/check : 作業場所でpython3 -m unittest -vを実行し、実出力とログの場所、終了コードを返す外部検査コマンド。
これらは利用試験の呼出元の補助であり、LATIS Coreの新しい操作ではありません。必要な場合だけ使ってください。
非対話実行なので、未解決の質問が必要なら最終応答に質問を書いて終了してください。外部LLMのAPIは呼ばず、他のエージェントも起動しないでください。

依頼:
{data['task']}
'''


def render_event(event):
    type_ = event.get("type")
    if type_ == "system":
        if event.get("subtype") == "init":
            print(f"[起動] model={event.get('model')} / effort指定={EFFORT} / version={event.get('claude_code_version')}", flush=True)
        elif event.get("subtype") == "permission_denied":
            print("[権限] 操作が拒否されました。", flush=True)
    elif type_ in {"assistant", "user"}:
        content = event.get("message", {}).get("content", [])
        if not isinstance(content, list):
            return
        for block in content:
            if block.get("type") == "text":
                print("[Claude] " + block["text"], flush=True)
            elif block.get("type") == "tool_use":
                print("[操作] " + block["name"] + " " + json.dumps(block["input"], ensure_ascii=False), flush=True)
            elif block.get("type") == "tool_result":
                print("[操作結果] " + str(block.get("content", "")), flush=True)
    elif type_ == "result":
        print(f"[終了] subtype={event.get('subtype')} / is_error={event.get('is_error')} / turns={event.get('num_turns')} / ms={event.get('duration_ms')}", flush=True)


def run_claude(directory, turn="initial", *, prompt=None, session=None, resume=False, event_renderer=None):
    # 短いパスならClaudeが既定の/tmpへ切り替えない。実行後は専用領域を削除する。
    settings_for(directory, ROOT)
    with tempfile.TemporaryDirectory(prefix="ls-", dir="/private/tmp") as runtime:
        return _run_claude(directory, turn, prompt=prompt, session=session, resume=resume, runtime=runtime, event_renderer=event_renderer)


def _run_claude(directory, turn, *, prompt, session, resume, runtime, event_renderer=None):
    directory = Path(directory).resolve()
    workspace = directory / "workspace"
    read_roots = {workspace, workspace.resolve(), ROOT / "docs/v0.3.0"}
    edit_roots = {workspace, workspace.resolve()}
    allowed = [*(f"Read(/{path}/**)" for path in sorted(read_roots)), *(f"Edit(/{path}/**)" for path in sorted(edit_roots)),
               f"Bash({directory}/tool/latis *)", f"Bash({directory}/tool/observe)", f"Bash({directory}/tool/check)"]
    sandbox = settings_for(directory, ROOT, runtime=runtime)
    command = [claude_executable(), "-p", "--safe-mode", "--restricted", "--settings", canonical(sandbox), "--model", MODEL, "--effort", EFFORT,
               "--output-format", "stream-json", "--verbose", "--tools", "Read,Write,Edit,Bash,Glob,Grep",
               "--allowedTools", *allowed,
               "--permission-mode", "dontAsk", "--add-dir", str(ROOT / "docs/v0.3.0")]
    command += ["--resume" if resume else "--session-id", session] if session else ["--no-session-persistence"]
    prompt = prompt or prompt_for(directory)
    sources = {str(path.relative_to(ROOT)): sha(path) for path in sorted([*ROOT.glob("latis/*.py"), Path(__file__).resolve(), ROOT / "scripts/claude_sandbox.py", ROOT / "scripts/test_support.py", ROOT / "docs/v0.3.0/LATIS_LLM_Guide.md", ROOT / "docs/v0.3.0/LATIS_API.md"])}
    write_json(directory / (turn + "-launch.json"), dict(command=command, prompt=prompt, cwd=str(directory / "workspace"), model=MODEL, effort=EFFORT, sandbox=sandbox, sources=sources))
    print(f"\n\033[36m[M3] {directory.name} / {turn} を開始（{MODEL} / {EFFORT}）\033[0m", flush=True)
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               cwd=directory / "workspace", env=launch_environment(runtime=runtime), start_new_session=True)
    expired = threading.Event()
    def stop():
        expired.set()
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    timer = threading.Timer(900, stop)
    timer.start()
    events = []
    try:
        process.stdin.write(prompt)
        process.stdin.close()
        for line in process.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                print(line, end="", flush=True)
                continue
            events.append(event)
            # 保存する原記録は変えず、接続側が人向けの表示を提供できるようにする。
            if event_renderer is None:
                render_event(event)
            else:
                event_renderer(json.loads(line))
        code = process.wait()
    finally:
        timer.cancel()
        if process.poll() is None:
            stop()
            process.wait()
    write_json(directory / (turn + "-events.json"), events)
    results = [event for event in events if event.get("type") == "result"]
    models = [event.get("model") for event in events if event.get("type") == "system" and event.get("subtype") == "init"]
    result = dict(exit_code=code, timed_out=expired.is_set(), models=models, result=results[-1] if results else None)
    write_json(directory / (turn + "-result.json"), result)
    if code or expired.is_set() or not results or results[-1].get("is_error") or models != [MODEL]:
        raise RuntimeError(f"Claudeの起動・終了が不正です: {directory.name}/{turn}")
    return result


def read_calls(directory):
    path = Path(directory) / "calls.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def observed_nodes(calls, nodes):
    """現在版の完全レコードと、全文が返った検索結果を区別して数える。"""
    full, bodies = set(), set()
    for call in calls:
        response = call.get("response")
        if not response or not response["ok"]:
            continue
        data = response["data"]
        values = []
        if call["operation"] == "detail":
            values.append(data["node"])
        elif call["operation"] == "history" and call["request"].get("target_type") == "node":
            values.extend(revision["snapshot"] for revision in data["revisions"])
        for value in values:
            if value["id"] in nodes and value == nodes[value["id"]]:
                full.add(value["id"])
                bodies.add(value["id"])
        if call["operation"] == "search":
            for value in data["items"]:
                current = nodes.get(value["id"])
                if current and value["revision_id"] == current["revision_id"] and value["excerpt"] == current["body"]:
                    bodies.add(value["id"])
    return full, bodies


def evaluate(directory, *, require_change=True):
    directory = Path(directory)
    facts = load_json(directory / "fixture.json")
    name, ids, before = facts["case"], facts["ids"], facts["before"]
    fixture = Fixture(directory / "workspace")
    after = fixture.snapshot()
    write_json(directory / "after.json", after)
    calls = read_calls(directory)
    successful = [call for call in calls if call["response"] and call["response"]["ok"]]
    ops = [call["operation"] for call in successful]
    nodes = {node["id"]: node for node in after["nodes"]}
    relations = after["relations"]
    checks = dict(meta_used="meta" in ops, actual_cli_used=bool(calls))
    helpers = [json.loads(line) for line in (directory / "helpers.jsonl").read_text().splitlines()] if (directory / "helpers.jsonl").exists() else []
    if name in {"smoke", "discovery", "paging", "unobserved", "projection", "handover"} or name == "ambiguous" and not require_change:
        checks["database_unchanged"] = after == before
    if name in {"smoke", "discovery", "paging", "ambiguous", "unobserved", "failed", "projection", "handover", "retry", "unrelated"} or name.startswith("rebase-"):
        checks["code_and_tests_unchanged"] = facts["files_before"] == {path.name: sha(path) for path in fixture.workspace.glob("*.py")}
    if name == "discovery":
        found = {call["request"].get("node_id") for call in successful if call["operation"] == "detail"}
        checks.update(target_read=ids["limit"] in found, memo_read=ids["memo"] in found,
                      raw_records_searched=any(call["operation"] == "search" and set(call["request"].get("kinds", [])) & {"artifact", "proposal"} for call in calls),
                      candidate_read="relations" in ops)
    elif name == "paging":
        returned = {item["id"] for call in successful if call["operation"] == "search" for item in call["response"]["data"]["items"]}
        checks["all_records_observed"] = set(ids.values()) <= returned
    elif name == "ambiguous" and not require_change:
        checks["no_apply_before_answer"] = "apply" not in [call["operation"] for call in calls]
        observed = {call["request"].get("node_id") for call in successful if call["operation"] == "detail"}
        old = {node["id"]: node for node in before["nodes"]}
        observed.update(item["id"] for call in successful if call["operation"] == "search" for item in call["response"]["data"]["items"] if item["excerpt"] == old[item["id"]]["body"])
        checks["agreements_read"] = {ids[key] for key in ("normal_retention", "audit_retention")} <= observed
    elif name in {"ambiguous", "explicit", "retry", "unrelated"} or name.startswith("rebase-"):
        old_nodes = {node["id"]: node for node in before["nodes"]}
        normal, audit = nodes[ids["normal_retention"]], nodes[ids["audit_retention"]]
        checks.update(normal_same_id_updated="48時間" in normal["body"] and normal["revision_id"] != old_nodes[normal["id"]]["revision_id"],
                      audit_preserved=audit == old_nodes[audit["id"]], consult_used="consult" in ops, apply_used="apply" in ops)
        if name.startswith("rebase-") or name == "unrelated":
            checks["concurrent_update_injected"] = (directory / "injected.json").is_file()
            failed = [call for call in calls if call["operation"] == "apply" and call["response"] and not call["response"]["ok"]]
            if name != "unrelated":
                checks["stale_apply_rejected"] = bool(failed)
                checks["reconsulted_after_rejection"] = bool(failed) and any(call["operation"] == "consult" and call["started"] > failed[0]["started"] for call in successful)
            else:
                checks["unrelated_not_blocking"] = not failed
            if name == "rebase-target":
                checks["concurrent_title_preserved"] = "並行更新" in normal["title"]
        if name == "retry":
            writes = [call for call in calls if call["operation"] == "apply"]
            checks["same_key_replayed"] = len(writes) >= 2 and writes[0]["request"]["idempotency_key"] == writes[1]["request"]["idempotency_key"] and writes[0]["response"] == writes[1]["response"]
        if name == "explicit":
            current_hashes = {file: sha(fixture.workspace / file) for file in ("retention.py", "test_retention.py")}
            checks["actual_test_command_used"] = any(item["operation"] == "check" and item["exit_code"] == 0 and item["subjects_unchanged"] and item["content_hashes"] == current_hashes for item in helpers)
            result = run_unittest(fixture.workspace)
            checks["real_tests_passed"] = result.returncode == 0
            checks["observed_files_match"] = all(nodes[ids[key]]["content_hash"] == sha(fixture.workspace / file) for key, file in (("app_artifact", "retention.py"), ("test_artifact", "test_retention.py")))
            fresh = [node for node in nodes.values() if node.get("evidence") and node["id"] not in old_nodes]
            current = {node["id"]: node["revision_id"] for node in nodes.values()}
            valid = {node["id"] for node in fresh if node["evidence"]["outcome"] == "passed" and all(current[ref["id"]] == ref["revision_id"] for ref in node["evidence"]["subject_refs"]) and {ids["app_artifact"], ids["test_artifact"]} <= {ref["id"] for ref in node["evidence"]["subject_refs"]}}
            checks["new_current_evidence"] = bool(valid)
            checks["both_agreements_verified"] = all(any(rel["relation_kind"] == "verified_by" and rel["from_node_id"] == ids[key] and rel["to_node_id"] in valid and rel["confirmation"] == "confirmed" and rel["lifecycle"] == "active" for rel in relations) for key in ("normal_retention", "audit_retention"))
            checks["old_evidence_preserved"] = nodes[ids["baseline_evidence"]] == old_nodes[ids["baseline_evidence"]]
    elif name == "failed":
        checks["actual_failed_test_used"] = any(item["operation"] == "check" and item["exit_code"] != 0 and item["subjects_unchanged"] for item in helpers)
        fresh = [node for node in nodes.values() if node.get("evidence") and node["id"] not in {old["id"] for old in before["nodes"]}]
        checks["new_failed_evidence"] = bool(fresh) and all(node["evidence"]["outcome"] == "failed" for node in fresh)
        checks["failed_not_confirmed"] = not any(rel["relation_kind"] == "verified_by" and rel["to_node_id"] in {node["id"] for node in fresh} and rel["confirmation"] == "confirmed" for rel in relations)
        checks["app_observed"] = nodes[ids["app_artifact"]]["content_hash"] == sha(fixture.workspace / "retention.py")
    elif name == "unobserved":
        checks["physical_files_observed"] = any(item["operation"] == "observe" for item in helpers)
        checks["no_new_test_run"] = not any(item["operation"] == "check" for item in helpers)
    elif name == "organize":
        checks.update(base_kept=nodes[ids["base"]]["lifecycle"] == "accepted", replaced=nodes[ids["replace"]]["lifecycle"] == "superseded",
                      withdrawn=nodes[ids["withdraw"]]["lifecycle"] == "retired", split_old_retired=nodes[ids["split"]]["lifecycle"] == "retired",
                      proposal_adopted=nodes[ids["draft"]]["lifecycle"] == "accepted", rationale_preserved=nodes[ids["reason"]]["kind"] == "rationale")
        confirmed = [rel for rel in relations if rel["confirmation"] == "confirmed" and rel["lifecycle"] == "active"]
        checks["exception_condition_recorded"] = any(rel["relation_kind"] == "exception_to" and rel["to_node_id"] == ids["base"] and rel["qualifier"] for rel in confirmed)
        checks["replacement_recorded"] = any(rel["relation_kind"] == "supersedes" and rel["to_node_id"] == ids["replace"] for rel in confirmed)
        checks["split_sources_recorded"] = len({rel["from_node_id"] for rel in confirmed if rel["relation_kind"] == "originates_from" and rel["to_node_id"] == ids["split"]}) == 2
        checks["candidate_confirmed"] = any(rel["id"] == ids["candidate"] for rel in confirmed)
    elif name == "projection":
        checks["descendant_search_used"] = any(call["operation"] == "search" and call["request"].get("include_descendants") is True and ids["rule"] in {item["id"] for item in call["response"]["data"]["items"]} for call in successful)
        view = fixture.workspace / "view"
        projected = [json.loads(path.read_bytes()[4:].split(b"\n---\n", 1)[0])["id"] for path in view.glob("*/node-*.md")]
        checks["markdown_selection_correct"] = projected == [ids["rule"]] and (view / "index.md").is_file() and "export" in ops
    elif name == "handover":
        details, bodies = observed_nodes(successful, nodes)
        checks["agreements_and_files_reread"] = {ids[key] for key in ("normal_retention", "audit_retention")} <= bodies and {ids[key] for key in ("app_artifact", "test_artifact")} <= details
        checks["history_reread"] = any(call["operation"] == "history" and call["request"].get("target_id") == ids["normal_retention"] for call in successful)
        checks["verification_reread"] = "relations" in ops and any(nodes.get(id_, {}).get("evidence") for id_ in details)
        checks["physical_files_observed"] = any(item["operation"] == "observe" and item["content_hashes"] == {file: sha(fixture.workspace / file) for file in ("retention.py", "test_retention.py")} for item in helpers)
    report = dict(case=name, checks=checks, mechanical_pass=all(checks.values()), semantic_review="pending", calls=len(calls),
                  note="自然文の質問・意味・説明と、実行コマンド・証拠の対応はtranscriptとDBを別途レビューする。")
    write_json(directory / ("initial-check.json" if name == "ambiguous" and not require_change else "check.json"), report)
    print("[機械検査] " + canonical(report), flush=True)
    return report


def run(output, cases):
    output = Path(output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    print(f"[M3] 出力先={output} / CLI指定={MODEL} / effort={EFFORT}", flush=True)
    reports = []
    for name in cases:
        directory = prepare_case(output / name, name, handover_source=output / "explicit" if name == "handover" else None)
        if name == "ambiguous":
            session = str(uuid.uuid4())
            run_claude(directory, session=session)
            initial = evaluate(directory, require_change=False)
            if not initial["mechanical_pass"]:
                raise RuntimeError("対象の返答前に不正な変更・探索不足がありました。")
            run_claude(directory, "reply", prompt="通常ログだけ48時間にしてください。監査ログは変更しないでください。理由は障害調査の時間を確保するためです。今回は合意の改訂と理由の記録だけを行い、コードとテストは編集しないでください。", session=session, resume=True)
        else:
            run_claude(directory)
        report = evaluate(directory)
        reports.append(report)
        write_json(output / "summary.json", dict(model=MODEL, effort=EFFORT, cases=reports, semantic_review="pending"))
        if not report["mechanical_pass"]:
            raise RuntimeError("機械検査が不合格です。後続のケースは実行しません: " + name)
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Claude CLIによるLATIS利用検査。生ログはlog-window e2eへ出力する。")
    parser.add_argument("--output", required=True, help="まだ存在しない専用出力ディレクトリ")
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    args = parser.parse_args()
    run(args.output, args.cases)
