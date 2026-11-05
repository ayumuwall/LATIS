"""閲覧中のScopeと版を、固定番号で読める単一のspec.mdへ投影する。"""

import html
import json

from latis import projection, storage
from latis.engine import basis_status
from latis.model import memberships, require
from tools.graph_demo.projection import DISPLAY_PREFIXES, display_numbers, read_snapshot

KINDS = {"agreement":"合意", "proposal":"提案", "intent":"意図", "rationale":"理由", "question":"問い",
         "scope":"範囲", "artifact":"成果物", "task":"タスク"}
STATES = {"draft":"草稿", "proposed":"提案", "accepted":"採択", "rejected":"不採用", "retired":"終了", "superseded":"置換済み"}
BASIS = {"current":"記録した版は一致", "changed":"根拠版が変更", "untracked":"対象版は未追跡", "not_applicable":"版比較の対象外"}


def inline(value):
    """見出し・リンク・表のラベルだけをエスケープする。本文は原文を使う。"""
    text = html.escape(str(value),quote=False).replace("\r"," ").replace("\n"," ")
    for char in ("\\", "`", "*", "_", "[", "]", "|"):
        text = text.replace(char,"\\" + char)
    return text


def comment(name, value):
    # 不透明なIDやタイトルにコメント終端があっても、外側のMarkdownへ出さない。
    encoded = json.dumps(value,ensure_ascii=True,separators=(",", ":")).replace("<","\\u003c").replace(">","\\u003e")
    return f"<!-- {name} {encoded} -->"


