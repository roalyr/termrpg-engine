"""
Milestone 3: the build. Done when modules and frames can be swapped, and the budget
and size rules behave as the validator predicts.
"""
import re
import unittest
from pathlib import Path

from engine import build, stats, world
from engine.content import load_pack
from engine.effects import run
from engine.frozen import freeze
from engine.state import Ctx, new_game
from tui import app, render

ROOT = Path(__file__).resolve().parent.parent
CONTENT = load_pack(ROOT / "packs" / "test_scifi")
PLAYER = "char_player"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def me(state):
    return state.characters[state.player]


def walk(state, keys):
    for key in keys:
        state = world.move(CONTENT, state, key)
    return state


def effects(state, *items):
    return run(CONTENT, state, Ctx(self_id=PLAYER), [freeze(e) for e in items])


def slot_of(state, item_id, where=None):
    for slot, inst in stats.held(me(state)):
        if inst.item == item_id and (where is None or slot[0] == where):
            return slot
    raise AssertionError(f"{item_id} not held")


def stored_index(state, item_id):
    where = build.storage_here(CONTENT, state)
    return next(i for i, inst in enumerate(build.stored(state, where)) if inst.item == item_id)


def last(state):
    return state.messages[-1].text


def at_bench():
    """New game, standing next to room A's bench (refit, dismantle, fabricate, modify, repair)."""
    s = walk(new_game(CONTENT, 1), "ss")                 # (3, 4); the second step bumps the bench
    assert build.refit_here(CONTENT, s)
    return s


def at_bay():
    """New game, through to room B, standing next to the suit bay."""
    s = walk(new_game(CONTENT, 1), "aaww")
    s = world.act(CONTENT, s, "u")
    s = world.act(CONTENT, s, "g")
    s = walk(s, "ssaa")                                  # (2, 2), next to the bay at (2, 1)
    assert build.refit_here(CONTENT, s) and build.storage_here(CONTENT, s) == "storage_bay"
    return s


class TestRefitPlaces(unittest.TestCase):
    def test_refit_only_at_a_refit_workshop(self):
        s = new_game(CONTENT, 1)
        self.assertFalse(build.refit_here(CONTENT, s))
        slot = slot_of(s, "module_cutter")
        self.assertEqual(build.remove_problem(CONTENT, s, slot), "Needs a refit workshop.")
        s = build.remove(CONTENT, s, slot)
        self.assertEqual(last(s), "Needs a refit workshop.")
        self.assertEqual(len(me(s).fitted), 2)
        self.assertEqual(s.turn, 0)                      # refused actions take no time


