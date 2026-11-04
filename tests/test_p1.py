"""P1の検索範囲・読み取り専用投影・排他的公開を実DBで検証する。"""

import base64
import errno
import json
import re
import sqlite3
from unittest.mock import patch

from latis import Engine, projection, storage
from latis.model import CAPABILITIES, KINDS, NODE_KEYS, OPERATIONS, STATES, canonical, now, reference
from tests.support import ContractCase, node, relation


class P1Tests(ContractCase):
    def export(self, name="view", **selection):
        destination = self.directory / name
        result = self.ok("export", dict(format="markdown", destination=str(destination), **selection))
        self.assertEqual(result["destination"], str(destination))
        self.assertEqual(result["format"], "markdown")
        return destination, result

    def document(self, path):
        content = path.read_bytes()
        self.assertTrue(content.startswith(b"---\n"))
        metadata, body = content[4:].split(b"\n---\n", 1)
        return json.loads(metadata), body

    def projected(self, directory):
        return {self.document(path)[0]["id"]: self.document(path) for path in directory.glob("*/node-*.md")}

    def hierarchy(self):
        operations = [node(key, "scope", title=key) for key in ("root", "left", "right", "leaf", "candidate", "retired")]
        operations += [node(key, title=key) for key in ("direct", "deep", "unscoped", "excluded", "ended")]
        for ref_, a, b in (("rl", "root", "left"), ("rr", "root", "right"), ("ll", "left", "leaf"), ("rlf", "right", "leaf"), ("old", "root", "retired")):
            operations.append(relation(ref_, "$" + a, "$" + b, "contains"))
        operations.append(relation("candidate_edge", "$root", "$candidate", "contains", "candidate"))
        for a, b in (("direct", "root"), ("deep", "leaf"), ("excluded", "candidate"), ("ended", "retired")):
            operations.append(relation("membership_" + a, "$" + a, "$" + b, "scoped_to"))
        created = self.apply(*operations)["created_refs"]
        old = self.ok("relation-detail", dict(relation_id=created["old"]["id"]))["relation"]
        self.apply(dict(op="update_relation", id=old["id"], expected_revision_id=old["revision_id"], set=dict(lifecycle="retired")))
        return {key: self.current(ref_["id"]) for key, ref_ in created.items() if ref_["type"] == "node"}

    def test_P01_descendant_diamond_direct_and_unscoped(self):
        values = self.hierarchy()
        request = dict(scope_ids=[values["root"]["id"]])
        direct = self.ok("search", request)
        self.assertEqual([item["id"] for item in direct["items"]], [values["direct"]["id"]])
        expanded = self.ok("search", dict(**request, include_descendants=True))
        self.assertEqual(expanded["applied_filters"]["expanded_scope_ids"], sorted(values[key]["id"] for key in ("root", "left", "right", "leaf")))
        self.assertEqual([item["id"] for item in expanded["items"]], sorted(values[key]["id"] for key in ("direct", "deep")))
        self.assertEqual(next(item for item in expanded["items"] if item["id"] == values["deep"]["id"])["scope_ids"], [values["leaf"]["id"]])
        extra = self.ok("search", dict(**request, include_descendants=True, include_unscoped=True))
        self.assertEqual({item["id"] for item in extra["items"]}, {values[key]["id"] for key in ("direct", "deep", "unscoped")})

    def test_P02_multiple_roots_empty_scope_and_filters(self):
        values = self.hierarchy()
        roots = [values[key]["id"] for key in ("left", "right", "left")]
        result = self.ok("search", dict(scope_ids=roots, include_descendants=True, query="DEEP"))
        self.assertEqual(result["applied_filters"]["scope_ids"], sorted(set(roots)))
        self.assertEqual(result["applied_filters"]["expanded_scope_ids"], sorted({*roots, values["leaf"]["id"]}))
        self.assertEqual([item["id"] for item in result["items"]], [values["deep"]["id"]])
        for flag in (False, True):
            result = self.ok("search", dict(scope_ids=[], include_descendants=flag))
            self.assertEqual(result["applied_filters"]["expanded_scope_ids"], [])
            self.assertEqual(len(result["items"]), 5)
        self.error("search", dict(scope_ids=[values["direct"]["id"]], include_descendants=True), "INVALID_REQUEST")
        self.error("search", dict(scope_ids=["missing"], include_descendants=True), "TARGET_NOT_FOUND")

    def test_P03_cursor_binds_flag_and_expansion_and_stales_on_hierarchy_change(self):
        values = self.hierarchy()
        request = dict(scope_ids=[values["root"]["id"]], include_descendants=True, limit=1)
        first = self.ok("search", request)
        cursor = first["page"]["next_cursor"]
        second = self.ok("search", dict(**request, cursor=cursor))
        self.assertNotEqual(first["items"][0]["id"], second["items"][0]["id"])
        self.error("search", dict(request, cursor=cursor, include_descendants=False), "INVALID_REQUEST")
        decoded = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        decoded["filters"]["expanded_scope_ids"] = [values["root"]["id"]]
        changed = base64.urlsafe_b64encode(canonical(decoded).encode()).decode().rstrip("=")
        self.error("search", dict(**request, cursor=changed), "INVALID_REQUEST")
        self.apply(relation("new_child", values["root"]["id"], values["candidate"]["id"], "contains"))
        self.error("search", dict(**request, cursor=cursor), "CURSOR_STALE")

    def test_P04_descendants_do_not_expand_consult_watch(self):
        values = self.hierarchy()
        self.ok("search", dict(scope_ids=[values["root"]["id"]], include_descendants=True))
        plan = self.consult(node("new", lifecycle="draft"), context=dict(scope_ids=[values["root"]["id"]]))
        self.assertEqual(plan["basis"]["watch"]["scope_ids"], [values["root"]["id"]])
        self.assertNotIn(values["deep"]["id"], plan["basis"]["watch"]["node_ids"])
        self.apply(self.update(values["deep"], body="子孫だけの変更"))
        result = self.ok("apply", self.application(plan))
        self.assertGreater(result["validated_at_revision"], result["consulted_at_revision"])

    def test_P05_capabilities_and_disabled_optional_features(self):
        for result in (self.ok("meta", {}), self.ok("init", {})):
            self.assertEqual(result["capabilities"], list(CAPABILITIES))
        with patch.object(Engine, "capabilities", tuple(OPERATIONS)):
            self.assertEqual(self.ok("meta", {})["capabilities"], OPERATIONS)
            for op, request, capability in (("search", dict(scope_ids=[], include_descendants=True), "search_descendants"),
                                            ("export", dict(format="markdown", destination=str(self.directory / "disabled")), "markdown_export")):
                response = self.error(op, request, "UNSUPPORTED_FEATURE")
                self.assertEqual(response["errors"][0]["details"]["capability"], capability)
            self.assertEqual(self.ok("search", {})["items"], [])
        self.assertFalse((self.directory / "disabled").exists())

    def test_P06_all_kinds_and_terminal_states_are_exported(self):
        for kind in sorted(KINDS):
            self.create(kind=kind, lifecycle="draft")
        rejected = self.create(lifecycle="draft")
        self.save(self.update(rejected, lifecycle="rejected"))
        retired = self.create()
        self.apply(self.update(retired, lifecycle="retired"))
        old = self.create()
        self.apply(node("replacement"), self.update(old, lifecycle="superseded"), relation("replacement_edge", "$replacement", old["id"], "supersedes"))
        self.create(lifecycle="proposed")
        directory, result = self.export()
        expected = self.snapshot()
        self.assertEqual(set(self.projected(directory)), {n["id"] for n in expected["nodes"]})
        self.assertEqual({metadata["kind"] for metadata, _ in self.projected(directory).values()}, KINDS)
        self.assertEqual({metadata["lifecycle"] for metadata, _ in self.projected(directory).values()}, STATES)
        metadata, _ = self.document(directory / "index.md")
        self.assertEqual(metadata, {**{key: result[key] for key in ("database_id", "graph_revision", "snapshot_id")}, "spec_version": expected["meta"]["spec_version"], "selection": {}})

    def test_P07_scope_selection_is_direct_and_can_be_empty(self):
        values = self.hierarchy()
        self.save(relation("candidate_membership", values["unscoped"]["id"], values["root"]["id"], "scoped_to", "candidate"))
        created = self.apply(relation("ended_membership", values["excluded"]["id"], values["root"]["id"], "scoped_to"))["created_refs"]["ended_membership"]
        self.apply(dict(op="update_relation", id=created["id"], expected_revision_id=created["revision_id"], set=dict(lifecycle="retired")))
        directory, _ = self.export(scope_ids=[values["root"]["id"], values["root"]["id"]])
        self.assertEqual(set(self.projected(directory)), {values["direct"]["id"]})
        self.assertEqual(self.document(directory / "index.md")[0]["selection"], dict(scope_ids=[values["root"]["id"]]))
        empty, _ = self.export("empty", scope_ids=[values["left"]["id"]])
        self.assertEqual([p.name for p in empty.iterdir()], ["index.md"])
        other, _ = self.export("multiple", scope_ids=[values["leaf"]["id"], values["root"]["id"]])
        self.assertEqual(set(self.projected(other)), {values[key]["id"] for key in ("direct", "deep")})

    def test_P08_node_selection_normalizes_and_validates(self):
        first, second = self.create(), self.create(kind="scope")
        directory, _ = self.export(node_ids=[second["id"], first["id"], second["id"]])
        self.assertEqual(self.document(directory / "index.md")[0]["selection"], dict(node_ids=sorted([first["id"], second["id"]])))
        for selection, code in ((dict(node_ids=[]), "INVALID_REQUEST"), (dict(scope_ids=[]), "INVALID_REQUEST"),
                                (dict(node_ids=None), "INVALID_REQUEST"), (dict(scope_ids=None), "INVALID_REQUEST"),
                                (dict(node_ids=[first["id"]], scope_ids=[second["id"]]), "INVALID_REQUEST"),
                                (dict(scope_ids=[first["id"]]), "INVALID_REQUEST"), (dict(node_ids=["missing"]), "TARGET_NOT_FOUND"),
                                (dict(scope_ids=["missing"]), "TARGET_NOT_FOUND")):
            with self.subTest(selection=selection):
                self.error("export", dict(format="markdown", destination=str(self.directory / "invalid"), **selection), code)
                self.assertFalse((self.directory / "invalid").exists())

    def test_P09_front_matter_preserves_fields_and_exact_body_bytes(self):
        body = "\ufeff原文🙂\r\n---\n[リンク](../外)\n末尾の空白  \r\n\t改行なし"
        value = self.create(kind="artifact", lifecycle="draft", title="原文 | [題名](file:never)", body=body,
                            locator="file:/does-not-exist/latis-private", content_hash="sha256:" + "a" * 64)
        directory, _ = self.export(node_ids=[value["id"]])
        metadata, projected_body = self.document(directory / projection.filename(value))
        self.assertEqual(set(metadata), NODE_KEYS - {"body"} | {"scope_ids", "provenance_ids", "relations"})
        self.assertEqual({key: metadata[key] for key in NODE_KEYS - {"body"}}, {key: value[key] for key in NODE_KEYS - {"body"}})
        self.assertEqual(projected_body, body.encode("utf-8"))
        self.assertEqual(metadata["provenance_ids"], self.ok("detail", dict(node_id=value["id"]))["provenance_ids"])
        self.assertEqual(metadata["scope_ids"], [])
        self.assertEqual(metadata["relations"], [])

    def test_P10_relations_and_evidence_keep_outside_ids_and_fixed_revisions(self):
        agreement, outside = self.create(), self.create(kind="artifact", lifecycle="draft")
        proof = self.create(kind="artifact", lifecycle="draft", evidence=dict(subject_refs=[reference(outside)], method="検査", outcome="passed", observed_at=now(), actor="test"))
        self.apply(relation("verified", agreement["id"], proof["id"], "verified_by"), relation("old", proof["id"], outside["id"], "supports"))
        old = self.ok("relations", dict(node_id=proof["id"], relation_kinds=["supports"]))["items"][0]["relation"]
        self.apply(dict(op="update_relation", id=old["id"], expected_revision_id=old["revision_id"], set=dict(lifecycle="retired")))
        self.save(relation("candidate", proof["id"], agreement["id"], "supports", "candidate"))
        self.save(self.update(outside, body="証拠対象の現在版だけを更新"))
        directory, _ = self.export(node_ids=[proof["id"]])
        metadata, _ = self.document(directory / projection.filename(proof))
        snapshot = self.snapshot()
        expected = [dict(direction="out" if rel["from_node_id"] == proof["id"] else "in", relation=rel) for rel in snapshot["relations"] if proof["id"] in (rel["from_node_id"], rel["to_node_id"])]
        self.assertEqual(metadata["relations"], expected)
        self.assertEqual(metadata["evidence"]["subject_refs"], [reference(outside)])
        self.assertEqual(len(metadata["relations"]), 3)
        self.assertEqual(set(self.projected(directory)), {proof["id"]})
        self.assertNotIn(projection.filename(outside), (directory / "index.md").read_text())

    def test_P11_opaque_unicode_id_safe_path_and_markdown_escaping(self):
        original = self.create(title="|[外部](https://example.invalid) <img> `x`\n次の行")
        data = self.snapshot()
        opaque = "../../日本語\\dir\n|[リンク](x)🙂"
        data = json.loads(canonical(data).replace(canonical(original["id"]), canonical(opaque)))
        source = self.directory / "opaque.json"
        source.write_text(canonical(data), encoding="utf-8")
        other = Engine(self.directory / "opaque.sqlite")
        self.ok("restore", dict(format="json", source=str(source)), other)
        destination = self.directory / "opaque-view"
        self.ok("export", dict(format="markdown", destination=str(destination), node_ids=[opaque]), other)
        expected = "agreement/node-" + base64.urlsafe_b64encode(opaque.encode()).decode().rstrip("=") + ".md"
        self.assertTrue((destination / expected).is_file())
        self.assertEqual(self.document(destination / expected)[0]["id"], opaque)
        index = (destination / "index.md").read_text()
        self.assertNotIn("<img>", index.split("# LATIS", 1)[1])
        self.assertNotIn("[外部](", index)
        self.assertIn("&#124;", index)
        self.assertEqual(re.findall(r"\[本文\]\(([^)]+)\)", index), [expected])
        self.assertEqual(len(list(destination.rglob("*.md"))), 2)

    def test_P12_index_orders_nodes_and_links_only_existing_files(self):
        values = [self.create(title=f"題名{number}") for number in range(3)]
        directory, _ = self.export(node_ids=[value["id"] for value in reversed(values)])
        index = (directory / "index.md").read_text()
        paths = re.findall(r"\[本文\]\(([^)]+)\)", index)
        self.assertEqual(paths, [projection.filename(value) for value in sorted(values, key=lambda item: item["id"])])
        self.assertTrue(all((directory / path).is_file() for path in paths))

    def test_P13_one_snapshot_during_concurrent_wal_commit(self):
        value = self.create(kind="artifact", lifecycle="draft", body="投影開始時の版")
        with sqlite3.connect(self.engine.path) as connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        before = self.ok("meta", {})
        writer = projection.write
        def during_write(directory, state, selection, nodes):
            self.assertFalse((self.directory / "view").exists())
            other = Engine(self.engine.path)
            self.ok("save-draft", dict(change_set=dict(operations=[self.update(value, body="並行更新後の版")]), record=dict(actor="test", reason="並行更新"), idempotency_key="wal-change"), other)
            writer(directory, state, selection, nodes)
        with patch.object(projection, "write", side_effect=during_write):
            directory, result = self.export()
        self.assertEqual(result["snapshot_id"], before["snapshot_id"])
        self.assertEqual(self.document(directory / "index.md")[0]["snapshot_id"], before["snapshot_id"])
        self.assertEqual(self.document(directory / projection.filename(value))[1], value["body"].encode())
        self.assertEqual(self.current(value["id"])["body"], "並行更新後の版")

    def test_P14_existing_outputs_and_symlinks_are_never_replaced(self):
        destinations = [self.directory / key for key in ("empty", "nonempty", "file", "symlink")]
        destinations[0].mkdir()
        destinations[1].mkdir()
        (destinations[1] / "marker").write_text("既存の内容")
        destinations[2].write_text("既存ファイル")
        destinations[3].symlink_to(self.directory / "absent")
        for path in destinations:
            with self.subTest(path=path):
                self.error("export", dict(format="markdown", destination=str(path)), "DESTINATION_EXISTS")
        self.assertEqual((destinations[1] / "marker").read_text(), "既存の内容")
        self.assertEqual(destinations[2].read_text(), "既存ファイル")
        self.assertTrue(destinations[3].is_symlink())
        self.assertEqual(list(self.directory.glob(".latis-*")), [])

    def test_P15_publication_race_preserves_even_empty_competing_directory(self):
        rename = storage.rename_directory
        for name, marker in (("race-empty", False), ("race-marker", True), ("race-link", None)):
            destination = self.directory / name
            def racing(source, output):
                if marker is None:
                    output.symlink_to(self.directory / "missing")
                else:
                    output.mkdir()
                    if marker:
                        (output / "marker").write_text("競合側")
                rename(source, output)
            with patch.object(storage, "rename_directory", side_effect=racing):
                self.error("export", dict(format="markdown", destination=str(destination)), "DESTINATION_EXISTS")
            self.assertFalse((destination / "index.md").exists())
            if marker:
                self.assertEqual((destination / "marker").read_text(), "競合側")
            self.assertEqual(list(self.directory.glob(".latis-*")), [])

    def test_P16_write_sync_and_rename_failure_remove_staging(self):
        self.create()
        before = self.snapshot()
        for name, target_ in (("write", "latis.projection.write"), ("sync", "latis.storage.os.fsync"), ("rename", "latis.storage.rename_directory")):
            destination = self.directory / name
            def failure(*args):
                if name == "write":
                    (args[0] / "partial.md").write_text("未完成の出力")
                raise OSError(errno.EIO, "検査用のI/O失敗")
            with patch(target_, side_effect=failure):
                with self.assertRaises(OSError):
                    self.engine.execute("export", dict(format="markdown", destination=str(destination)))
            self.assertFalse(destination.exists())
            self.assertEqual(list(self.directory.glob(".latis-*")), [])
        self.assertEqual(self.snapshot(), before)

    def test_P17_projection_is_readonly_and_markdown_restore_is_rejected(self):
        value = self.create()
        before = self.snapshot()
        directory, _ = self.export()
        (directory / projection.filename(value)).write_text("変更した投影")
        (directory / "index.md").unlink()
        self.assertEqual(self.current(value["id"]), value)
        self.assertEqual(self.snapshot(), before)
        other = Engine(self.directory / "no-import.sqlite")
        self.error("restore", dict(format="markdown", source=str(directory)), "UNSUPPORTED_FORMAT", other)
        self.assertFalse(other.path.exists())

    def test_P18_cli_and_full_json_restore_remain_compatible(self):
        values = self.hierarchy()
        response = self.cli("search", dict(scope_ids=[values["root"]["id"]], include_descendants=True))
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertEqual(len(json.loads(response.stdout)["data"]["items"]), 2)
        response = self.cli("export", dict(format="markdown", destination=str(self.directory / "cli-view"), node_ids=[values["deep"]["id"]]))
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertEqual(len(self.projected(self.directory / "cli-view")), 1)
        data = self.snapshot()
        self.assertEqual(data["format_version"], 2)
        self.assertEqual(len(data["nodes"]), 11)
        self.error("export", dict(format="json", destination=str(self.directory / "subset"), scope_ids=[values["root"]["id"]]), "INVALID_REQUEST")
        source = self.directory / "full.json"
        source.write_text(canonical(data), encoding="utf-8")
        other = Engine(self.directory / "restored.sqlite")
        result = self.ok("restore", dict(source=str(source), format="json"), other)
        self.assertEqual(result["capabilities"], list(CAPABILITIES))
        self.assertEqual(self.ok("search", dict(scope_ids=[values["root"]["id"]], include_descendants=True), other), self.ok("search", dict(scope_ids=[values["root"]["id"]], include_descendants=True)))

    def test_P19_invalid_destination_and_cli_io_exit(self):
        self.error("export", dict(format="markdown", destination=""), "INVALID_REQUEST")
        self.error("export", dict(format="markdown", destination="bad\0path"), "INVALID_REQUEST")
        blocked = self.directory / "blocked"
        blocked.write_text("親がファイル")
        response = self.cli("export", dict(format="markdown", destination=str(blocked / "view")))
        self.assertEqual(response.returncode, 2)
        response_data = json.loads(response.stdout)
        self.assertFalse(response_data["ok"])
        self.assertEqual(response_data["errors"][0]["code"], "INTERNAL_ERROR")
        self.assertTrue(response.stderr)
