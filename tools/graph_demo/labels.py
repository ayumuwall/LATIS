"""LLMへ共有するオブジェクトID対応表。同じDBの読取結果だけから更新する。"""

from contextlib import contextmanager
from collections import Counter
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading

from latis.model import Error
from tools.graph_demo.projection import project


class DisplayLog:
    """表示用のイベントだけを変換し、コマンド・応答の原記録は変更しない。"""

    def __init__(self, db, renderer):
        self.db = Path(db).resolve()
        self.renderer = renderer
        self.meta = None
        self.anchor = None
        self.labels = {}
        self.pattern = None

    def refresh(self):
        view = project(self.db)
        if self.anchor is not None:
            ancestor = next((c for c in view["commits"] if c["graph_revision"] == self.anchor["graph_revision"]), None)
            if (view["meta"]["database_id"] != self.anchor["database_id"] or ancestor is None
                    or ancestor["snapshot_id"] != self.anchor["snapshot_id"]):
                raise OSError("オブジェクトIDの基準DBまたは履歴が変わりました。")
        if self.meta == view["meta"]:
            return
        numbers = view["display_numbers"]
        labels = {n["id"]: f'{numbers[n["id"]]}「{n["title"]}」' for n in view["nodes"]}
        relation_counts = Counter((r["from_node_id"],r["relation_kind"],r["to_node_id"]) for r in view["relations"])
        for relation in view["relations"]:
            key = (relation["from_node_id"],relation["relation_kind"],relation["to_node_id"])
            extra = f'（内部ID: {relation["id"]}）' if relation_counts[key] > 1 else ""
            labels[relation["id"]] = f'{numbers[key[0]]} → {key[1]} → {numbers[key[2]]}〈関係〉{extra}'
        counts = {}
        for revision in sorted(view["revisions"], key=lambda r: (r["commit_revision"], r["revision_id"])):
            target = revision["target_id"]
            counts[target] = counts.get(target, 0) + 1
            labels[revision["revision_id"]] = f'{labels[target]}〈第{counts[target]}版〉'
        self.labels = labels
        # 不透明なIDの完全な字句だけを対象にし、hash等の一部分を変えない。
        self.pattern = re.compile(r'(?<![\w])(?:' + '|'.join(re.escape(k) for k in sorted(labels, key=len, reverse=True)) + r')(?![\w])') if labels else None
        self.meta = view["meta"]
        self.anchor = self.meta

    def text(self, value):
        return self.pattern.sub(lambda match: self.labels[match[0]], value) if self.pattern else value

    def present(self, value):
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.present(item) for item in value]
        if isinstance(value, dict):
            return {self.text(key): self.present(item) for key, item in value.items()}
        return value

    def __call__(self, event):
        try:
            self.refresh()
        except (Error, sqlite3.Error, OSError):
            # 古い対応表を別のsnapshotへ流用しない。
            self.meta = None
            self.labels = {}
            self.pattern = None
            print("[オブジェクトID未確認] 対応表を取得できません。このイベントは原記録で表示します。", flush=True)
        self.renderer(self.present(event))


def write_index(db, destination):
    view = project(Path(db).resolve())
    payload = dict(format="latis-display-numbers",format_version=1,meta=view["meta"],items=[
        dict(number=view["display_numbers"][node["id"]],id=node["id"],revision_id=node["revision_id"],kind=node["kind"],title=node["title"])
        for node in view["nodes"]])
    destination = Path(destination)
    with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=destination.parent,prefix=".latis-numbers-",delete=False) as temporary:
        temp = Path(temporary.name)
        json.dump(payload,temporary,ensure_ascii=False,indent=2)
        temporary.write("\n")
    try:
        os.replace(temp,destination)
    finally:
        temp.unlink(missing_ok=True)
    return payload


@contextmanager
def updating_index(db, destination):
    """実行中も番号表を更新する。公開ファイルは完成した一つのsnapshotで置き換える。"""
    write_index(db,destination)
    stop = threading.Event()
    def watch():
        while not stop.wait(.25):
            try:
                write_index(db,destination)
            except (Error,sqlite3.Error,OSError):
                # 書込み中の一時的なロックでは、最後の正常な表を保持する。
                pass
    thread = threading.Thread(target=watch,daemon=True)
    thread.start()
    try:
        yield Path(destination)
    finally:
        stop.set();thread.join(timeout=2)
        write_index(db,destination)
