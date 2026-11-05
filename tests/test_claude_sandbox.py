"""LLMを呼ばずに、隔離設定・秘密環境変数の除去・検査器の偽成功を検査する。"""

import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts.check_claude_sandbox import prepare_probe
from scripts.claude_sandbox import launch_environment, runtime_read_paths, settings_for
from scripts.llm_acceptance import MODEL, ROOT, run_claude


class ClaudeSandboxTests(unittest.TestCase):
    def test_policy_requires_sandbox_and_protects_originals(self):
        with patch("scripts.claude_sandbox.runtime_read_paths", return_value=["/runtime"]):
            settings = settings_for("/private/tmp/example/case", ROOT)
        sandbox = settings["sandbox"]
        self.assertTrue(sandbox["enabled"])
        self.assertTrue(sandbox["failIfUnavailable"])
        self.assertFalse(sandbox["allowUnsandboxedCommands"])
        self.assertFalse(sandbox["autoAllowBashIfSandboxed"])
        self.assertEqual(sandbox["excludedCommands"], [])
        self.assertEqual(sandbox["filesystem"]["denyRead"], ["/"])
        self.assertEqual(sandbox["filesystem"]["denyWrite"], [str(ROOT), "/private/tmp/example/case/tool"])
        self.assertEqual({Path(path).name for path in sandbox["filesystem"]["allowWrite"]},
                         {"calls.jsonl", "helpers.jsonl", "injected.json", "lost-response.json"})
        self.assertNotIn(str(ROOT), sandbox["filesystem"]["allowRead"])
        self.assertEqual(sandbox["network"], dict(allowedDomains=[], allowAllUnixSockets=False, allowLocalBinding=False))

    def test_environment_does_not_pass_tokens_or_shell_injection_variables(self):
        with patch.dict(os.environ, {"HOME": "/example", "PATH": "/bin", "ANTHROPIC_API_KEY": "dummy",
                                    "AWS_SECRET_ACCESS_KEY": "dummy", "BASH_ENV": "/injection", "PYTHONPATH": "/injection",
                                    "LATIS_SANDBOX_SECRET_CANARY": "dummy"}, clear=True):
            environment = launch_environment()
        self.assertEqual(environment["HOME"], "/example")
        self.assertEqual(environment["PATH"], "/bin")
        self.assertEqual(environment["FORCE_COLOR"], "1")
        self.assertFalse({"ANTHROPIC_API_KEY", "AWS_SECRET_ACCESS_KEY", "BASH_ENV", "PYTHONPATH", "LATIS_SANDBOX_SECRET_CANARY"} & environment.keys())

    def test_unsupported_platform_fails_instead_of_running_without_isolation(self):
        runtime_read_paths.cache_clear()
        self.addCleanup(runtime_read_paths.cache_clear)
        with patch("scripts.claude_sandbox.sys.platform", "unsupported"):
            with self.assertRaisesRegex(RuntimeError, "隔離なしでは起動しません"):
                runtime_read_paths()

    def test_relative_shared_library_reference_does_not_widen_policy(self):
        runtime_read_paths.cache_clear()
        self.addCleanup(runtime_read_paths.cache_clear)
        response = subprocess.CompletedProcess([], 0, "binary:\n\t@rpath/unknown.dylib (compatibility version 1.0.0)\n", "")
        with patch("scripts.claude_sandbox.sys.platform", "darwin"), patch("scripts.claude_sandbox.Path.is_file", return_value=True), patch("scripts.claude_sandbox.subprocess.run", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "隔離を緩めず中止"):
                runtime_read_paths()

    def test_launcher_actually_supplies_policy_and_restricted_file_tools(self):
        temporary_directory = tempfile.TemporaryDirectory
        with temporary_directory() as temporary:
            directory = Path(temporary)
            (directory / "workspace").mkdir()
            process = Mock()
            process.stdin = io.StringIO()
            process.stdout = io.StringIO(json.dumps(dict(type="system", subtype="init", model=MODEL)) + "\n" +
                                          json.dumps(dict(type="result", subtype="success", is_error=False)) + "\n")
            process.wait.return_value = 0
            process.poll.return_value = 0
            # 起動は模擬する。macOS以外でも実在する親に作り、実際の隔離成功とは数えない。
            with patch("scripts.llm_acceptance.tempfile.TemporaryDirectory", side_effect=lambda **options: temporary_directory(prefix=options["prefix"], dir=temporary)) as scratch_directory, patch("scripts.llm_acceptance.settings_for", return_value={"sandbox": {"enabled": True}}), patch("scripts.llm_acceptance.claude_executable", return_value="/example/claude"), patch("scripts.llm_acceptance.subprocess.Popen", return_value=process) as launch:
                run_claude(directory, prompt="架空の試験")
            command = launch.call_args.args[0]
            self.assertIn("--safe-mode", command)
            self.assertIn("--restricted", command)
            self.assertEqual(json.loads(command[command.index("--settings") + 1]), {"sandbox": {"enabled": True}})
            self.assertEqual(command[command.index("--permission-mode") + 1], "dontAsk")
            self.assertNotIn("--dangerously-skip-permissions", command)
            self.assertEqual(command[command.index("--model") + 1], MODEL)
            self.assertEqual(command[command.index("--effort") + 1], "high")
            environment = launch.call_args.kwargs["env"]
            scratch = environment["CLAUDE_CODE_TMPDIR"]
            self.assertEqual(scratch_directory.call_args.kwargs["dir"], "/private/tmp")
            self.assertEqual(Path(scratch).parent, directory.resolve())
            self.assertEqual(environment["TMPDIR"], scratch)
            self.assertFalse(Path(scratch).exists())

    def test_probe_does_not_report_unsandboxed_execution_as_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory, canary, tool = prepare_probe(Path(temporary) / "probe")
            result = subprocess.run([str(tool)], cwd=directory / "workspace", capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            checks = json.loads((directory / "workspace/probe-result.json").read_text())
            self.assertTrue(checks["inside_read_write"])
            self.assertFalse(checks["outside_read"])
            self.assertFalse(checks["outside_write"])
            self.assertEqual(canary.read_text().strip(), "modified")
