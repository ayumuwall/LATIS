"""SQLite正本、履歴の再構成、一貫した退避・復元。"""

import ctypes
import errno
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from .model import (SPEC, RULES, LEGACY_SPEC, LEGACY_RULES, project_name, NODE_KEYS, RELATION_KEYS, KINDS, RELATIONS, STATES, CONTENT,
                    ORIGINS, CONFIRMATIONS, Error, canonical, change_set, choice, decode_json, fail, integer, memberships,
                    node_values, now, obj, proposal, record, reference, refs, require, string, strings, timestamp,
                    transition, uid, validate_graph)

APP_ID = 0x4C415449
SCHEMA = 3
FORMAT_VERSION = 3
TABLES = ("nodes", "relations", "revisions", "provenance", "commits", "idempotency_records")
META_KEYS = {"database_id", "graph_revision", "snapshot_id", "rules_version", "spec_version", "project_name"}


def is_busy(exc):
    return isinstance(exc, sqlite3.OperationalError) and (
        (getattr(exc, "sqlite_errorcode", 0) or 0) & 255 in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
        or "locked" in str(exc).lower() or "busy" in str(exc).lower())


def parse_record(raw):
    require(isinstance(raw, str), "DBのJSON列は文字列である必要があります。", "INVALID_DATABASE")
    value = decode_json(raw.encode("utf-8"))
    canonical(value)
    return value


def validate_meta(meta, *, legacy=False):
    keys = META_KEYS - {"project_name"} if legacy else META_KEYS
    obj(meta, keys, keys)
    if not legacy:
        project_name(meta["project_name"])
    string(meta["database_id"])
    string(meta["snapshot_id"])
    integer(meta["graph_revision"], 0, 9007199254740991)
    expected = (LEGACY_SPEC,LEGACY_RULES) if legacy else (SPEC,RULES)
    require((meta["spec_version"],meta["rules_version"]) == expected, "未対応の仕様版です。", "UNSUPPORTED_FORMAT")


def validate_target(value, type_):
    keys = NODE_KEYS if type_ == "node" else RELATION_KEYS
    obj(value, keys, keys)
    for key in ("id", "revision_id"):
        string(value[key])
        require(not value[key].startswith("$"), "保存IDにローカル参照は使用できません。")
    integer(value["commit_revision"], 1, 9007199254740991)
    timestamp(value["created_at"])
    timestamp(value["updated_at"])
    if type_ == "node":
        choice(value["kind"], KINDS)
        node_values(dict(value), value["kind"])
        if value["evidence"] is not None:
            require(value["evidence"] == node_evidence(value), "証拠の正規化が不正です。")
    else:
        choice(value["relation_kind"], RELATIONS)
        choice(value["lifecycle"], {"active", "retired"})
        choice(value["confirmation"], CONFIRMATIONS)
        choice(value["origin"], ORIGINS)
        for key in ("from_node_id", "to_node_id"):
            string(value[key])
            require(not value[key].startswith("$"), "関係の端点は既存IDです。")
        if value["priority"] is not None:
            integer(value["priority"])
        if value["qualifier"] is not None:
            string(value["qualifier"], True)
        require(refs(value["basis_refs"], True) == value["basis_refs"], "根拠版の正規化が不正です。")
        require((value["relation_kind"] in CONTENT and value["confirmation"] == "confirmed") or not value["basis_refs"], "関係の根拠版が不正です。")


def initial(name):
    project_name(name)
    stamp, snapshot = now(), uid()
    return dict(format="latis-snapshot", format_version=FORMAT_VERSION,
                meta=dict(database_id=uid(), project_name=name, graph_revision=0, snapshot_id=snapshot, rules_version=RULES, spec_version=SPEC),
                nodes=[], relations=[], revisions=[], provenance=[], idempotency_records=[],
                commits=[dict(graph_revision=0, snapshot_id=snapshot, created_at=stamp, change_refs=[], membership_changes=[], provenance_id=None)])


