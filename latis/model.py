"""公開契約の型検査、正規化、グラフの不変条件。"""

import hashlib
import calendar
import json
import re
import uuid
from datetime import datetime, timezone

SPEC = "0.3-demo-draft"
RULES = "core-0.3.0"
KINDS = {"agreement", "proposal", "intent", "rationale", "question", "scope", "artifact", "task"}
STATES = {"draft", "proposed", "accepted", "rejected", "superseded", "retired"}
RELATIONS = {"contains", "scoped_to", "depends_on", "supports", "conflicts_with", "governs",
             "specializes", "exception_to", "supersedes", "originates_from", "implemented_by", "verified_by"}
CONTENT = RELATIONS - {"contains", "scoped_to", "originates_from", "supersedes"}
ORIGINS = {"agent", "human", "import", "system", "unknown"}
CONFIRMATIONS = {"candidate", "confirmed"}
LIMITS = dict(max_page_size=100, max_title_chars=240, max_body_bytes=1048576,
              max_request_bytes=4194304, max_change_operations=100, max_locator_chars=2048,
              max_evidence_subject_refs=100)
OPERATIONS = ["meta", "search", "detail", "relation-detail", "relations", "history", "save-draft", "consult", "apply"]
CAPABILITIES = (*OPERATIONS, "search_descendants", "markdown_export")
NODE_KEYS = {"id", "revision_id", "commit_revision", "kind", "title", "body", "lifecycle",
             "locator", "content_hash", "evidence", "created_at", "updated_at"}
RELATION_KEYS = {"id", "revision_id", "commit_revision", "from_node_id", "to_node_id", "relation_kind",
                 "lifecycle", "confirmation", "origin", "priority", "qualifier", "basis_refs", "created_at", "updated_at"}


class Error(Exception):
    def __init__(self, code, message, status=400, **details):
        super().__init__(message)
        self.code, self.status, self.details = code, status, details


def fail(code, message, status=400, **details):
    raise Error(code, message, status, **details)


def require(condition, message, code="INVALID_REQUEST", status=400, **details):
    if not condition:
        fail(code, message, status, **details)


def obj(value, allowed, required=()):
    require(isinstance(value, dict), "オブジェクトが必要です。")
    require(not (set(value) - set(allowed)), "未知のフィールドです。", fields=sorted(set(value) - set(allowed)))
    require(set(required) <= set(value), "必須フィールドがありません。", fields=sorted(set(required) - set(value)))
    return value


def string(value, empty=False):
    require(isinstance(value, str) and (empty or bool(value)), "文字列が不正です。")
    require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value), "不正なUnicodeです。")
    return value


def integer(value, minimum=None, maximum=None):
    require(type(value) is int, "整数が必要です。")
    require((minimum is None or value >= minimum) and (maximum is None or value <= maximum), "整数が範囲外です。")
    return value


def boolean(value):
    require(type(value) is bool, "真偽値が必要です。")
    return value


def choice(value, choices):
    require(isinstance(value, str) and value in choices, "未対応の値です。", value=value)
    return value


def strings(value, nonempty=False, choices=None, ordered=False):
    require(isinstance(value, list) and (not nonempty or bool(value)), "配列が不正です。")
    for item in value:
        string(item)
        if choices is not None:
            choice(item, choices)
    return list(value) if ordered else sorted(set(value))


def timestamp(value):
    string(value)
    match = re.fullmatch(r"([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt]([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]+)?(?:[Zz]|\+00:00)", value)
    require(match is not None, "UTCのRFC 3339時刻が必要です。")
    year, month, day, hour, minute, second = map(int, match.groups())
    require(1 <= month <= 12 and 1 <= day <= calendar.monthrange(year, month)[1] and
            0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 60, "日時が不正です。")
    if second == 60:
        require(hour == 23 and minute == 59 and day == calendar.monthrange(year, month)[1], "うるう秒の位置が不正です。")
    return value


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def uid():
    return uuid.uuid4().hex


def decode_json(raw):
    """CLIと復元で同じ厳密なJSON読取規則を使用する。"""
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("JSONキーが重複しています。")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("JSONの数値が不正です。")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid_constant)
    except RecursionError as exc:
        raise ValueError("JSONの構造が深すぎます。") from exc


