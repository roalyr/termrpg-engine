"""
The fantasy test pack: the same engine as the sci-fi pack, with the genre's own rules.
Gear without a suit, weight as the only budget, mana that is spent and stamina that
fills, blessings changed only at an altar, armour that keeps its wearer off the stairs.
"""
import random
import unittest
from pathlib import Path

from core.pack import validate_pack
from engine import build, encounter, stats, turns, world
from engine.content import load_pack
from engine.effects import run
from engine.frozen import freeze
from engine.state import Ctx, new_game
from lib.text import visible_len
from lib.ui import default_ui
from tui import app, render

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "packs" / "test_fantasy"
CONTENT = load_pack(PACK)
PLAYER = "char_player"


def me(state):
    return state.characters[state.player]


def walk(state, keys):
    for key in keys:
        state = world.move(CONTENT, state, key)
    return state


def effects(state, *items, cid=PLAYER):
    return run(CONTENT, state, Ctx(self_id=cid), [freeze(e) for e in items])


def slot_of(state, item_id, where=None):
    for slot, inst in stats.held(me(state)):
        if inst.item == item_id and (where is None or slot[0] == where):
            return slot
    raise AssertionError(f"{item_id} not held")


def equipped(state):
    return [i.item for i in me(state).equipped]


def last(state):
    return state.messages[-1].text


def at_rack(state):
    """Beside the armour stand, from the start."""
    return walk(state, "waaas")                          # (3, 1): the stand is at (4, 1)


def set_pool(state, cid, stat_id, value):
    cs = state.characters[cid]
    chars = dict(state.characters)
    chars[cid] = cs._replace(pools=freeze({**cs.pools, stat_id: value}))
    return state._replace(characters=freeze(chars))


class TestPack(unittest.TestCase):
    def test_valid_without_warnings(self):
        report = validate_pack(PACK)
        self.assertEqual(report.errors, ())
        self.assertEqual(report.warnings, ())

    def test_no_suit_no_power_no_heat(self):
        self.assertFalse(any(s.get("role") in ("power", "mass", "heat") for s in CONTENT.all("stat").values()))
        self.assertEqual([s for s, r in CONTENT.all("stat").items() if r.get("budget")], ["stat_weight"])


class TestGearWithoutASuit(unittest.TestCase):
    def test_the_sword_sits_in_the_bodys_hand(self):
        s = new_game(CONTENT, 1)
        self.assertEqual(equipped(s), ["gear_sword"])
        rows = [(r.slot_type, r.slot) for r in build.gear_rows(CONTENT, s) if r.group == "worn"]
        self.assertEqual(rows, [("slot_worn", None), ("slot_hand", ("equipped", 0)), ("slot_hand", None),
                                ("slot_back", None), ("slot_blessing", None)])
        self.assertEqual(stats.size(CONTENT, me(s)), 3)                        # the body's size

    def test_armour_and_a_buckler_go_on_anywhere(self):
        s = new_game(CONTENT, 1)
        self.assertFalse(build.equip_here(CONTENT, s))                         # no workshop nearby
        s = build.fit(CONTENT, s, slot_of(s, "gear_leather_armour"))
        self.assertEqual(last(s), "You put on Leather armour.")
        s = build.fit(CONTENT, s, slot_of(s, "gear_buckler"))
        self.assertEqual(equipped(s), ["gear_sword", "gear_leather_armour", "gear_buckler"])
        self.assertEqual(stats.stat(CONTENT, me(s), "stat_armor"), 2)
        self.assertEqual(stats.current(CONTENT, me(s), "stat_health"), 22)     # the armour's health comes with it
        s = build.remove(CONTENT, s, slot_of(s, "gear_buckler", "equipped"))
        self.assertEqual(last(s), "You take off Buckler.")

    def test_weight_is_the_only_budget(self):
        s = new_game(CONTENT, 1)
        s = build.fit(CONTENT, s, slot_of(s, "gear_leather_armour"))
        s = build.fit(CONTENT, s, slot_of(s, "gear_buckler"))
        self.assertEqual((stats.budget_used(CONTENT, me(s), "stat_weight"),
                          stats.budget_provided(CONTENT, me(s), "stat_weight")), (7, 8))
        s = effects(s, {"op": "give_item", "item": "gear_fur_cloak", "count": 1})
        s = build.fit(CONTENT, s, slot_of(s, "gear_fur_cloak"))                # 7 + 1 of 8: just fits
        s = effects(s, {"op": "give_item", "item": "gear_sword", "count": 1})
        self.assertEqual(build.fit_problem(CONTENT, s, slot_of(s, "gear_sword", "inventory")),
                         "No free slot for Sword.")                            # both hands are full


