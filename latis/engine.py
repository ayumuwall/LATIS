"""9操作と保守操作を提供する合意エンジン。"""

import base64
import copy
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

from . import storage
from .model import (SPEC, RULES, LIMITS, OPERATIONS, CONTENT, RELATIONS, KINDS, STATES, CONFIRMATIONS,
                    Error, boolean, canonical, change_set, choice, context, digest, fail, integer,
                    memberships, now, obj, proposal, record, reference, refs, require, string,
                    strings, transition, uid, validate_graph)


def envelope(data, meta, errors=None):
    return dict(ok=errors is None, data=data, meta=dict(api_version="v1", spec_version=SPEC, rules_version=RULES,
                database_id=meta.get("database_id"), graph_revision=meta.get("graph_revision"), snapshot_id=meta.get("snapshot_id")), errors=errors or [])


def target(state, type_, id_):
    string(id_)
    require(id_ in state[type_ + "s"], "対象が存在しません。", "TARGET_NOT_FOUND", 404, target_id=id_)
    return state[type_ + "s"][id_]


def existing_revision(state, ref):
    revision = state["revisions"].get(ref["revision_id"])
    require(revision is not None and revision["target_id"] == ref["id"] and revision["target_type"] == ref["type"],
            "対象の版が存在しません。", "REVISION_NOT_FOUND", 404, target_id=ref["id"], revision_id=ref["revision_id"])
    return revision


def basis_status(rel, state):
    if rel["relation_kind"] not in CONTENT:
        return "not_applicable"
    if not rel["basis_refs"]:
        return "untracked"
    return "current" if all(state["nodes"][r["id"]]["revision_id"] == r["revision_id"] for r in rel["basis_refs"]) else "changed"


def diagnostic(code, targets, kind="structural_fact", **details):
    messages = {"unscoped": "直接のScope所属がありません。", "basis_changed": "判断が参照した版が更新されています。",
                "verification_basis_changed": "検証関係が参照した版が更新されています。", "partial_result": "結果の一部を表示しています。",
                "recorded_conflict": "競合として記録された確定関係があります。", "candidate_conflict": "競合の候補関係があります。",
                "unclassified_changes": "照合後に未分類の合意が変更されています。"}
    return dict(code=code, evidence_kind=kind, target_refs=targets, message=messages.get(code, code), details=details)


def relation_diagnostics(rel, state):
    if rel["lifecycle"] != "active" or rel["confirmation"] != "confirmed" or basis_status(rel, state) != "changed":
        return []
    changed = [dict(node_id=r["id"], recorded_revision_id=r["revision_id"], current_revision_id=state["nodes"][r["id"]]["revision_id"])
               for r in rel["basis_refs"] if state["nodes"][r["id"]]["revision_id"] != r["revision_id"]]
    code = "verification_basis_changed" if rel["relation_kind"] in {"implemented_by", "verified_by"} else "basis_changed"
    return [diagnostic(code, [reference(rel, "relation")], changed_refs=sorted(changed, key=lambda r: r["node_id"]))]


def node_diagnostics(node, state):
    result = []
    if node["kind"] != "scope" and not memberships(state)[node["id"]]:
        result.append(diagnostic("unscoped", [reference(node)]))
    for rel in sorted(state["relations"].values(), key=lambda r: r["id"]):
        if node["id"] in (rel["from_node_id"], rel["to_node_id"]) and rel["relation_kind"] in {"implemented_by", "verified_by"}:
            result.extend(relation_diagnostics(rel, state))
    return result


def unique_diagnostics(items):
    return [json.loads(value) for value in sorted({canonical(item) for item in items})]


def summary(node, state, excerpt=True):
    result = {k: node[k] for k in ("id", "revision_id", "kind", "lifecycle", "title")}
    if excerpt:
        result.update(excerpt=node["body"][:240], scope_ids=memberships(state)[node["id"]])
    return result


def page(items, request, filters, state, operation):
    limit = integer(request.get("limit", 20), 1, 100)
    cursor = request.get("cursor")
    offset = 0
    identity = dict(database_id=state["meta"]["database_id"], graph_revision=state["meta"]["graph_revision"],
                    snapshot_id=state["meta"]["snapshot_id"], rules_version=RULES)
    if cursor is not None:
        string(cursor)
        try:
            raw = json.loads(base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True))
            obj(raw, {"identity", "operation", "filters", "offset"}, {"identity", "operation", "filters", "offset"})
            offset = integer(raw["offset"], 0)
        except (ValueError, UnicodeError, Error):
            fail("INVALID_REQUEST", "cursorが不正です。")
        require(raw["operation"] == operation and raw["filters"] == filters, "cursorの検索条件が異なります。")
        require(raw["identity"] == identity, "DB版が変わりました。検索し直してください。", "CURSOR_STALE", 409)
    selected = items[offset:offset + limit]
    more = offset + limit < len(items)
    next_cursor = None
    if more:
        next_cursor = base64.urlsafe_b64encode(canonical(dict(identity=identity, operation=operation, filters=filters, offset=offset + limit)).encode()).decode().rstrip("=")
    return selected, dict(limit=limit, returned_count=len(selected), has_more=more, next_cursor=next_cursor)