def scope_markdown(path, database_id, revision, snapshot_id, scope_id):
    data = read_snapshot(path)
    require(data["meta"]["database_id"] == database_id, "表示中のDBから切り替わりました。", "BASIS_UNAVAILABLE", 409)
    state = storage.state_at(data, revision)
    require(state["meta"]["snapshot_id"] == snapshot_id, "表示中の履歴から分岐しました。", "BASIS_UNAVAILABLE", 409)
    selection, nodes = projection.select(dict(scope_ids=[scope_id]),state)
    historical = dict(data,revisions=[r for r in data["revisions"] if r["commit_revision"] <= revision])
    numbers = display_numbers(historical)
    scope = state["nodes"][scope_id]
    direct = {node["id"] for node in nodes}
    included = {node["id"]:node for node in nodes}
    relations = sorted(state["relations"].values(),key=lambda rel:rel["id"])
    # 正本に保存された理由を参照文脈として同じ文書へ収める。Scope所属は追加しない。
    for relation in relations:
        reason = state["nodes"][relation["from_node_id"]]
        if (relation["to_node_id"] in direct and state["nodes"][relation["to_node_id"]]["kind"] == "agreement"
                and relation["relation_kind"] == "supports" and relation["confirmation"] == "confirmed"
                and relation["lifecycle"] == "active" and reason["kind"] == "rationale"):
            included[reason["id"]] = reason
    anchors = set(included) | {scope_id}
    scopes = memberships(state)

    def number(id_):
        return numbers[id_]

    def reference(id_):
        label = number(id_) + " " + inline(state["nodes"][id_]["title"])
        return f"[{label}](#{number(id_).lower()})" if id_ in anchors else label + "（範囲外の参照）"

    def node_metadata(node):
        return dict(id=node["id"],revision_id=node["revision_id"],kind=node["kind"],lifecycle=node["lifecycle"],
                    number=number(node["id"]),scope_ids=scopes[node["id"]],
                    role="scope" if node["id"] == scope_id else "direct" if node["id"] in direct else "context")

    order = {kind:index for index,kind in enumerate(DISPLAY_PREFIXES)}
    ordered = sorted(included.values(),key=lambda node:(order[node["kind"]],int(number(node["id"]).split("-")[1])))
    lines = [f'<a id="{number(scope_id).lower()}"></a>',f"# {number(scope_id)} {inline(scope['title'])} Specification", "",
             comment("latis-source:",dict(meta=state["meta"],selection=selection,scope=node_metadata(scope))), "",
             f"版: rev {revision}", "", "## Purpose", "", scope["body"], "", "## Requirements", ""]

    def record(node, tag):
        id_ = node["id"]
        lines.extend([f'<a id="{number(id_).lower()}"></a>', f"### {tag}{number(id_)} {inline(node['title'])}", "",
                      comment("latis-node:",node_metadata(node)), "", f"状態: {STATES[node['lifecycle']]}", "", node["body"], ""])
        if id_ not in direct:
            lines.extend(["参照文脈として収録。", ""])
        if scopes[id_]:
            lines.extend(["所属: " + " / ".join(reference(scope) for scope in scopes[id_]), ""])
        attached = [rel for rel in relations if id_ in (rel["from_node_id"],rel["to_node_id"])]
        reasons = [rel for rel in attached if rel["to_node_id"] == id_ and rel["relation_kind"] == "supports"
                   and rel["lifecycle"] == "active" and rel["confirmation"] == "confirmed"
                   and state["nodes"][rel["from_node_id"]]["kind"] == "rationale"]
        if reasons:
            lines.extend(["理由: " + " / ".join(reference(rel["from_node_id"]) for rel in reasons), ""])
        if attached:
            lines.extend(["#### Relations", "", "| 向き | 関係 | 相手 | 状態 | 根拠版 |", "| --- | --- | --- | --- | --- |"])
            for rel in attached:
                outgoing = rel["from_node_id"] == id_
                other = rel["to_node_id"] if outgoing else rel["from_node_id"]
                status = ("確定" if rel["confirmation"] == "confirmed" else "候補") + " / " + ("有効" if rel["lifecycle"] == "active" else "終了")
                lines.append(f"| {'→' if outgoing else '←'} | `{rel['relation_kind']}` | {reference(other)} | {status} | {BASIS[basis_status(rel,state)]} |")
            references = [dict(id=rel["id"],revision_id=rel["revision_id"],relation_kind=rel["relation_kind"],
                from_node_id=rel["from_node_id"],from_number=number(rel["from_node_id"]),
                to_node_id=rel["to_node_id"],to_number=number(rel["to_node_id"])) for rel in attached]
            lines.extend(["",comment("latis-relations:",references), ""])
        if node["evidence"]:
            evidence = node["evidence"]
            outcome = {"passed":"成功", "failed":"失敗", "inconclusive":"判定できず"}[evidence["outcome"]]
            lines.extend(["#### Evidence", "", f"結果: {outcome}", "", "方法: " + evidence["method"], "", "対象:", ""])
            for ref in evidence["subject_refs"]:
                current = state["nodes"][ref["id"]]["revision_id"] == ref["revision_id"]
                target = reference(ref["id"]) if current else number(ref["id"]) + " " + inline(state["nodes"][ref["id"]]["title"])
                lines.append(f"- {target}（{'記録した対象版は一致' if current else '過去の対象版'}）")
            lines.append("")

    accepted = [node for node in ordered if node["kind"] == "agreement" and node["lifecycle"] == "accepted"]
    for node in accepted:
        record(node,"Requirement: ")
    if not accepted:
        lines.extend(["この範囲に採択済みの合意は登録されていません。", ""])
    others = [node for node in ordered if node["kind"] == "agreement" and node["lifecycle"] != "accepted"]
    if others:
        lines.extend(["## Other Agreements", ""])
        for node in others:
            record(node,"Agreement: ")
    context = [node for node in ordered if node["kind"] != "agreement" and node["id"] != scope_id]
    if context:
        lines.extend(["## Context", ""])
        for node in context:
            record(node,KINDS[node["kind"]] + ": ")
    return ("\n".join(lines).rstrip()+"\n").encode("utf-8"), f"{number(scope_id)}.md"
