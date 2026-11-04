"""別プロセスのCLI、現物の観測、実テスト、証拠、復元をまとめて通す。"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class RehearsalTests(unittest.TestCase):
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
