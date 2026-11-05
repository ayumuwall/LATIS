"""ClaudeのBashと子プロセスに適用する、macOSの隔離設定。"""

from functools import lru_cache
import os
from pathlib import Path
import shutil
import subprocess
import sys


@lru_cache(maxsize=1)
def runtime_read_paths():
    """Pythonと共有ライブラリの所在を列挙し、ホーム全体を開けない。"""
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        raise RuntimeError("このLLM試験の隔離はmacOS専用です。隔離なしでは起動しません。")
    prefix = Path(sys.base_prefix).resolve()
    pending = [Path(sys.executable), *(prefix / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/lib-dynload").glob("*.so")]
    paths = {str(prefix), "/System/Library", "/usr/lib", "/usr/bin", "/bin", "/dev/null", "/dev/zero", "/dev/random", "/dev/urandom", "/dev/fd"}
    visited = set()
    while pending:
        binary = pending.pop()
        resolved = binary.resolve(strict=True)
        if resolved in visited:
            continue
        visited.add(resolved)
        result = subprocess.run(["/usr/bin/otool", "-L", str(binary)], capture_output=True, text=True, check=True, timeout=10)
        for line in result.stdout.splitlines()[1:]:
            dependency = line.strip().split(" (", 1)[0]
            if dependency.startswith("/") and not dependency.startswith(("/System/", "/usr/lib/")):
                path = Path(dependency)
                paths.update((str(path.parent), str(path.resolve(strict=True).parent)))
                # dyldは途中のシンボリックリンク自体も読む。実体のlibだけでは足りない。
                paths.update(str(parent) for parent in path.parents if parent.is_symlink())
                pending.append(path)
            elif dependency.startswith("@"):
                raise RuntimeError(f"共有ライブラリの相対参照を解決できません。隔離を緩めず中止します: {dependency}")
    return sorted(paths)


def settings_for(directory, repository, *, runtime=None):
    """専用コピー・実装の読取と、コピー・監査ファイルの書込だけを追加する。"""
    original_directory = Path(directory).absolute()
    directory, repository = original_directory.resolve(), Path(repository).resolve()
    audit = [directory / name for name in ("calls.jsonl", "helpers.jsonl", "injected.json", "lost-response.json")]
    scratch = [str(Path(runtime).resolve())] if runtime is not None else []
    return dict(
        sandbox=dict(
            enabled=True, failIfUnavailable=True, allowUnsandboxedCommands=False,
            autoAllowBashIfSandboxed=False, excludedCommands=[],
            filesystem=dict(
                denyRead=["/"],
                allowRead=sorted({str(directory / "workspace"), str(directory / "tool"), str(directory / "fixture.json"),
                                  *(str(path) for path in audit), str(repository / "docs/v0.3.0"), *runtime_read_paths(), *scratch}),
                allowWrite=[*(str(path) for path in audit), *scratch],
                denyWrite=[str(repository), str(directory / "tool")],
            ),
            network=dict(allowedDomains=[], allowAllUnixSockets=False, allowLocalBinding=False),
        ),
        permissions=dict(deny=[f"Edit(/{repository}/**)"]),
    )


def launch_environment(*, runtime=None):
    """既存ログインはClaude本体に任せ、任意の秘密環境変数を子へ渡さない。"""
    names = {"HOME", "USER", "LOGNAME", "PATH", "SHELL", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE", "TERM"}
    environment = {key: value for key, value in os.environ.items() if key in names}
    # Homebrewのsitecustomizeがsys.executableを許可外の中継パスへ戻さないよう、
    # 継承した値ではなく実行中のPythonの実体を固定する。
    environment.update(FORCE_COLOR="1", PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1",
                       PYTHONEXECUTABLE=str(Path(sys.executable).resolve()))
    if runtime is not None:
        environment.update(CLAUDE_CODE_TMPDIR=str(Path(runtime).resolve()), TMPDIR=str(Path(runtime).resolve()))
    return environment


def claude_executable():
    path = shutil.which("claude")
    if not path:
        raise RuntimeError("Claude CLIが見つかりません。")
    return path
