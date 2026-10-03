"""
Milestone 5: crafting. Done when the test tool can be dismantled, learned, fabricated,
reinforced and repaired.
"""
import re
import unittest
from pathlib import Path

from engine import build, craft, stats, world
from engine.content import load_pack
from engine.effects import run
from engine.frozen import freeze
from engine.state import Ctx, new_game
from tui import render
from tui.ui import default_ui
from tui.widgets import option_text

UI = default_ui()

ROOT = Path(__file__).resolve().parent.parent
CONTENT = load_pack(ROOT / "packs" / "test")
PLAYER = "char_player"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def me(state):
    return state.characters[state.player]


def effects(state, *items):
    return run(CONTENT, state, Ctx(self_id=PLAYER), [freeze({"subject": "self", **e}) for e in items])


def at_bench():
    """Next to room A's bench: refit, dismantle, fabricate, modify, repair, up to grade A."""
    s = new_game(CONTENT, 1)
    for key in "ss":
        s = world.move(CONTENT, s, key)
    return s


def carried(state, item_id):
    return next(("inventory", i) for i, inst in enumerate(me(state).inventory) if inst.item == item_id)


def count(state, item_id):
    return sum(i.count for i in me(state).inventory if i.item == item_id)


def texts(state):
    return [m.text for m in state.messages]


class TestTheToolsLife(unittest.TestCase):
    def test_dismantle_learn_fabricate_reinforce_repair(self):
        s = effects(at_bench(), {"op": "give_item", "item": "module_tool", "count": 1})
        materials = count(s, "material_a")

        # Dismantling without the skill gives materials but not the design.
        s = craft.dismantle(CONTENT, s, carried(s, "module_tool"))
        self.assertIn("Took apart Tool A: Material A x2.", texts(s))
        self.assertIn("Tool A is beyond you for now.", texts(s))
        self.assertEqual(count(s, "material_a"), materials + 2)
        self.assertNotIn("module_tool", me(s).designs)

        # With skill A 2, the next one teaches the design.
        s = effects(s, {"op": "grant_xp", "skill": "skill_a", "amount": 30},
                    {"op": "give_item", "item": "module_tool", "count": 1})
        s = craft.dismantle(CONTENT, s, carried(s, "module_tool"))
        self.assertIn("You understand how Tool A is made.", texts(s))
        self.assertEqual(craft.designs(CONTENT, s), ["module_tool"])

        # Fabricate a copy from three materials; it takes two turns.
        turn, materials = s.turn, count(s, "material_a")
        s = craft.fabricate(CONTENT, s, "module_tool")
        self.assertIn("Made Tool A.", texts(s))
        self.assertEqual(count(s, "material_a"), materials - 3)
        self.assertEqual(s.turn, turn + 2)
        new_tool = carried(s, "module_tool")
        self.assertEqual(stats.item_at(me(s), new_tool).condition, 4)

        # Reinforce it: the material decides what's added, and it fills the one mod slot.
        options = {option_text(UI, o): o for o in build.item_options(CONTENT, s, new_tool)}
        self.assertIn("Modify: Reinforced", options)
        s = craft.modify(CONTENT, s, new_tool, "mod_reinforced")
        tool = stats.item_at(me(s), carried(s, "module_tool"))
        self.assertIn("Tool A is now Reinforced.", texts(s))
        self.assertEqual(tool.mods, ("mod_reinforced",))
        self.assertEqual(tool.condition, 6)                          # +2 maximum condition
        view = stats.item_view(CONTENT, tool)
        self.assertEqual((view["name"], view["stats"]["stat_armor"]), ("Tool A (Reinforced)", 1))
        self.assertEqual(craft.modify_problem(CONTENT, s, carried(s, "module_tool"), "mod_reinforced"),
                         "Tool A (Reinforced) is already Reinforced.")

        # Repair the fitted tool after wear.
        s = effects(s, {"op": "wear", "pick": {"slot_type": "slot_frame_hand"}, "amount": 3})
        fitted = ("fitted", 0)
        self.assertEqual(me(s).fitted[0].condition, 1)
        s = craft.repair(CONTENT, s, fitted)
        self.assertIn("Repaired Tool A.", texts(s))
        self.assertEqual(me(s).fitted[0].condition, 3)               # amount 2
        s = craft.repair(CONTENT, s, fitted)
        self.assertEqual(craft.repair_problem(CONTENT, s, fitted), "Tool A is in good shape.")