class TestBlessingsAtTheAltar(unittest.TestCase):
    def test_a_blessing_takes_only_at_the_altar(self):
        s = at_rack(new_game(CONTENT, 1))
        where = build.storage_here(CONTENT, s)
        index = next(i for i, inst in enumerate(build.stored(s, where)) if inst.item == "gear_ward_blessing")
        s = build.take(CONTENT, s, index)
        self.assertEqual(build.fit_problem(CONTENT, s, slot_of(s, "gear_ward_blessing")),
                         "Only a priest at an altar can do that.")
        s = walk(s, "w")                                                       # (2, 1), beside the altar
        self.assertTrue(build.equip_here(CONTENT, s, "slot_blessing"))
        self.assertFalse(build.equip_here(CONTENT, s, "slot_hand"))            # the altar only grants blessings
        s = build.fit(CONTENT, s, slot_of(s, "gear_ward_blessing"))
        self.assertIn("gear_ward_blessing", equipped(s))
        self.assertEqual(stats.stat(CONTENT, me(s), "stat_mana"), 6)
        self.assertEqual(stats.current(CONTENT, me(s), "stat_mana"), 6)


class TestPlateAndTheStairs(unittest.TestCase):
    def test_plate_sets_the_wearers_size(self):
        s = at_rack(new_game(CONTENT, 1))
        where = build.storage_here(CONTENT, s)
        index = next(i for i, inst in enumerate(build.stored(s, where)) if inst.item == "gear_plate_armour")
        s = build.take(CONTENT, s, index)
        self.assertEqual(build.fit_problem(CONTENT, s, slot_of(s, "gear_plate_armour")),
                         "You can't use Plate armour yet.")
        s = effects(s, {"op": "grant_xp", "skill": "skill_smithing", "amount": 30})   # stronger arms: weight 12
        s = build.fit(CONTENT, s, slot_of(s, "gear_plate_armour"))
        self.assertEqual(stats.size(CONTENT, me(s)), 4)
        s = walk(s, "dss")                                                     # (3, 2), (4, 2), onto the stairs
        self.assertEqual(s.focus, ("placement", "smithy_stairs"))
        s = world.act(CONTENT, s, "g")
        self.assertEqual(me(s).location, "loc_smithy")
        self.assertEqual(last(s), "Plate armour doesn't fit Stairs.")


class TestTheCellar(unittest.TestCase):
    def down(self, state):
        state = walk(state, "waasss")                                          # round Hedda, onto the stairs
        self.assertEqual(state.focus, ("placement", "smithy_stairs"))
        return world.act(CONTENT, state, "g")

    def test_the_cold_hurts_without_something_warm(self):
        s = self.down(new_game(CONTENT, 1))
        self.assertEqual(me(s).location, "loc_cellar")
        health = stats.current(CONTENT, me(s), "stat_health")
        s = turns.advance(CONTENT, s, 1)
        self.assertLess(stats.current(CONTENT, me(s), "stat_health"), health)

    def test_the_witchs_cloak_keeps_it_out(self):
        s = new_game(CONTENT, 1)
        s = walk(s, "a")                                                       # facing Hedda
        self.assertEqual(s.focus, ("character", "char_witch"))
        s = world.act(CONTENT, s, "b")                                         # trade two iron for the cloak
        self.assertIn("gear_fur_cloak", [i.item for i in me(s).inventory])
        s = build.fit(CONTENT, s, slot_of(s, "gear_fur_cloak"))
        s = self.down(s)
        health = stats.current(CONTENT, me(s), "stat_health")
        s = turns.advance(CONTENT, s, 1)
        self.assertEqual(stats.current(CONTENT, me(s), "stat_health"), health)