class Engine:
    def __init__(self, path):
        self.path = Path(path).absolute()
        self.meta = {}
        self.exit_code = 0

    def execute(self, operation, request):
        self.exit_code = 0
        self.meta = {}
        try:
            # core-0.3.0の検索結果が実行環境の更新だけで変わらないようにする。
            require(unicodedata.unidata_version == "15.0.0", "この実装のcore-0.3.0にはPython 3.12（Unicode 15.0.0）が必要です。", "RULES_CHANGED", 409)
            require(len(canonical(request).encode()) <= LIMITS["max_request_bytes"], "入力が上限を超えています。", "LIMIT_EXCEEDED", 413)
            require(isinstance(request, dict), "入力はJSONオブジェクトです。")
            if operation in {"init", "restore"}:
                return self._maintenance(operation, request)
            require(operation in set(OPERATIONS) | {"backup", "export"}, "操作が未対応です。")
            conn = storage.connect(self.path)
            try:
                conn.execute("BEGIN IMMEDIATE" if operation in {"apply", "save-draft"} else "BEGIN")
                data = storage.read(conn)
                self.meta = data["meta"]
                state = storage.state_at(data)
                require(state["nodes"] == {n["id"]: n for n in data["nodes"]} and state["relations"] == {r["id"]: r for r in data["relations"]},
                        "現在版と履歴が一致しません。", "INVALID_DATABASE")
                if operation in {"save-draft", "apply"}:
                    response = self._write(operation, request, conn, data, state)
                elif operation == "consult":
                    response = envelope(self._consult(request, state), self.meta)
                elif operation in {"backup", "export"}:
                    response = self._backup(operation, request, conn, data)
                else:
                    response = envelope(self._read(operation, request, data, state), self.meta)
                conn.commit()
                self.meta = {k: response["meta"][k] for k in ("database_id", "graph_revision", "snapshot_id", "spec_version", "rules_version")}
                return response
            finally:
                conn.close()
        except Error as exc:
            self.exit_code = 1
            return envelope(None, self.meta, [dict(code=exc.code, message=str(exc), details=exc.details)])
        except sqlite3.OperationalError as exc:
            if storage.is_busy(exc):
                self.exit_code = 1
                return envelope(None, self.meta, [dict(code="BUSY", message="DBが使用中です。同じキーで再試行できます。", details={})])
            raise

    def _read(self, operation, request, data, state):
        if operation == "meta":
            obj(request, {})
            return dict(api_version="v1", **state["meta"], capabilities=OPERATIONS, limits=LIMITS)
        if operation == "search":
            obj(request, {"query", "kinds", "lifecycles", "scope_ids", "include_unscoped", "include_descendants", "limit", "cursor"})
            filters = dict(query=string(request.get("query", ""), True), kinds=strings(request.get("kinds", ["agreement"]), True, KINDS),
                           lifecycles=strings(request.get("lifecycles", ["accepted"]), True, STATES), scope_ids=strings(request.get("scope_ids", [])),
                           include_unscoped=boolean(request.get("include_unscoped", False)), include_descendants=boolean(request.get("include_descendants", False)))
            require(not filters["include_descendants"], "子孫Scope検索は未対応です。", "UNSUPPORTED_FEATURE", capability="search_descendants")
            for id_ in filters["scope_ids"]:
                require(target(state, "node", id_)["kind"] == "scope", "scope_idsにはScopeを指定してください。")
            filters["expanded_scope_ids"] = filters["scope_ids"]
            normalize = lambda text: unicodedata.normalize("NFKC", text).casefold()
            query = normalize(filters["query"])
            terms = query.split()
            scopes = memberships(state)
            candidates = []
            for node in state["nodes"].values():
                title, body = normalize(node["title"]), normalize(node["body"])
                if node["kind"] not in filters["kinds"] or node["lifecycle"] not in filters["lifecycles"]:
                    continue
                if filters["scope_ids"] and not (set(scopes[node["id"]]) & set(filters["scope_ids"]) or filters["include_unscoped"] and not scopes[node["id"]]):
                    continue
                if not all(term in title or term in body for term in terms):
                    continue
                rank = 0 if not terms or title == query else 1 if all(term in title for term in terms) else 2
                item = summary(node, state)
                item["matched_fields"] = [name for name, text in (("title", title), ("body", body)) if terms and any(term in text for term in terms)]
                candidates.append((rank, node["id"], item))
            candidates.sort(key=lambda x: (x[0], x[1]))
            items, paging = page([item[2] for item in candidates], request, filters, state, operation)
            diagnostics = [d for item in items for d in node_diagnostics(state["nodes"][item["id"]], state)]
            if paging["has_more"]:
                diagnostics.append(diagnostic("partial_result", [], "unverified"))
            return dict(items=items, page=paging, applied_filters=filters, diagnostics=unique_diagnostics(diagnostics))
        if operation in {"detail", "relation-detail"}:
            type_ = "node" if operation == "detail" else "relation"
            key = type_ + "_id"
            obj(request, {key, "revision_id"}, {key})
            value = target(state, type_, request[key])
            historical = "revision_id" in request
            if historical:
                value = existing_revision(state, {"type": type_, "id": request[key], "revision_id": string(request["revision_id"])})["snapshot"]
            revision = state["revisions"][value["revision_id"]]
            if type_ == "node":
                result = dict(node=value, scope_ids=None if historical else memberships(state)[value["id"]],
                              diagnostics=[] if historical else node_diagnostics(value, state), provenance_ids=revision["provenance_ids"])
                if historical:
                    result["scope_resolution"] = "not_included_for_historical_revision"
                return result
            return dict(relation=value, basis_status=None if historical else basis_status(value, state),
                        diagnostics=[] if historical else relation_diagnostics(value, state), provenance_ids=revision["provenance_ids"])
        if operation == "relations":
            obj(request, {"node_id", "direction", "relation_kinds", "confirmations", "lifecycles", "limit", "cursor"}, {"node_id"})
            node = target(state, "node", request["node_id"])
            filters = dict(node_id=node["id"], direction=choice(request.get("direction", "both"), {"in", "out", "both"}),
                           relation_kinds=strings(request.get("relation_kinds", sorted(RELATIONS)), True, RELATIONS),
                           confirmations=strings(request.get("confirmations", ["candidate", "confirmed"]), True, CONFIRMATIONS),
                           lifecycles=strings(request.get("lifecycles", ["active"]), True, {"active", "retired"}))
            values = []
            for rel in sorted(state["relations"].values(), key=lambda r: r["id"]):
                outgoing = rel["from_node_id"] == node["id"]
                incoming = rel["to_node_id"] == node["id"]
                if not (outgoing or incoming) or filters["direction"] == "out" and not outgoing or filters["direction"] == "in" and not incoming:
                    continue
                if rel["relation_kind"] in filters["relation_kinds"] and rel["confirmation"] in filters["confirmations"] and rel["lifecycle"] in filters["lifecycles"]:
                    values.append(dict(relation=rel, basis_status=basis_status(rel, state),
                                       other_node_summary=summary(state["nodes"][rel["to_node_id"] if outgoing else rel["from_node_id"]], state, False)))
            items, paging = page(values, request, filters, state, operation)
            diagnostics = [d for item in items for d in relation_diagnostics(item["relation"], state)]
            if paging["has_more"]:
                diagnostics.append(diagnostic("partial_result", [], "unverified"))
            return dict(items=items, page=paging, diagnostics=unique_diagnostics(diagnostics))
        obj(request, {"target_type", "target_id", "limit", "cursor"}, {"target_type", "target_id"})
        type_ = choice(request["target_type"], {"node", "relation"})
        value = target(state, type_, request["target_id"])
        filters = dict(target_type=type_, target_id=value["id"])
        revisions = sorted([r for r in data["revisions"] if r["target_type"] == type_ and r["target_id"] == value["id"]],
                           key=lambda r: (-r["commit_revision"], r["revision_id"]))
        selected, paging = page(revisions, request, filters, state, operation)
        provenance_ids = {p for r in selected for p in r["provenance_ids"]}
        return dict(target=dict(type=type_, id=value["id"]), revisions=selected,
                    provenance=[p for p in data["provenance"] if p["id"] in provenance_ids], page=paging)

    def _normalize(self, request, state):
        obj(request, {"proposal", "change_set", "context", "options"}, {"proposal", "change_set"})
        options = obj(request.get("options", {}), {"max_related_items"})
        maximum = integer(options.get("max_related_items", 20), 1, 100)
        normalized = dict(proposal=proposal(request["proposal"]), change_set=change_set(request["change_set"], state), context=context(request.get("context", {})))
        return normalized, maximum

    def _basis(self, normalized, state):
        ctx, operations = normalized["context"], normalized["change_set"]["operations"]
        seeds, references, extra_evidence = set(), [], set()
        scopes = set(ctx["scope_ids"])
        for id_ in scopes:
            require(target(state, "node", id_)["kind"] == "scope", "context.scope_idsにはScopeを指定してください。")
        seeds.update(ctx["anchor_node_ids"])
        for ref in ctx["basis_refs"]:
            value = target(state, ref["type"], ref["id"])
            require(value["revision_id"] == ref["revision_id"], "指定された根拠版が現在版と異なります。", "BASIS_CHANGED", 409, changed_refs=[reference(value, ref["type"])])
            references.append(ref)
            if ref["type"] == "node":
                seeds.add(ref["id"])
            else:
                seeds.update((value["from_node_id"], value["to_node_id"]))
                seeds.update(r["id"] for r in value["basis_refs"])
                if value["relation_kind"] == "verified_by" and value["confirmation"] == "confirmed":
                    extra_evidence.add(value["to_node_id"])
        created = {"$" + op["ref"]: op for op in operations if op["op"] == "create_node"}
        for op in operations:
            if op["op"] == "update_node":
                seeds.add(op["id"])
            elif op["op"] in {"create_relation", "update_relation"}:
                if op["op"] == "create_relation":
                    endpoints = op["from"], op["to"]
                    relation_kind = op["relation_kind"]
                    confirming = op["confirmation"] == "confirmed"
                    if relation_kind == "scoped_to" and not op["to"].startswith("$"):
                        scopes.add(op["to"])
                else:
                    old = target(state, "relation", op["id"])
                    references.append(reference(old, "relation"))
                    endpoints = old["from_node_id"], old["to_node_id"]
                    relation_kind = old["relation_kind"]
                    confirming = op["reconfirm"] or old["confirmation"] == "candidate" and op["set"].get("confirmation") == "confirmed"
                seeds.update(id_ for id_ in endpoints if not id_.startswith("$"))
                for id_ in op.get("basis_targets", []):
                    if not id_.startswith("$"):
                        seeds.add(id_)
                        extra_evidence.add(id_)
                if relation_kind == "verified_by" and confirming:
                    evidence_node = created.get(endpoints[1]) if endpoints[1].startswith("$") else target(state, "node", endpoints[1])
                    if evidence_node and evidence_node.get("evidence"):
                        seeds.update(r["id"] for r in evidence_node["evidence"]["subject_refs"])
        for id_ in extra_evidence:
            node = target(state, "node", id_)
            if node["evidence"]:
                seeds.update(r["id"] for r in node["evidence"]["subject_refs"])
        membership = memberships(state)
        for id_ in seeds:
            references.append(reference(target(state, "node", id_)))
            scopes.update(membership[id_])
        for rel in state["relations"].values():
            if rel["relation_kind"] == "scoped_to" and rel["from_node_id"] in seeds and rel["lifecycle"] == "active" and rel["confirmation"] == "confirmed":
                references.append(reference(rel, "relation"))
        return dict(schema_version="basis-1", **{k: state["meta"][k] for k in ("database_id", "graph_revision", "snapshot_id", "rules_version")}, change_digest=digest(normalized), refs=refs(references),
                    watch=dict(node_ids=sorted(seeds), scope_ids=sorted(scopes)), exploration_note=ctx["exploration_note"])

    def _consult(self, request, state):
        normalized, maximum = self._normalize(request, state)
        self._simulate(normalized["change_set"], state, False)
        basis = self._basis(normalized, state)
        # spec_versionはenvelope/metaに置き、basisの形には追加しない。
        basis.pop("spec_version", None)
        seeds, scopes = set(basis["watch"]["node_ids"]), set(basis["watch"]["scope_ids"])
        neighbors, related_relations = set(), []
        for rel in sorted(state["relations"].values(), key=lambda r: r["id"]):
            if rel["lifecycle"] == "active" and seeds & {rel["from_node_id"], rel["to_node_id"]}:
                if rel["from_node_id"] in seeds:
                    neighbors.add(rel["to_node_id"])
                if rel["to_node_id"] in seeds:
                    neighbors.add(rel["from_node_id"])
                related_relations.append(rel)
        membership = memberships(state)
        same_scope = scopes | {id_ for id_, scope_ids in membership.items() if scopes & set(scope_ids)}
        related = []
        for id_ in seeds | neighbors | same_scope:
            reasons = [reason for reason, subset in (("seed", seeds), ("explicit_relation_neighbor", neighbors), ("same_scope", same_scope)) if id_ in subset]
            item = summary(target(state, "node", id_), state)
            item["inclusion_reasons"] = reasons
            related.append(item)
        related.sort(key=lambda item: ({"seed": 0, "explicit_relation_neighbor": 1, "same_scope": 2}[item["inclusion_reasons"][0]], item["id"]))
        diagnostics = [d for id_ in sorted(seeds) for d in node_diagnostics(state["nodes"][id_], state)]
        for rel in related_relations:
            diagnostics.extend(relation_diagnostics(rel, state))
            if rel["relation_kind"] == "conflicts_with":
                confirmed = rel["confirmation"] == "confirmed"
                diagnostics.append(diagnostic("recorded_conflict" if confirmed else "candidate_conflict", [reference(rel, "relation")],
                                              "recorded_judgment" if confirmed else "agent_inference" if rel["origin"] == "agent" else "unverified"))
        has_more = len(related) > maximum
        if has_more:
            diagnostics.append(diagnostic("partial_result", [], "unverified"))
        return dict(normalized_request=normalized, basis=basis, related_items=related[:maximum], related_page=dict(returned_count=min(len(related), maximum), has_more=has_more),
                    diagnostics=unique_diagnostics(diagnostics), structural_validation="valid",
                    next_queries=[dict(operation="relations", request=dict(node_id=id_)) for id_ in sorted(seeds)[:20]] if has_more else [])

    def _simulate(self, changes, before, allocate, draft=False):
        state = copy.deepcopy(before)
        commit_revision, stamp = before["meta"]["graph_revision"] + 1, now()
        integer(commit_revision, 1, 9007199254740991)
        state["meta"].update(graph_revision=commit_revision, snapshot_id=uid() if allocate else "pending")
        local, changed, confirmed = {}, set(), []
        operations = changes["operations"]
        for op in operations:
            if op["op"].startswith("update_"):
                type_ = op["op"].removeprefix("update_")
                old = target(before, type_, op["id"])
                require(old["revision_id"] == op["expected_revision_id"], "更新対象の版が変わりました。", "PRECONDITION_CHANGED", 409, changed_refs=[reference(old, type_)])
            else:
                local[op["ref"]] = dict(type=op["op"].removeprefix("create_"), id=uid() if allocate else "pending:" + op["ref"],
                                        revision_id=uid() if allocate else "pending:" + op["ref"])

        def resolve(id_):
            if not id_.startswith("$"):
                target(state, "node", id_)
                return id_
            ref = local.get(id_[1:])
            require(ref is not None and ref["type"] == "node", "ノードのローカル参照が不正です。", "INVALID_CHANGE")
            return ref["id"]

        def changed_value(type_, value, old=None, reconfirm=False):
            if old is not None and value == old and not reconfirm:
                return
            if old is not None:
                value = dict(value, revision_id=uid() if allocate else "pending:" + value["id"], commit_revision=commit_revision, updated_at=stamp)
            state[type_ + "s"][value["id"]] = value
            changed.add((type_, value["id"]))

        for op in operations:
            name = op["op"]
            if name == "create_node":
                if draft:
                    require(op["lifecycle"] in {"draft", "proposed"} or op["kind"] == "scope" and op["lifecycle"] == "accepted",
                            "採択にはconsult/applyが必要です。", "CONSULTATION_REQUIRED", 409)
                ref = local[op["ref"]]
                value = {k: op[k] for k in ("kind", "title", "body", "lifecycle", "locator", "content_hash", "evidence")}
                value.update(id=ref["id"], revision_id=ref["revision_id"], commit_revision=commit_revision, created_at=stamp, updated_at=stamp)
                if value["evidence"]:
                    for subject in value["evidence"]["subject_refs"]:
                        existing_revision(before, subject)
                        require(subject["id"] != value["id"], "証拠は自分自身を参照できません。", "INVALID_CHANGE")
                changed_value("node", value)
            elif name == "update_node":
                old = before["nodes"][op["id"]]
                patch = op["set"]
                if draft:
                    require(old["lifecycle"] in {"draft", "proposed"} and patch.get("lifecycle", old["lifecycle"]) in {"draft", "proposed", "rejected", "retired"},
                            "採択済み記録の変更にはconsult/applyが必要です。", "CONSULTATION_REQUIRED", 409)
                if set(patch) & {"locator", "content_hash"}:
                    require(old["kind"] == "artifact" and old["evidence"] is None, "この記録の所在・ハッシュは更新できません。", "INVALID_CHANGE")
                transition(old["lifecycle"], patch.get("lifecycle", old["lifecycle"]), old["kind"])
                value = dict(old, **patch)
                from .model import node_values
                node_values(value, value["kind"])
                changed_value("node", value, old)

        for op in operations:
            name = op["op"]
            if name == "create_relation":
                ref = local[op["ref"]]
                value = dict(id=ref["id"], revision_id=ref["revision_id"], commit_revision=commit_revision,
                             from_node_id=resolve(op["from"]), to_node_id=resolve(op["to"]), relation_kind=op["relation_kind"], lifecycle="active",
                             confirmation=op["confirmation"], origin=op["origin"], priority=op["priority"], qualifier=op["qualifier"], basis_refs=[], created_at=stamp, updated_at=stamp)
                newly_confirmed = value["confirmation"] == "confirmed"
                changed_value("relation", value)
            elif name == "update_relation":
                old = before["relations"][op["id"]]
                value = dict(old, **op["set"])
                require(old["lifecycle"] != "retired" or value["lifecycle"] == "retired", "終了した関係は復活できません。", "INVALID_CHANGE")
                require(old["confirmation"] != "confirmed" or value["confirmation"] == "confirmed", "確定関係を候補へ戻せません。", "INVALID_CHANGE")
                require(not (old["relation_kind"] == "supersedes" and old["confirmation"] == "confirmed") or value["lifecycle"] == "active",
                        "実行済みの置換は終了できません。", "INVALID_CHANGE")
                require(not op["reconfirm"] or old["relation_kind"] in CONTENT and old["confirmation"] == "confirmed" and value["lifecycle"] == "active",
                        "この関係は再確認できません。", "INVALID_CHANGE")
                require(not (old["relation_kind"] in CONTENT and old["confirmation"] == "confirmed" and value["qualifier"] != old["qualifier"]) or op["reconfirm"],
                        "確定判断の条件変更にはreconfirm=trueが必要です。", "INVALID_CHANGE")
                newly_confirmed = old["confirmation"] == "candidate" and value["confirmation"] == "confirmed"
                if newly_confirmed:
                    require(value["lifecycle"] == "active", "終了済み関係を確定できません。", "INVALID_CHANGE")
                changed_value("relation", value, old, op["reconfirm"])
                value = state["relations"][value["id"]]
            else:
                continue
            if draft:
                source = value["from_node_id"]
                allowed_scoped = value["relation_kind"] == "scoped_to" and any(
                    side.get(source, {}).get("lifecycle") in {"draft", "proposed"} for side in (before["nodes"], state["nodes"]))
                require(value["confirmation"] == "candidate" or allowed_scoped and not (name == "update_relation" and newly_confirmed),
                        "確定関係の変更にはconsult/applyが必要です。", "CONSULTATION_REQUIRED", 409)
                if name == "update_relation" and value["confirmation"] == "confirmed":
                    require(set(op["set"]) <= {"lifecycle"} and value["lifecycle"] == "retired", "草稿の所属は作成・終了だけが可能です。", "CONSULTATION_REQUIRED", 409)
            if newly_confirmed or op.get("reconfirm"):
                confirmed.append((value, op))

        for value, op in confirmed:
            kind = value["relation_kind"]
            a, b = state["nodes"][value["from_node_id"]], state["nodes"][value["to_node_id"]]
            if kind == "supersedes":
                old_b = before["nodes"].get(b["id"])
                require(a["kind"] == b["kind"] == "agreement" and a["lifecycle"] == "accepted" and b["lifecycle"] == "superseded" and
                        old_b is not None and old_b["lifecycle"] == "accepted" and ("node", b["id"]) in changed,
                        "全体置換には旧accepted合意のsuperseded化が必要です。", "INVALID_CHANGE")
            if kind == "exception_to":
                require(a["lifecycle"] == b["lifecycle"] == "accepted" and bool(value["qualifier"]), "確定する例外には採択済み合意と条件が必要です。", "INVALID_CHANGE")
            if kind in CONTENT:
                additional = [reference(state["nodes"][resolve(id_)]) for id_ in op.get("basis_targets", [])]
                fixed = []
                if kind == "verified_by":
                    ev = b["evidence"]
                    require(ev is not None and ev["outcome"] == "passed", "検証の確定にはpassedの証拠が必要です。", "INVALID_CHANGE")
                    fixed = ev["subject_refs"]
                    changes_found = []
                    for subject in fixed:
                        existing_revision(before, subject)
                        subject_node = state["nodes"][subject["id"]]
                        if subject_node["revision_id"] != subject["revision_id"]:
                            changes_found.append(dict(node_id=subject["id"], observed_revision_id=subject["revision_id"],
                                                      current_revision_id=before["nodes"][subject["id"]]["revision_id"],
                                                      changed_in_change_set=("node", subject["id"]) in changed))
                    require(not changes_found, "検査した対象版が最終版と一致しません。", "EVIDENCE_SUBJECT_CHANGED", 409,
                            evidence_target=op["to"] if op["op"] == "create_relation" else b["id"], subject_changes=sorted(changes_found, key=lambda r: r["node_id"]))
                value["basis_refs"] = refs([reference(a), reference(b), *additional, *fixed], True)
                state["relations"][value["id"]] = value
        for type_, id_ in changed:
            if type_ == "node":
                value = state["nodes"][id_]
                old = before["nodes"].get(id_)
                if value["lifecycle"] == "superseded" and old and old["lifecycle"] != "superseded":
                    require(any(r["relation_kind"] == "supersedes" and r["to_node_id"] == id_ for r, _ in confirmed),
                            "superseded化と置換関係の確定を同じ変更へ含めてください。", "INVALID_CHANGE")
        validate_graph(state)
        require(bool(changed), "反映する変更がありません。", "NO_CHANGES")
        created = {ref: reference(state[item["type"] + "s"][item["id"]], item["type"]) for ref, item in local.items()}
        updated = [reference(state[type_ + "s"][id_], type_) for type_, id_ in sorted(changed) if id_ not in {r["id"] for r in local.values()}]
        return state, changed, created, updated

    def _check_changes(self, data, baseline, current, basis):
        expected_numbers = set(range(baseline["meta"]["graph_revision"] + 1, current["meta"]["graph_revision"] + 1))
        commits = [c for c in data["commits"] if c["graph_revision"] in expected_numbers]
        require({c["graph_revision"] for c in commits} == expected_numbers, "照合後の変更履歴が不足しています。", "BASIS_UNAVAILABLE", 409, next_action="reconsult")
        versions = {r["revision_id"]: r for r in data["revisions"]}
        covered = set()
        for commit in commits:
            for change in commit["change_refs"]:
                revision = versions.get(change["after_revision_id"])
                require(revision is not None and revision["commit_revision"] == commit["graph_revision"] and
                        revision["target_type"] == change["type"] and revision["target_id"] == change["id"] and
                        (change["before_revision_id"] is None or change["before_revision_id"] in versions),
                        "差分を再構成する版が不足しています。", "BASIS_UNAVAILABLE", 409, next_action="reconsult")
                covered.add(revision["revision_id"])
        require(covered == {r["revision_id"] for r in data["revisions"] if r["commit_revision"] in expected_numbers},
                "commitと変更版が対応していません。", "BASIS_UNAVAILABLE", 409, next_action="reconsult")
        for ref in basis["refs"]:
            value = target(current, ref["type"], ref["id"])
            require(value["revision_id"] == ref["revision_id"], "照合の根拠版が変わりました。", "BASIS_CHANGED", 409,
                    changed_refs=[reference(value, ref["type"])], current_revision=current["meta"]["graph_revision"], next_action="reconsult")
        watch_nodes, watch_scopes = set(basis["watch"]["node_ids"]), set(basis["watch"]["scope_ids"])
        unclassified, changed_refs = {}, []
        before = baseline
        fields = ("qualifier", "basis_refs", "confirmation", "lifecycle")
        for commit in data["commits"]:
            if commit["graph_revision"] <= baseline["meta"]["graph_revision"]:
                continue
            after = storage.state_at(data, commit["graph_revision"])
            before_members, after_members = memberships(before), memberships(after)
            scope_agreements = set()
            for side, member in ((before, before_members), (after, after_members)):
                scope_agreements.update(id_ for id_, node in side["nodes"].items() if node["kind"] == "agreement" and node["lifecycle"] == "accepted" and set(member[id_]) & watch_scopes)
            for id_ in sorted(set(before["nodes"]) | set(after["nodes"])):
                a, b = before["nodes"].get(id_), after["nodes"].get(id_)
                if id_ in scope_agreements and (a != b or before_members.get(id_, []) != after_members.get(id_, [])):
                    changed_refs.append(reference(b or a))
                if a != b and b and b["kind"] == "agreement" and b["lifecycle"] == "accepted" and not after_members[id_]:
                    unclassified[id_] = reference(b)
            for id_ in sorted(set(before["relations"]) | set(after["relations"])):
                a, b = before["relations"].get(id_), after["relations"].get(id_)
                confirmed = any(side and side["confirmation"] == "confirmed" for side in (a, b))
                relevant = any(side and {side["from_node_id"], side["to_node_id"]} & (watch_nodes | scope_agreements) for side in (a, b))
                different = a is None or b is None or any(a[k] != b[k] for k in fields)
                # 草稿の所属整理だけでは、Scope全体の採択を止めない。
                sample = b or a
                if sample["relation_kind"] == "scoped_to" and all(
                    not side or side["nodes"][sample["from_node_id"]]["lifecycle"] in {"draft", "proposed"}
                    for side in (before if a else None, after if b else None)
                ):
                    different = False
                if confirmed and relevant and different:
                    changed_refs.append(reference(b or a, "relation"))
            before = after
        changed_refs = list({(r["type"], r["id"]): r for r in changed_refs}.values())
        require(not changed_refs, "照合した関連範囲が変わりました。", "CONTEXT_CHANGED", 409,
                consulted_at_revision=baseline["meta"]["graph_revision"], current_revision=current["meta"]["graph_revision"],
                changed_refs=refs(changed_refs), next_action="reconsult")
        if unclassified:
            values = [unclassified[k] for k in sorted(unclassified)]
            return [diagnostic("unclassified_changes", values[:20], "unverified", has_more=len(values) > 20, after_revision=baseline["meta"]["graph_revision"])]
        return []

    def _write(self, operation, request, conn, data, state):
        allowed = {"change_set", "record", "idempotency_key"} if operation == "save-draft" else {"proposal", "change_set", "context", "basis", "decision", "idempotency_key"}
        obj(request, allowed, allowed)
        key = string(request["idempotency_key"])
        require(bool(re.fullmatch(r"[A-Za-z0-9.:_-]{1,128}", key)), "idempotency_keyが不正です。")
        baseline = None
        if operation == "save-draft":
            normalized = dict(change_set=change_set(request["change_set"], state), record=record(request["record"]))
        else:
            obj(request["basis"], {"schema_version", "database_id", "graph_revision", "snapshot_id", "rules_version", "change_digest", "refs", "watch", "exploration_note"},
                {"schema_version", "database_id", "graph_revision", "snapshot_id", "rules_version", "change_digest", "refs", "watch", "exploration_note"})
            basis = request["basis"]
            integer(basis["graph_revision"], 0, 9007199254740991)
            # 成功済み再送の入力正規化にも、現在版でなく元の基準版を使用する。
            if basis["graph_revision"] <= state["meta"]["graph_revision"] and any(c["graph_revision"] == basis["graph_revision"] for c in data["commits"]):
                baseline = storage.state_at(data, basis["graph_revision"])
            normalized, _ = self._normalize({k: request[k] for k in ("proposal", "change_set", "context")}, baseline)
            normalized.update(basis=copy.deepcopy(basis), decision=record(request["decision"], True))
        request_digest = digest(dict(operation=operation, request=normalized))
        for previous in data["idempotency_records"]:
            if previous["idempotency_key"] == key:
                require(previous["request_digest"] == request_digest and previous["operation"] == operation, "同じキーに異なる入力が指定されています。", "IDEMPOTENCY_CONFLICT", 409)
                return previous["response"]
        diagnostics = []
        if operation == "apply":
            require(basis["database_id"] == state["meta"]["database_id"] and basis["schema_version"] == "basis-1", "basisのDBまたは形式が異なります。", "INVALID_BASIS")
            require(basis["rules_version"] == RULES, "照合規則が変わりました。", "RULES_CHANGED", 409)
            require(baseline is not None and baseline["meta"]["snapshot_id"] == basis["snapshot_id"], "基準の履歴を利用できません。", "BASIS_UNAVAILABLE", 409)
            body = {k: normalized[k] for k in ("proposal", "change_set", "context")}
            require(basis["change_digest"] == digest(body), "照合した変更内容と一致しません。", "INVALID_BASIS")
            for ref in refs(basis["refs"]):
                revision = baseline["revisions"].get(ref["revision_id"])
                require(revision is not None and revision["target_type"] == ref["type"] and revision["target_id"] == ref["id"],
                        "照合時の参照版が不足しています。", "BASIS_UNAVAILABLE", 409, next_action="reconsult")
            expected = self._basis(body, baseline)
            require(canonical(expected) == canonical(basis), "basisの参照集合・監視範囲が照合結果と一致しません。", "INVALID_BASIS")
            for op in normalized["change_set"]["operations"]:
                if op["op"].startswith("update_"):
                    type_ = op["op"].removeprefix("update_")
                    value = target(state, type_, op["id"])
                    require(value["revision_id"] == op["expected_revision_id"], "更新対象の版が変わりました。", "PRECONDITION_CHANGED", 409, changed_refs=[reference(value, type_)], next_action="reconsult")
            diagnostics = self._check_changes(data, baseline, state, basis)
            require(normalized["decision"]["semantic_review"] == "ready", "未解決の意味判断があります。", "UNRESOLVED_DECISION", 409)
        final, changed, created, updated = self._simulate(normalized["change_set"], state, True, operation == "save-draft")
        stamp, provenance_id = now(), uid()
        author = normalized["record"] if operation == "save-draft" else normalized["decision"]
        provenance = dict(id=provenance_id, commit_revision=final["meta"]["graph_revision"], target_refs=refs([*created.values(), *updated]),
                          actor=author["actor"], principal_refs=author["principal_refs"], reason=author["reason"], created_at=stamp,
                          source_refs=author["source_refs"] if operation == "save-draft" else normalized["proposal"]["source_refs"])
        if "execution_context" in author:
            provenance["execution_context"] = author["execution_context"]
        result = dict(created_refs=created, updated_refs=updated, commit_revision=final["meta"]["graph_revision"], provenance_id=provenance_id)
        if operation == "apply":
            provenance.update(proposal=normalized["proposal"], change_set=normalized["change_set"], decision=author,
                              consulted_basis=basis, validated_at_revision=state["meta"]["graph_revision"])
            result.update(consulted_at_revision=basis["graph_revision"], validated_at_revision=state["meta"]["graph_revision"], diagnostics=diagnostics)
        response = envelope(result, final["meta"])
        storage.write_commit(conn, data, final, changed, provenance, response, key, operation, request_digest)
        return response

    def _maintenance(self, operation, request):
        if operation == "init":
            obj(request, {})
            if self.path.exists():
                conn = storage.connect(self.path)
                try:
                    conn.execute("BEGIN")
                    data = storage.read(conn)
                    storage.validate_snapshot(data)
                finally:
                    conn.close()
            else:
                data = storage.initial()
                storage.publish(self.path, lambda temporary: storage.create_file(temporary, data))
            self.meta = data["meta"]
            return envelope(dict(api_version="v1", **self.meta, capabilities=OPERATIONS, limits=LIMITS), self.meta)
        obj(request, {"source", "format"}, {"source", "format"})
        source = Path(string(request["source"])).resolve()
        require(not self.path.exists() and not self.path.is_symlink(), "復元先が既に存在します。", "DESTINATION_EXISTS", 409)
        string(request["format"])
        require(request["format"] in {"sqlite", "json"}, "未対応の復元形式です。", "UNSUPPORTED_FORMAT")
        require(source.is_file(), "復元元が存在しません。", "TARGET_NOT_FOUND", 404)
        if request["format"] == "json":
            try:
                from .cli import decode_json
                data = decode_json(source.read_bytes())
            except (UnicodeError, ValueError):
                fail("INVALID_DATABASE", "復元元のJSONが不正です。")
        else:
            conn = storage.connect(source)
            try:
                conn.execute("BEGIN")
                require(conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLiteの整合性検査が失敗しました。", "INVALID_DATABASE")
                data = storage.read(conn)
            finally:
                conn.close()
        storage.validate_snapshot(data)
        storage.publish(self.path, lambda temporary: storage.create_file(temporary, data))
        self.meta = data["meta"]
        return envelope(dict(api_version="v1", **self.meta, capabilities=OPERATIONS, limits=LIMITS), self.meta)

    def _backup(self, operation, request, conn, data):
        obj(request, {"destination"} if operation == "backup" else {"destination", "format", "node_ids", "scope_ids"}, {"destination"})
        destination = string(request["destination"])
        format_ = "sqlite" if operation == "backup" else request.get("format", "json")
        string(format_)
        require(format_ in {"sqlite", "json", "markdown"} if operation == "backup" else format_ in {"json", "markdown"}, "未対応の出力形式です。", "UNSUPPORTED_FORMAT")
        require(format_ != "markdown", "Markdown投影は未対応です。", "UNSUPPORTED_FEATURE", capability="markdown_export")
        require(not ({"node_ids", "scope_ids"} & set(request)), "JSONは完全スナップショットだけを出力できます。")
        storage.validate_snapshot(data)
        def writer(temporary):
            if format_ == "json":
                Path(temporary).write_text(canonical(data) + "\n", encoding="utf-8")
            else:
                destination_conn = sqlite3.connect(temporary)
                try:
                    conn.backup(destination_conn)
                finally:
                    destination_conn.close()
        destination = storage.publish(destination, writer)
        return envelope(dict(format=format_, destination=destination, **{k: self.meta[k] for k in ("database_id", "graph_revision", "snapshot_id")}), self.meta)
