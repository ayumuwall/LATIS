"""展示向け読取が正本を変更せず、不正な履歴を拒否することを確認する。"""

import sqlite3
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path

from latis import storage
from latis.model import Error
from tools.graph_demo.projection import project, read_snapshot, display_numbers, DISPLAY_PREFIXES
from tests.support import ContractCase, ROOT, node, relation


class GraphSnapshotTests(unittest.TestCase):
    def test_read_preserves_snapshot_and_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.sqlite"
            snapshot = storage.initial("検証用プロジェクト")
            storage.create_file(path, snapshot)
            before = path.read_bytes()
            self.assertEqual(read_snapshot(path), snapshot)
            self.assertEqual(path.read_bytes(), before)

    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.sqlite"
            with self.assertRaises(Error):
                read_snapshot(path)
            self.assertFalse(path.exists())

    def test_unsupported_schema_and_rules_are_distinct_from_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.sqlite"
            snapshot = storage.initial("検証用プロジェクト")
            storage.create_file(path, snapshot)
            with sqlite3.connect(path) as conn:
                conn.execute("PRAGMA user_version=99")
            with self.assertRaises(Error) as error:
                read_snapshot(path)
            self.assertEqual(error.exception.code, "UNSUPPORTED_FORMAT")
            with sqlite3.connect(path) as conn:
                conn.execute("PRAGMA user_version=3")
                snapshot["meta"]["rules_version"] = "unsupported"
                conn.execute("UPDATE metadata SET data=? WHERE id=1", (storage.canonical(snapshot["meta"]),))
            with self.assertRaises(Error) as error:
                read_snapshot(path)
            self.assertEqual(error.exception.code, "UNSUPPORTED_FORMAT")


