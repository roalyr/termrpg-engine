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
            self.assertTrue("not checked" in warning or "reserved feature" in warning, warning)


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
        self.edit("pack.json", lambda m: m["files"].__setitem__("recipes", ["recipes.json"]))
        self.assertIn("there is no schema for 'recipes' yet", self.errors())

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
        self.status_effects({"op": "if", "if": {"check": "size", "max": 7}, "then": []})
        self.assertIn("unknown size class '7'", self.errors())

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

    # --- World and objects ---

    def location(self, loc_id, change):
        def apply(data):
            change(next(e for e in data["entries"] if e["id"] == loc_id))
        self.edit("locations.json", apply)

    def placement(self, loc_id, pl_id, change):
        self.location(loc_id, lambda loc: change(next(p for p in loc["placements"] if p["id"] == pl_id)))

    def test_placement_outside_grid(self):
        self.placement("room_a", "pl_a_crate", lambda p: p.__setitem__("at", [9, 9]))
        self.assertIn("position [9, 9] is outside the grid", self.errors())

    def test_placement_on_empty_tile_of_shaped_room(self):
        self.placement("room_b", "pl_b_terminal", lambda p: p.__setitem__("at", [4, 0]))
        self.assertIn("position [4, 0] is outside the grid", self.errors())

    def test_placement_position_taken(self):
        self.placement("room_a", "pl_a_crate", lambda p: p.__setitem__("at", [0, 2]))
        self.assertIn("position [0, 2] is already taken by 'pl_a_door_b'", self.errors())

    def test_rows_must_match_size(self):
        self.location("room_b", lambda loc: loc["grid"]["rows"].pop())
        self.assertIn("rows must be 5 strings of 7 characters", self.errors())

    def test_placement_ids_unique_across_locations(self):
        self.placement("room_b", "pl_b_terminal", lambda p: p.__setitem__("id", "pl_a_crate"))
        self.assertIn("duplicate placement 'pl_a_crate'", self.errors())

    def test_unknown_placement_reference(self):
        self.placement("room_a", "pl_a_door_b", lambda p: p["exit"].__setitem__("entry", "pl_missing"))
        self.assertIn("unknown placement 'pl_missing'", self.errors())

    def test_exit_arrival_must_be_in_destination(self):
        self.placement("room_a", "pl_a_door_b", lambda p: p["exit"].__setitem__("entry", "pl_a_crate"))
        self.assertIn("exit arrives at 'pl_a_crate', which is not in 'room_b'", self.errors())

    def test_exit_into_template(self):
        self.placement("room_a", "pl_a_door_b", lambda p: p["exit"].update(location="room_template_a", entry=None) or p["exit"].pop("entry"))
        self.assertIn("exit leads to 'room_template_a', which is a template", self.errors())

    def test_exit_needs_one_destination(self):
        self.placement("room_a", "pl_a_door_b", lambda p: p["exit"].__setitem__("zone", "zone_a"))
        self.assertIn("exit: use only one of: location, zone", self.errors())

    def test_location_entry_elsewhere(self):
        self.location("room_b", lambda loc: loc.__setitem__("entry", "pl_a_crate"))
        self.assertIn("entry 'pl_a_crate' is placed in another location", self.errors())

    def test_start_entry_elsewhere(self):
        self.edit("pack.json", lambda m: m["start"].__setitem__("entry", "pl_b_terminal"))
        self.assertIn("start.entry 'pl_b_terminal' is not in 'room_a'", self.errors())

    def test_start_in_template(self):
        self.edit("pack.json", lambda m: m["start"].update(location="room_template_a") or m["start"].pop("entry"))
        self.assertIn("start.location 'room_template_a' is a template", self.errors())

    def test_placement_state_must_belong_to_object(self):
        self.placement("room_a", "pl_a_crate", lambda p: p.__setitem__("state", "state_open"))
        self.assertIn("state 'state_open' is not one of the object's states", self.errors())

    def test_state_glyph_must_belong_to_object(self):
        self.edit("objects.json", lambda d: d["entries"][2].__setitem__("state_glyphs", {"state_open": "x"}))
        self.assertIn("state_glyphs names 'state_open'", self.errors())

    def test_region_loop(self):
        self.edit("regions.json", lambda d: d["entries"][0].__setitem__("parent", "region_a_1"))
        self.assertIn("is its own ancestor", self.errors())

    def test_zone_pool_needs_templates(self):
        self.edit("zones.json", lambda d: d["entries"][0]["room_pool"][0].__setitem__("location", "room_a"))
        self.assertIn("'room_a' is not a template", self.errors())

    def test_this_is_not_a_placement_reference(self):
        report = validate_pack(self.pack)
        self.assertFalse(any("'this'" in e for e in report.errors))

    # --- Items ---

    def item(self, item_id, change):
        def apply(data):
            change(next(e for e in data["entries"] if e["id"] == item_id))
        self.edit("items.json", apply)

    def test_unknown_item_kind(self):
        self.item("misc_key", lambda i: i.__setitem__("kind", "weapon"))
        self.assertIn("kind: unknown kind 'weapon'", self.errors())

    def test_frame_needs_slots(self):
        self.item("frame_a", lambda i: i.pop("slots"))
        self.assertIn("missing required field 'slots'", self.errors())

    def test_fields_belong_to_their_kind(self):
        self.item("material_a", lambda i: i.__setitem__("slot_type", "slot_frame_a"))
        self.assertIn("unknown field 'slot_type'", self.errors())

    def test_implant_needs_body_slot(self):
        self.item("implant_a", lambda i: i.__setitem__("slot_type", "slot_frame_a"))
        self.assertIn("slot type 'slot_frame_a' is a frame slot; an implant needs a body slot", self.errors())

    def test_module_needs_frame_slot(self):
        self.item("module_tool", lambda i: i.__setitem__("slot_type", "slot_body_a"))
        self.assertIn("slot type 'slot_body_a' is a body slot; a module needs a frame slot", self.errors())

    def test_stacked_items_cannot_wear(self):
        self.item("material_a", lambda i: i.__setitem__("condition", 3))
        self.assertIn("items that stack can't have a condition", self.errors())

    def test_unknown_stat_key(self):
        self.item("frame_a", lambda i: i["stats"].__setitem__("stat_missing", 1))
        self.assertIn("stats.stat_missing: unknown stat 'stat_missing'", self.errors())

    def test_unknown_grade(self):
        self.item("frame_a", lambda i: i.__setitem__("grade", "grade_missing"))
        self.assertIn("unknown grade 'grade_missing'", self.errors())

    def test_budget_keys_are_fixed(self):
        self.item("module_tool", lambda i: i["uses"].__setitem__("fuel", 1))
        self.assertIn("uses: unknown field 'fuel'", self.errors())

    def test_grade_colour_from_palette(self):
        self.edit("vocab.json", lambda v: v["grades"][0].__setitem__("colour", "pink"))
        self.assertIn("grades[0].colour: must be one of", self.errors())

    # --- Actions and skills ---

    def action(self, action_id, change):
        def apply(data):
            change(next(e for e in data["entries"] if e["id"] == action_id))
        self.edit("actions.json", apply)

    def skill(self, skill_id, change):
        def apply(data):
            change(next(e for e in data["entries"] if e["id"] == skill_id))
        self.edit("skills.json", apply)

    def test_unknown_target(self):
        self.action("action_strike", lambda a: a.__setitem__("target", "everyone"))
        self.assertIn("target: must be one of", self.errors())

    def test_tile_name_length(self):
        self.action("action_burst", lambda a: a.__setitem__("short", "Much too long"))
        self.assertIn("short: must be at most 8 characters", self.errors())

    def test_consumes_item_or_tag(self):
        self.action("action_burst", lambda a: a["cost"]["consumes"].__setitem__("tag", "tag_a"))
        self.assertIn("consumes: use only one of: item, tag", self.errors())

    def test_scaled_amount_needs_one_source(self):
        self.action("action_strike", lambda a: a["effects"][0]["amount"].__setitem__("skill", "skill_a"))
        self.assertIn("amount: use only one of: stat, skill", self.errors())

    def test_trains_unknown_skill(self):
        self.action("action_strike", lambda a: a.__setitem__("trains", {"skill_missing": 1}))
        self.assertIn("unknown skill 'skill_missing'", self.errors())

    def test_end_encounter_result(self):
        self.action("action_retreat", lambda a: a["effects"][0]["then"][0].__setitem__("result", "draw"))
        self.assertIn("result: must be one of", self.errors())

    def test_item_grants_unknown_action(self):
        self.item("module_tool", lambda i: i.__setitem__("actions", ["action_missing"]))
        self.assertIn("unknown action 'action_missing'", self.errors())

    def test_levels_in_order(self):
        self.skill("skill_a", lambda k: k["levels"].reverse())
        self.assertIn("levels must be listed once each, lowest first", self.errors())

    def test_xp_must_rise(self):
        self.skill("skill_a", lambda k: k["levels"][2].__setitem__("xp", 30))
        self.assertIn("each level must need more xp than the one before", self.errors())

    def test_level_above_max(self):
        self.edit("pack.json", lambda m: m.__setitem__("settings", {"skill_max_level": 3}))
        self.assertIn("level 5 is above skill_max_level (3)", self.errors())

    def test_level_one_starts_at_zero(self):
        self.skill("skill_a", lambda k: k["levels"][0].__setitem__("xp", 5))
        self.assertIn("level 1 needs 0 xp", self.errors())

    # --- Characters, encounters, loot ---

    def character(self, char_id, change):
        def apply(data):
            change(next(e for e in data["entries"] if e["id"] == char_id))
        self.edit("characters.json", apply)

    def test_everything_referenced_is_checked(self):
        report = validate_pack(TEST_PACK)
        self.assertFalse(any("not checked" in w for w in report.warnings), report.warnings)

    def test_template_has_no_location(self):
        self.character("char_drone", lambda ch: ch.__setitem__("location", "room_a"))
        self.assertIn("templates are spawned by encounters and zones", self.errors())

    def test_character_on_a_placement(self):
        self.character("char_npc", lambda ch: ch.__setitem__("at", [1, 4]))
        self.assertIn("position [1, 4] is already taken by placement 'pl_a_crate'", self.errors())

    def test_character_on_wall(self):
        self.character("char_npc", lambda ch: ch.__setitem__("at", [0, 0]))
        self.assertIn("is not a floor tile of 'room_a'", self.errors())

    def test_character_on_taken_tile(self):
        self.character("char_npc", lambda ch: ch.__setitem__("at", [4, 1]))
        self.assertIn("already taken by placement 'pl_a_locker'", self.errors())

    def test_at_needs_location(self):
        self.character("char_npc", lambda ch: ch.pop("location"))
        self.assertIn("'at' needs a location", self.errors())

    def test_frame_must_be_a_frame(self):
        self.character("char_player", lambda ch: ch.__setitem__("frame", "module_tool"))
        self.assertIn("'module_tool' is worn as a frame but is a module", self.errors())

    def test_fitted_must_be_modules(self):
        self.character("char_player", lambda ch: ch["fitted"].append("implant_a"))
        self.assertIn("fitted lists 'implant_a', which is an implant, not a module", self.errors())

    def test_too_many_modules_for_slots(self):
        self.character("char_player", lambda ch: ch["fitted"].extend(["module_tool", "module_tool"]))
        self.assertIn("no free 'slot_frame_hand' slot in the frame for 'module_tool'", self.errors())

    def test_fitted_without_frame(self):
        self.character("char_player", lambda ch: ch.pop("frame"))
        self.assertIn("has fitted modules but wears no frame", self.errors())

    def test_power_budget(self):
        self.item("module_system", lambda i: i["uses"].__setitem__("power", 9))
        self.assertIn("fitted gear needs 10 power, the loadout provides 6", self.errors())

    def test_heat_load(self):
        self.item("module_system", lambda i: i["uses"].__setitem__("heat", 8))
        self.assertIn("constant heat 8 leaves no room below maximum heat 8", self.errors())

    def test_cargo_capacity(self):
        self.character("char_player", lambda ch: ch["inventory"].append({"item": "misc_key", "count": 4}))
        self.assertIn("inventory needs 7 cargo stacks, the loadout carries 6", self.errors())

    def test_implant_needs_body_slot_on_character(self):
        self.character("char_npc", lambda ch: ch["body"].pop("slots"))
        self.assertIn("no free 'slot_body_a' slot in the body for 'implant_a'", self.errors())

    def test_skill_level_above_max(self):
        self.character("char_player", lambda ch: ch["skills"].__setitem__("skill_a", 6))
        self.assertIn("skill 'skill_a' at level 6 is above skill_max_level (5)", self.errors())

    def test_player_is_not_a_template(self):
        self.edit("pack.json", lambda m: m["start"].__setitem__("player", "char_drone"))
        self.assertIn("start.player 'char_drone' is a template", self.errors())

    def test_player_placed_elsewhere(self):
        self.character("char_player", lambda ch: ch.__setitem__("location", "room_b"))
        self.assertIn("start.player 'char_player' is placed in 'room_b'", self.errors())

    def test_leader_loop(self):
        self.character("char_npc", lambda ch: ch.__setitem__("leader", "char_npc"))
        self.assertIn("ends up leading itself", self.errors())

    def test_unique_character_takes_no_count(self):
        self.edit("encounters.json", lambda d: d["entries"][0]["allies"][0].__setitem__("count", 2))
        self.assertIn("'char_npc' is unique; only templates take a count", self.errors())

    def test_loot_table_rolls_itself(self):
        self.edit("loot.json", lambda d: d["entries"][1]["entries"].append({"table": "loot_crate"}))
        self.assertIn("loot table 'loot_crate' rolls itself", self.errors())

    def test_unknown_loot_table(self):
        self.character("char_drone", lambda ch: ch.__setitem__("loot", "loot_missing"))
        self.assertIn("unknown loot table 'loot_missing'", self.errors())

    def test_art_width(self):
        self.character("char_drone", lambda ch: ch["art"].append("x" * 22))
        self.assertIn("must be at most 21 characters", self.errors())

    def test_reserved_feature_warns(self):
        self.edit("pack.json", lambda m: m.__setitem__("extends", ["base"]))
        report = validate_pack(self.pack)
        self.assertEqual(report.errors, ())
        self.assertTrue(any("extends: uses a reserved feature" in w for w in report.warnings))


if __name__ == "__main__":
    unittest.main()
