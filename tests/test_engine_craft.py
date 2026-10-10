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
        s = effects(at_bench(), {"op": "give_item", "item": "module_cutter", "count": 1})
        materials = count(s, "material_scrap")

        # Dismantling without the skill gives materials but not the design.
        s = craft.dismantle(CONTENT, s, carried(s, "module_cutter"))
        self.assertIn("Took apart Cutter: Scrap x2.", texts(s))
        self.assertIn("Cutter is beyond you for now.", texts(s))
        self.assertEqual(count(s, "material_scrap"), materials + 2)
        self.assertNotIn("module_cutter", me(s).designs)

        # With skill A 2, the next one teaches the design.
        s = effects(s, {"op": "grant_xp", "skill": "skill_salvage", "amount": 30},
                    {"op": "give_item", "item": "module_cutter", "count": 1})
        s = craft.dismantle(CONTENT, s, carried(s, "module_cutter"))
        self.assertIn("You understand how Cutter is made.", texts(s))
        self.assertEqual(craft.designs(CONTENT, s), ["module_cutter"])

        # Fabricate a copy from three materials; it takes two turns.
        turn, materials = s.turn, count(s, "material_scrap")
        s = craft.fabricate(CONTENT, s, "module_cutter")
        self.assertIn("Made Cutter.", texts(s))
        self.assertEqual(count(s, "material_scrap"), materials - 3)
        self.assertEqual(s.turn, turn + 2)
        new_tool = carried(s, "module_cutter")
        self.assertEqual(stats.item_at(me(s), new_tool).condition, 4)

        # Reinforce it: the material decides what's added, and it fills the one mod slot.
        options = {option_text(UI, o): o for o in build.item_options(CONTENT, s, new_tool)}
        self.assertIn("Modify: Reinforced", options)
        s = craft.modify(CONTENT, s, new_tool, "mod_reinforced")
        tool = stats.item_at(me(s), carried(s, "module_cutter"))
        self.assertIn("Cutter is now Reinforced.", texts(s))
        self.assertEqual(tool.mods, ("mod_reinforced",))
        self.assertEqual(tool.condition, 6)                          # +2 maximum condition
        view = stats.item_view(CONTENT, tool)
        self.assertEqual((view["name"], view["stats"]["stat_armor"]), ("Cutter (Reinforced)", 1))
        self.assertEqual(craft.modify_problem(CONTENT, s, carried(s, "module_cutter"), "mod_reinforced"),
                         "Cutter (Reinforced) is already Reinforced.")

        # Repair the fitted tool after wear.
        s = effects(s, {"op": "wear", "pick": {"slot_type": "slot_hand"}, "amount": 3})
        fitted = ("fitted", 0)
        self.assertEqual(me(s).fitted[0].condition, 1)
        s = craft.repair(CONTENT, s, fitted)
        self.assertIn("Repaired Cutter.", texts(s))
        self.assertEqual(me(s).fitted[0].condition, 3)               # amount 2
        s = craft.repair(CONTENT, s, fitted)
        self.assertEqual(craft.repair_problem(CONTENT, s, fitted), "Cutter is in good shape.")