class TestModules(unittest.TestCase):
    def test_remove_and_refit_a_module(self):
        s = at_bench()
        s = build.remove(CONTENT, s, slot_of(s, "module_cutter"))
        self.assertEqual(last(s), "Removed Cutter.")
        self.assertEqual([i.item for i in me(s).fitted], ["module_shield"])
        self.assertEqual(stats.budget_used(CONTENT, me(s), "power"), 3)
        self.assertFalse(world.conditions.evaluate(CONTENT, s, Ctx(self_id=PLAYER),
                                                   freeze({"check": "has_tag", "tag": "tag_tool", "source": "fitted", "subject": "self"}))[0])
        s = build.fit(CONTENT, s, slot_of(s, "module_cutter", "inventory"))
        self.assertEqual(last(s), "Fitted Cutter.")
        self.assertEqual(stats.budget_used(CONTENT, me(s), "power"), 4)

    def test_no_free_slot(self):
        s = effects(at_bench(), {"op": "give_item", "item": "module_shield", "count": 1, "subject": "self"})
        self.assertEqual(build.fit_problem(CONTENT, s, slot_of(s, "module_shield", "inventory")),
                         "No free slot for Shield.")

    def test_power_budget(self):
        s = at_bench()
        s = build.remove(CONTENT, s, slot_of(s, "module_shield"))
        s = effects(s, {"op": "modify_stat", "stat": "stat_power", "amount": -4, "subject": "self"})
        self.assertEqual(build.fit_problem(CONTENT, s, slot_of(s, "module_shield", "inventory")),
                         "Needs 4 Power, has 2.")

    def test_heat_load(self):
        s = at_bench()
        s = build.remove(CONTENT, s, slot_of(s, "module_shield"))
        s = effects(s, {"op": "modify_stat", "stat": "stat_heat", "amount": -6, "subject": "self"})
        self.assertEqual(build.fit_problem(CONTENT, s, slot_of(s, "module_shield", "inventory")),
                         "Needs 2 Heat, has 2.")

    def test_heat_pool_follows_the_load(self):
        s = at_bench()
        self.assertEqual(me(s).pools["stat_heat"], 2)
        s = build.remove(CONTENT, s, slot_of(s, "module_shield"))
        self.assertEqual(me(s).pools["stat_heat"], 0)

    def test_frame_comes_off_after_its_modules(self):
        s = at_bench()
        self.assertEqual(build.remove_problem(CONTENT, s, ("frame", 0)), "Remove its modules first.")

    def test_removing_the_frame_needs_cargo_room(self):
        s = at_bench()
        s = build.remove(CONTENT, s, slot_of(s, "module_cutter"))
        s = build.remove(CONTENT, s, slot_of(s, "module_shield"))
        # Without the frame the body carries 2 stacks; the pack holds far more.
        self.assertEqual(build.remove_problem(CONTENT, s, ("frame", 0)), "No room for Light suit.")


class TestFrameSwap(unittest.TestCase):
    def test_swap_suits_at_the_bay(self):
        s = at_bay()
        s = effects(s, {"op": "take_item", "item": "consumable_medkit", "count": 3, "subject": "self"},
                    {"op": "take_item", "item": "material_scrap", "count": 12, "subject": "self"},
                    {"op": "take_item", "item": "misc_keycard", "count": 1, "subject": "self"})
        self.assertEqual(me(s).inventory, ())

        # Strip the light suit and park everything in the bay.
        for item in ("module_cutter", "module_shield"):
            s = build.remove(CONTENT, s, slot_of(s, item))
            s = build.store(CONTENT, s, slot_of(s, item, "inventory"))
        s = effects(s, {"op": "restore", "stat": "stat_health", "amount": 99, "subject": "self"})
        s = build.remove(CONTENT, s, ("frame", 0))
        self.assertIsNone(me(s).frame)
        # The suit's 20 health go with it, and room B's hazard costs 1 during the turn.
        self.assertEqual(stats.current(CONTENT, me(s), "stat_health"), 30 - 20 - 1)
        self.assertEqual(stats.size(CONTENT, me(s)), 3)                                       # the body
        s = build.store(CONTENT, s, slot_of(s, "frame_light", "inventory"))
        self.assertEqual(last(s), "Stored Light suit in Suit bay.")

        # The heavy suit needs skill A 2.
        s = build.take(CONTENT, s, stored_index(s, "frame_heavy"))
        heavy = slot_of(s, "frame_heavy", "inventory")
        self.assertEqual(build.fit_problem(CONTENT, s, heavy), "You can't use Heavy suit yet.")
        s = effects(s, {"op": "grant_xp", "skill": "skill_salvage", "amount": 30, "subject": "self"})
        s = build.fit(CONTENT, s, heavy)
        self.assertEqual(me(s).frame.item, "frame_heavy")
        self.assertEqual(stats.size(CONTENT, me(s)), 5)
        self.assertEqual(stats.stat(CONTENT, me(s), "stat_health"), 55)                     # body 10 + frame 45

        # Its bigger budgets take both modules back.
        for item in ("module_cutter", "module_shield"):
            s = build.take(CONTENT, s, stored_index(s, item))
            s = build.fit(CONTENT, s, slot_of(s, item, "inventory"))
        self.assertEqual([i.item for i in me(s).fitted], ["module_cutter", "module_shield"])
        self.assertEqual(stats.stat(CONTENT, me(s), "stat_armor"), 5)                        # frame 3 + module 2

        # A size-5 suit can't get back through the door into room A (holds 3).
        s = walk(s, "dww")
        self.assertEqual(s.focus, ("placement", "storage_door"))
        s = world.act(CONTENT, s, "g")
        self.assertEqual(me(s).location, "loc_storage")
        self.assertEqual(last(s), "Heavy suit doesn't fit Door.")

    def test_heavy_frame_cant_be_put_on_in_a_small_room(self):
        s = at_bench()
        s = effects(s, {"op": "take_item", "item": "material_scrap", "count": 12, "subject": "self"})
        for item in ("module_cutter", "module_shield"):
            s = build.remove(CONTENT, s, slot_of(s, item))
        s = effects(s, {"op": "take_item", "item": "consumable_medkit", "count": 3, "subject": "self"},
                    {"op": "take_item", "item": "module_shield", "count": 1, "subject": "self"},
                    {"op": "take_item", "item": "module_cutter", "count": 1, "subject": "self"},
                    {"op": "take_item", "item": "misc_keycard", "count": 1, "subject": "self"})
        s = build.remove(CONTENT, s, ("frame", 0))
        s = effects(s, {"op": "give_item", "item": "frame_heavy", "count": 1, "subject": "self"},
                    {"op": "grant_xp", "skill": "skill_salvage", "amount": 30, "subject": "self"})
        self.assertEqual(build.fit_problem(CONTENT, s, slot_of(s, "frame_heavy", "inventory")),
                         "Heavy suit doesn't fit Workshop.")


