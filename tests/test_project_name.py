"""必須のDB名と、旧HEADの正規CLIで作った履歴の明示移行を検査する。"""

from contextlib import closing
import copy
import json
import sqlite3

from latis import Engine, storage
from latis.model import SPEC, RULES, LEGACY_SPEC, LEGACY_RULES, Error
from tests.support import ContractCase, ROOT


class ProjectNameTests(ContractCase):
    def test_initialization_requires_a_valid_name_and_never_overwrites(self):
        destination = self.directory / "new.sqlite"
        engine = Engine(destination)
        for request in ({}, *({"project_name": value} for value in (None, "", " ", " 前後", "前後 ", "改\n行", "a" * 241))):
            self.error("init", request, "INVALID_REQUEST", engine)
            self.assertFalse(destination.exists())
        name = 'ログ管理サービス <検証> & "名前"'
        first = self.ok("init", dict(project_name=name), engine)
        before = destination.read_bytes()
        self.assertEqual(first["project_name"], name)
        self.assertEqual(self.ok("init", dict(project_name=name), engine), first)
        self.error("init", dict(project_name="別の名前"), "PROJECT_NAME_MISMATCH", engine)
        self.assertEqual(destination.read_bytes(), before)
        self.assertEqual(self.ok("meta", {}, engine)["project_name"], name)

    def test_name_is_required_in_persisted_metadata_and_restore(self):
        for value in (None, "", " "):
            snapshot = storage.initial("有効な名前")
            if value is None:
                del snapshot["meta"]["project_name"]
            else:
                snapshot["meta"]["project_name"] = value
            with self.assertRaises(Error) as error:
                storage.validate_snapshot(snapshot)
            self.assertEqual(error.exception.code, "INVALID_DATABASE")
        name = self.ok("meta", {})["project_name"]
        for format_ in ("json", "sqlite"):
            source = self.directory / ("backup." + format_)
            self.ok("export" if format_ == "json" else "backup", dict(destination=str(source)))
            before = source.read_bytes()
            restored = Engine(self.directory / ("restored-" + format_ + ".sqlite"))
            self.assertEqual(self.ok("restore", dict(source=str(source), format=format_), restored)["project_name"], name)
            self.assertEqual(source.read_bytes(), before)

    def test_explicit_legacy_migration_keeps_history_and_successful_retries(self):
        # 86a8d9bの実装でinit → save-draft → consult/apply → exportした素材。
        original = json.loads((ROOT / "tests/fixtures/project-name-legacy.json").read_text())
        retry = json.loads((ROOT / "tests/fixtures/project-name-legacy-retry.json").read_text())
        for format_ in ("json", "sqlite"):
            source = self.directory / ("legacy." + format_)
            if format_ == "json":
                source.write_text(json.dumps(original))
            else:
                storage.create_file(source, original)
                with sqlite3.connect(source) as conn:
                    conn.execute("PRAGMA user_version=2")
            before = source.read_bytes()
            target = Engine(self.directory / ("named-" + format_ + ".sqlite"))
            request = dict(source=str(source), format=format_)
            self.error("restore", request, "UNSUPPORTED_FORMAT", target)
            self.error("migrate", request, "INVALID_REQUEST", target)
            self.assertFalse(target.path.exists())
            result = self.ok("migrate", dict(**request, project_name="ログ管理サービス"), target)
            self.assertEqual(result["project_name"], "ログ管理サービス")
            self.assertEqual((result["spec_version"], result["rules_version"]), (SPEC, RULES))
            with closing(storage.connect(target.path)) as conn:
                migrated = storage.read(conn)
            self.assertEqual(migrated["format_version"], 3)
            self.assertEqual({key: migrated["meta"][key] for key in ("database_id", "graph_revision", "snapshot_id")},
                             {key: original["meta"][key] for key in ("database_id", "graph_revision", "snapshot_id")})
            for key in storage.TABLES:
                self.assertEqual(migrated[key], original[key])
            old_response = next(r["response"] for r in original["idempotency_records"] if r["idempotency_key"] == retry["idempotency_key"])
            self.assertEqual(target.execute("apply", retry), old_response)
            self.assertEqual((old_response["meta"]["spec_version"], old_response["meta"]["rules_version"]), (LEGACY_SPEC, LEGACY_RULES))
            uncommitted = dict(retry, idempotency_key="uncommitted-old-basis")
            self.error("apply", uncommitted, "RULES_CHANGED", target)
            self.assertEqual(source.read_bytes(), before)
            self.error("migrate", dict(**request, project_name="別の名前"), "DESTINATION_EXISTS", target)

    def test_migration_rejects_corrupt_history_and_unsupported_versions(self):
        original = json.loads((ROOT / "tests/fixtures/project-name-legacy.json").read_text())
        for label in ("corrupt", "unsupported"):
            snapshot = copy.deepcopy(original)
            if label == "corrupt":
                snapshot["revisions"].pop()
            else:
                snapshot["meta"]["rules_version"] = "unknown"
            source = self.directory / (label + ".json")
            source.write_text(json.dumps(snapshot))
            target = Engine(self.directory / (label + ".sqlite"))
            self.error("migrate", dict(source=str(source), format="json", project_name="移行先"),
                       "INVALID_DATABASE" if label == "corrupt" else "UNSUPPORTED_FORMAT", target)
            self.assertFalse(target.path.exists())

    def test_renaming_uses_an_explicit_new_copy_and_keeps_source(self):
        self.create()
        original = self.snapshot()
        source = self.directory / "source.json"
        source.write_text(json.dumps(original))
        before = source.read_bytes()
        target = Engine(self.directory / "renamed.sqlite")
        self.ok("migrate", dict(source=str(source), format="json", project_name="新しいプロジェクト名"), target)
        self.assertEqual(self.ok("meta", {}, target)["project_name"], "新しいプロジェクト名")
        self.assertEqual(source.read_bytes(), before)
        with closing(storage.connect(target.path)) as conn:
            migrated = storage.read(conn)
        for key in storage.TABLES:
            self.assertEqual(migrated[key], original[key])

    def test_known_historical_versions_cannot_disagree_with_the_consulted_rules(self):
        self.create()
        snapshot = self.snapshot()
        response = snapshot["idempotency_records"][0]["response"]
        response["meta"].update(spec_version=LEGACY_SPEC,rules_version=LEGACY_RULES)
        with self.assertRaises(Error) as error:
            storage.validate_snapshot(snapshot)
        self.assertEqual(error.exception.code,"INVALID_DATABASE")
