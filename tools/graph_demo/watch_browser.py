#!/usr/bin/env python3
"""実LLMが更新する専用DBをPlaywrightで表示・収録する。書込みはしない。"""

import argparse
import json
import sys
import threading
import time
from hashlib import sha256
from pathlib import Path
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.graph_demo.server import make_handler


def watch(db, output, stop_file, ready_file):
    from playwright.sync_api import sync_playwright, expect
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    sources = {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest()
               for p in sorted((ROOT / "tools/graph_demo").rglob("*")) if p.suffix in (".py", ".js", ".css", ".html", ".svg")}
    errors, frames = [], []
    class Handler(make_handler(Path(db).resolve())):
        def log_request(self, code="-", size="-"):
            if code != 200:
                super().log_request(code, size)
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(viewport=dict(width=1920, height=1080), locale="ja-JP",
                    record_video_dir=str(output / "video"), record_video_size=dict(width=1920, height=1080))
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}", wait_until="domcontentloaded")
                expect(page.locator("#mode")).to_have_text("LIVE")
                page.evaluate('''() => {const label=document.createElement('div');label.className='recording-label';label.textContent='RECORDED / 収録映像';document.body.append(label);}''')
                video = page.video
                Path(ready_file).write_text(json.dumps(dict(url=page.url, browser=browser.version)))
                start, previous = time.monotonic(), None
                while not Path(stop_file).exists():
                    if time.monotonic() - start > 950:
                        raise TimeoutError("収録の停止通知がありません。")
                    revision = page.locator("#revision").inner_text()
                    if revision != previous:
                        frame = dict(revision=revision, mode=page.locator("#mode").inner_text(),
                                     title=page.locator("#details h1").inner_text() if page.locator("#details h1").count() else None,
                                     body=page.locator("#details .body-text").inner_text() if page.locator("#details .body-text").count() else None,
                                     observed_ns=time.time_ns())
                        frames.append(frame)
                        page.screenshot(path=str(output / f"frame-{len(frames):02d}.png"))
                        previous = revision
                    page.wait_for_timeout(200)
                page.screenshot(path=str(output / "final.png"))
                context.close()
                video.save_as(str(output / "demo.webm"))
                browser.close()
            report = dict(passed=not errors and bool(frames), frames=frames, page_errors=errors, sources=sources,
                          video=str(output / "demo.webm"), note="実CLI更新を実ブラウザーで収録。収録映像と明示して再生する。")
            (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            if not report["passed"]:
                raise RuntimeError("ブラウザー収録の検査が不合格です。")
        finally:
            server.shutdown()
            thread.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("db", "output", "stop-file", "ready-file"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    watch(args.db, args.output, args.stop_file, args.ready_file)