class TestRefusals(unittest.TestCase):
    def test_needs_a_workshop(self):
        s = effects(new_game(CONTENT, 1), {"op": "give_item", "item": "module_tool", "count": 1})
        self.assertEqual(craft.dismantle_problem(CONTENT, s, carried(s, "module_tool")), "No workshop here does that.")
        self.assertFalse(any(o.kind == "dismantle" for o in build.item_options(CONTENT, s, carried(s, "module_tool"))))

    def test_grade_limit(self):
        s = at_bench()
        self.assertEqual(craft.modify_problem(CONTENT, s, ("fitted", 1), "mod_reinforced"),
                         "System A is beyond this workshop.")

    def test_missing_materials(self):
        s = effects(at_bench(), {"op": "learn_design", "item": "module_tool"},
                    {"op": "take_item", "item": "material_a", "count": 11})
        self.assertEqual(craft.fabricate_problem(CONTENT, s, "module_tool"), "Needs Material A x3.")

    def test_no_mod_slot(self):
        s = at_bench()
        s = effects(s, {"op": "grant_xp", "skill": "skill_a", "amount": 90},
                    {"op": "give_item", "item": "material_exotic", "count": 1})
        s = craft.modify(CONTENT, s, ("fitted", 0), "mod_exotic")
        self.assertEqual(craft.modify_problem(CONTENT, s, ("fitted", 0), "mod_reinforced"),
                         "Tool A (Strange) has no free mod slot.")

    def test_modification_requirements(self):
        s = effects(at_bench(), {"op": "give_item", "item": "material_exotic", "count": 1})
        self.assertEqual(craft.modify_problem(CONTENT, s, ("fitted", 0), "mod_exotic"), "You can't use Strange yet.")

    def test_fabricated_item_must_fit_in_cargo(self):
        s = effects(at_bench(), {"op": "learn_design", "item": "module_tool"},
                    {"op": "give_item", "item": "misc_key", "count": 2})
        self.assertEqual(len(me(s).inventory), 6)
        self.assertEqual(craft.fabricate_problem(CONTENT, s, "module_tool"), "No room for Tool A.")


class TestModifyingFittedGear(unittest.TestCase):
    def test_fitted_modification_changes_the_loadout(self):
        s = at_bench()
        s = effects(s, {"op": "grant_xp", "skill": "skill_a", "amount": 90},
                    {"op": "give_item", "item": "material_exotic", "count": 1})
        self.assertEqual(stats.budget_used(CONTENT, me(s), "heat"), 2)
        s = craft.modify(CONTENT, s, ("fitted", 0), "mod_exotic")
        self.assertEqual(stats.budget_used(CONTENT, me(s), "heat"), 3)      # Strange adds 1 heat use
        self.assertIn("action_burst", stats.item_view(CONTENT, me(s).fitted[0])["actions"])
        self.assertEqual(count(s, "material_exotic"), 0)


class TestPaging(unittest.TestCase):
    def test_more_than_nine_entries(self):
        from tui import app
        s = effects(at_bench(), {"op": "learn_design", "item": "module_tool"},
                    {"op": "give_item", "item": "misc_key", "count": 2})
        slots = build.pack_slots(CONTENT, s)
        self.assertGreater(len(slots), 9)
        frame = ANSI.sub("", render.render(CONTENT, s, 44, 80, panel="pack"))
        self.assertIn("Page 1/2", frame)
        s, view, _ = app.handle(CONTENT, s, "p")
        s, view, _ = app.handle(CONTENT, s, "]", view)
        s, view, _ = app.handle(CONTENT, s, "1", view)
        self.assertEqual(slots[view.selected], ("design", 0))      # the tenth entry
        frame = ANSI.sub("", render.render(CONTENT, s, 44, 80, panel="pack", selected=view.selected, page=view.page))
        self.assertIn("1 Tool A", frame)
        self.assertIn("Page 2/2", frame)


class TestScreen(unittest.TestCase):
    def test_designs_and_crafting_options_on_the_board(self):
        s = effects(at_bench(), {"op": "learn_design", "item": "module_tool"},
                    {"op": "give_item", "item": "module_tool", "count": 1})
        slots = build.pack_slots(CONTENT, s)
        self.assertEqual(slots[-1], ("design", 0))
        frame = ANSI.sub("", render.render(CONTENT, s, 44, 80, panel="pack", selected=len(slots) - 1))
        self.assertIn("Designs:", frame)
        self.assertIn("B Fabricate", frame)
        tool = slots.index(carried(s, "module_tool"))
        frame = ANSI.sub("", render.render(CONTENT, s, 44, 80, panel="pack", selected=tool))
        self.assertIn("V Dismantle", frame)
        self.assertIn("Modify: Reinforced", frame)


if __name__ == "__main__":
    unittest.main()
