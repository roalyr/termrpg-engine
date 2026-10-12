import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.content import Content, PackError, load_pack

ROOT = Path(__file__).resolve().parent.parent
TEST_PACK = ROOT / "packs" / "test_scifi"


class TestLoadPack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = load_pack(TEST_PACK)

    def test_loads_every_kind(self):
        for namespace in ("region", "location", "object", "item", "action", "skill", "character",
                          "encounter", "loot_table", "event", "modification", "string", "placement",
                          "tag", "stat", "status", "slot_type", "grade", "object_state", "phase"):
            self.assertTrue(self.content.all(namespace), namespace)

    def test_lookup(self):
        self.assertEqual(self.content.get("item", "gear_light_suit")["kind"], "gear")
        with self.assertRaisesRegex(KeyError, "unknown item 'nope'"):
            self.content.get("item", "nope")
        self.assertEqual(self.content.all("no_such_namespace"), {})

    def test_records_are_read_only(self):
        item = self.content.get("item", "gear_light_suit")
        with self.assertRaises(TypeError):
            item["name"] = "Changed"
        self.assertIsInstance(item["slots"], tuple)
        with self.assertRaises(TypeError):
            self.content.index["item"]["new"] = {}

    def test_defaults_from_the_schemas(self):
        tool = self.content.get("item", "gear_cutter")
        self.assertEqual(tool["stack"], 1)
        self.assertEqual(tool["dismantle"]["learn"], True)
        self.assertEqual(tool["mod_slots"], 1)
        self.assertEqual(self.content.get("item", "gear_shield")["uses"]["stat_power"], 3)
        self.assertEqual(self.content.get("slot_type", "slot_hand")["equip_at_workshop"], True)
        self.assertEqual(self.content.get("stat", "stat_armor")["budget"], False)
        search = self.content.get("object", "obj_crate")["interactions"][0]
        self.assertEqual(search["repeat"], "daily")
        door = self.content.get("object", "obj_door")["interactions"][1]
        self.assertEqual(door["time"], 1)
        self.assertEqual(door["repeat"], "always")

    def test_defaults_inside_effects_and_conditions(self):
        strike = self.content.get("action", "action_strike")
        self.assertEqual(strike["effects"][0]["subject"], "target")   # damage hits the target
        self.assertEqual(strike["target"], "enemy")
        guard = self.content.get("action", "action_guard")
        condition = guard["ai"]["when"]
        self.assertEqual(condition["subject"], "self")
        crate = self.content.get("object", "obj_crate")["interactions"][0]
        roll = crate["effects"][1]["then"][0]
        self.assertEqual(roll, {"op": "roll_loot", "table": "loot_crate", "rolls": 1, "subject": "self"})

    def test_settings_defaults(self):
        self.assertEqual(self.content.settings["skill_max_level"], 5)
        self.assertEqual(self.content.settings["relation_default"], 0)

    def test_vocabulary_views(self):
        self.assertEqual(self.content.role_stat("health"), "stat_health")
        self.assertEqual(self.content.role_stat("cargo"), "stat_cargo")
        self.assertEqual(self.content.sizes[3]["name"], "person")
        self.assertEqual([r["min"] for r in self.content.relation_levels], [-50, 0, 50])
        self.assertEqual([r["rank"] for r in self.content.ranks], [0, 1])

    def test_placements_merge_their_template(self):
        door_b = self.content.get("placement", "storage_door")
        self.assertEqual(door_b["location"], "loc_storage")
        self.assertEqual(door_b["name"], "Door")                 # from the template
        self.assertEqual(door_b["state"], "state_open")          # placement override
        self.assertEqual(door_b["at"], (0, 3))
        self.assertEqual(door_b["exit"]["location"], "loc_workshop")
        self.assertEqual([i["id"] for i in door_b["interactions"]], ["open", "close"])
        door_a = self.content.get("placement", "workshop_door")
        self.assertEqual(door_a["state"], "state_closed")        # template's first state
        passage = self.content.get("placement", "workshop_passage")
        self.assertEqual(passage["name"], "Tunnel hatch")         # name override
        self.assertIsNone(passage["state"])                        # no states at all

    def test_placement_interactions_merge_by_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            shutil.copytree(TEST_PACK, pack)
            data = json.loads((pack / "locations.json").read_text())
            crate = next(p for p in data["entries"][0]["placements"] if p["id"] == "workshop_crate")
            crate["interactions"] = [
                {"id": "search", "label": "Search carefully", "effects": []},
                {"id": "kick", "label": "Kick it", "effects": []}]
            crate["tags"] = ["tag_filter"]
            (pack / "locations.json").write_text(json.dumps(data))
            placed = load_pack(pack).get("placement", "workshop_crate")
        self.assertEqual([i["label"] for i in placed["interactions"]], ["Search carefully", "Kick it"])
        self.assertEqual(placed["tags"], ("tag_filter",))

    def test_palette_has_the_defaults_and_the_packs_colours(self):
        self.assertEqual((self.content.palette["grey"], self.content.palette["rust"]), (245, 130))
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            shutil.copytree(TEST_PACK, pack)
            data = json.loads((pack / "palette.json").read_text())
            data["entries"] = [e for e in data["entries"] if e["id"] != "grey"]       # left out: the default
            next(e for e in data["entries"] if e["id"] == "red")["code"] = 160      # changed for this game
            (pack / "palette.json").write_text(json.dumps(data))
            palette = load_pack(pack).palette
        self.assertEqual((palette["grey"], palette["red"]), (245, 160))

    def test_text_and_messages(self):
        self.assertEqual(self.content.text("@str_greeting"), "Hello.")
        self.assertEqual(self.content.text("Plain words."), "Plain words.")
        self.assertEqual(self.content.message("enter_location", location="Workshop"), "You enter Workshop.")
        self.assertEqual(self.content.message("not_written"), "not_written")

    def test_warnings_are_kept(self):
        self.assertTrue(any("reserved" in w for w in self.content.warnings))

    def test_invalid_pack_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            shutil.copytree(TEST_PACK, pack)
            vocab = json.loads((pack / "vocab.json").read_text())
            vocab["stats"][0]["role"] = "cargo"
            (pack / "vocab.json").write_text(json.dumps(vocab))
            with self.assertRaises(PackError) as caught:
                load_pack(pack)
        self.assertIn("stat role 'cargo' must be given to exactly one stat", str(caught.exception))
        self.assertTrue(caught.exception.report.errors)


class TestEngineNamesNoContent(unittest.TestCase):
    """The engine and its UI must never name content: no test-pack id may appear in their code."""

    def test_no_pack_ids_in_engine_code(self):
        content = load_pack(TEST_PACK)
        ids = {str(i) for namespace in content.index.values() for i in namespace}
        sources = {p: p.read_text(encoding="utf-8")
                   for folder in ("engine", "tui") for p in (ROOT / folder).rglob("*.py")}
        sources[ROOT / "play.py"] = (ROOT / "play.py").read_text(encoding="utf-8")
        self.assertTrue(sources)
        for path, text in sources.items():
            quoted = set(re.findall(r"""["']([a-z][a-z0-9_]*)["']""", text))
            self.assertEqual(quoted & ids, set(), path.name)


if __name__ == "__main__":
    unittest.main()
