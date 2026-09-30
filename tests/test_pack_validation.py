import json
import shutil
import tempfile
import unittest
from pathlib import Path

from core import schema
from core.pack import validate_pack, SCHEMA_DIR

TEST_PACK = Path(__file__).resolve().parent.parent / "packs" / "test"


class TestSchemaFiles(unittest.TestCase):
    def test_schemas_resolve_and_use_supported_keywords(self):
        self.assertEqual(schema.schema_problems(schema.load_schemas(SCHEMA_DIR)), [])

    def test_schema_versions_agree(self):
        schemas = schema.load_schemas(SCHEMA_DIR)
        version = schemas["pack.schema.json"]["properties"]["schema_version"]["const"]
        for name, doc in schemas.items():
            self.assertEqual(doc.get("x-schema-version"), version, name)


class TestTestPack(unittest.TestCase):
    def test_test_pack_is_valid(self):
        report = validate_pack(TEST_PACK)
        self.assertEqual(report.errors, ())
        for warning in report.warnings:
            self.assertIn("not checked", warning)


class TestPackErrors(unittest.TestCase):
    """Breaks a copy of the test pack one way at a time and checks the message."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.pack = Path(self.temp.name) / "pack"
        shutil.copytree(TEST_PACK, self.pack)

    def tearDown(self):
        self.temp.cleanup()

    def edit(self, file_name, change):
        path = self.pack / file_name
        data = json.loads(path.read_text())
        change(data)
        path.write_text(json.dumps(data))

    def errors(self):
        return "\n".join(validate_pack(self.pack).errors)

    def status_effects(self, *effects):
        self.edit("vocab.json", lambda v: v["statuses"][0].__setitem__("on_turn", list(effects)))

    def test_missing_manifest(self):
        (self.pack / "pack.json").unlink()
        self.assertIn("pack.json: file not found", self.errors())

    def test_invalid_json_reports_line(self):
        (self.pack / "vocab.json").write_text('{\n  "stats": [,]\n}')
        self.assertIn("vocab.json: line 2", self.errors())

    def test_wrong_schema_version(self):
        self.edit("pack.json", lambda m: m.__setitem__("schema_version", 2))
        self.assertIn("schema_version: must be 1", self.errors())

    def test_kind_without_schema(self):
        self.edit("pack.json", lambda m: m["files"].__setitem__("items", ["items.json"]))
        self.assertIn("there is no schema for 'items' yet", self.errors())

    def test_path_outside_pack_rejected(self):
        self.edit("pack.json", lambda m: m["files"].__setitem__("vocab", ["../vocab.json"]))
        self.assertIn("files.vocab[0]", self.errors())

    def test_unknown_field(self):
        self.edit("vocab.json", lambda v: v["slot_types"][0].__setitem__("colour", "red"))
        self.assertIn("slot_types[0]: unknown field 'colour'", self.errors())

    def test_bad_id(self):
        self.edit("vocab.json", lambda v: v["tags"][0].__setitem__("id", "Tag A"))
        self.assertIn("tags[0].id: 'Tag A' does not match", self.errors())

    def test_duplicate_id(self):
        self.edit("vocab.json", lambda v: v["tags"].append({"id": "tag_a", "name": "again"}))
        self.assertIn("duplicate tag 'tag_a'", self.errors())

    def test_unknown_op(self):
        self.status_effects({"op": "dmg", "amount": 1})
        self.assertIn("unknown op 'dmg'", self.errors())

    def test_effect_without_op(self):
        self.status_effects({"amount": 1})
        self.assertIn("on_turn[0]: needs 'op'", self.errors())

    def test_bad_condition_names_the_forms(self):
        self.status_effects({"op": "if", "if": {"alll": []}, "then": []})
        self.assertIn("needs 'check', or one of: all, any, not", self.errors())

    def test_exclusive_fields(self):
        self.status_effects({"op": "take_item", "item": "item_a", "tag": "tag_a"})
        self.assertIn("use only one of: item, tag", self.errors())

    def test_named_character_subject_reports_the_id(self):
        self.status_effects({"op": "apply_status", "status": "status_stun", "subject": {"character": "Bad Id"}})
        self.assertIn("subject.character: 'Bad Id' does not match", self.errors())

    def test_dangling_reference(self):
        self.status_effects({"op": "damage", "amount": 1, "damage_type": "dmg_missing"})
        self.assertIn("unknown damage type 'dmg_missing'", self.errors())

    def test_nested_reference_in_condition(self):
        self.status_effects({"op": "if", "if": {"check": "status", "status": "status_missing"}, "then": []})
        self.assertIn("unknown status 'status_missing'", self.errors())

    def test_unnamed_size(self):
        self.status_effects({"op": "if", "if": {"check": "size", "max": 4}, "then": []})
        self.assertIn("unknown size class '4'", self.errors())

    def test_seeded_range_and_bounds(self):
        self.status_effects({"op": "damage", "amount": {"min": 1}, "damage_type": "dmg_a"})
        self.assertIn("missing required field 'max'", self.errors())

    def test_role_given_twice(self):
        self.edit("vocab.json", lambda v: v["stats"][1].__setitem__("role", "health"))
        errors = self.errors()
        self.assertIn("stat role 'health' must be given to exactly one stat (found stat_health, stat_power)", errors)
        self.assertIn("stat role 'power' must be given to exactly one stat (found none)", errors)

    def test_health_must_be_pool(self):
        self.edit("vocab.json", lambda v: v["stats"][0].pop("kind"))
        self.assertIn("stat 'stat_health' has role 'health' and must be a pool", self.errors())

    def test_relation_settings(self):
        self.edit("pack.json", lambda m: m.__setitem__("settings", {"relation_min": 10, "relation_max": 5}))
        self.assertIn("relation_min must be below relation_max", self.errors())

    def test_reserved_feature_warns(self):
        self.edit("pack.json", lambda m: m.__setitem__("extends", ["base"]))
        report = validate_pack(self.pack)
        self.assertEqual(report.errors, ())
        self.assertTrue(any("extends: uses a reserved feature" in w for w in report.warnings))


if __name__ == "__main__":
    unittest.main()
