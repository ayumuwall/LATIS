#!/usr/bin/env python3
"""実DB・正規CLI・Playwrightで、保存から描画と障害復旧を確認する。"""

import argparse
import json
import re
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from latis.model import uid
from scripts.reset_demo import reset
from tools.graph_demo.prepare import node, relation
from tools.graph_demo.projection import read_snapshot, project
from tools.graph_demo.server import make_handler


def run(source, output):
    from playwright.sync_api import sync_playwright, expect
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    work = output / "work"
    reset(source, work, state="baseline", format_="json")
    db = work / "demo.sqlite"
    checks, errors, calls, latency = [], [], [], []
    completed = False
    timing = output / "commits.jsonl"
    wrapper = output / "timed_cli.py"
    wrapper.write_text(f'''import json,sqlite3,sys,time
from pathlib import Path
sys.path.insert(0,{str(ROOT)!r})
original=sqlite3.connect
class Connection(sqlite3.Connection):
    def commit(self):
        super().commit()
        stamp=time.time_ns()
        with Path({str(timing)!r}).open('a') as stream:
            stream.write(json.dumps(dict(operation=sys.argv[-1],committed_ns=stamp))+'\\n')
def connect(*args,**kwargs):
    kwargs['factory']=Connection
    return original(*args,**kwargs)
sqlite3.connect=connect
from latis.cli import main
raise SystemExit(main())
''')

    def check(name, condition=True, **details):
        checks.append(dict(name=name, passed=bool(condition), **details))
        print(f"[ブラウザー検査] {name}: {'合格' if condition else '不合格'}", flush=True)
        if not condition:
            raise AssertionError(name)

    def call(operation, request, target=db, expected_error=None):
        result = subprocess.run([sys.executable, str(wrapper), "--db", str(target), operation],
            input=json.dumps(request, ensure_ascii=False).encode(), capture_output=True, timeout=30)
        response = json.loads(result.stdout)
        calls.append(dict(operation=operation, request=request, response=response, exit_code=result.returncode))
        (output / "calls.json").write_text(json.dumps(calls, ensure_ascii=False, indent=2) + "\n")
        if expected_error:
            assert not response["ok"] and response["errors"][0]["code"] == expected_error, response
            return response
        assert result.returncode == 0 and response["ok"], response
        return response

    def application(operations, target=db):
        consultation = call("consult", dict(proposal=dict(title="展示ブラウザーの検査", body="架空の専用データで描画を確認する。"),
                            change_set=dict(operations=operations)), target)["data"]
        return dict(**consultation["normalized_request"], basis=consultation["basis"],
            decision=dict(actor="test:graph-browser", authority_ref="展示UIの実ブラウザー検証指示", reason="保存・表示・復旧を確認する", semantic_review="ready"), idempotency_key=uid())

    class Handler(make_handler(db)):
        def log_request(self, code="-", size="-"):
            if code != 200:
                super().log_request(code, size)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(viewport=dict(width=1920, height=1080), locale="ja-JP")
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.add_init_script('''document.addEventListener('DOMContentLoaded',()=>{
                    window.__draws=[];let previous='';
                    new MutationObserver(()=>{const text=document.querySelector('#revision')?.textContent;
                      if(text&&text!==previous){previous=text;requestAnimationFrame(()=>requestAnimationFrame(()=>window.__draws.push({text,painted_ns:Date.now()*1e6})));}
                    }).observe(document.documentElement,{subtree:true,childList:true,characterData:true});
                });''')
                url = f"http://127.0.0.1:{server.server_port}"

                def data():
                    return page.request.get(url + "/api/graph").json()["data"]

                def wait_revision(response, measure=False):
                    number = response["meta"]["graph_revision"]
                    snapshot = response["meta"]["snapshot_id"]
                    expect(page.locator("#revision")).to_contain_text(snapshot, timeout=7000)
                    if measure:
                        page.wait_for_function("snapshot => window.__draws.some(d=>d.text.includes(snapshot))", arg=snapshot)
                        painted = page.evaluate("snapshot => window.__draws.find(d=>d.text.includes(snapshot)).painted_ns", snapshot)
                        committed = json.loads(timing.read_text().splitlines()[-1])["committed_ns"]
                        seconds = (painted - committed) / 1e9
                        latency.append(dict(graph_revision=number, seconds=seconds, committed_ns=committed, painted_ns=painted))
                        check("実commit完了から描画まで2秒以内", 0 <= seconds <= 2, seconds=seconds)

                page.goto(url, wait_until="domcontentloaded")
                expect(page.locator("#mode")).to_have_text("LIVE")
                before = read_snapshot(db)
                initial = data()
                normal = next(n for n in initial["nodes"] if n["title"] == "通常ログの保持期間")
                normal_id = normal["id"]
                normal_row = page.locator(f'.data-row[data-node-id="{normal_id}"]').first
                normal_row.locator(".item-button").click()
                expect(page.locator("#details .body-text")).to_contain_text("24時間")
                expect(page.locator(".data-row .badge")).to_have_count(0)
                normal_number = initial["display_numbers"][normal_id]
                expect(normal_row.locator(".object-number")).to_have_text(normal_number)
                check("複数所属の同じ合意は同じ番号",set(page.locator(f'.data-row[data-node-id="{normal_id}"] .object-number').all_text_contents()) == {normal_number})
                page.locator("#filter").fill(normal_number)
                check("番号検索はA-1とA-10等を区別",set(page.locator(".data-row").evaluate_all("rows=>rows.map(r=>r.dataset.nodeId)")) == {normal_id})
                incident = next(n for n in initial["nodes"] if n["kind"] == "scope" and n["title"] == "障害対応")
                incident_number = initial["display_numbers"][incident["id"]]
                root = next(n for n in initial["nodes"] if n["kind"] == "scope" and n["title"].startswith("ログ関連"))
                page.locator("#filter").fill("")
                page.locator(f'.scope-row[data-scope-id="{root["id"]}"] .scope-toggle').click()
                page.locator("#filter").fill("一致しない検索条件")
                page.locator("#details > .relation-card").get_by_role("button",name=f'{incident_number} 障害対応',exact=True).click()
                expect(page.locator("#details h1")).to_have_text("障害対応")
                expect(page.locator("#details .detail-number")).to_have_text(incident_number)
                incident_heading = page.locator(f'.scope-row[data-scope-id="{incident["id"]}"]')
                expect(incident_heading).to_have_class("scope-row selected")
                expect(incident_heading.locator(".scope-toggle")).to_have_attribute("aria-expanded","true")
                check("scoped_to先を番号付きScope見出しで選択・表示")
                with page.expect_download() as downloading:
                    page.locator("#details .export-button").click()
                download = downloading.value
                destination = output / "scope-inspector.md"
                download.save_as(str(destination))
                document=destination.read_text()
                header=json.loads(re.search(r"<!-- latis-source: (.*?) -->",document).group(1))
                records=[json.loads(value) for value in re.findall(r"<!-- latis-node: (.*?) -->",document)]
                expected={id_ for id_,scope_ids in initial["scope_ids"].items() if incident["id"] in scope_ids}
                check("Scope詳細から表示版を単一Markdownへ保存",header["meta"] == initial["meta"] and {r["id"] for r in records if r["role"] == "direct"} == expected)
                check("ファイル名はScope番号",download.suggested_filename == incident_number + ".md")
                page.screenshot(path=str(output / "00-scope-navigation.png"))
                page.locator("#filter").fill("")
                normal_scope = next(n for n in initial["nodes"] if n["kind"] == "scope" and n["title"] == "通常ログ")
                with page.expect_download() as downloading:
                    page.locator(f'.scope-row[data-scope-id="{normal_scope["id"]}"] .export-button').click()
                destination = output / "scope-header.md"
                downloading.value.save_as(str(destination))
                document=destination.read_text()
                header=json.loads(re.search(r"<!-- latis-source: (.*?) -->",document).group(1))
                check("Scope見出しから番号付き要件をまとめて保存",header["scope"]["id"] == normal_scope["id"] and "## Requirements" in document)
                check("Markdownの内部IDと元の版を保持",normal_id in document and normal["revision_id"] in document and "### Requirement: " + normal_number in document)
                page.route("**/api/export/scope/**",lambda route:route.fulfill(status=503,json=dict(ok=False,error=dict(message="書き出し失敗の検査"))))
                page.locator(f'.scope-row[data-scope-id="{normal_scope["id"]}"] .export-button').click()
                expect(page.locator("#export-status")).to_have_text("書き出し失敗の検査")
                check("書き出し失敗を表示して閲覧状態を保持",page.locator("#mode").inner_text() == "LIVE")
                page.unroute("**/api/export/scope/**")
                normal_row.locator(".item-button").click()
                expect(page.locator("#details .detail-number")).to_have_text(normal_number)
                check("詳細に元のIDと表示番号を保持",normal_id in page.locator("#details .metadata").first.inner_text())
                for width,height in ((1920,1080),(1366,768)):
                    page.set_viewport_size(dict(width=width,height=height))
                    check(f"{width}幅の合意行を細く表示",normal_row.bounding_box()["height"] <= 64)
                    page.screenshot(path=str(output / f"00-compact-{width}.png"))
                page.set_viewport_size(dict(width=1920,height=1080))
                page.screenshot(path=str(output / "01-initial.png"))
                page.locator("#filter").fill("保持期間")
                check("検索結果の合意を重複計数しない", len(set(page.locator(".data-row").evaluate_all("rows=>rows.map(r=>r.dataset.nodeId)"))) == 2)
                page.locator("#filter").fill("")
                group = page.locator(".scope-toggle").filter(has_text="通常ログ")
                group.click()
                group.click()
                check("選択・検索・折畳みでDB不変", read_snapshot(db) == before)
                check("初期ロードは静的", page.locator(".data-row .badge").count() == 0)

                draft = call("save-draft", dict(change_set=dict(operations=[node("q", "question", "検査用の問い", "今回の表示確認に使う草稿。", "draft")]),
                    record=dict(actor="test:browser", reason="草稿で確定表示を出さないことを確認"), idempotency_key=uid()))
                wait_revision(draft)
                check("草稿保存に確定マーカーなし", page.locator(".data-row .badge").count() == 0)
                scope_id = next(id_ for id_ in initial["scope_ids"][normal_id] if next(n for n in initial["nodes"] if n["id"] == id_)["title"] == "通常ログ")
                utc_request = application([node("utc", "agreement", "ブラウザー検査のUTC合意", "通常ログのタイムスタンプはUTCで統一する。"),
                    node("reason", "rationale", "UTCの理由", "時差による取り違えを防ぐため。"),
                    relation("member", "$utc", scope_id), relation("support", "$reason", "$utc", "supports")])
                check("consultはDBを変更しない", read_snapshot(db)["meta"]["snapshot_id"] == draft["meta"]["snapshot_id"])
                denied = dict(utc_request, decision=dict(utc_request["decision"], semantic_review="needs_user_decision"))
                call("apply", denied, expected_error="UNRESOLVED_DECISION")
                check("失敗applyはDB不変", read_snapshot(db)["meta"]["graph_revision"] == draft["meta"]["graph_revision"])
                utc = call("apply", utc_request)
                wait_revision(utc, measure=True)
                utc_id = utc["data"]["created_refs"]["utc"]["id"]
                utc_row = page.locator(f'.data-row[data-node-id="{utc_id}"]')
                expect(utc_row).to_be_visible()
                expect(utc_row.locator(".badge")).to_have_text("NEW")
                page.locator("#reduce-motion").uncheck()
                check("確定行だけに短い強調を有効化できる", utc_row.evaluate("e=>getComputedStyle(e).animationName") == "confirm")
                page.emulate_media(reduced_motion="reduce")
                check("OSのモーション停止で確定アニメーションなし", utc_row.evaluate("e=>getComputedStyle(e).animationName") == "none")
                page.emulate_media(reduced_motion="no-preference")
                page.locator("#reduce-motion").check()
                check("画面の停止設定で確定アニメーションなし", utc_row.evaluate("e=>getComputedStyle(e).animationName") == "none")
                row_box, rows_box = utc_row.bounding_box(), page.locator("#rows").bounding_box()
                check("新規採択の行を閲覧領域へ表示", row_box["y"] >= rows_box["y"] - 1 and row_box["y"] + row_box["height"] <= rows_box["y"] + rows_box["height"] + 1)
                expect(page.locator("#details .body-text")).to_contain_text("UTC")
                page.screenshot(path=str(output / "02-new.png"))
                expect(page.locator(".data-row .badge")).to_have_count(0, timeout=6000)
                replayed = call("apply", utc_request)
                check("成功済み再送は同じ応答・単一commit", replayed == utc and read_snapshot(db)["meta"]["graph_revision"] == utc["meta"]["graph_revision"])

                page.locator("#filter").fill("保持期間")
                normal_row.locator(".item-button").click()
                old_box = normal_row.bounding_box()
                normal = next(n for n in data()["nodes"] if n["id"] == normal_id)
                revised = call("apply", application([dict(op="update_node", id=normal_id, expected_revision_id=normal["revision_id"], set=dict(body=normal["body"].replace("24時間", "48時間")))]))
                wait_revision(revised, measure=True)
                expect(page.locator("#details .body-text")).to_contain_text("48時間")
                expect(page.locator("#details .detail-number")).to_have_text(normal_number)
                check("本文改訂で合意番号を変えない",data()["display_numbers"][normal_id] == normal_number)
                expect(page.locator("#details > .diff del")).to_have_text("24")
                expect(page.locator("#details > .diff ins")).to_have_text("48")
                new_box = normal_row.bounding_box()
                check("同じIDの行位置と合意件数を保持", abs(old_box["y"]-new_box["y"]) <= 1 and len(set(page.locator(".data-row").evaluate_all("rows=>rows.map(r=>r.dataset.nodeId)"))) == 2)
                audit = next(n for n in data()["nodes"] if n["title"] == "監査ログの保持期間")
                check("監査ログ90日を保持", "90日（2160時間）" in audit["body"])
                page.screenshot(path=str(output / "03-revised.png"))
                page.locator("#filter").fill("")
                expect(page.locator(".data-row .badge")).to_have_count(0, timeout=6000)

                relation_id = utc["data"]["created_refs"]["support"]["id"]
                r = next(r for r in data()["relations"] if r["id"] == relation_id)
                changed = call("apply", application([dict(op="update_relation", id=r["id"], expected_revision_id=r["revision_id"], set=dict(lifecycle="retired"))]))
                wait_revision(changed)
                check("関係のみの更新で合意を追加しない", len([n for n in data()["nodes"] if n["kind"] == "agreement"]) == 14 and page.locator(".data-row .badge").count() == 0)
                held = dict(ok=True, data=data())
                page.route("**/api/graph", lambda route: route.fulfill(json=held))
                for index in range(2):
                    latest = call("apply", application([node(f"batch{index}", "agreement", f"近接commitの合意{index}", "この架空の記録を区別しなければならない。")]))
                page.unroute("**/api/graph")
                wait_revision(latest)
                expect(page.locator("#sync-status")).to_contain_text("複数件更新")
                check("近接commitは実履歴の最終状態へ同期")
                retired_id = latest["data"]["created_refs"]["batch1"]["id"]
                retired_node = next(n for n in data()["nodes"] if n["id"] == retired_id)
                retired = call("apply", application([
                    dict(op="update_node", id=retired_id, expected_revision_id=retired_node["revision_id"], set={"lifecycle": "retired"})
                ]))
                wait_revision(retired)
                expect(page.locator(f'.data-row[data-node-id="{retired_id}"]')).to_have_count(0)
                expect(page.locator("#selected-kind")).to_contain_text("終了")
                page.locator("#all-states").check()
                expect(page.locator(f'.data-row[data-node-id="{retired_id}"] .badge')).to_have_text("終了")
                page.locator("#all-states").uncheck()
                check("終了した合意を採択済みと区別する")
                page.reload(wait_until="domcontentloaded")
                expect(page.locator("#mode")).to_have_text("LIVE")
                expect(page.locator(".data-row .badge")).to_have_count(0)
                check("再読込で確定を再演しない")
                retained = page.locator("#details h1").inner_text()
                malformed = data()
                del malformed["nodes"][0]["created_at"]
                for name, payload in (("通信失敗", dict(status=503,json=dict(ok=False,error=dict(message="検査用の通信失敗")))),
                                      ("不正応答", dict(json=dict(ok=True,data=dict(meta={})))),
                                      ("不正なノード形式", dict(json=dict(ok=True,data=malformed)))):
                    def fault(route):
                        route.fulfill(**payload)
                    page.route("**/api/graph", fault)
                    expect(page.locator("#mode")).to_have_text("DISCONNECTED",timeout=6000)
                    check(name + "でも最後の正常表示を保持", page.locator("#details h1").inner_text() == retained)
                    page.unroute("**/api/graph")
                    expect(page.locator("#mode")).to_have_text("LIVE",timeout=6000)
                    expect(page.locator("#sync-status")).to_contain_text("RECONNECTED")
                    expect(page.locator(".data-row .badge")).to_have_count(0)
                with sqlite3.connect(db) as lock:
                    lock.execute("BEGIN EXCLUSIVE")
                    expect(page.locator("#mode")).to_have_text("DISCONNECTED",timeout=6000)
                expect(page.locator("#mode")).to_have_text("LIVE",timeout=6000)
                check("実DBの排他ロックから復旧")

                empty = output / "empty.sqlite"
                call("init", {"project_name":"空の表示検査"}, empty)
                empty.replace(db)
                expect(page.locator("#selected-kind")).to_have_text("—",timeout=6000)
                expect(page.locator("#details h1")).to_have_count(0)
                expect(page.locator("#sync-status")).to_contain_text("RESET")
                check("空の別DBで旧Inspectorを消す")
                branches = []
                for label in ("a", "b"):
                    dest = output / ("branch-" + label)
                    reset(source, dest, state="baseline", format_="sqlite")
                    target = dest / "demo.sqlite"
                    response = call("apply", application([node("branch", "agreement", "履歴の枝" + label, "独立した履歴として扱わなければならない。")], target), target)
                    branches.append(response)
                    target.replace(db)
                    expect(page.locator("#revision")).to_contain_text(response["meta"]["snapshot_id"],timeout=6000)
                    expect(page.locator("#sync-status")).to_contain_text("RESET")
                    expect(page.locator(".data-row .badge")).to_have_count(0)
                check("同じDB・連番の別snapshotをRESET", branches[0]["meta"]["graph_revision"] == branches[1]["meta"]["graph_revision"] and branches[0]["meta"]["snapshot_id"] != branches[1]["meta"]["snapshot_id"])

                saved = call("save-draft",dict(change_set=dict(operations=[
                    node("draft_agreement","agreement","草稿状態の表示","草稿本文を採択済みとして扱ってはならない。","draft"),
                    node("proposed_agreement","agreement","提案状態の表示","提案本文を採択済みとして扱ってはならない。","proposed")]),
                    record=dict(actor="test:browser",reason="合意の未採択状態を表示で区別する"),idempotency_key=uid()))
                wait_revision(saved)
                page.locator("#all-states").check()
                for ref,label in (("draft_agreement","草稿"),("proposed_agreement","提案")):
                    id_ = saved["data"]["created_refs"][ref]["id"]
                    expect(page.locator(f'.data-row[data-node-id="{id_}"] .badge')).to_have_text(label)
                check("草稿・提案の合意にNEWを出さない")
                draft_id = saved["data"]["created_refs"]["draft_agreement"]["id"]
                current = next(n for n in data()["nodes"] if n["id"] == draft_id)
                rejected = call("save-draft",dict(change_set=dict(operations=[dict(op="update_node",id=draft_id,
                    expected_revision_id=current["revision_id"],set=dict(lifecycle="rejected"))]),
                    record=dict(actor="test:browser",reason="不採用の未採択合意を区別する"),idempotency_key=uid()))
                wait_revision(rejected)
                expect(page.locator(f'.data-row[data-node-id="{draft_id}"] .badge')).to_have_text("不採用")
                check("不採用の合意を採択済みと区別する")
                old_id = branches[-1]["data"]["created_refs"]["branch"]["id"]
                old = next(n for n in data()["nodes"] if n["id"] == old_id)
                replaced = call("apply",application([node("replacement","agreement","置換後の合意","置換の実履歴を保持しなければならない。"),
                    dict(op="update_node",id=old_id,expected_revision_id=old["revision_id"],set=dict(lifecycle="superseded")),
                    relation("supersedes","$replacement",old_id,"supersedes"),relation("member","$replacement",scope_id)]))
                wait_revision(replaced)
                expect(page.locator(f'.data-row[data-node-id="{old_id}"] .badge')).to_have_text("置換済み")
                check("確定した置換と旧合意の終了状態を反映する")
                replacement_id = replaced["data"]["created_refs"]["replacement"]["id"]
                member_id = replaced["data"]["created_refs"]["member"]["id"]
                member = next(r for r in data()["relations"] if r["id"] == member_id)
                audit_scope = next(n["id"] for n in data()["nodes"] if n["kind"] == "scope" and n["title"] == "監査ログ")
                moved = call("apply",application([dict(op="update_relation",id=member_id,expected_revision_id=member["revision_id"],set=dict(lifecycle="retired")),
                    relation("moved",replacement_id,audit_scope)]))
                wait_revision(moved)
                page.locator(f'.data-row[data-node-id="{replacement_id}"] .item-button').click()
                check("所属移動を実scoped_toどおり反映する",data()["scope_ids"][replacement_id] == [audit_scope] and "監査ログ" in page.locator("#details").inner_text())
                page.locator("#all-states").uncheck()

                injection = call("apply", application([node("literal", "agreement", '<img src=x onerror="window.injected=1">', '原文を保持しなければならない。<script>window.injected=1</script>')]))
                wait_revision(injection)
                check("保存文字列をHTMLとして実行しない", not page.evaluate("Boolean(window.injected)") and page.locator("#details img").count() == 0)
                for width,height in ((1920,1080),(1366,768)):
                    page.set_viewport_size(dict(width=width,height=height))
                    metrics = page.evaluate('''() => {const main=document.querySelector('main').getBoundingClientRect(),stream=document.querySelector('.stream').getBoundingClientRect(),footer=document.querySelector('footer').getBoundingClientRect();return {main_bottom:main.bottom,stream_top:stream.top,footer_bottom:footer.bottom,height:innerHeight};}''')
                    check(f"{width}×{height}の領域が重ならない", metrics["main_bottom"] <= metrics["stream_top"] + 1 and metrics["footer_bottom"] <= height + 1, metrics=metrics)
                    page.screenshot(path=str(output / f"04-layout-{width}.png"))
                check("JavaScriptの実行エラーなし", not errors, errors=errors)
                context.close()
                browser.close()
                completed = True
        finally:
            server.shutdown()
            thread.join()
            (output / "report.json").write_text(json.dumps(dict(passed=completed and bool(checks) and all(c["passed"] for c in checks) and not errors,
                checks=checks, latency=latency, page_errors=errors,
                timing_method="SQLite Connection.commitの正常終了直後と、DOM更新後2回目のrequestAnimationFrameを同じ端末の時刻で比較。LLM時間は含めない。"), ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run(Path(args.source).resolve(), args.output)