def connect(path, *, legacy=False):
    require(Path(path).is_file(), "DBが存在しません。initで初期化してください。", "TARGET_NOT_FOUND", 404)
    try:
        conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=rw", uri=True, timeout=2)
        require(conn.execute("PRAGMA application_id").fetchone()[0] == APP_ID, "LATISのDBではありません。", "INVALID_DATABASE")
        require(conn.execute("PRAGMA user_version").fetchone()[0] == (2 if legacy else SCHEMA), "未対応のDB形式です。", "UNSUPPORTED_FORMAT")
        schema = list(conn.execute("SELECT type,name,sql FROM sqlite_master"))
        require({name for type_, name, _ in schema if type_ == "table"} == {"metadata", *TABLES} and
                all(type_ == "table" or type_ == "index" and sql is None for type_, _, sql in schema),
                "未対応のテーブル・ビュー・トリガー等を含むDBです。", "INVALID_DATABASE")
        for table in ("metadata", *TABLES):
            require([row[1] for row in conn.execute(f"PRAGMA table_info({table})")] == ["id", "data"], "未対応のDB列を含みます。", "INVALID_DATABASE")
        require(conn.execute("SELECT count(*) FROM metadata").fetchone()[0] == 1, "DBメタデータが重複しています。", "INVALID_DATABASE")
        meta = parse_record(conn.execute("SELECT data FROM metadata WHERE id=1").fetchone()[0])
        validate_meta(meta,legacy=legacy)
        return conn
    except Error as exc:
        if "conn" in locals():
            conn.close()
        if exc.code in {"UNSUPPORTED_FORMAT", "INVALID_DATABASE"}:
            raise
        fail("INVALID_DATABASE", "DBの記録形式が不正です。", cause=str(exc))
    except (sqlite3.DatabaseError, ValueError, KeyError, TypeError) as exc:
        if "conn" in locals():
            conn.close()
        if is_busy(exc):
            raise
        fail("INVALID_DATABASE", "DBの形式が不正です。", cause=str(exc))


def read(conn, *, legacy=False):
    try:
        result = {"format": "latis-snapshot", "format_version": 2 if legacy else FORMAT_VERSION,
                  "meta": parse_record(conn.execute("SELECT data FROM metadata WHERE id=1").fetchone()[0])}
        validate_meta(result["meta"],legacy=legacy)
        for table in TABLES:
            key = {"revisions": "revision_id", "commits": "graph_revision", "idempotency_records": "idempotency_key"}.get(table, "id")
            result[table] = []
            for id_, raw in conn.execute(f"SELECT id,data FROM {table}"):
                item = parse_record(raw)
                require(item[key] == id_, "SQLiteの主キーと記録IDが一致しません。", "INVALID_DATABASE")
                if table in {"nodes", "relations"}:
                    validate_target(item, "node" if table == "nodes" else "relation")
                result[table].append(item)
        order_snapshot(result)
        return result
    except Error as exc:
        fail("INVALID_DATABASE", "DBの記録形式が不正です。", cause=str(exc))
    except (sqlite3.DatabaseError, ValueError, TypeError, KeyError) as exc:
        if is_busy(exc):
            raise
        fail("INVALID_DATABASE", "DBを読み取れません。", cause=str(exc))


def order_snapshot(data):
    for name in ("nodes", "relations", "provenance"):
        data[name].sort(key=lambda x: x["id"])
    data["revisions"].sort(key=lambda x: (x["commit_revision"], x["target_type"], x["target_id"], x["revision_id"]))
    data["commits"].sort(key=lambda x: x["graph_revision"])
    data["idempotency_records"].sort(key=lambda x: x["idempotency_key"])


