#!/usr/bin/env python3
"""ソースの専用コピーからwheelを作り、新しい環境で配布物を検査する。"""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.check_distribution import sha, verify


def run(output):
    output = Path(output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    source = output / "source"
    source.mkdir()
    for name in ("latis", "docs/v0.3.0"):
        shutil.copytree(ROOT / name, source / name, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
    for name in ("pyproject.toml", "README.md", "README.ja.md", "LICENSE"):
        if (ROOT / name).is_file():
            shutil.copyfile(ROOT / name, source / name)
    manifest = {str(path.relative_to(source)): sha(path) for path in sorted(source.rglob("*")) if path.is_file()}
    (output / "build-source.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print("一時的なビルド環境でwheelを構築します。", flush=True)
    build_python = output / "build-env/bin/python"
    subprocess.run([sys.executable, "-m", "venv", str(build_python.parent.parent)], check=True)
    subprocess.run([str(build_python), "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(output / "wheels"), str(source)], check=True)
    print("新しい実行環境へローカルwheelだけを導入します。", flush=True)
    runtime_python = output / "runtime-env/bin/python"
    subprocess.run([sys.executable, "-m", "venv", str(runtime_python.parent.parent)], check=True)
    wheel, = (output / "wheels").glob("*.whl")
    subprocess.run([str(runtime_python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)], check=True)
    if any(sha(ROOT / relative) != digest for relative, digest in manifest.items()):
        raise RuntimeError("ビルド中にソースが変わりました。新しい出力先でやり直してください。")
    return verify(runtime_python, output / "check", wheel)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="まだ存在しないビルド・検査の出力先")
    run(parser.parse_args().output)