class TestImplants(unittest.TestCase):
    def test_fit_an_implant_into_a_body_slot(self):
        s = at_bay()
        s = effects(s, {"op": "take_item", "item": "material_scrap", "count": 12, "subject": "self"})
        s = build.take(CONTENT, s, stored_index(s, "implant_eye"))
        s = build.fit(CONTENT, s, slot_of(s, "implant_eye", "inventory"))
        self.assertEqual([i.item for i in me(s).implants], ["implant_eye"])
        self.assertEqual(stats.stat(CONTENT, me(s), "stat_initiative"), 1)
        s = effects(s, {"op": "give_item", "item": "implant_eye", "count": 1, "subject": "self"})
        self.assertEqual(build.fit_problem(CONTENT, s, slot_of(s, "implant_eye", "inventory")),
                         "No free slot for Eye implant.")


class TestStorage(unittest.TestCase):
    def test_storage_limits(self):
        s = walk(new_game(CONTENT, 1), "aaas")               # (3, 1), next to the locker (holds size 2)
        self.assertEqual(build.storage_here(CONTENT, s), "workshop_locker")
        s = effects(s, {"op": "give_item", "item": "frame_light", "count": 1, "subject": "self"})
        self.assertEqual(build.store_problem(CONTENT, s, slot_of(s, "frame_light", "inventory")),
                         "Light suit doesn't fit Locker.")
        s = build.store(CONTENT, s, slot_of(s, "material_scrap"))
        locker = build.stored(s, "workshop_locker")
        self.assertEqual([(i.item, i.count) for i in locker], [("material_odd_metal", 1), ("material_scrap", 10)])  # the whole stack
        self.assertEqual(sum(i.count for i in me(s).inventory if i.item == "material_scrap"), 2)
        s = build.take(CONTENT, s, 1)
        self.assertEqual([i.item for i in build.stored(s, "workshop_locker")], ["material_odd_metal"])
        self.assertEqual(sum(i.count for i in me(s).inventory if i.item == "material_scrap"), 12)

    def test_the_board_keeps_the_pick_when_numbers_shift(self):
        s = walk(new_game(CONTENT, 1), "aaas")               # next to the locker
        slots = build.pack_slots(CONTENT, s)
        picked = slots.index(slot_of(s, "material_scrap"))
        s, view, _ = app.handle(CONTENT, s, "o", app.View("pack", picked))      # store it
        stored = build.pack_slots(CONTENT, s)[view.selected]
        self.assertEqual(stored[0], "storage")
        self.assertEqual(build.entry_at(CONTENT, s, stored).item, "material_scrap")
        s, view, _ = app.handle(CONTENT, s, "k", view)                          # and take it back
        back = build.pack_slots(CONTENT, s)[view.selected]
        self.assertEqual(back[0], "inventory")
        self.assertEqual(build.entry_at(CONTENT, s, back).count, 10)

    def test_the_pick_is_dropped_when_the_item_is_gone(self):
        s = new_game(CONTENT, 1)
        s = effects(s, {"op": "take_item", "item": "consumable_medkit", "count": 2, "subject": "self"})
        slots = build.pack_slots(CONTENT, s)
        picked = slots.index(slot_of(s, "consumable_medkit"))
        s, view, _ = app.handle(CONTENT, s, "u", app.View("pack", picked))      # uses the last one
        self.assertIsNone(view.selected)

    def test_starting_contents(self):
        s = new_game(CONTENT, 1)
        self.assertEqual([i.item for i in s.storage["storage_bay"]], ["frame_heavy", "implant_eye"])
        self.assertEqual([i.item for i in s.storage["workshop_locker"]], ["material_odd_metal"])