def state_at(data, revision=None):
    revision = data["meta"]["graph_revision"] if revision is None else revision
    commits = {c["graph_revision"]: c for c in data["commits"]}
    require(revision in commits, "基準履歴を利用できません。", "BASIS_UNAVAILABLE", 409)
    state = {"meta": dict(data["meta"], graph_revision=revision, snapshot_id=commits[revision]["snapshot_id"]),
             "nodes": {}, "relations": {}, "revisions": {}}
    for item in sorted(data["revisions"], key=lambda r: r["commit_revision"]):
        if item["commit_revision"] <= revision:
            state[item["target_type"] + "s"][item["target_id"]] = item["snapshot"]
            state["revisions"][item["revision_id"]] = item
    return state


def write_commit(conn, data, state, changed, provenance, response, key, operation, request_digest):
    commit_revision = state["meta"]["graph_revision"]
    changes = []
    before = state_at(data)
    for type_, id_ in sorted(changed):
        target = state[type_ + "s"][id_]
        old = before[type_ + "s"].get(id_)
        revision = dict(revision_id=target["revision_id"], target_type=type_, target_id=id_,
                        commit_revision=commit_revision, change_type="update" if old else "create",
                        snapshot=target, provenance_ids=[provenance["id"]])
        conn.execute(f"INSERT OR REPLACE INTO {type_}s(id,data) VALUES (?,?)", (id_, canonical(target)))
        conn.execute("INSERT INTO revisions(id,data) VALUES (?,?)", (revision["revision_id"], canonical(revision)))
        changes.append(dict(type=type_, id=id_, before_revision_id=old["revision_id"] if old else None, after_revision_id=target["revision_id"]))
    before_members, after_members = memberships(before), memberships(state)
    membership_changes = [dict(node_id=id_, before_scope_ids=before_members.get(id_, []), after_scope_ids=after_members.get(id_, []))
                          for id_ in sorted(state["nodes"]) if before_members.get(id_, []) != after_members.get(id_, [])]
    commit = dict(graph_revision=commit_revision, snapshot_id=state["meta"]["snapshot_id"], created_at=provenance["created_at"],
                  change_refs=changes, membership_changes=membership_changes, provenance_id=provenance["id"])
    conn.execute("INSERT INTO commits(id,data) VALUES (?,?)", (commit_revision, canonical(commit)))
    conn.execute("INSERT INTO provenance(id,data) VALUES (?,?)", (provenance["id"], canonical(provenance)))
    idem = dict(idempotency_key=key, operation=operation, request_digest=request_digest, response=response)
    conn.execute("INSERT INTO idempotency_records(id,data) VALUES (?,?)", (key, canonical(idem)))
    conn.execute("UPDATE metadata SET data=? WHERE id=1", (canonical(state["meta"]),))


def create_file(path, data):
    conn = sqlite3.connect(path)
    try:
        conn.execute(f"PRAGMA application_id={APP_ID}")
        conn.execute(f"PRAGMA user_version={SCHEMA}")
        conn.execute("CREATE TABLE metadata(id INTEGER PRIMARY KEY CHECK(id=1),data TEXT NOT NULL)")
        conn.execute("INSERT INTO metadata VALUES (1,?)", (canonical(data["meta"]),))
        for table in TABLES:
            conn.execute(f"CREATE TABLE {table}(id {'INTEGER' if table == 'commits' else 'TEXT'} PRIMARY KEY,data TEXT NOT NULL)")
            key = {"revisions": "revision_id", "commits": "graph_revision", "idempotency_records": "idempotency_key"}.get(table, "id")
            conn.executemany(f"INSERT INTO {table} VALUES (?,?)", [(item[key], canonical(item)) for item in data[table]])
        conn.commit()
    finally:
        conn.close()


