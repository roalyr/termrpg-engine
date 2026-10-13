"""Playtesting: the pack's starts, the stale-save warning, and the command line with the dev menu."""
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from core.pack import validate_pack
from core.uipack import validate_ui_pack
from engine import save, starts
from engine.content import load_pack
from engine.state import day_of, new_game
from lib.ui import default_ui
from tui import app
from tools.lib.complete import Completer
from tui.dev import Console, state_lines

ROOT = Path(__file__).resolve().parent.parent
TEST_PACK = ROOT / "packs" / "test_scifi"
CONTENT = load_pack(TEST_PACK)
UI = default_ui()


class StartsTest(unittest.TestCase):
    def test_a_start_is_a_new_game_then_its_effects(self):
        s = starts.begin(CONTENT, 1, "start_storage")
        me = s.characters[s.player]
        self.assertEqual(me.location, "loc_storage")
        self.assertIn("gear_cutter", [i.item for i in me.inventory])
        self.assertGreaterEqual(s.flags["flag_power"], 1)
        self.assertIsNotNone(starts.begin(CONTENT, 1, "start_fight").encounter)      # what it sets off is settled
        juno = starts.begin(CONTENT, 1, "start_with_juno").characters["char_juno"]
        self.assertEqual(juno.leader, "char_player")
        with self.assertRaises(KeyError):
            starts.begin(CONTENT, 1, "start_nowhere")

    def test_the_checker_reads_starts_like_any_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            shutil.copytree(TEST_PACK, pack)
            data = json.loads((pack / "starts.json").read_text())
            data["entries"][0]["effects"].append({"op": "give_item", "item": "gear_missing"})
            data["entries"][1]["effects"].append({"op": "set_flag", "flag": "flag_power", "value": 1,
                                                  "subject": {"role": "hero"}})
            data["entries"].append({"id": "start_storage", "name": "Twice", "effects": []})
            (pack / "starts.json").write_text(json.dumps(data))
            errors = "\n".join(validate_pack(pack).errors)
        self.assertIn("unknown item 'gear_missing'", errors)
        self.assertIn("role 'hero' used outside an event", errors)
        self.assertIn("duplicate start 'start_storage'", errors)

    def test_play_refuses_an_unknown_start(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(app.run(TEST_PACK, Path(tempfile.mkdtemp()) / "s.json", 1, True, start="start_nowhere"), 1)
        self.assertIn("No start 'start_nowhere'", out.getvalue())
        self.assertIn("start_fight", out.getvalue())


class StaleSaveTest(unittest.TestCase):
    def test_a_save_knows_when_the_pack_changed_since(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack, path = Path(tmp) / "pack", Path(tmp) / "slot1.json"
            shutil.copytree(TEST_PACK, pack)
            content = load_pack(pack)
            save.save(content, new_game(content, 1), path)
            self.assertFalse(save.older_than_pack(content, path))
            strings = json.loads((pack / "strings.json").read_text())
            strings["entries"][0]["text"] = "Changed."
            (pack / "strings.json").write_text(json.dumps(strings))
            changed = load_pack(pack)
            self.assertNotEqual(changed.fingerprint, content.fingerprint)
            self.assertTrue(save.older_than_pack(changed, path))
            save.save(changed, save.load(changed, path), path)        # saved again: it's up to date
            self.assertFalse(save.older_than_pack(changed, path))
            data = json.loads(path.read_text())
            del data["pack_fingerprint"]                                # saves from before fingerprints: no warning
            path.write_text(json.dumps(data))
            self.assertFalse(save.older_than_pack(changed, path))

    def test_the_warning_has_words_in_the_default_ui_pack(self):
        self.assertNotEqual(UI.word("save_older_than_pack"), "save_older_than_pack")


class ConsoleTest(unittest.TestCase):
    """The command line and the dev menu, driven with key names as the game passes them on."""

    def setUp(self):
        self.state = new_game(CONTENT, 1)
        self.fresh = False
        self.console = Console(CONTENT, UI, False, lambda: self.state, self.put)

    def put(self, state, fresh=False):
        self.state, self.fresh = state, fresh

    def keys(self, *keys):
        for key in keys:
            if len(key) > 1 and key not in ("enter", "esc", "backspace", "up", "down", "left", "right", "tab"):
                for letter in key:
                    self.console.handle(letter)
            else:
                self.console.handle(key)

    def menu(self, entry):
        self.keys("dev", "enter", entry, "enter")

    def test_only_known_commands_and_ops(self):
        self.keys("nonsense", "enter")
        self.assertIn("Unknown op 'nonsense'", self.console.render(48, 24))
        self.keys("esc")
        self.assertTrue(self.console.closed)

    def test_tab_completes_ops_fields_and_ids(self):
        self.keys("gi", "tab", "it", "tab", "gear_")
        self.assertEqual(self.console.form.value, "give_item item=gear_")
        text = self.console.render(48, 24)
        self.assertIn("gear_cutter  Cutter", text)
        self.assertIn("Fields: item* count subject", text)
        self.keys("down", "down", "tab")                     # several match: Tab takes the pick
        self.assertEqual(self.console.form.value, "give_item item=gear_cutter ")
        self.keys("enter")
        self.assertTrue(self.console.closed)
        self.assertIn("gear_cutter", [i.item for i in self.state.characters[self.state.player].inventory])

    def test_typed_effects_are_checked_and_name_characters(self):
        self.keys("give_item item=gear_nope", "enter")
        self.assertIn("unknown item 'gear_nope'", self.console.render(48, 24))
        self.keys(*["backspace"] * 30, "join_party subject=char_juno", "enter")
        self.assertTrue(self.console.closed)
        self.assertEqual(self.state.characters["char_juno"].leader, "char_player")

    def test_the_menu_fits_the_phone_screen_and_esc_closes(self):
        self.keys("/dev", "enter")
        text = self.console.render(48, 24)
        for words in ("Give an item", "Go to a location", "State", "Start again from a start"):
            self.assertIn(words, text)
        self.keys("esc")
        self.assertTrue(self.console.closed)

    def test_give_go_and_set_through_effects(self):
        self.menu("give")
        self.keys("odd metal", "enter", "backspace", "2", "enter")
        self.assertTrue(self.console.closed)
        me = self.state.characters[self.state.player]
        self.assertEqual(sum(i.count for i in me.inventory if i.item == "material_odd_metal"), 2)
        self.console = Console(CONTENT, UI, False, lambda: self.state, self.put)
        self.menu("go to")
        self.keys("storage", "enter")
        self.assertEqual(self.state.characters[self.state.player].location, "loc_storage")
        self.console = Console(CONTENT, UI, False, lambda: self.state, self.put)
        self.menu("set a flag")
        self.keys("enter", "backspace", "7", "enter")
        self.assertEqual(self.state.flags["flag_power"], 7)

    def test_next_day_and_a_fight(self):
        self.menu("next day")
        self.assertEqual(day_of(CONTENT, self.state.turn), 2)
        self.console = Console(CONTENT, UI, False, lambda: self.state, self.put)
        self.menu("encounter")
        self.keys("enter")
        self.assertIsNotNone(self.state.encounter)

    def test_an_effect_as_json_is_checked_first(self):
        self.menu("type an effect")
        self.keys('{"op": "give_item", "item": "gear_nope"}', "enter")
        self.assertIn("unknown item 'gear_nope'", self.console.render(48, 24))      # ids checked, as typed lines
        self.keys(*["backspace"] * 50, '{"op": "nonsense"}', "enter")
        self.assertFalse(self.console.closed)
        self.keys(*["backspace"] * 30, '{"op": "set_flag", "flag": "flag_power", "add": 3}', "enter")
        self.assertTrue(self.console.closed)
        self.assertEqual(self.state.flags["flag_power"], 3)

    def test_state_and_starting_again(self):
        self.menu("state")
        text = self.console.render(48, 40)
        self.assertIn("Day 1", text)
        self.assertIn("flag_power 0", text)
        self.keys("esc")                                       # back to the menu, its filter kept
        self.keys(*["backspace"] * 5, "start again", "enter", "juno", "enter")
        self.assertTrue(self.fresh)
        self.assertEqual(self.state.characters["char_juno"].leader, "char_player")

    def test_state_lines_name_people_and_events(self):
        lines = "\n".join(state_lines(CONTENT, starts.begin(CONTENT, 1, "start_with_juno")))
        self.assertIn("char_juno: loc_workshop (party)", lines)
        self.assertIn("juno → char_player", lines)
        self.assertIn("event_rest [day_start]", lines)


class CompleterTest(unittest.TestCase):
    """Completion from the schemas and a pack's ids, as the console and the tools use it."""

    def setUp(self):
        self.c = Completer(lambda ns: [(i, str(r.get("name", i))) for i, r in CONTENT.all(ns).items()], {"dev": ""})

    def texts(self, line):
        return [s.text for s in self.c.suggest(line)[1]]

    def test_ops_then_fields_then_values(self):
        self.assertIn("dev", self.texts(""))
        self.assertNotIn("if", self.texts(""))                       # effects inside effects: JSON
        self.assertEqual(self.texts("set_f"), ["set_flag"])
        self.assertEqual(self.texts("set_flag fl"), ["flag="])
        self.assertEqual(self.texts("set_flag flag=flag_power "), ["value=", "add="])
        self.assertEqual(self.texts("move_to location=loc_s"), ["loc_storage", "loc_side_room"])
        self.assertEqual(self.texts("set_state object=thi"), ["this"])
        self.assertIn("char_juno", self.texts("join_party subject="))
        self.assertIn("party", self.texts("join_party subject="))

    def test_completing_goes_as_far_as_the_suggestions_agree(self):
        self.assertEqual(self.c.complete("set_state object=storage_d"), "set_state object=storage_door ")
        self.assertEqual(self.c.complete("set_state object=st"), "set_state object=storage_")
        self.assertEqual(self.c.complete("give_item c"), "give_item count=")

    def test_building_an_effect(self):
        self.assertEqual(self.c.build("give_item item=gear_cutter count=2"),
                         ({"op": "give_item", "item": "gear_cutter", "count": 2}, ""))
        self.assertEqual(self.c.build("change_relation of=char_juno toward=player amount=10")[0]["of"],
                         {"character": "char_juno"})
        self.assertEqual(self.c.build('give_item item=gear_cutter count={"min": 1, "max": 3}')[0]["count"],
                         {"min": 1, "max": 3})
        self.assertIn("missing required field 'item'", self.c.build("give_item")[1])
        self.assertIn("has no field 'itm'", self.c.build("give_item itm=x")[1])
        self.assertIn("Write it as JSON", self.c.build("if")[1])


class CommandKeyTest(unittest.TestCase):
    def test_ui_packs_cant_bind_the_command_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "ui"
            shutil.copytree(ROOT / "packs" / "ui" / "default", folder)
            keys = json.loads((folder / "keys.json").read_text())
            keys.setdefault("bindings", {})["wait"] = "/"
            (folder / "keys.json").write_text(json.dumps(keys))
            self.assertTrue(validate_ui_pack(folder).errors)


if __name__ == "__main__":
    unittest.main()
