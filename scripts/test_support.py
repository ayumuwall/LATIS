"""実検査で、同秒・同サイズの変更を古いバイトコードと取り違えない実行。"""

import os
import subprocess
import sys
import tempfile


def run_unittest(directory):
    # -Bだけでは既存pycの読込を防げないため、参照先も毎回空の場所へ分離する。
    with tempfile.TemporaryDirectory(prefix="latis-pycache-") as cache:
        environment = dict(os.environ, FORCE_COLOR="1", PYTHONPYCACHEPREFIX=cache, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, "-m", "unittest", "-v"], cwd=directory, capture_output=True, env=environment)