def canonical(value):
    def check(v):
        if isinstance(v, dict):
            for k, item in v.items():
                string(k, True)
                check(item)
        elif isinstance(v, list):
            for item in v:
                check(item)
        elif isinstance(v, str):
            string(v, True)
        else:
            require(v is None or type(v) in (bool, int), "JSON数値は整数だけを使用できます。")
    try:
        check(value)
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (RecursionError, ValueError) as exc:
        fail("INVALID_REQUEST", "JSONを正規化できません。", cause=str(exc))


def digest(value):
    return "sha256:" + hashlib.sha256(canonical(value).encode()).hexdigest()


def reference(record, kind="node"):
    return {"type": kind, "id": record["id"], "revision_id": record["revision_id"]}


def refs(value, node_only=False):
    require(isinstance(value, list), "参照配列が必要です。")
    found = {}
    for ref in value:
        obj(ref, {"type", "id", "revision_id"}, {"type", "id", "revision_id"})
        choice(ref["type"], {"node"} if node_only else {"node", "relation"})
        string(ref["id"])
        string(ref["revision_id"])
        require(not ref["id"].startswith("$"), "既存のIDが必要です。")
        key = ref["type"], ref["id"]
        require(key not in found or found[key] == ref, "同じ対象に異なる版を指定できません。")
        found[key] = dict(ref)
    return sorted(found.values(), key=lambda r: (r["type"], r["id"], r["revision_id"]))


def evidence(value):
    obj(value, {"subject_refs", "method", "outcome", "observed_at", "actor", "source_refs"},
        {"subject_refs", "method", "outcome", "observed_at", "actor"})
    require(isinstance(value["subject_refs"], list), "subject_refsは配列です。")
    require(1 <= len(value["subject_refs"]) <= 100, "検査対象は1〜100件です。", "LIMIT_EXCEEDED", 413)
    return dict(subject_refs=refs(value["subject_refs"], True), method=string(value["method"]),
                outcome=choice(value["outcome"], {"passed", "failed", "inconclusive"}),
                observed_at=timestamp(value["observed_at"]), actor=string(value["actor"]),
                source_refs=strings(value.get("source_refs", []), ordered=True))