def publish(destination, writer):
    destination = Path(destination).absolute()
    require(not destination.exists() and not destination.is_symlink(), "出力先が既に存在します。", "DESTINATION_EXISTS", 409)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".latis-", dir=destination.parent)
    os.close(fd)
    try:
        writer(temporary)
        with open(temporary, "rb") as stream:
            os.fsync(stream.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            fail("DESTINATION_EXISTS", "出力先が既に存在します。", 409)
    finally:
        os.unlink(temporary)
    return str(destination)


def rename_directory(source, destination):
    """存在確認との競合でも空ディレクトリを上書きしない、排他的な公開。"""
    if os.name == "nt":
        os.rename(source, destination)
        return
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        rename = library.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        args = (os.fsencode(source), os.fsencode(destination), 0x4)  # RENAME_EXCL
    elif sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        rename = library.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        args = (-100, os.fsencode(source), -100, os.fsencode(destination), 1)  # RENAME_NOREPLACE
    else:
        raise OSError(errno.ENOTSUP, "排他的なディレクトリ公開に未対応の環境です。")
    rename.restype = ctypes.c_int
    if rename(*args) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(destination))


def publish_directory(destination, writer):
    require("\0" not in destination, "出力先にNULは使用できません。")
    destination = Path(destination).absolute()
    require(not destination.exists() and not destination.is_symlink(), "出力先が既に存在します。", "DESTINATION_EXISTS", 409)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".latis-", dir=destination.parent))
    try:
        writer(temporary)
        for path in temporary.rglob("*"):
            if path.is_file():
                with path.open("rb") as stream:
                    os.fsync(stream.fileno())
        try:
            rename_directory(temporary, destination)
        except OSError as exc:
            if exc.errno in {errno.EEXIST, errno.ENOTEMPTY} or destination.exists() or destination.is_symlink():
                fail("DESTINATION_EXISTS", "出力先が既に存在します。", 409)
            raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return str(destination)


def validate_snapshot(data, *, legacy=False):
    """不正な記録を切り捨てず、履歴を再生して完全性を検査する。"""
    try:
        _validate_snapshot(data,legacy=legacy)
    except Error as exc:
        if exc.code == "UNSUPPORTED_FORMAT":
            raise
        fail("INVALID_DATABASE", "スナップショットの整合性検査に失敗しました。", cause=str(exc), original_code=exc.code)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, RecursionError) as exc:
        fail("INVALID_DATABASE", "スナップショットの構造が不正です。", cause=str(exc))


