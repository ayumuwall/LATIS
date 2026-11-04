"""JSON stdin/stdoutのCLI。診断はstderrへ分離する。"""

import argparse
import json
import os
import sys

from .engine import Engine, envelope
from .model import Error, LIMITS, canonical, fail


def decode_json(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("JSONキーが重複しています。")
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError("JSONの数値が不正です。")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid_constant)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        fail("INVALID_REQUEST", "CLI引数が不正です。", cause=message)


def main():
    engine = None
    try:
        parser = Parser(description="LATIS 合意エンジン（JSON入出力）")
        parser.add_argument("--db", default=None, help="SQLite DBのパス")
        parser.add_argument("operation", help="meta/search/detail/relation-detail/relations/history/save-draft/consult/apply/init/backup/export/restore")
        args = parser.parse_args()
        engine = Engine(args.db if args.db is not None else os.environ.get("LATIS_DB", ".latis/latis.sqlite"))
        raw = sys.stdin.buffer.read(LIMITS["max_request_bytes"] + 1)
        if len(raw) > LIMITS["max_request_bytes"]:
            fail("LIMIT_EXCEEDED", "入力が4 MiBを超えています。", 413)
        try:
            request = decode_json(raw)
        except (ValueError, UnicodeError):
            fail("INVALID_REQUEST", "UTF-8のJSONが必要です。")
        result = engine.execute(args.operation, request)
        print(canonical(result))
        return engine.exit_code
    except Error as exc:
        print(canonical(envelope(None, engine.meta if engine else {}, [dict(code=exc.code, message=str(exc), details=exc.details)])))
        return 1
    except Exception as exc:
        print(f"実行障害: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(canonical(envelope(None, engine.meta if engine else {}, [dict(code="INTERNAL_ERROR", message="予期しない実行障害が発生しました。", details={})])))
        return 2


if __name__ == "__main__":
    sys.exit(main())
