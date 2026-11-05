"""展示用の読み取り専用HTTPサーバー。"""

import argparse
import json
import re
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from latis.model import Error
from tools.graph_demo.projection import project
from tools.graph_demo.export import scope_markdown

STATIC = Path(__file__).resolve().parent / "static"
FILES = {"/": ("index.html", "text/html; charset=utf-8"),
         "/app.js": ("app.js", "text/javascript; charset=utf-8"),
         "/model.js": ("model.js", "text/javascript; charset=utf-8"),
         "/favicon.svg": ("favicon.svg", "image/svg+xml"),
         "/recorded": ("recorded.html", "text/html; charset=utf-8"),
         "/recorded.js": ("recorded.js", "text/javascript; charset=utf-8"),
         "/styles.css": ("styles.css", "text/css; charset=utf-8")}


def make_handler(db, recording=None):
    db = Path(db)
    if not db.is_absolute():
        raise ValueError("DBパスは絶対パスで指定してください。")
    manifest, media = None, []
    if recording is not None:
        from hashlib import sha256
        recording = Path(recording)
        if not recording.is_absolute():
            raise ValueError("録画manifestは絶対パスで指定してください。")
        manifest = json.loads(recording.read_text())
        if manifest.get("mode") != "RECORDED" or not manifest.get("clips"):
            raise ValueError("録画manifestの形式が不正です。")
        for clip in manifest["clips"]:
            name = clip["file"]
            if Path(name).name != name or not name.endswith(".webm"):
                raise ValueError("録画ファイル名が不正です。")
            path = recording.parent / name
            if sha256(path.read_bytes()).hexdigest() != clip["sha256"]:
                raise ValueError("録画ファイルのハッシュが一致しません。")
            media.append(path)

    class Handler(BaseHTTPRequestHandler):
        def response_headers(self, code, length, content_type, extra=()):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.send_header("Content-Length", str(length))
            for key, value in extra:
                self.send_header(key, value)
            self.end_headers()

        def respond(self, code, payload, content_type, extra=()):
            self.response_headers(code, len(payload), content_type, extra)
            self.wfile.write(payload)

        def video(self, index):
            if index >= len(media):
                self.send_error(404)
                return
            path = media[index]
            size = path.stat().st_size
            start, end, code = 0, size - 1, 200
            extra = [("Accept-Ranges", "bytes")]
            requested = self.headers.get("Range")
            if requested:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
                if not match or not any(match.groups()):
                    self.send_error(416)
                    return
                a, b = match.groups()
                start, end = (int(a), min(int(b), end) if b else end) if a else (max(0, size - int(b)), end)
                if start > end or start >= size:
                    self.send_error(416)
                    return
                code = 206
                extra.append(("Content-Range", f"bytes {start}-{end}/{size}"))
            self.response_headers(code, end - start + 1, "video/webm", extra)
            with path.open("rb") as stream:
                stream.seek(start)
                remaining = end - start + 1
                try:
                    while remaining:
                        chunk = stream.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        def do_GET(self):
            parsed = urlsplit(self.path)
            path = parsed.path
            if parsed.query:
                self.respond(400, b'{"ok":false,"error":{"code":"INVALID_REQUEST","message":"Query parameters are not supported"}}', "application/json")
                return
            export = re.fullmatch(r"/api/export/scope/([^/]+)/(0|[1-9][0-9]*)/([^/]+)/([^/]+)",path)
            if export:
                database_id, revision, snapshot_id, scope_id = export.groups()
                try:
                    payload, name = scope_markdown(db,unquote(database_id),int(revision),unquote(snapshot_id),unquote(scope_id))
                    self.respond(200,payload,"text/markdown; charset=utf-8",[("Content-Disposition",f'attachment; filename="{name}"')])
                except Error as exc:
                    self.respond(exc.status,json.dumps(dict(ok=False,error=dict(code=exc.code,message=str(exc))),ensure_ascii=False).encode(),"application/json; charset=utf-8")
                except (sqlite3.Error,OSError):
                    self.respond(503,json.dumps(dict(ok=False,error=dict(code="BUSY",message="書き出せません。DBへの接続を確認してください。")),ensure_ascii=False).encode(),"application/json; charset=utf-8")
                return
            if path == "/api/recording":
                self.respond(200, json.dumps(dict(ok=True, data=manifest), ensure_ascii=False).encode(), "application/json; charset=utf-8")
            elif re.fullmatch(r"/media/\d+\.webm", path):
                self.video(int(path[7:-5]))
            elif path in ("/health", "/api/graph") or re.fullmatch(r"/api/replay/\d+", path):
                try:
                    data = project(db, int(path.rsplit("/", 1)[1])) if path.startswith("/api/replay/") else project(db)
                    result = {"ok": True, "data": {"meta": data["meta"]} if path == "/health" else data}
                    code = 200
                except Error as exc:
                    result = {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
                    code = exc.status
                except (sqlite3.Error, OSError):
                    result = {"ok": False, "error": {"code": "BUSY", "message": "DBへ接続できません。再接続を待っています。"}}
                    code = 503
                self.respond(code, json.dumps(result, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            elif path in FILES:
                name, content_type = FILES[path]
                try:
                    payload = (STATIC / name).read_bytes()
                except OSError:
                    self.send_error(404)
                    return
                self.respond(200, payload, content_type)
            else:
                self.send_error(404)

        def do_POST(self):
            self.respond(405, b'{"ok":false,"error":{"code":"READ_ONLY"}}', "application/json")

        do_PUT = do_POST
        do_PATCH = do_POST
        do_DELETE = do_POST

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="既存のLATIS DBの絶対パス")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", choices=("127.0.0.1",), default="127.0.0.1")
    parser.add_argument("--recording", help="実収録のmanifest.jsonの絶対パス")
    args = parser.parse_args()
    handler = make_handler(args.db, args.recording)
    with ThreadingHTTPServer((args.host, args.port), handler) as server:
        print(f"展示ビュー: http://127.0.0.1:{server.server_port} / DB: {args.db}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
