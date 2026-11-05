"""展示ビュー向けに、LATIS正本を一貫した読取状態として取得する。"""

import sqlite3
from pathlib import Path

from latis import storage
from latis.engine import basis_status, node_diagnostics
from latis.model import memberships
from latis.model import fail, require

DISPLAY_PREFIXES = {"agreement": "A", "proposal": "P", "intent": "I", "rationale": "R",
                    "question": "Q", "scope": "S", "artifact": "AR", "task": "T"}


def display_numbers(data):
    """作成された版の順から、種類ごとに固定の表示番号を導出する。"""
    counts = {kind: 0 for kind in DISPLAY_PREFIXES}
    numbers = {}
    creations = sorted((r for r in data["revisions"] if r["target_type"] == "node" and r["change_type"] == "create"),
                       key=lambda r: (r["commit_revision"], r["target_id"]))
    for revision in creations:
        kind = revision["snapshot"]["kind"]
        counts[kind] += 1
        numbers[revision["target_id"]] = f"{DISPLAY_PREFIXES[kind]}-{counts[kind]}"
    return numbers


def read_snapshot(path):
    """指定DBを作成せずに読み、検証済みの全記録を返す。"""
    path = Path(path)
    require(path.is_absolute(), "DBパスは絶対パスで指定してください。", "INVALID_REQUEST")
    require(path.is_file(), "DBが存在しません。", "TARGET_NOT_FOUND", 404)
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.4)
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        require(conn.execute("PRAGMA application_id").fetchone()[0] == storage.APP_ID,
                "LATISのDBではありません。", "INVALID_DATABASE")
        require(conn.execute("PRAGMA user_version").fetchone()[0] == storage.SCHEMA,
                "未対応のDB形式です。", "UNSUPPORTED_FORMAT")
        schema = list(conn.execute("SELECT type,name,sql FROM sqlite_master"))
        require({name for kind, name, _ in schema if kind == "table"} == {"metadata", *storage.TABLES}
                and all(kind == "table" or kind == "index" and sql is None for kind, _, sql in schema),
                "未対応のDB構造です。", "INVALID_DATABASE")
        for table in ("metadata", *storage.TABLES):
            require([row[1] for row in conn.execute(f"PRAGMA table_info({table})")] == ["id", "data"],
                    "未対応のDB列です。", "INVALID_DATABASE")
        require(conn.execute("SELECT count(*) FROM metadata").fetchone()[0] == 1,
                "DBメタデータが不正です。", "INVALID_DATABASE")
        # 未対応の版と、対応形式内の破損を区別して返す。
        storage.validate_meta(storage.parse_record(conn.execute("SELECT data FROM metadata WHERE id=1").fetchone()[0]))
        data = storage.read(conn)
        storage.validate_snapshot(data)
        state = storage.state_at(data)
        require(state["meta"] == data["meta"], "現在のsnapshotが履歴と一致しません。", "INVALID_DATABASE")
        require(state["nodes"] == {item["id"]: item for item in data["nodes"]}
                and state["relations"] == {item["id"]: item for item in data["relations"]},
                "現在状態が履歴と一致しません。", "INVALID_DATABASE")
        conn.commit()
        return data
    except sqlite3.DatabaseError as exc:
        if storage.is_busy(exc):
            raise
        fail("INVALID_DATABASE", "DBを読み取れません。", cause=str(exc))
    finally:
        conn.close()


def project(path, revision=None):
    """正本の全状態と履歴を、表示側が絞り込める形で返す。"""
    data = read_snapshot(path)
    if revision is not None:
        require(type(revision) is int and revision >= 0, "履歴の版は0以上の整数で指定してください。", "INVALID_REQUEST")
        historical = storage.state_at(data, revision)
        commits = [c for c in data["commits"] if c["graph_revision"] <= revision]
        provenance_ids = {c["provenance_id"] for c in commits}
        data = dict(meta=historical["meta"],
            nodes=sorted(historical["nodes"].values(), key=lambda n: n["id"]),
            relations=sorted(historical["relations"].values(), key=lambda r: r["id"]),
            revisions=[r for r in data["revisions"] if r["commit_revision"] <= revision],
            provenance=[p for p in data["provenance"] if p["id"] in provenance_ids], commits=commits,
            idempotency_records=[r for r in data["idempotency_records"] if r["response"]["data"]["commit_revision"] <= revision])
    state = storage.state_at(data)
    revisions = {r["revision_id"]: r for r in data["revisions"]}
    provenance = {p["id"]: p for p in data["provenance"]}
    successes = {r["response"]["data"]["commit_revision"]: r for r in data["idempotency_records"]}
    operations = {number: record["operation"] for number, record in successes.items()}
    scope_order = []
    events = []
    for commit in data["commits"]:
        if not commit["graph_revision"]:
            continue
        record = provenance[commit["provenance_id"]]
        operation = operations[commit["graph_revision"]]
        # 表示順は採択時の作成順を使う。優先順位・効力の計算ではない。
        created = successes[commit["graph_revision"]]["response"]["data"]["created_refs"]
        for op in record.get("change_set", {}).get("operations", []):
            if op["op"] == "create_node" and op["kind"] == "scope":
                scope_order.append(created[op["ref"]]["id"])
        events.append(dict(
            graph_revision=commit["graph_revision"], snapshot_id=commit["snapshot_id"],
            created_at=commit["created_at"], operation=operation,
            confirmed=operation == "apply" and "decision" in record,
            reason=record["reason"], provenance_id=record["id"],
            changes=[dict(type=change["type"], id=change["id"],
                          before=revisions[change["before_revision_id"]]["snapshot"] if change["before_revision_id"] else None,
                          after=revisions[change["after_revision_id"]]["snapshot"])
                     for change in commit["change_refs"]],
            membership_changes=commit["membership_changes"],
        ))
    return {
        "meta": data["meta"],
        "nodes": data["nodes"],
        "relations": data["relations"],
        "revisions": data["revisions"],
        "provenance": data["provenance"],
        "commits": data["commits"],
        "idempotency_records": data["idempotency_records"],
        "events": events,
        "display_numbers": display_numbers(data),
        "scope_ids": memberships(state),
        "scope_order": [*scope_order, *(n["id"] for n in data["nodes"] if n["kind"] == "scope" and n["id"] not in scope_order)],
        "basis_status": {r["id"]: basis_status(r, state) for r in data["relations"]},
        "diagnostics": {n["id"]: node_diagnostics(n, state) for n in data["nodes"]},
        "selection": {"filter": "all", "nodes": len(data["nodes"]),
                      "relations": len(data["relations"])},
    }