class TestUsingItems(unittest.TestCase):
    def test_consumable_spends_one(self):
        s = effects(new_game(CONTENT, 1), {"op": "damage", "amount": 10, "damage_type": "dmg_toxic", "subject": "self"})
        slot = slot_of(s, "consumable_medkit")
        option = build.item_options(CONTENT, s, slot)[0]
        self.assertEqual((option.kind, option.label), ("use", "Use"))
        s = build.item_act(CONTENT, s, slot, option.key)
        self.assertEqual(s.messages[0].text, "Used Medkit.")
        self.assertEqual(sum(i.count for i in me(s).inventory if i.item == "consumable_medkit"), 2)
        self.assertGreater(stats.current(CONTENT, me(s), "stat_health"), 20)


class TestScreen(unittest.TestCase):
    def test_the_fitting_screen_shows_the_loadout(self):
        s = at_bench()
        frame = ANSI.sub("", render.render(CONTENT, s, 52, 60, selected=1, screen="fitting"))
        for words in ("Fitting · Light suit", "At: Workbench", "4/6", "1 Light suit", "2 Cutter 4/4",
                      "Hand  · empty", "R Remove", "Remove: PWR 4→3/6", "I Details"):
            self.assertIn(words, frame)

    def test_the_pack_panel_is_for_carrying(self):
        s = at_bench()
        frame = ANSI.sub("", render.render(CONTENT, s, 52, 60, panel="pack", selected=0))
        self.assertIn("CRG 4/6", frame)
        self.assertIn("1 Medkit x3", frame)
        self.assertIn("U Use", frame)
        self.assertNotIn("Light suit", frame)                    # the loadout is on the fitting screen
        self.assertNotIn("Remove", frame)

    def test_app_keys_on_the_fitting_screen(self):
        s = at_bench()
        s, view, _ = app.handle(CONTENT, s, "f")
        self.assertEqual((view.screen, view.selected), ("fitting", 0))
        s, view, _ = app.handle(CONTENT, s, "s", view)           # down moves the pick
        self.assertEqual(view.selected, 1)
        s, view, _ = app.handle(CONTENT, s, "r", view)
        self.assertEqual(last(s), "Removed Cutter.")
        row = build.fitting_rows(CONTENT, s)[[i for i, r in enumerate(build.fitting_rows(CONTENT, s))
                                              if r.slot is not None][view.selected]]
        self.assertEqual((row.group, build.entry_at(CONTENT, s, row.slot).item), ("spare", "module_cutter"))
        s, view, _ = app.handle(CONTENT, s, "f", view)           # F fits the picked spare item again
        self.assertEqual(last(s), "Fitted Cutter.")
        s, view, _ = app.handle(CONTENT, s, "x", view)
        self.assertEqual(view, app.View())


if __name__ == "__main__":
    unittest.main()
