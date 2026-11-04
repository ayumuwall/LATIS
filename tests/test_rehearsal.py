"""別プロセスのCLI、現物の観測、実テスト、証拠、復元をまとめて通す。"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.test_support import run_unittest

ROOT = Path(__file__).resolve().parent.parent


class RehearsalTests(unittest.TestCase):
    def test_real_tests_do_not_reuse_equal_size_equal_mtime_bytecode(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            module = workspace / "subject.py"
            module.write_text("value = 24\n")
            (workspace / "test_subject.py").write_text("import unittest\nfrom subject import value\nclass SubjectTests(unittest.TestCase):\n    def test_value(self):\n        self.assertEqual(value, 24)\n")
            environment = dict(os.environ)
            environment.pop("PYTHONPYCACHEPREFIX", None)
            environment.pop("PYTHONDONTWRITEBYTECODE", None)
            command = [sys.executable, "-m", "unittest", "-v"]
            initial = subprocess.run(command, cwd=workspace, capture_output=True, env=environment)
            self.assertEqual(initial.returncode, 0, initial.stderr)
            stat = module.stat()
            module.write_text("value = 48\n")
            os.utime(module, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            cached = subprocess.run(command, cwd=workspace, capture_output=True, env=environment)
            self.assertEqual(cached.returncode, 0, cached.stderr)
            fresh = run_unittest(workspace)
            self.assertEqual(fresh.returncode, 1, fresh.stderr)
            self.assertIn(b"48 != 24", fresh.stderr)
            self.assertEqual(module.read_text(), "value = 48\n")

    def test_real_cli_exhibition_scenario(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo"
            result = subprocess.run([sys.executable, "scripts/rehearse.py", "--output", str(output)], cwd=ROOT, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode() + result.stdout.decode())
            summary = json.loads((output / "summary.json").read_text())
            self.assertTrue(summary["real_tests_passed"])
            self.assertTrue(summary["old_evidence_reconfirmation_rejected"])
            self.assertTrue(summary["backup_restore_verified"])
            self.assertTrue(summary["fresh_cli_reuse_verified"])
            self.assertFalse(summary["independent_llm_session_verified"])
            self.assertIn("Ran 3 tests", (output / "check-updated.log").read_text())
