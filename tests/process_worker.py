"""試験用の子プロセス。正本のcommit・出力公開の直前だけ待機する。"""

import json
import os
import sys

from latis import Engine, storage


def pause(**details):
    print(json.dumps(dict(paused=True, **details)), flush=True)
    if sys.stdin.readline() != "continue\n":
        raise RuntimeError("試験の続行合図がありません。")


def main():
    mode, database, operation = sys.argv[1:]
    request = json.loads(sys.stdin.readline())
    if mode == "commit":
        original = storage.write_commit
        def write(*args, **kwargs):
            original(*args, **kwargs)
            pause(stage="before_commit")
        storage.write_commit = write
    elif mode == "file":
        original = os.link
        def link(source, destination, *args, **kwargs):
            pause(stage="before_publish", source=str(source), destination=str(destination))
            return original(source, destination, *args, **kwargs)
        storage.os.link = link
    elif mode == "directory":
        original = storage.rename_directory
        def rename(source, destination):
            pause(stage="before_publish", source=str(source), destination=str(destination))
            return original(source, destination)
        storage.rename_directory = rename
    else:
        raise ValueError("試験用の待機位置が不正です。")
    engine = Engine(database)
    result = engine.execute(operation, request)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return engine.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
