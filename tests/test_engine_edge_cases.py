"""
Edge cases found by a code review of the rebuilt engine: one test (or a few) per finding.
Cases the test pack can't show are played on a temporary copy of it with a small change.
"""
import json
import os
import pty
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import uipack
from core.pack import validate_pack
from engine import build, encounter, events, stats, turns, world
from engine.content import load_pack
from engine.effects import choose_option, run
from engine.frozen import freeze
from engine.state import Ctx, new_game
from tui import app, text
from tui.ui import default_ui, ui_dir_for

ROOT = Path(__file__).resolve().parent.parent
CONTENT = load_pack(ROOT / "packs" / "test")
PLAYER, NPC = "char_player", "char_npc"
UI = default_ui()


def me(state):
    return state.characters[PLAYER]


def do(state, *effects, who=PLAYER):
    return run(CONTENT, state, Ctx(self_id=who), [freeze(e) for e in effects])


def health(state, cid=PLAYER):
    return stats.current(CONTENT, state.characters[cid], "stat_health")


def slot_of(state, item_id, group=None):
    return next(slot for slot, inst in stats.held(me(state))
                if inst.item == item_id and (group is None or slot[0] == group))


def answer_everything(state, content=CONTENT):
    """Settles, answering any morning question with its first option."""
    state = events.settle(content, state)
    while state.pending is not None:
        state = events.settle(content, choose_option(content, state, 0))
    return state


