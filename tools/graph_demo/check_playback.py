#!/usr/bin/env python3
"""実履歴の再生・関係参照・収録映像とLIVE復帰を実ブラウザーで確認する。"""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import threading
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.reset_demo import reset
from tools.graph_demo.projection import project
from tools.graph_demo.server import make_handler


def run(source, output, recording=None):
    from playwright.sync_api import sync_playwright, expect
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    reset(Path(source).resolve(), output / "work", state="final", format_="sqlite")
    db = output / "work/demo.sqlite"
    before = sha256(db.read_bytes()).hexdigest()
    data = project(db)
    normal = next(n for n in data["nodes"] if n["kind"] == "agreement" and n["title"] == "通常ログの保持期間")
    revised = next(e for e in data["events"] if any(c["type"] == "node" and c["id"] == normal["id"] and c["before"] and "24" in c["before"]["body"] and "48" in c["after"]["body"] for c in e["changes"]))
    checks, errors, requests = [], [], []
    completed = False
    def check(name, condition=True):
        checks.append(dict(name=name, passed=bool(condition)))
        print(f"[再生検査] {name}: {'合格' if condition else '不合格'}", flush=True)
        if not condition:
            raise AssertionError(name)
    class Handler(make_handler(db, Path(recording).resolve() if recording else None)):
        def log_request(self, code="-", size="-"):
            if code not in (200,206): super().log_request(code,size)
    with ThreadingHTTPServer(("127.0.0.1",0),Handler) as server:
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome",headless=True)
                context = browser.new_context(viewport=dict(width=1920,height=1080),locale="ja-JP",reduced_motion="reduce")
                base = f"http://127.0.0.1:{server.server_port}"
                context.route("**/*",lambda route: route.continue_() if route.request.url.startswith(base + "/") else route.abort())
                page = context.new_page()
                page.on("pageerror",lambda e: errors.append(str(e)))
                page.on("request",lambda req: requests.append(req.url))
                page.goto(base,wait_until="domcontentloaded")
                expect(page.locator("#mode")).to_have_text("LIVE")
                def select_normal():
                    page.locator(f'.data-row[data-node-id="{normal["id"]}"] .item-button').first.click()
                select_normal()
                expect(page.locator("#details .body-text")).to_contain_text("48時間")
                focus = page.locator(".focus-map")
                focus.locator("summary").click()
                relations = [r for r in data["relations"] if normal["id"] in (r["from_node_id"],r["to_node_id"])]
                check("選択した記録の実関係だけに線を描く",focus.locator("svg").count() == len(relations))
                check("向き・型・候補確定・終了を明示",all(r["relation_kind"] in focus.inner_text() for r in relations) and "選択元" in focus.inner_text())
                focus.get_by_role("button",name="関係の原文・根拠版",exact=True).first.click()
                expect(page.locator("#selected-kind")).to_contain_text("relation")
                check("関係の正本へ辿れる",relations[0]["id"] in page.locator("#details").inner_text())
                select_normal()
                page.locator("#reduce-motion").uncheck()
                check("OSのモーション軽減を尊重",page.locator(".data-row").first.evaluate("e=>getComputedStyle(e).animationName") == "none")
                page.locator("#reduce-motion").check()
                check("画面の停止設定を反映",not page.locator("body").evaluate("e=>e.classList.contains('motion')"))

                # LIVE取得が遅れて戻っても、REPLAYへ上書きしない。
                page.evaluate('''() => {const original=window.fetch;window.delayLive=true;window.fetch=async (...args)=>{const response=await original(...args);if(window.delayLive&&args[0]==='/api/graph')await new Promise(r=>setTimeout(r,1400));return response;};}''')
                page.wait_for_timeout(900)
                page.locator("#start-replay").click()
                expect(page.locator("#replay-position")).to_have_text(f'rev 0 / {data["meta"]["graph_revision"]}')
                page.wait_for_timeout(1700)
                expect(page.locator("#mode")).to_have_text("REPLAY")
                check("遅れたLIVE応答がREPLAYを上書きしない",page.locator("#details h1").count() == 0)
                page.locator("#replay-toggle").click()
                expect(page.locator("#replay-position")).to_have_text(f'rev 1 / {data["meta"]["graph_revision"]}')
                page.locator("#replay-toggle").click()
                page.wait_for_timeout(2800)
                check("停止後に版を進めない",page.locator("#replay-position").inner_text().startswith("rev 1 /"))
                page.locator("#replay-toggle").click()
                expect(page.locator("#replay-position")).to_have_text(f'rev 2 / {data["meta"]["graph_revision"]}')
                page.locator("#replay-toggle").click()
                check("停止後の再開は次の実commit")

                def seek(number):
                    page.locator("#replay-range").evaluate("(e,n)=>{e.value=n;e.dispatchEvent(new Event('input'));}",number)
                    expect(page.locator("#replay-position")).to_have_text(f'rev {number} / {data["meta"]["graph_revision"]}')
                    expect(page.locator("#mode")).to_have_text("REPLAY")
                seek(revised["graph_revision"]-1)
                select_normal()
                expect(page.locator("#details .body-text")).to_contain_text("24時間")
                expect(page.locator("#details .detail-number")).to_have_text(data["display_numbers"][normal["id"]])
                seek(revised["graph_revision"])
                expect(page.locator("#details .body-text")).to_contain_text("48時間")
                expect(page.locator("#details .detail-number")).to_have_text(data["display_numbers"][normal["id"]])
                check("REPLAYの旧版・新版も同じ合意番号")
                check("実履歴の前後で同じIDの24時間と48時間を表示",len(page.locator(f'.data-row[data-node-id="{normal["id"]}"]').all()) == 2)
                page.locator("#changes .change-button").first.click()
                expect(page.locator("#details h1")).to_have_text(f'COMMIT {revised["graph_revision"]}')
                expect(page.locator("#details .diff del")).to_contain_text("24")
                expect(page.locator("#details .diff ins")).to_contain_text("48")
                page.get_by_role("button",name="保存前の原文",exact=True).first.click()
                expect(page.locator("#details .body-text")).to_contain_text("24時間")
                expect(page.locator("#details > .badge")).to_contain_text("過去版")
                check("CHANGE LOGから同一IDの差分・原文・判断へ辿れる")
                seek(data["meta"]["graph_revision"])
                relation_event = next(e for e in reversed(data["events"]) if e["confirmed"] and all(c["type"] == "relation" for c in e["changes"]))
                page.get_by_role("button",name=f'COMMIT {relation_event["graph_revision"]} /',exact=False).click()
                page.get_by_role("button",name="保存後の関係",exact=True).first.click()
                expect(page.locator("#selected-kind")).to_contain_text("relation")
                check("関係のみのcommitも実版へ辿れる")
                page.evaluate('''() => {const original=window.fetch;window.delayReplay=true;window.fetch=async (...args)=>{const response=await original(...args);if(window.delayReplay&&args[0]==='/api/replay/0')await new Promise(r=>setTimeout(r,1200));return response;};}''')
                page.locator("#replay-first").click()
                seek(1)
                page.wait_for_timeout(1500)
                check("遅れた過去版の応答を採用しない",page.locator("#replay-position").inner_text().startswith("rev 1 /"))
                page.evaluate("window.delayReplay=false")
                page.locator("#replay-first").click()
                expect(page.locator("#replay-position")).to_have_text(f'rev 0 / {data["meta"]["graph_revision"]}')
                check("先頭へ戻ると未来の記録を消す",page.locator(".data-row").count() == 0 and page.locator("#changes .change-button").count() == 0)
                page.route("**/api/replay/1",lambda route:route.fulfill(status=503,json=dict(ok=False,error=dict(message="過去版の取得失敗を検査"))))
                page.locator("#replay-next").click()
                expect(page.locator("#mode")).to_have_text("REPLAY / 停止")
                check("過去版の取得失敗で最後の実記録を保持",page.locator(".data-row").count() == 0 and page.locator("#revision").inner_text().startswith("rev 00000"))
                page.unroute("**/api/replay/1")
                seek(1)
                check("REPLAYの取得復旧後に実記録を表示")
                page.locator("#return-live").click()
                page.evaluate("window.delayLive=false")
                expect(page.locator("#mode")).to_have_text("LIVE",timeout=6000)
                expect(page.locator(".data-row .badge")).to_have_count(0)
                check("LIVE復帰で過去の確定を再演しない")
                page.screenshot(path=str(output / "live.png"))

                if recording:
                    page.get_by_role("link",name="収録映像",exact=True).click()
                    expect(page.locator("#mode")).to_have_text("RECORDED / 収録映像")
                    page.wait_for_function("() => document.getElementById('recording').readyState >= 1")
                    page.locator("#recording").evaluate("v=>{v.muted=true;return v.play();}")
                    page.wait_for_function("() => document.getElementById('recording').currentTime > .2")
                    check("実収録をRECORDEDと明示して再生",page.locator("#recording-info").inner_text().find("claude-opus-5-5") >= 0)
                    page.locator("#recording").evaluate("v=>{v.pause();v.currentTime=Math.min(10,v.duration/2);}")
                    page.wait_for_function("() => document.getElementById('recording').currentTime >= 1")
                    check("録画の停止・シークができる")
                    page.locator("#clips button").nth(1).click()
                    page.wait_for_function("() => document.getElementById('recording').readyState >= 1")
                    expect(page.locator("#recording-info")).to_contain_text("48時間")
                    page.screenshot(path=str(output / "recorded.png"))
                    page.get_by_role("link",name="LIVEへ戻る",exact=True).click()
                    expect(page.locator("#mode")).to_have_text("LIVE")
                    check("録画からLIVEへ復帰")
                check("閲覧・フォーカス・再生でDBを変更しない",sha256(db.read_bytes()).hexdigest() == before)
                check("外部CDN・外部通信が不要",all(url.startswith(base+"/") for url in requests))
                check("JavaScriptの実行エラーなし",not errors)
                context.close(); browser.close(); completed = True
        finally:
            server.shutdown(); thread.join()
            (output / "report.json").write_text(json.dumps(dict(passed=completed and all(c["passed"] for c in checks),checks=checks,page_errors=errors,db_sha256=before),ensure_ascii=False,indent=2)+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source","output"):
        parser.add_argument("--"+name,required=True)
    parser.add_argument("--recording",help="収録済み映像も検査する場合だけ指定")
    args = parser.parse_args()
    run(args.source,args.output,args.recording)
