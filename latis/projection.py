"""同じ読み取りスナップショットから作る、編集元にしないMarkdown投影。"""

import base64
import string
from pathlib import Path

from .model import canonical, memberships, require, strings


def select(request, state):
    require(not ("node_ids" in request and "scope_ids" in request), "node_idsとscope_idsは同時指定できません。")
    selection = {}
    for key in ("node_ids", "scope_ids"):
        if key not in request:
            continue
        selection[key] = strings(request[key], True)
        for id_ in selection[key]:
            require(id_ in state["nodes"], "対象が存在しません。", "TARGET_NOT_FOUND", 404, target_id=id_)
            if key == "scope_ids":
                require(state["nodes"][id_]["kind"] == "scope", "scope_idsにはScopeを指定してください。")
    scopes = memberships(state)
    selected = set(selection.get("node_ids", state["nodes"]))
    if "scope_ids" in selection:
        selected = {id_ for id_ in selected if set(scopes[id_]) & set(selection["scope_ids"])}
    return selection, [state["nodes"][id_] for id_ in sorted(selected)]


def filename(node):
    encoded = base64.urlsafe_b64encode(node["id"].encode("utf-8")).decode("ascii").rstrip("=")
    return f'{node["kind"]}/node-{encoded}.md'


def cell(value):
    # 本文や不透明なIDが表・リンク・HTMLとして解釈されないよう表示する。
    return "".join(f"&#{ord(char)};" if char in string.punctuation or ord(char) < 32 else char for char in value)


def write(directory, state, selection, nodes):
    directory = Path(directory)
    scopes = memberships(state)
    attached = {node["id"]: [] for node in nodes}
    for rel in sorted(state["relations"].values(), key=lambda item: item["id"]):
        for endpoint, direction in (("from_node_id", "out"), ("to_node_id", "in")):
            if rel[endpoint] in attached:
                attached[rel[endpoint]].append(dict(direction=direction, relation=rel))
    for node in nodes:
        metadata = {key: value for key, value in node.items() if key != "body"}
        metadata.update(scope_ids=scopes[node["id"]],
                        provenance_ids=state["revisions"][node["revision_id"]]["provenance_ids"], relations=attached[node["id"]])
        path = directory / filename(node)
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(("---\n" + canonical(metadata) + "\n---\n" + node["body"]).encode("utf-8"))
    metadata = {key: state["meta"][key] for key in ("database_id", "graph_revision", "snapshot_id", "spec_version")}
    metadata["selection"] = selection
    rows = ["---", canonical(metadata), "---", "# LATIS Markdown投影", "",
            "読み取り専用の投影です。編集してもDBへ反映されません。", "",
            "| ID | title | kind | lifecycle | ファイル |", "| --- | --- | --- | --- | --- |"]
    for node in nodes:
        fields = [cell(node[key]) for key in ("id", "title", "kind", "lifecycle")]
        rows.append("| " + " | ".join([*fields, f"[本文]({filename(node)})"]) + " |")
    (directory / "index.md").write_bytes(("\n".join(rows) + "\n").encode("utf-8"))