class PackCopy:
    """A temporary copy of the test pack to change one thing in."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "test"
        shutil.copytree(ROOT / "packs" / "test", self.dir)

    def edit(self, name, change):
        path = self.dir / name
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def entry(self, data, entry_id):
        return next(e for e in data["entries"] if e["id"] == entry_id)

    def load(self):
        return load_pack(self.dir)

    def close(self):
        self.tmp.cleanup()


class TestModifyItem(unittest.TestCase):
    def test_rolled_stat_amounts_are_kept_as_numbers(self):           # finding 1
        s = do(new_game(CONTENT, 1), {"op": "modify_item", "pick": {"item": "frame_a"},
                                      "stats": {"stat_armor": {"min": 1, "max": 2}}, "subject": "self"})
        armor = stats.item_view(CONTENT, me(s).frame)["stats"]["stat_armor"]
        self.assertIn(armor, (1, 2))
        self.assertGreaterEqual(stats.stat(CONTENT, me(s), "stat_armor"), 1)

    def test_one_off_a_stack_needs_a_cargo_stack(self):                 # finding 11
        s = new_game(CONTENT, 1)
        free = int(stats.budget_provided(CONTENT, me(s), "cargo")) - len(me(s).inventory)
        s = do(s, *[{"op": "give_item", "item": "misc_key", "count": 1, "subject": "self"}] * free)
        self.assertEqual(len(me(s).inventory), stats.budget_provided(CONTENT, me(s), "cargo"))   # full
        before = me(s).inventory
        s = do(s, {"op": "modify_item", "pick": {"item": "consumable_a"}, "name_suffix": "Odd", "subject": "self"})
        self.assertEqual(me(s).inventory, before)
        self.assertIn(CONTENT.message("cargo_full", item="Consumable A"), [m.text for m in s.messages])


class TestDefeatOutsideFights(unittest.TestCase):
    def test_the_player_gets_up_and_can_be_hurt_again(self):          # finding 2
        pack = PackCopy()
        try:
            pack.edit("characters.json", lambda d: pack.entry(d, PLAYER).pop("on_defeat"))
            content = pack.load()
            hurt = [freeze({"op": "damage", "amount": 999, "damage_type": "dmg_a", "subject": "self"})]
            s = run(content, new_game(content, 1), Ctx(self_id=PLAYER), hurt)
            self.assertFalse(s.characters[PLAYER].down)
            self.assertEqual(stats.current(content, s.characters[PLAYER], "stat_health"), 1)
            s = run(content, s, Ctx(self_id=PLAYER), hurt)            # not immune: down, and up again
            self.assertIn(content.message("character_down", character="Player"), [m.text for m in s.messages])
        finally:
            pack.close()

    def test_on_defeat_healing_isnt_undone(self):
        pack = PackCopy()
        try:
            pack.edit("characters.json", lambda d: pack.entry(d, PLAYER).update(
                on_defeat=[{"op": "restore", "stat": "stat_health", "amount": 7, "subject": "self"}]))
            content = pack.load()
            s = run(content, new_game(content, 1), Ctx(self_id=PLAYER),
                    [freeze({"op": "damage", "amount": 999, "damage_type": "dmg_a", "subject": "self"})])
            self.assertEqual(stats.current(content, s.characters[PLAYER], "stat_health"), 7)
        finally:
            pack.close()


class TestKeys(unittest.TestCase):
    def press(self, data):
        master, slave = pty.openpty()
        try:
            os.write(master, data)
            with os.fdopen(os.dup(slave), "r") as fake, mock.patch("sys.stdin", fake):
                return text.read_key()
        finally:
            os.close(master)
            os.close(slave)

    def test_whole_characters_and_sequences(self):                      # finding 4
        self.assertEqual(self.press("é".encode()), "é")
        self.assertEqual(self.press(b"\x1b[A"), "\x1b[A")
        self.assertEqual(self.press(b"w"), "w")

    def test_arrows_move_and_odd_keys_do_nothing(self):
        s = new_game(CONTENT, 1)
        moved, _, quit_now = app.handle(CONTENT, s, "\x1b[D", app.View(), UI)      # Left
        self.assertEqual(me(moved).at[1], me(s).at[1] - 1)
        self.assertFalse(quit_now)
        same, view, quit_now = app.handle(CONTENT, s, "é", app.View(), UI)
        self.assertEqual((same.characters, view, quit_now), (s.characters, app.View(), False))
        _, view, _ = app.handle(CONTENT, s, "\x1b", app.View("pack"), UI)          # Esc closes
        self.assertIsNone(view.panel)

    def test_upper_case_bindings_are_refused(self):                    # finding 13
        tmp = tempfile.TemporaryDirectory()
        try:
            ui_dir = Path(tmp.name) / "mine"
            shutil.copytree(ui_dir_for("default"), ui_dir)
            path = ui_dir / "keys.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data.setdefault("bindings", {})["pack"] = "P"
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertTrue(any("bindings.pack" in e for e in uipack.validate_ui_pack(ui_dir).errors))
        finally:
            tmp.cleanup()


class TestRestore(unittest.TestCase):
    def test_restoring_heat_cools(self):                                # finding 5
        s = new_game(CONTENT, 1)
        s = do(s, {"op": "modify_stat", "stat": "stat_heat", "amount": 0, "subject": "self"})
        hot = stats.current(CONTENT, me(s), "stat_heat")
        s = do(s, {"op": "restore", "stat": "stat_heat", "amount": 1, "subject": "self"})
        self.assertEqual(stats.current(CONTENT, me(s), "stat_heat"), max(0, hot - 1))
        s = do(s, {"op": "restore", "stat": "stat_heat", "amount": 99, "subject": "self"})
        self.assertEqual(stats.current(CONTENT, me(s), "stat_heat"), 0)


class TestUniqueEnemies(unittest.TestCase):
    def test_a_beaten_unique_enemy_isnt_fought_again(self):            # finding 7
        pack = PackCopy()
        try:
            pack.edit("encounters.json", lambda d: d["entries"].append(
                {"id": "enc_duel", "name": "Duel", "enemies": [{"character": NPC}]}))
            content = pack.load()
            s = new_game(content, 1)
            started = encounter.begin(content, s._replace(encounter_request="enc_duel"))
            self.assertEqual(started.encounter.enemies, (NPC,))
            down = run(content, s, Ctx(self_id=NPC),
                       [freeze({"op": "damage", "amount": 999, "damage_type": "dmg_a", "subject": "self"})])
            self.assertTrue(down.characters[NPC].down)
            again = encounter.begin(content, down._replace(encounter_request="enc_duel"))
            self.assertIsNone(again.encounter)
            self.assertIsNone(again.encounter_request)
        finally:
            pack.close()


class TestTime(unittest.TestCase):
    def test_every_morning_of_a_long_wait_counts(self):               # finding 8
        s = do(new_game(CONTENT, 1), {"op": "damage", "amount": 25, "damage_type": "dmg_a", "subject": "self"})
        hurt = health(s)
        self.assertLessEqual(hurt + 20, stats.stat(CONTENT, me(s), "stat_health"))
        s = answer_everything(turns.advance(CONTENT, s, 120))      # two mornings
        self.assertEqual(s.turn, 120)
        self.assertEqual(health(s), hurt + 20)                     # +10 each morning
        self.assertEqual((s.triggers, s.turns_owed), ((), 0))

    def test_morning_events_see_their_own_day(self):
        s = answer_everything(turns.advance(CONTENT, new_game(CONTENT, 1), 300))
        self.assertEqual((s.turn, s.triggers, s.turns_owed), (300, (), 0))

    def test_places_act_only_where_the_player_is(self):              # finding 9
        s = do(new_game(CONTENT, 1), {"op": "move_to", "location": "room_b", "subject": "self"}, who=NPC)
        before = health(s, NPC)
        s = turns.advance(CONTENT, s, 3)                              # Room B's hazard, the player away
        self.assertEqual(health(s, NPC), before)

    def test_a_place_speaks_once_per_turn(self):
        pack = PackCopy()
        try:
            def add_message(data):
                room = pack.entry(data, "room_a")
                room["on_turn"] = list(room.get("on_turn", [])) + [{"op": "message", "text": "Fans hum."}]
            pack.edit("locations.json", add_message)
            content = pack.load()
            s = turns.advance(content, new_game(content, 1), 1)        # the NPC stands in room A too
            self.assertEqual([m.text for m in s.messages].count("Fans hum."), 1)
        finally:
            pack.close()

    def test_a_waiting_question_isnt_replaced(self):
        terminal = CONTENT.get("object", "obj_terminal")["interactions"][0]["effects"]
        s = do(new_game(CONTENT, 1), *terminal)
        first = s.pending
        s = do(s, {"op": "choose", "prompt": "Another?", "options": [{"label": "Yes", "effects": []}]})
        self.assertEqual(s.pending, first)


class TestBudgets(unittest.TestCase):
    def test_removing_what_powers_the_rest_is_refused(self):           # finding 10
        s = new_game(CONTENT, 1)
        s = do(s, {"op": "move_to", "location": "room_b", "subject": "self"})
        chars = dict(s.characters)
        chars[PLAYER] = me(s)._replace(at=(2, 2))                    # by the bay, a refit workshop
        s = s._replace(characters=freeze(chars))
        s = do(s, {"op": "modify_item", "pick": {"item": "module_tool"}, "stats": {"stat_power": 4},
                   "subject": "self"},
               {"op": "modify_stat", "stat": "stat_power", "amount": -4, "subject": "self"})
        tool = slot_of(s, "module_tool", "fitted")
        self.assertIn("Power", build.remove_problem(CONTENT, s, tool) or "")
        self.assertIsNone(build.remove_problem(CONTENT, s, slot_of(s, "module_system", "fitted")))


class TestUsedItem(unittest.TestCase):
    def test_the_used_item_comes_from_where_the_check_looked(self):    # finding 12
        s = do(new_game(CONTENT, 1), {"op": "give_item", "item": "module_tool", "count": 1, "subject": "self"})
        carried = {"check": "has_tag", "tag": "tag_a", "source": "carried"}
        fitted = {"check": "has_tag", "tag": "tag_a", "source": "fitted"}
        self.assertEqual(world.used_item(CONTENT, s, Ctx(self_id=PLAYER), freeze(carried))[1], "inventory")
        self.assertEqual(world.used_item(CONTENT, s, Ctx(self_id=PLAYER), freeze(fitted))[1], "fitted")


class TestPlacement(unittest.TestCase):
    def test_characters_without_a_position_get_their_own_tile(self):  # finding 14
        pack = PackCopy()
        try:
            def unplace(data):
                pack.entry(data, NPC).pop("at")
                rival = json.loads(json.dumps(pack.entry(data, NPC)))
                rival.update(id="char_twin", name="Twin")
                rival.pop("interactions", None)
                data["entries"].append(rival)
            pack.edit("characters.json", unplace)
            content = pack.load()
            s = new_game(content, 1)
            spots = [tuple(s.characters[c].at) for c in (PLAYER, NPC, "char_twin")]
            self.assertEqual(len(set(spots)), 3)
            for spot in spots[1:]:
                self.assertTrue(world.standable(content, "room_a", spot))
        finally:
            pack.close()


class TestValidator(unittest.TestCase):
    def test_skill_levels_count_toward_budgets(self):                  # finding 15
        pack = PackCopy()
        try:
            pack.edit("items.json", lambda d: pack.entry(d, "frame_a")["stats"].update(stat_power=3))
            errors = validate_pack(pack.dir).errors
            self.assertTrue(any("fitted gear needs 4 power" in e for e in errors), errors)

            def level_one_power(data):
                pack.entry(data, "skill_a")["levels"][0]["stats"] = {"stat_power": 1}
            pack.edit("skills.json", level_one_power)
            errors = validate_pack(pack.dir).errors
            self.assertFalse(any("fitted gear needs 4 power" in e for e in errors), errors)
        finally:
            pack.close()


if __name__ == "__main__":
    unittest.main()