class GraphProjectionContractTests(ContractCase):
    def test_display_log_resolves_nodes_relations_and_versions_without_changing_raw_events(self):
        from tools.graph_demo.labels import DisplayLog
        import io
        from contextlib import redirect_stdout
        first = self.create(title="最初の合意")
        target = self.create(title="別の合意")
        edge = self.apply(relation("edge",first["id"],target["id"],kind="depends_on"))
        view = project(self.engine.path)
        edge_id = next(iter(edge["created_refs"].values()))["id"]
        rendered = []
        log = DisplayLog(self.engine.path, rendered.append)
        raw = dict(type="assistant", message=dict(content=[dict(type="text", text=f'{first["id"]} {first["revision_id"]} {edge_id} x{first["id"]}x')]))
        original = json.loads(json.dumps(raw))
        before = read_snapshot(self.engine.path)
        log(raw)
        text = rendered[-1]["message"]["content"][0]["text"]
        self.assertIn('A-1「最初の合意」',text)
        self.assertIn('〈第1版〉',text)
        self.assertIn('A-1 → depends_on → A-2〈関係〉',text)
        self.assertIn(f'x{first["id"]}x',text)
        self.assertEqual(raw,original)
        self.assertEqual(read_snapshot(self.engine.path),before)
        self.apply(self.update(self.current(first["id"]),body="改訂後の本文"))
        second = self.current(first["id"])
        log(dict(type="assistant",message=dict(content=[dict(type="text",text=second["revision_id"])])))
        self.assertIn('A-1「最初の合意」〈第2版〉',rendered[-1]["message"]["content"][0]["text"])
        self.save(relation("duplicate",first["id"],target["id"],kind="depends_on",confirmation="candidate"))
        log(dict(type="assistant",message=dict(content=[dict(type="text",text=edge_id)])))
        self.assertIn(f'（内部ID: {edge_id}）',rendered[-1]["message"]["content"][0]["text"])
        with patch("tools.graph_demo.labels.project",side_effect=OSError("読取不可")), redirect_stdout(io.StringIO()) as output:
            log(raw)
        self.assertEqual(rendered[-1],raw)
        self.assertIn("オブジェクトID未確認",output.getvalue())
        # DB差替えや巻戻しのときも、以前の対応を使い続けない。
        changed = dict(view,meta=dict(view["meta"],database_id="different-db"))
        with patch("tools.graph_demo.labels.project",return_value=changed), redirect_stdout(io.StringIO()):
            log(raw)
        self.assertEqual(rendered[-1],raw)

    def test_llm_display_index_tracks_real_updates_without_changing_database(self):
        import time
        from tools.graph_demo.labels import updating_index
        first=self.create(title="最初の合意")
        target=self.directory / "latis-display-numbers.json"
        with updating_index(self.engine.path,target):
            data=json.loads(target.read_text())
            self.assertEqual(data["items"][0]["number"],"A-1")
            self.assertEqual(data["items"][0]["id"],first["id"])
            second=self.create(title="追加した合意")
            before=read_snapshot(self.engine.path)
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                data=json.loads(target.read_text())
                if data["meta"] == before["meta"]:break
                time.sleep(.02)
            self.assertEqual(data["meta"],before["meta"])
            self.assertEqual(next(n["number"] for n in data["items"] if n["id"] == second["id"]),"A-2")
            self.assertTrue(all("body" not in n for n in data["items"]))
        self.assertEqual(read_snapshot(self.engine.path),before)

    def test_display_numbers_are_per_kind_and_stable_across_revisions_and_restore(self):
        created = self.save(*(node(ref=kind,kind=kind,lifecycle="draft",title=kind) for kind in DISPLAY_PREFIXES))
        ids = {kind: ref["id"] for kind,ref in created["created_refs"].items()}
        before = project(self.engine.path)
        self.assertEqual(before["display_numbers"], {ids[kind]: prefix + "-1" for kind,prefix in DISPLAY_PREFIXES.items()})
        original_revision = before["meta"]["graph_revision"]
        self.apply(self.update(self.current(ids["agreement"]),body="本文の改訂で番号を変えてはならない。",lifecycle="accepted"))
        self.apply(self.update(self.current(ids["agreement"]),lifecycle="retired"))
        second = self.create(title="新しい合意")
        after = project(self.engine.path)
        self.assertEqual(after["display_numbers"][second["id"]],"A-2")
        self.assertTrue(all(after["display_numbers"][id_] == number for id_,number in before["display_numbers"].items()))
        self.assertEqual(project(self.engine.path,original_revision)["display_numbers"],before["display_numbers"])
        snapshot = self.snapshot()
        snapshot["revisions"].reverse()
        self.assertEqual(display_numbers(snapshot),after["display_numbers"])
        for format_ in ("sqlite","json"):
            export = self.directory / ("display." + format_)
            self.ok("backup" if format_ == "sqlite" else "export",
                    dict(destination=str(export)) if format_ == "sqlite" else dict(format=format_,destination=str(export)))
            restored = self.directory / ("restored-" + format_ + ".sqlite")
            from latis import Engine
            self.ok("restore",dict(format=format_,source=str(export)),engine=Engine(restored))
            self.assertEqual(project(restored)["display_numbers"],after["display_numbers"])

    def test_same_commit_numbers_use_id_order_and_are_read_only(self):
        result = self.apply(node(ref="a"),node(ref="b"),node(ref="c",kind="scope"))
        original = self.engine.path.read_bytes()
        view = project(self.engine.path)
        agreements = sorted(ref["id"] for name,ref in result["created_refs"].items() if name in ("a","b"))
        self.assertEqual([view["display_numbers"][id_] for id_ in agreements],["A-1","A-2"])
        self.assertEqual(view["display_numbers"][result["created_refs"]["c"]["id"]],"S-1")
        self.assertEqual(self.engine.path.read_bytes(),original)

    def test_replay_matches_original_snapshot_and_excludes_future_history(self):
        value = self.create()
        before = project(self.engine.path)
        self.apply(self.update(value, body="通常ログは48時間保持しなければならない。"))
        original = self.engine.path.read_bytes()
        historical = project(self.engine.path, before["meta"]["graph_revision"])
        self.assertEqual(historical, before)
        self.assertEqual(project(self.engine.path, 0)["nodes"], [])
        self.assertEqual(self.engine.path.read_bytes(), original)
        with self.assertRaises(Error) as error:
            project(self.engine.path, 999)
        self.assertEqual(error.exception.code, "BASIS_UNAVAILABLE")

    def test_real_changes_match_export_and_keep_history(self):
        initial = self.create()
        self.apply(self.update(initial, body="通常ログは48時間保持する。"))
        exported = self.snapshot()
        view = project(self.engine.path)
        for name in ("meta", "nodes", "relations", "revisions", "provenance", "commits", "idempotency_records"):
            self.assertEqual(view[name], exported[name])
        self.assertEqual(view["selection"]["nodes"], len(exported["nodes"]))
        self.assertEqual(view["selection"]["filter"], "all")

    def test_inconsistent_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.sqlite"
            snapshot = storage.initial("検証用プロジェクト")
            storage.create_file(path, snapshot)
            snapshot["meta"]["snapshot_id"] = "different"
            with sqlite3.connect(path) as conn:
                conn.execute("UPDATE metadata SET data=?", (storage.canonical(snapshot["meta"]),))
            with self.assertRaises(Error):
                read_snapshot(path)


    def test_writer_commits_while_reader_keeps_one_snapshot(self):
        value = self.create()
        with sqlite3.connect(self.engine.path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
        before = self.snapshot()
        application = self.application(self.consult(self.update(value, body="48時間")))
        original = storage.read
        result = []
        errors = []
        reader = threading.current_thread()

        def write():
            try:
                result.append(self.engine.execute("apply", application))
            except Exception as exc:
                errors.append(exc)

        def concurrent_read(conn):
            if threading.current_thread() is reader:
                # 明示トランザクションでメタデータを読んだ後に別接続をcommitする。
                conn.execute("SELECT data FROM metadata").fetchone()
                writer = threading.Thread(target=write)
                writer.start()
                writer.join(timeout=10)
                self.assertFalse(writer.is_alive())
            return original(conn)

        with patch("tools.graph_demo.projection.storage.read", concurrent_read):
            captured = read_snapshot(self.engine.path)
        self.assertFalse(errors, errors)
        self.assertTrue(result[0]["ok"], result)
        self.assertEqual(captured, before)
        self.assertEqual(read_snapshot(self.engine.path)["meta"]["graph_revision"], before["meta"]["graph_revision"] + 1)

    def test_events_distinguish_draft_apply_retry_and_relation_only_changes(self):
        value = self.create()
        self.save(node(kind="question", lifecycle="draft"))
        request = self.application(self.consult(self.update(value, body="通常ログは48時間保持する。")))
        first = self.ok("apply", request)
        self.assertEqual(self.ok("apply", request), first)
        scope = self.create(kind="scope", title="通常ログ")
        self.apply(relation("scope", value["id"], scope["id"], "scoped_to"))
        view = project(self.engine.path)
        self.assertEqual([e["operation"] for e in view["events"]], ["apply", "save-draft", "apply", "apply", "apply"])
        self.assertEqual([e["confirmed"] for e in view["events"]], [True, False, True, True, True])
        revised = view["events"][2]["changes"][0]
        self.assertEqual(revised["before"]["body"], value["body"])
        self.assertEqual(revised["after"]["body"], "通常ログは48時間保持する。")
        self.assertEqual(view["events"][-1]["changes"][0]["type"], "relation")
        self.assertEqual(view["scope_ids"][value["id"]], [scope["id"]])

    @unittest.skipUnless(shutil.which("node"), "展示UIのJavaScript検査にNodeが必要です。")
    def test_browser_model_with_real_database_history(self):
        seeded = self.seed()
        before = project(self.engine.path)
        self.save(node(ref="draft", kind="question", lifecycle="draft"))
        draft = project(self.engine.path)
        self.apply(self.update(seeded["normal_retention"], body="通常ログは48時間保持する。"))
        after = project(self.engine.path)
        result = subprocess.run(["node", str(ROOT / "tests/graph_model.test.cjs")],
                                input=json.dumps(dict(before=before, draft=draft, after=after)).encode(), capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, (result.stdout.decode(), result.stderr.decode()))

class GraphHttpTests(ContractCase):
    def test_scope_markdown_is_one_numbered_document_and_pins_the_displayed_snapshot(self):
        import re
        import urllib.request
        import urllib.error
        from urllib.parse import quote
        from http.server import ThreadingHTTPServer
        from tools.graph_demo.server import make_handler
        values = self.seed()
        root = values["logs_scope"]["id"]
        extra = self.apply(node(ref="child",kind="scope"),node(ref="deep"),node(ref="empty",kind="scope"),
                           relation("contains",root,"$child","contains"),relation("member","$deep","$child","scoped_to"))
        empty = extra["created_refs"]["empty"]["id"]
        original = project(self.engine.path)
        expected = self.directory / "core-markdown"
        self.ok("export",dict(format="markdown",destination=str(expected),scope_ids=[root]))
        self.apply(node(ref="later"),relation("later_member","$later",root,"scoped_to"))
        before = self.engine.path.read_bytes()
        meta = original["meta"]
        with ThreadingHTTPServer(("127.0.0.1",0),make_handler(self.engine.path)) as server:
            thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def url(scope_id, snapshot=meta["snapshot_id"], database=meta["database_id"]):
                components = [database,str(meta["graph_revision"]),snapshot,scope_id]
                return f"http://127.0.0.1:{server.server_port}/api/export/scope/" + "/".join(quote(v,safe="") for v in components)
            try:
                with urllib.request.urlopen(url(root)) as response:
                    self.assertEqual(response.headers["Content-Type"],"text/markdown; charset=utf-8")
                    self.assertEqual(response.headers["Cache-Control"],"no-store")
                    self.assertIn(f'filename="{original["display_numbers"][root]}.md"',response.headers["Content-Disposition"])
                    document=response.read().decode()
                    header=json.loads(re.search(r"<!-- latis-source: (.*?) -->",document).group(1))
                    records=[json.loads(value) for value in re.findall(r"<!-- latis-node: (.*?) -->",document)]
                    self.assertEqual(header["meta"],meta)
                    self.assertEqual(header["scope"]["id"],root)
                    direct={id_ for id_,scopes in original["scope_ids"].items() if root in scopes}
                    self.assertEqual({record["id"] for record in records if record["role"] == "direct"},direct)
                    self.assertNotIn(extra["created_refs"]["deep"]["id"],{r["id"] for r in records})
                    for file in expected.glob("*/node-*.md"):
                        front,body=file.read_text()[4:].split("\n---\n",1)
                        exported_node=json.loads(front)
                        record=next(r for r in records if r["id"] == exported_node["id"])
                        self.assertEqual(record["revision_id"],exported_node["revision_id"])
                        self.assertIn(body,document)
                        self.assertIn(original["display_numbers"][exported_node["id"]],document)
                    self.assertIn("## Purpose",document)
                    self.assertIn("## Requirements",document)
                    for id_ in direct:
                        original_node=next(n for n in original["nodes"] if n["id"] == id_)
                        if original_node["kind"] == "agreement":self.assertIn("### Requirement: " + original["display_numbers"][id_],document)
                    anchors=set(re.findall(r'<a id="([a-z0-9-]+)"></a>',document))
                    self.assertTrue(set(re.findall(r'\]\(#([a-z0-9-]+)\)',document)) <= anchors)
                    self.assertNotIn("#### Scenario:",document)
                with urllib.request.urlopen(url(empty)) as response:
                    document=response.read().decode()
                    self.assertIn("## Requirements",document)
                    self.assertNotIn("### Requirement:",document)
                    self.assertNotIn("<!-- latis-node:",document)
                for endpoint,code in ((url(values["normal_retention"]["id"]),400),(url("missing"),404),
                                      (url(root,snapshot="other"),409),(url(root,database="other"),409),(url(root)+"?path=other",400)):
                    with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(endpoint)
                    self.assertEqual(error.exception.code,code)
            finally:
                server.shutdown();thread.join()
        self.assertEqual(self.engine.path.read_bytes(),before)

    def test_get_is_read_only_and_post_is_rejected(self):
        import json
        import threading
        import urllib.error
        import urllib.request
        from http.server import ThreadingHTTPServer
        from tools.graph_demo.server import make_handler

        self.create()
        before = self.engine.path.read_bytes()
        with ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.engine.path)) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/api/graph"
                with urllib.request.urlopen(url) as response:
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    data = json.load(response)
                self.assertTrue(data["ok"])
                self.assertEqual(data["data"]["selection"]["nodes"], 1)
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(url, data=b"{}", method="POST"))
                self.assertEqual(error.exception.code, 405)
            finally:
                server.shutdown()
                thread.join()
        self.assertEqual(self.engine.path.read_bytes(), before)

    def test_static_files_errors_and_locked_database(self):
        import urllib.request
        import urllib.error
        from http.server import ThreadingHTTPServer
        from tools.graph_demo.server import make_handler
        self.create()
        with ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.engine.path)) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                for route in ("/", "/app.js", "/model.js", "/styles.css", "/health", "/recorded", "/recorded.js", "/api/recording", "/api/replay/0"):
                    with urllib.request.urlopen(base + route) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.headers["Cache-Control"], "no-store")
                        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
                for route, code in (("/api/graph?db=/tmp/other", 400), ("/../projection.py", 404)):
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(base + route)
                    self.assertEqual(error.exception.code, code)
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(base + "/api/replay/999")
                self.assertEqual(error.exception.code, 409)
                with sqlite3.connect(self.engine.path) as lock:
                    lock.execute("BEGIN EXCLUSIVE")
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(base + "/api/graph")
                    self.assertEqual(error.exception.code, 503)
                    self.assertEqual(json.load(error.exception)["error"]["code"], "BUSY")
                self.engine.path.unlink()
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(base + "/api/graph")
                self.assertEqual(error.exception.code, 404)
                self.assertFalse(self.engine.path.exists())
                self.engine.path.write_bytes(b"invalid database")
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(base + "/api/graph")
                self.assertEqual(error.exception.code, 400)
                self.assertEqual(json.load(error.exception)["error"]["code"], "INVALID_DATABASE")
            finally:
                server.shutdown()
                thread.join()

    def test_recording_is_fixed_and_range_requests_do_not_touch_database(self):
        import urllib.request
        import urllib.error
        from hashlib import sha256
        from http.server import ThreadingHTTPServer
        from tools.graph_demo.server import make_handler
        self.create()
        before = self.engine.path.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = b"recorded-video-fixture"
            (root / "clip.webm").write_bytes(payload)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps(dict(mode="RECORDED", clips=[dict(file="clip.webm", sha256=sha256(payload).hexdigest())])))
            with ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.engine.path, manifest)) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    base = f"http://127.0.0.1:{server.server_port}"
                    with urllib.request.urlopen(urllib.request.Request(base + "/media/0.webm", headers={"Range":"bytes=2-6"})) as response:
                        self.assertEqual(response.status, 206)
                        self.assertEqual(response.read(), payload[2:7])
                        self.assertEqual(response.headers["Content-Range"], f"bytes 2-6/{len(payload)}")
                    for route in ("/media/1.webm", "/media/../../clip.webm"):
                        with self.assertRaises(urllib.error.HTTPError) as error:
                            urllib.request.urlopen(base + route)
                        self.assertEqual(error.exception.code, 404)
                finally:
                    server.shutdown()
                    thread.join()
            (root / "clip.webm").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                make_handler(self.engine.path, manifest)
        self.assertEqual(self.engine.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