def node_values(values, kind):
    if "title" in values:
        string(values["title"])
        require(len(values["title"]) <= 240, "titleが上限を超えています。", "LIMIT_EXCEEDED", 413)
    if "body" in values:
        string(values["body"], True)
        require(len(values["body"].encode()) <= 1048576, "bodyが上限を超えています。", "LIMIT_EXCEEDED", 413)
    if "lifecycle" in values:
        choice(values["lifecycle"], STATES)
        require(values["lifecycle"] != "superseded" or kind == "agreement", "supersededはagreementだけです。", "INVALID_CHANGE")
    for key in ("locator", "content_hash", "evidence"):
        if values.get(key) is not None:
            require(kind == "artifact", "外部観測の情報はartifactだけに指定できます。", "INVALID_CHANGE")
    locator = values.get("locator")
    if locator is not None:
        string(locator)
        require(len(locator) <= 2048, "locatorが上限を超えています。", "LIMIT_EXCEEDED", 413)
        require(bool(re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", locator)) and
                not any(c.isspace() or ord(c) < 32 or 127 <= ord(c) <= 159 for c in locator), "URIが不正です。", "INVALID_CHANGE")
    if values.get("content_hash") is not None:
        require(isinstance(values["content_hash"], str) and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", values["content_hash"])), "SHA-256が不正です。", "INVALID_CHANGE")
    if values.get("evidence") is not None:
        values["evidence"] = evidence(values["evidence"])


def record(value, decision=False):
    allowed = {"actor", "reason", "principal_refs", "execution_context"}
    required = {"actor", "reason"}
    if decision:
        allowed |= {"authority_ref", "semantic_review", "resolutions"}
        required |= {"authority_ref", "semantic_review"}
    else:
        allowed.add("source_refs")
    obj(value, allowed, required)
    result = dict(value, actor=string(value["actor"]), reason=string(value["reason"]),
                  principal_refs=strings(value.get("principal_refs", [])))
    if "execution_context" in value:
        obj(value["execution_context"], {"model", "model_version", "provider", "session_ref"})
        for item in value["execution_context"].values():
            string(item)
    if decision:
        string(value["authority_ref"])
        choice(value["semantic_review"], {"ready", "needs_user_decision"})
        resolutions = value.get("resolutions", [])
        require(isinstance(resolutions, list), "resolutionsは配列です。")
        result["resolutions"] = []
        for item in resolutions:
            obj(item, {"issue", "source_refs", "resolution", "authority_ref"}, {"issue", "source_refs", "resolution", "authority_ref"})
            result["resolutions"].append(dict(issue=string(item["issue"]), source_refs=strings(item["source_refs"], ordered=True),
                                               resolution=string(item["resolution"]), authority_ref=string(item["authority_ref"])))
    else:
        result["source_refs"] = strings(value.get("source_refs", []), ordered=True)
    return result


def proposal(value):
    obj(value, {"title", "body", "source_refs"}, {"title", "body"})
    node_values(value, "proposal")
    return dict(title=value["title"], body=value["body"], source_refs=strings(value.get("source_refs", []), ordered=True))


def context(value):
    obj(value, {"scope_ids", "anchor_node_ids", "basis_refs", "exploration_note"})
    return dict(scope_ids=strings(value.get("scope_ids", [])), anchor_node_ids=strings(value.get("anchor_node_ids", [])),
                basis_refs=refs(value.get("basis_refs", [])), exploration_note=string(value.get("exploration_note", ""), True))


def change_set(value, state=None):
    obj(value, {"operations"}, {"operations"})
    operations = value["operations"]
    require(isinstance(operations, list), "operationsは配列です。")
    require(1 <= len(operations) <= 100, "操作数は1〜100件です。", "LIMIT_EXCEEDED", 413)
    result, local, updated = [], set(), set()
    for raw in operations:
        require(isinstance(raw, dict), "操作はオブジェクトです。")
        op = dict(raw)
        name = choice(op.get("op"), {"create_node", "update_node", "create_relation", "update_relation"})
        if name.startswith("create_"):
            require(isinstance(op.get("ref"), str) and bool(re.fullmatch(r"[a-z][A-Za-z0-9_]{0,63}", op["ref"])), "refが不正です。")
            require(op["ref"] not in local, "refが重複しています。")
            local.add(op["ref"])
        else:
            string(op.get("id"))
            string(op.get("expected_revision_id"))
            require(not op["id"].startswith("$"), "新規対象へのupdateは禁止です。", "INVALID_CHANGE")
            key = name, op["id"]
            require(key not in updated, "同じ対象へのupdateは一つにまとめてください。", "INVALID_CHANGE")
            updated.add(key)
        if name == "create_node":
            obj(op, {"op", "ref", "kind", "title", "body", "lifecycle", "locator", "content_hash", "evidence"},
                {"op", "ref", "kind", "title", "body", "lifecycle"})
            choice(op["kind"], KINDS)
            choice(op["lifecycle"], {"draft", "proposed", "accepted"})
            for key in ("locator", "content_hash", "evidence"):
                op.setdefault(key, None)
            node_values(op, op["kind"])
        elif name == "update_node":
            obj(op, {"op", "id", "expected_revision_id", "set"}, {"op", "id", "expected_revision_id", "set"})
            obj(op["set"], {"title", "body", "lifecycle", "locator", "content_hash"})
            require(bool(op["set"]), "setが空です。", "INVALID_CHANGE")
            op["set"] = dict(op["set"])
            node_values({k: v for k, v in op["set"].items() if k != "lifecycle"}, "artifact")
            if "lifecycle" in op["set"]:
                choice(op["set"]["lifecycle"], STATES)
        else:
            if name == "create_relation":
                obj(op, {"op", "ref", "from", "to", "relation_kind", "confirmation", "origin", "priority", "qualifier", "basis_targets"},
                    {"op", "ref", "from", "to", "relation_kind", "confirmation", "origin"})
                string(op["from"])
                string(op["to"])
                choice(op["relation_kind"], RELATIONS)
                choice(op["confirmation"], CONFIRMATIONS)
                choice(op["origin"], ORIGINS)
                op.setdefault("priority", None)
                op.setdefault("qualifier", None)
                content_confirmed = op["relation_kind"] in CONTENT and op["confirmation"] == "confirmed"
                require(content_confirmed or "basis_targets" not in op, "この関係へbasis_targetsは指定できません。", "INVALID_CHANGE")
                if content_confirmed:
                    op.setdefault("basis_targets", [])
                values = op
            else:
                obj(op, {"op", "id", "expected_revision_id", "set", "reconfirm", "basis_targets"}, {"op", "id", "expected_revision_id"})
                op["set"] = dict(obj(op.get("set", {}), {"lifecycle", "confirmation", "priority", "qualifier"}))
                op["reconfirm"] = boolean(op.get("reconfirm", False))
                require(bool(op["set"]) or op["reconfirm"], "関係の変更がありません。", "INVALID_CHANGE")
                if "lifecycle" in op["set"]:
                    choice(op["set"]["lifecycle"], {"active", "retired"})
                if "confirmation" in op["set"]:
                    choice(op["set"]["confirmation"], CONFIRMATIONS)
                if state and op["id"] in state["relations"]:
                    old = state["relations"][op["id"]]
                    confirming = old["confirmation"] == "candidate" and op["set"].get("confirmation") == "confirmed"
                    allowed = old["relation_kind"] in CONTENT and (confirming or op["reconfirm"])
                    require(allowed or "basis_targets" not in op, "basis_targetsを指定できません。", "INVALID_CHANGE")
                    if allowed and "basis_targets" not in op:
                        excluded = {old["from_node_id"], old["to_node_id"]}
                        target = state["nodes"].get(old["to_node_id"], {})
                        if old["relation_kind"] == "verified_by" and target.get("evidence"):
                            excluded |= {r["id"] for r in target["evidence"]["subject_refs"]}
                        op["basis_targets"] = sorted({r["id"] for r in old["basis_refs"]} - excluded) if op["reconfirm"] else []
                values = op["set"]
            if values.get("priority") is not None:
                integer(values["priority"])
            if values.get("qualifier") is not None:
                string(values["qualifier"], True)
            if "basis_targets" in op:
                op["basis_targets"] = strings(op["basis_targets"])
        result.append(op)
    return {"operations": result}


def memberships(state):
    result = {id_: set() for id_ in state["nodes"]}
    for rel in state["relations"].values():
        if rel["relation_kind"] == "scoped_to" and rel["lifecycle"] == "active" and rel["confirmation"] == "confirmed":
            result[rel["from_node_id"]].add(rel["to_node_id"])
    return {id_: sorted(scopes) for id_, scopes in result.items()}


def transition(before, after, kind):
    allowed = {"draft": {"draft", "proposed", "accepted", "rejected", "retired"},
               "proposed": {"draft", "proposed", "accepted", "rejected", "retired"},
               "accepted": {"accepted", "retired", "superseded"},
               "rejected": {"rejected"}, "retired": {"retired"}, "superseded": {"superseded"}}
    require(after in allowed[before] and (after != "superseded" or kind == "agreement"), "状態遷移が不正です。", "INVALID_CHANGE")


def validate_graph(state):
    nodes, relations = state["nodes"], state["relations"]
    seen = set()
    edges = {k: {} for k in ("contains", "exception_to", "supersedes")}
    for rel in relations.values():
        a, b, kind = rel["from_node_id"], rel["to_node_id"], rel["relation_kind"]
        require(a in nodes and b in nodes, "関係の端点が存在しません。", "TARGET_NOT_FOUND", 404)
        require(a != b, "自己関係は禁止です。", "INVALID_CHANGE")
        ka, kb = nodes[a]["kind"], nodes[b]["kind"]
        valid = True
        if kind == "contains":
            valid = ka == kb == "scope"
        elif kind == "scoped_to":
            valid = kb == "scope" and ka != "scope"
        elif kind in {"exception_to", "supersedes", "specializes", "conflicts_with"}:
            valid = ka == kb == "agreement"
        elif kind in {"implemented_by", "verified_by"}:
            valid = ka == "agreement" and kb == "artifact"
        require(valid, "関係の端点の型が不正です。", "INVALID_CHANGE")
        active = rel["lifecycle"] == "active"
        confirmed = rel["confirmation"] == "confirmed"
        if active and confirmed:
            key = kind, a, b, rel["qualifier"]
            require(key not in seen, "確定関係が重複しています。", "INVALID_CHANGE")
            seen.add(key)
            if kind == "exception_to":
                require(bool(rel["qualifier"]), "例外条件が必要です。", "INVALID_CHANGE")
        if active and kind in edges and (confirmed or kind != "contains"):
            edges[kind].setdefault(a, []).append(b)
    for kind, graph in edges.items():
        # 再帰上限に依存しない深さ優先探索。
        done, visiting = set(), set()
        for start in graph:
            stack = [(start, False)]
            while stack:
                node, leaving = stack.pop()
                if leaving:
                    visiting.discard(node)
                    done.add(node)
                elif node not in done:
                    require(node not in visiting, "関係に循環があります。", "INVALID_CHANGE", relation_kind=kind)
                    visiting.add(node)
                    stack.append((node, True))
                    stack.extend((child, False) for child in graph.get(node, []))