def _validate_snapshot(data, *, legacy=False):
    require(isinstance(data, dict), "スナップショットはオブジェクトです。")
    require(data.get("format") == "latis-snapshot" and type(data.get("format_version")) is int and data["format_version"] == (2 if legacy else FORMAT_VERSION),
            "未対応のスナップショット形式です。", "UNSUPPORTED_FORMAT")
    obj(data, {"format", "format_version", "meta", *TABLES}, {"format", "format_version", "meta", *TABLES})
    canonical(data)
    meta = data["meta"]
    validate_meta(meta,legacy=legacy)
    historical_pairs = {(LEGACY_SPEC,LEGACY_RULES)} if legacy else {(LEGACY_SPEC,LEGACY_RULES),(SPEC,RULES)}
    historical_rules = {pair[1] for pair in historical_pairs}
    for table in TABLES:
        require(isinstance(data[table], list), "記録は配列です。")
    collections = {}
    for table in TABLES:
        key = {"revisions": "revision_id", "commits": "graph_revision", "idempotency_records": "idempotency_key"}.get(table, "id")
        collections[table] = {item[key]: item for item in data[table]}
        require(len(collections[table]) == len(data[table]), "記録IDが重複しています。")
    versions = collections["revisions"]
    for rev in versions.values():
        obj(rev, {"revision_id", "target_type", "target_id", "commit_revision", "change_type", "snapshot", "provenance_ids"},
            {"revision_id", "target_type", "target_id", "commit_revision", "change_type", "snapshot", "provenance_ids"})
        choice(rev["target_type"], {"node", "relation"})
        choice(rev["change_type"], {"create", "update"})
        string(rev["revision_id"])
        string(rev["target_id"])
        integer(rev["commit_revision"], 1, meta["graph_revision"])
        target = rev["snapshot"]
        validate_target(target, rev["target_type"])
        require(target["id"] == rev["target_id"] and target["revision_id"] == rev["revision_id"] and
                target["commit_revision"] == rev["commit_revision"], "版の対応が不正です。")
        if rev["target_type"] == "node":
            if target["evidence"]:
                for ref in target["evidence"]["subject_refs"]:
                    subject = versions.get(ref["revision_id"])
                    require(subject is not None and subject["target_type"] == "node" and subject["target_id"] == ref["id"] and
                            subject["commit_revision"] < rev["commit_revision"] and ref["id"] != target["id"], "観測対象の過去版が不正です。")
        else:
            for ref in target["basis_refs"]:
                subject = versions.get(ref["revision_id"])
                require(subject is not None and subject["target_type"] == "node" and subject["target_id"] == ref["id"] and
                        subject["commit_revision"] <= rev["commit_revision"], "根拠版が存在しません。")
        require(isinstance(rev["provenance_ids"], list) and len(rev["provenance_ids"]) == 1, "来歴参照が不正です。")
        string(rev["provenance_ids"][0])
    commits = collections["commits"]
    require(len(commits) == meta["graph_revision"] + 1 and sorted(commits) == list(range(meta["graph_revision"] + 1)), "commit履歴が連続していません。")
    require(len({c["snapshot_id"] for c in commits.values()}) == len(commits), "snapshot_idが重複しています。")
    state = {"nodes": {}, "relations": {}}
    used_revisions, used_provenance = set(), set()
    for number in range(meta["graph_revision"] + 1):
        commit = commits[number]
        obj(commit, {"graph_revision", "snapshot_id", "created_at", "change_refs", "membership_changes", "provenance_id"},
            {"graph_revision", "snapshot_id", "created_at", "change_refs", "membership_changes", "provenance_id"})
        string(commit["snapshot_id"])
        integer(commit["graph_revision"], 0, meta["graph_revision"])
        timestamp(commit["created_at"])
        before_members = memberships(state)
        old_nodes = dict(state["nodes"])
        old_relations = dict(state["relations"])
        changed = []
        require(isinstance(commit["change_refs"], list) and isinstance(commit["membership_changes"], list), "変更記録が不正です。")
        targets = set()
        for change in commit["change_refs"]:
            obj(change, {"type", "id", "before_revision_id", "after_revision_id"}, {"type", "id", "before_revision_id", "after_revision_id"})
            choice(change["type"], {"node", "relation"})
            key = change["type"], change["id"]
            require(key not in targets, "一つのcommitに対象の重複があります。")
            targets.add(key)
            rev = versions.get(change["after_revision_id"])
            require(rev is not None and rev["commit_revision"] == number and (rev["target_type"], rev["target_id"]) == key, "commitの版参照が不正です。")
            old = state[change["type"] + "s"].get(change["id"])
            target = rev["snapshot"]
            require(change["before_revision_id"] == (old["revision_id"] if old else None), "変更前の版が不正です。")
            require(rev["change_type"] == ("update" if old else "create"), "変更種別が不正です。")
            require(rev["provenance_ids"] == [commit["provenance_id"]], "来歴とcommitの対応が不正です。")
            if old:
                require(target["created_at"] == old["created_at"], "作成時刻が変更されています。")
                if change["type"] == "node":
                    require(target["kind"] == old["kind"], "kindが変更されています。")
                    transition(old["lifecycle"], target["lifecycle"], target["kind"])
                    require(target["evidence"] == old["evidence"], "証拠が書き換えられています。")
                    if old["evidence"]:
                        require(all(target[k] == old[k] for k in ("locator", "content_hash")), "証拠の所在・ハッシュが変更されています。")
                else:
                    require(all(old[k] == target[k] for k in ("from_node_id", "to_node_id", "relation_kind", "origin")), "関係の同一性が変更されています。")
                    require(old["lifecycle"] != "retired" or target["lifecycle"] == "retired", "終了した関係が復活しています。")
                    require(old["confirmation"] != "confirmed" or target["confirmation"] == "confirmed", "確定関係が候補へ戻っています。")
                    require(not (old["relation_kind"] == "supersedes" and old["confirmation"] == "confirmed") or target["lifecycle"] == "active", "置換の事実が終了されています。")
            elif change["type"] == "node":
                choice(target["lifecycle"], {"draft", "proposed", "accepted"})
            else:
                require(target["lifecycle"] == "active", "新規関係はactiveで作成します。")
            state[change["type"] + "s"][change["id"]] = target
            used_revisions.add(rev["revision_id"])
            changed.append(reference(target, change["type"]))
        validate_graph(state)
        after_members = memberships(state)
        expected_members = [dict(node_id=id_, before_scope_ids=before_members.get(id_, []), after_scope_ids=after_members.get(id_, []))
                            for id_ in sorted(state["nodes"]) if before_members.get(id_, []) != after_members.get(id_, [])]
        require(commit["membership_changes"] == expected_members, "Scope所属の変更記録が不正です。")
        if number == 0:
            require(not changed and commit["provenance_id"] is None, "初期commitが不正です。")
        else:
            prov = collections["provenance"].get(commit["provenance_id"])
            require(bool(changed), "変更のないcommitが保存されています。")
            require(prov is not None and prov["commit_revision"] == number and refs(prov["target_refs"]) == refs(changed), "来歴と変更対象が一致しません。")
            allowed = {"id", "commit_revision", "target_refs", "actor", "principal_refs", "source_refs", "reason", "created_at", "execution_context"}
            apply_fields = {"proposal", "change_set", "decision", "consulted_basis", "validated_at_revision"}
            obj(prov, allowed | apply_fields, allowed - {"execution_context"})
            string(prov["id"])
            integer(prov["commit_revision"], 1, meta["graph_revision"])
            require(refs(prov["target_refs"]) == prov["target_refs"], "来歴の対象集合が正規化されていません。")
            timestamp(prov["created_at"])
            stored_record = {k: prov[k] for k in ("actor", "principal_refs", "source_refs", "reason", "execution_context") if k in prov}
            require(record(stored_record) == stored_record, "来歴の実行情報が正規化されていません。")
            if set(prov) & apply_fields:
                require(apply_fields <= set(prov), "採択の来歴が不足しています。")
                decision = record(prov["decision"], True)
                require(decision == prov["decision"] and decision["semantic_review"] == "ready", "保存された採択判断が不正です。")
                require(proposal(prov["proposal"]) == prov["proposal"] and prov["source_refs"] == prov["proposal"]["source_refs"], "提案と来歴の出所が一致しません。")
                for key in ("actor", "reason", "principal_refs", "execution_context"):
                    require((key in prov) == (key in decision) and prov.get(key) == decision.get(key), "判断と来歴の実行情報が一致しません。")
                require(change_set(prov["change_set"], state_at(data, number - 1)) == prov["change_set"], "保存された変更計画が不正です。")
                integer(prov["validated_at_revision"], 0, number - 1)
                require(prov["validated_at_revision"] == number - 1, "反映直前の検査版が不正です。")
                basis = prov["consulted_basis"]
                obj(basis, {"schema_version", "database_id", "graph_revision", "snapshot_id", "rules_version", "change_digest", "refs", "watch", "exploration_note"},
                    {"schema_version", "database_id", "graph_revision", "snapshot_id", "rules_version", "change_digest", "refs", "watch", "exploration_note"})
                integer(basis["graph_revision"], 0, number - 1)
                require(basis["schema_version"] == "basis-1" and basis["database_id"] == meta["database_id"] and basis["rules_version"] in historical_rules and
                        basis["snapshot_id"] == commits[basis["graph_revision"]]["snapshot_id"], "照合時の基準履歴が不正です。")
                require(bool(re.fullmatch(r"sha256:[0-9a-f]{64}", basis["change_digest"])), "照合ダイジェストが不正です。")
                require(refs(basis["refs"]) == basis["refs"], "照合参照が不正です。")
                base_state = state_at(data, basis["graph_revision"])
                string(basis["exploration_note"], True)
                for ref in basis["refs"]:
                    r = versions.get(ref["revision_id"])
                    require(r is not None and r["target_id"] == ref["id"] and r["target_type"] == ref["type"] and r["commit_revision"] <= basis["graph_revision"], "照合対象の版が不正です。")
                    require(base_state[ref["type"] + "s"][ref["id"]]["revision_id"] == ref["revision_id"], "照合時点の現在版と一致しません。")
                obj(basis["watch"], {"node_ids", "scope_ids"}, {"node_ids", "scope_ids"})
                for watch_key in ("node_ids", "scope_ids"):
                    require(strings(basis["watch"][watch_key]) == basis["watch"][watch_key], "監視範囲が正規化されていません。")
                    for id_ in basis["watch"][watch_key]:
                        require(id_ in base_state["nodes"] and (watch_key != "scope_ids" or base_state["nodes"][id_]["kind"] == "scope"), "監視対象が存在しません。")
            used_provenance.add(prov["id"])
        for target in state["relations"].values():
            if target["relation_kind"] in CONTENT and target["confirmation"] == "confirmed":
                basis_ids = {r["id"] for r in target["basis_refs"]}
                require({target["from_node_id"], target["to_node_id"]} <= basis_ids, "両端の根拠版が不足しています。")
                if target["relation_kind"] == "verified_by":
                    ev = state["nodes"][target["to_node_id"]]["evidence"]
                    require(ev is not None and ev["outcome"] == "passed", "確認済み検証にpassedの証拠がありません。")
                    require(all(r in target["basis_refs"] for r in ev["subject_refs"]), "固定された観測対象版が不足しています。")
            old_relation = old_relations.get(target["id"])
            newly_confirmed = target["confirmation"] == "confirmed" and (old_relation is None or old_relation["confirmation"] == "candidate")
            rechecked = False
            if number and target["commit_revision"] == number:
                prov = collections["provenance"][commit["provenance_id"]]
                rechecked = any(op.get("id") == target["id"] and op.get("reconfirm") is True for op in prov.get("change_set", {}).get("operations", []))
                if old_relation and old_relation["confirmation"] == "confirmed" and target["relation_kind"] in CONTENT:
                    require(rechecked or all(old_relation[k] == target[k] for k in ("basis_refs", "qualifier")), "確定判断の変更に再確認の記録がありません。")
            if target["commit_revision"] == number and target["lifecycle"] == "active" and target["confirmation"] == "confirmed" and (newly_confirmed or rechecked):
                a, b = state["nodes"][target["from_node_id"]], state["nodes"][target["to_node_id"]]
                if target["relation_kind"] in CONTENT:
                    for ref in target["basis_refs"]:
                        require(state["nodes"][ref["id"]]["revision_id"] == ref["revision_id"], "確認時の最終版と根拠版が一致しません。")
                if target["relation_kind"] == "exception_to":
                    require(a["lifecycle"] == b["lifecycle"] == "accepted", "例外の確定時に端点が採択済みではありません。")
                if target["relation_kind"] == "supersedes":
                    old = old_nodes.get(b["id"])
                    require(a["lifecycle"] == "accepted" and b["lifecycle"] == "superseded" and old and old["lifecycle"] == "accepted", "置換の状態が不正です。")
        for id_, value in state["nodes"].items():
            if value["lifecycle"] == "superseded" and old_nodes.get(id_, {}).get("lifecycle") == "accepted":
                require(any(r["relation_kind"] == "supersedes" and r["to_node_id"] == id_ and r["confirmation"] == "confirmed" and r["commit_revision"] == number and
                            (r["id"] not in old_relations or old_relations[r["id"]]["confirmation"] == "candidate") for r in state["relations"].values()), "全体置換の確定関係がありません。")
    require(used_revisions == set(versions) and used_provenance == set(collections["provenance"]), "commitから辿れない版・来歴があります。")
    for name in ("nodes", "relations"):
        require(state[name] == collections[name], "現在版と履歴の最終版が一致しません。")
    require(commits[meta["graph_revision"]]["snapshot_id"] == meta["snapshot_id"], "metaとcommitが一致しません。")
    success_commits = set()
    for item in data["idempotency_records"]:
        obj(item, {"idempotency_key", "operation", "request_digest", "response"}, {"idempotency_key", "operation", "request_digest", "response"})
        choice(item["operation"], {"save-draft", "apply"})
        require(bool(re.fullmatch(r"[A-Za-z0-9.:_-]{1,128}", item["idempotency_key"])), "冪等性キーが不正です。")
        require(bool(re.fullmatch(r"sha256:[0-9a-f]{64}", item["request_digest"])), "入力ダイジェストが不正です。")
        response = obj(item["response"], {"ok", "data", "meta", "errors"}, {"ok", "data", "meta", "errors"})
        require(response["ok"] is True and response["errors"] == [], "成功記録が不正です。")
        response_meta = response["meta"]
        number = response_meta["graph_revision"]
        integer(number, 1, meta["graph_revision"])
        require(number in commits and response_meta["database_id"] == meta["database_id"] and response_meta["snapshot_id"] == commits[number]["snapshot_id"] and
                (response_meta["spec_version"],response_meta["rules_version"]) in historical_pairs and response_meta["api_version"] == "v1", "成功応答と履歴が一致しません。")
        require(number > 0 and number not in success_commits, "成功応答のcommitが重複しています。")
        success_commits.add(number)
        result = response["data"]
        prov = collections["provenance"][commits[number]["provenance_id"]]
        integer(result["commit_revision"], 1, meta["graph_revision"])
        require(result["commit_revision"] == number and result["provenance_id"] == prov["id"], "成功応答の対象commitが不正です。")
        require(isinstance(result["created_refs"], dict), "created_refsはオブジェクトです。")
        for local_ref in result["created_refs"]:
            require(bool(re.fullmatch(r"[a-z][A-Za-z0-9_]{0,63}", local_ref)), "成功応答のローカルrefが不正です。")
        result_refs = [*result["created_refs"].values(), *result["updated_refs"]]
        require(len(result_refs) == len(prov["target_refs"]) and refs(result_refs) == refs(prov["target_refs"]), "成功応答の変更対象が不正です。")
        require((item["operation"] == "apply") == ("decision" in prov), "成功応答の操作種別が不正です。")
        created = {(r["type"], r["id"], r["after_revision_id"]) for r in commits[number]["change_refs"] if r["before_revision_id"] is None}
        updated = {(r["type"], r["id"], r["after_revision_id"]) for r in commits[number]["change_refs"] if r["before_revision_id"] is not None}
        require({(r["type"], r["id"], r["revision_id"]) for r in result["created_refs"].values()} == created and
                {(r["type"], r["id"], r["revision_id"]) for r in result["updated_refs"]} == updated, "成功応答の作成・更新の分類が不正です。")
        if item["operation"] == "apply":
            require(result["validated_at_revision"] == prov["validated_at_revision"] and result["consulted_at_revision"] == prov["consulted_basis"]["graph_revision"], "成功応答の照合版が不正です。")
            require(response_meta["rules_version"] == prov["consulted_basis"]["rules_version"], "成功応答と照合時の規則版が一致しません。")
    require(success_commits == set(range(1, meta["graph_revision"] + 1)), "成功済み再試行記録が不足しています。")


def node_evidence(target):
    from .model import evidence
    return evidence(target["evidence"])