class TestPoolsInAFight(unittest.TestCase):
    def fight(self):
        """The rats, in the cellar: Hedda stays upstairs, so she doesn't join in."""
        s = effects(new_game(CONTENT, 1), {"op": "move_to", "location": "loc_cellar", "entry": "cellar_stairs"})
        s = encounter.begin(CONTENT, s._replace(encounter_request="enc_rats"))
        self.assertIsNotNone(s.encounter)
        return s

    def test_stamina_fills_with_each_slash_and_a_full_pool_costs_a_turn(self):
        s = self.fight()
        tile = next(t for t in encounter.tiles(CONTENT, s) if t.action == "action_slash")
        self.assertEqual(tile.cost, (("stat_stamina", "2"),))
        s = set_pool(s, PLAYER, "stat_stamina", 5)
        s = encounter.take_turn(CONTENT, s, "action_slash", s.encounter.enemies[0])
        self.assertIn("Player runs out of Stamina and stops for breath.", [m.text for m in s.messages])
        self.assertIn(PLAYER, s.encounter.skip)
        self.assertEqual(stats.current(CONTENT, me(s), "stat_stamina"), 0)    # back to rest: nothing worn loads it

    def test_stamina_falls_back_each_round(self):
        s = set_pool(self.fight(), PLAYER, "stat_stamina", 0)
        s = encounter.take_turn(CONTENT, s, "action_slash", s.encounter.enemies[0])
        self.assertEqual(stats.current(CONTENT, me(s), "stat_stamina"), 1)    # +2 for the slash, -1 at the round's end

    def test_mana_is_spent_and_refused_when_short(self):
        s = self.fight()
        chars = dict(s.characters)
        chars[PLAYER] = me(s)._replace(skills=freeze(dict(me(s).skills, skill_sorcery=1)))   # Firebolt
        s = effects(s._replace(characters=freeze(chars)), {"op": "modify_stat", "stat": "stat_mana", "amount": 4})
        s = set_pool(s, PLAYER, "stat_mana", 2)
        ok, why, _ = encounter.usable(CONTENT, s, PLAYER, "action_firebolt")
        self.assertEqual((ok, why), (False, "Not enough Mana."))
        s = set_pool(s, PLAYER, "stat_mana", 4)
        self.assertTrue(encounter.usable(CONTENT, s, PLAYER, "action_firebolt")[0])
        s = encounter.take_turn(CONTENT, s, "action_firebolt", s.encounter.enemies[0])
        mana = stats.current(CONTENT, me(s), "stat_mana")
        self.assertEqual(mana, 2)                                              # 4 - 3, then +1 at the round's end

    def test_rats_have_no_stamina_to_track(self):
        s = self.fight()
        rat = s.encounter.enemies[0]
        self.assertEqual(stats.stat(CONTENT, s.characters[rat], "stat_stamina"), 0)
        self.assertTrue(encounter.usable(CONTENT, s, rat, "action_bite")[0])


class TestTheInterface(unittest.TestCase):
    """The same screens and keys as the sci-fi pack, with weight, mana and stamina instead of power and heat."""
    UI = default_ui()

    def states(self):
        s = new_game(CONTENT, 1)
        cellar = effects(s, {"op": "move_to", "location": "loc_cellar", "entry": "cellar_stairs"})
        fight = encounter.begin(CONTENT, cellar._replace(encounter_request="enc_rats"))
        return [("walk", s, {}), ("cellar", cellar, {}), ("fight", fight, {}), ("gear", s, {"screen": "gear"}),
                ("gear picked", s, {"screen": "gear", "selected": 0}), ("character", s, {"screen": "character"}),
                ("pack", s, {"panel": "pack", "selected": 0}), ("map", s, {"screen": "map"})]

    def test_every_screen_fits(self):
        for name, state, options in self.states():
            for columns, rows in ((48, 24), (60, 40)):
                with self.subTest(screen=name, size=(columns, rows)):
                    frame = render.render(CONTENT, state, columns, rows, ui=self.UI, **options)
                    lines = frame.rstrip("\n").split("\n")
                    self.assertEqual({visible_len(line) for line in lines}, {columns})
                    self.assertLessEqual(len(lines), rows)

    def test_the_gear_screen_shows_the_genres_numbers(self):
        frame = render.render(CONTENT, new_game(CONTENT, 1), 52, 60, colour=False, ui=self.UI, screen="gear")
        for words in ("WT", "2/8", "Armour", "· empty", "Hand", "1 Sword", "Blessing"):
            self.assertIn(words, frame)
        self.assertNotIn("PWR", frame)

    def test_fight_tiles_show_each_pools_cost(self):
        s = TestPoolsInAFight.fight(self)
        chars = dict(s.characters)
        chars[PLAYER] = me(s)._replace(skills=freeze(dict(me(s).skills, skill_sorcery=1)))
        frame = render.render(CONTENT, s._replace(characters=freeze(chars)), 60, 40, colour=False, ui=self.UI)
        self.assertIn("▲2", frame)                                             # Slash: stamina fills
        self.assertIn("MP3", frame)                                            # Firebolt: mana is spent

    def test_random_keys_never_crash(self):
        keys = sorted((self.UI.bound_keys - {self.UI.bindings["quit"]}) | set("123456789") | set("ufrbehjklmnoyvzgtio"))
        for seed in range(1, 4):
            rng = random.Random(seed)
            state, view = new_game(CONTENT, seed), app.View()
            for _ in range(200):
                state, view, _ = app.handle(CONTENT, state, rng.choice(keys), view, self.UI)
                frame = render.render(CONTENT, state, 48, 24, view.panel, True, view.selected,
                                      view.page, self.UI, view.scroll, view.screen, view.log)
                self.assertEqual({visible_len(line) for line in frame.rstrip("\n").split("\n")}, {48})


if __name__ == "__main__":
    unittest.main()
