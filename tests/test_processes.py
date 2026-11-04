"""実プロセスの競合・強制終了で、部分更新と途中公開を検査する。"""

import json
import os
from pathlib import Path
import select
import subprocess
import sys
import unittest

from latis import storage
from tests.support import ContractCase, ROOT, node


@unittest.skipUnless(os.name == "posix", "子プロセスのパイプ待機と強制終了はPOSIX環境で検査する。")
class ProcessTests(ContractCase):
    def start(self, command):
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ROOT, text=True)
        def cleanup():
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)
        self.addCleanup(cleanup)
        return process

    def worker(self, mode, operation, request):
        process = self.start([sys.executable, "-m", "tests.process_worker", mode, str(self.engine.path), operation])
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        ready, _, _ = select.select([process.stdout], [], [], 10)
        self.assertTrue(ready, "待機位置へ到達しませんでした。")
        line = process.stdout.readline()
        self.assertTrue(line, process.stderr.read() if process.poll() is not None else "子プロセスの出力がありません。")
        record = json.loads(line)
        self.assertTrue(record.get("paused"), record)
        return process, record

    def finish(self, process):
        out, err = process.communicate(timeout=15)
        self.assertFalse(err, err)
        return process.returncode, json.loads(out)

    def test_readers_see_previous_commit_and_killed_writer_consumes_no_keys(self):
        before = self.snapshot()
        def request(ref, key):
            return dict(change_set=dict(operations=[node(ref=ref, kind="question", lifecycle="draft")]),
                        record=dict(actor="test:process", reason="途中障害の検査"), idempotency_key=key)
        interrupted, busy = request("interrupted", "interrupted"), request("busy", "busy")
        process, _ = self.worker("commit", "save-draft", interrupted)
        response = self.cli("meta", {})
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertEqual(json.loads(response.stdout)["meta"], dict(api_version="v1", **before["meta"]))
        response = self.cli("search", dict(kinds=["question"], lifecycles=["draft"]))
        self.assertEqual(json.loads(response.stdout)["data"]["items"], [])
        response = self.cli("save-draft", busy)
        self.assertEqual(response.returncode, 1, response.stderr)
        self.assertEqual(json.loads(response.stdout)["errors"][0]["code"], "BUSY")
        process.kill()
        process.communicate(timeout=10)
        self.assertEqual(self.snapshot(), before)
        saved = []
        for value in (interrupted, busy):
            response = self.cli("save-draft", value)
            self.assertEqual(response.returncode, 0, response.stderr)
            saved.append(json.loads(response.stdout))
        for value, original in zip((interrupted, busy), saved):
            self.assertEqual(json.loads(self.cli("save-draft", value).stdout), original)
        after = self.snapshot()
        storage.validate_snapshot(after)
        self.assertEqual(after["meta"]["graph_revision"], 2)
        self.assertEqual({item["idempotency_key"] for item in after["idempotency_records"]}, {"interrupted", "busy"})

    def test_different_keys_on_same_revision_have_one_winner(self):
        value = self.create()
        requests = [self.application(self.consult(self.update(value, body=body)), key=key)
                    for body, key in (("48時間", "first"), ("72時間", "second"))]
        processes = [self.start([sys.executable, "-m", "latis", "--db", str(self.engine.path), "apply"]) for _ in requests]
        for process, request in zip(processes, requests):
            process.stdin.write(json.dumps(request))
            process.stdin.close()
            process.stdin = None
        results = [self.finish(process) for process in processes]
        self.assertEqual(sorted(code for code, _ in results), [0, 1])
        loser = next(response for code, response in results if code == 1)
        self.assertEqual(loser["errors"][0]["code"], "PRECONDITION_CHANGED")
        self.assertEqual(len(self.ok("history", dict(target_type="node", target_id=value["id"]))["revisions"]), 2)
        after = self.snapshot()
        storage.validate_snapshot(after)
        self.assertEqual(after["meta"]["graph_revision"], 2)
        self.assertEqual(len(after["idempotency_records"]), 2)

    def test_two_prepared_exports_publish_one_complete_result(self):
        self.create()
        before = self.snapshot()
        for format_, mode in (("json", "file"), ("markdown", "directory")):
            with self.subTest(format=format_):
                destination = self.directory / ("export-" + format_)
                workers = [self.worker(mode, "export", dict(format=format_, destination=str(destination)))[0] for _ in range(2)]
                self.assertFalse(destination.exists())
                for process in workers:
                    process.stdin.write("continue\n")
                    process.stdin.flush()
                results = [self.finish(process) for process in workers]
                self.assertEqual(sorted(code for code, _ in results), [0, 1])
                self.assertEqual(next(response for code, response in results if code == 1)["errors"][0]["code"], "DESTINATION_EXISTS")
                if format_ == "json":
                    self.assertEqual(json.loads(destination.read_text()), before)
                else:
                    self.assertIn(before["meta"]["snapshot_id"], (destination / "index.md").read_text())
                    self.assertEqual(len(list(destination.glob("agreement/*.md"))), 1)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(list(self.directory.glob(".latis-*")), [])

    def test_kill_before_projection_publish_leaves_no_partial_destination(self):
        self.create()
        before = self.snapshot()
        destination = self.directory / "view"
        request = dict(format="markdown", destination=str(destination))
        process, paused = self.worker("directory", "export", request)
        staging = Path(paused["source"])
        self.assertTrue((staging / "index.md").is_file())
        self.assertFalse(destination.exists())
        process.kill()
        process.communicate(timeout=10)
        self.assertFalse(destination.exists())
        self.assertEqual(self.snapshot(), before)
        # SIGKILLではfinallyが動かない。未公開の隠し一時領域は完成品と扱わない。
        self.assertTrue(staging.is_dir())
        response = self.cli("export", request)
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertIn(before["meta"]["snapshot_id"], (destination / "index.md").read_text())