class TestRefusals(unittest.TestCase):
    def test_needs_a_workshop(self):
        s = effects(new_game(CONTENT, 1), {"op": "give_item", "item": "module_cutter", "count": 1})
        self.assertEqual(craft.dismantle_problem(CONTENT, s, carried(s, "module_cutter")), "No workshop here does that.")
        self.assertFalse(any(o.kind == "dismantle" for o in build.item_options(CONTENT, s, carried(s, "module_cutter"))))

    def test_grade_limit(self):
        s = at_bench()
        self.assertEqual(craft.modify_problem(CONTENT, s, ("fitted", 1), "mod_reinforced"),
                         "Shield is beyond this workshop.")

    def test_missing_materials(self):
        s = effects(at_bench(), {"op": "learn_design", "item": "module_cutter"},
                    {"op": "take_item", "item": "material_scrap", "count": 11})
        self.assertEqual(craft.fabricate_problem(CONTENT, s, "module_cutter"), "Needs Scrap x3.")

    def test_no_mod_slot(self):
        s = at_bench()
        s = effects(s, {"op": "grant_xp", "skill": "skill_salvage", "amount": 90},
                    {"op": "give_item", "item": "material_odd_metal", "count": 1})
        s = craft.modify(CONTENT, s, ("fitted", 0), "mod_odd_metal")
        self.assertEqual(craft.modify_problem(CONTENT, s, ("fitted", 0), "mod_reinforced"),
                         "Cutter (Odd metal) has no free mod slot.")

    def test_modification_requirements(self):
        s = effects(at_bench(), {"op": "give_item", "item": "material_odd_metal", "count": 1})
        self.assertEqual(craft.modify_problem(CONTENT, s, ("fitted", 0), "mod_odd_metal"), "You can't use Odd metal yet.")

    def test_fabricated_item_must_fit_in_cargo(self):
        s = effects(at_bench(), {"op": "learn_design", "item": "module_cutter"},
                    {"op": "give_item", "item": "misc_keycard", "count": 2})
        self.assertEqual(len(me(s).inventory), 6)
        self.assertEqual(craft.fabricate_problem(CONTENT, s, "module_cutter"), "No room for Cutter.")


class TestModifyingFittedGear(unittest.TestCase):
    def test_fitted_modification_changes_the_loadout(self):
        s = at_bench()
        s = effects(s, {"op": "grant_xp", "skill": "skill_salvage", "amount": 90},
                    {"op": "give_item", "item": "material_odd_metal", "count": 1})
        self.assertEqual(stats.budget_used(CONTENT, me(s), "heat"), 2)
        s = craft.modify(CONTENT, s, ("fitted", 0), "mod_odd_metal")
        self.assertEqual(stats.budget_used(CONTENT, me(s), "heat"), 3)      # Odd metal adds 1 heat use
        self.assertIn("action_burn", stats.item_view(CONTENT, me(s).fitted[0])["actions"])
        self.assertEqual(count(s, "material_odd_metal"), 0)


class TestPaging(unittest.TestCase):
    def test_more_than_nine_entries(self):
        from tui import app
        s = at_bench()
        s = s._replace(characters=freeze({**s.characters, s.player: me(s)._replace(inventory=me(s).inventory * 3)}))
        slots = build.pack_slots(CONTENT, s)
        self.assertGreater(len(slots), 9)
        frame = ANSI.sub("", render.render(CONTENT, s, 52, 80, panel="pack"))
        self.assertIn("Page 1/2", frame)
        s, view, _ = app.handle(CONTENT, s, "p")
        s, view, _ = app.handle(CONTENT, s, "]", view)
        s, view, _ = app.handle(CONTENT, s, "1", view)
        self.assertEqual(slots[view.selected], ("inventory", 9))   # the tenth entry
        frame = ANSI.sub("", render.render(CONTENT, s, 52, 80, panel="pack", selected=view.selected, page=view.page))
        self.assertIn("1 Scrap x10", frame)
        self.assertIn("Page 2/2", frame)


class TestScreen(unittest.TestCase):
    def test_designs_and_crafting_options_on_the_fitting_screen(self):
        s = effects(at_bench(), {"op": "learn_design", "item": "module_cutter"},
                    {"op": "give_item", "item": "module_cutter", "count": 1})
        rows = build.fitting_rows(CONTENT, s)
        pickable = [r.slot for r in rows if r.slot is not None]
        self.assertEqual(pickable[-1], ("design", 0))
        frame = ANSI.sub("", render.render(CONTENT, s, 52, 80, selected=len(pickable) - 1, screen="fitting"))
        self.assertIn("Designs", frame)
        self.assertIn("Scrap x3", frame)
        self.assertIn("B Fabricate", frame)
        tool = pickable.index(carried(s, "module_cutter"))
        frame = ANSI.sub("", render.render(CONTENT, s, 52, 80, selected=tool, screen="fitting"))
        self.assertIn("V Dismantle", frame)
        self.assertIn("M Modify", frame)
        frame = ANSI.sub("", render.render(CONTENT, s, 52, 80, panel="modify", selected=tool, screen="fitting"))
        self.assertIn("1 Reinforced", frame)
        self.assertIn("ARM +1", frame)


if __name__ == "__main__":
    unittest.main()
