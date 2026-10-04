"""
Milestone 4: encounters. Done when the test pack's drone encounter can be played to
each of its three outcomes.
"""
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from engine import encounter, save, stats
from engine.content import load_pack
from engine.effects import run
from engine.frozen import freeze
from engine.state import Ctx, Message, StatusInst, new_game
from tui import app, render

ROOT = Path(__file__).resolve().parent.parent
CONTENT = load_pack(ROOT / "packs" / "test")
PLAYER, NPC = "char_player", "char_juno"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def fight(seed=1, content=CONTENT):
    """A new game in room A (no hazard) with the drone encounter started."""
    s = new_game(content, seed)._replace(encounter_request="enc_drones")
    return encounter.begin(content, s)


def me(state):
    return state.characters[state.player]


def hp(state, cid=PLAYER):
    return stats.current(CONTENT, state.characters[cid], "stat_health")


def texts(state):
    """What the player reads: the messages, or the after-action screen once a fight is over."""
    if state.debrief is not None:
        return [state.debrief.title] + [m.text for m in state.debrief.messages]
    return [m.text for m in state.messages]


def set_pool(state, cid, stat_id, value):
    cs = state.characters[cid]
    return state._replace(characters=freeze({**state.characters, cid: cs._replace(pools=freeze({**cs.pools, stat_id: value}))}))


def strike_until_over(state, limit=20):
    seen = []
    for _ in range(limit):
        if state.encounter is None:
            break
        state = encounter.take_turn(CONTENT, state, "action_strike", encounter.living(state, "enemies")[0])
        seen += texts(state)
    return state, seen


class TestBegin(unittest.TestCase):
    def test_sides_and_intents(self):
        s = fight(2)
        enc = s.encounter
        self.assertEqual(enc.allies, (PLAYER, NPC))
        self.assertEqual(enc.enemies, ("char_drone#1", "char_drone#2"))
        self.assertEqual(enc.spawned, enc.enemies)
        self.assertEqual(s.characters["char_drone#1"].location, "loc_workshop")
        self.assertIsNone(s.characters["char_drone#1"].at)              # not on the map
        self.assertEqual(texts(s)[:2], ["Drones!", "Drones close in."])
        self.assertEqual(encounter.intent_line(CONTENT, s, "char_drone#1"), "STRIKE Player")

    def test_tiles(self):
        tiles = encounter.tiles(CONTENT, fight())
        self.assertEqual([(t.key, t.action) for t in tiles],
                         [("1", "action_strike"), ("2", "action_guard"), ("3", "action_retreat")])
        self.assertEqual(tiles[0].cost, "1")


class TestOutcomes(unittest.TestCase):
    def test_win(self):
        s = fight(2)
        xp_before = me(s).xp.get("skill_salvage", 0)
        material_before = sum(i.count for i in me(s).inventory if i.item == "material_scrap")
        s, seen = strike_until_over(s)
        self.assertIsNone(s.encounter)
        self.assertIn("Won.", seen)
        self.assertFalse(any(cid.startswith("char_drone#") for cid in s.characters))   # spawned copies leave
        self.assertGreater(sum(i.count for i in me(s).inventory if i.item == "material_scrap"), material_before)
        self.assertGreater(me(s).xp["skill_salvage"], xp_before)                             # Strike trains skill A
        self.assertEqual(s.flags["flag_power"], 1)                                          # on_win
        self.assertEqual(me(s).pools["stat_heat"], 2)                                   # cooled to the constant load

    def test_lose(self):
        s = set_pool(fight(2), PLAYER, "stat_health", 1)
        s = encounter.take_turn(CONTENT, s, "action_strike", "char_drone#1")
        self.assertIsNone(s.encounter)
        self.assertIn("Lost.", texts(s))
        # on_defeat ran after the encounter: the player is carried home and patched up.
        self.assertIn("You go down.", texts(s))
        self.assertEqual(me(s).location, "loc_workshop")
        self.assertFalse(me(s).down)
        self.assertEqual(hp(s), 5)
        self.assertIn("event_rescue", s.event_requests)

    def test_escape(self):
        s = fight(4)
        for _ in range(20):
            if s.encounter is None:
                break
            s = encounter.take_turn(CONTENT, s, "action_retreat")
        self.assertIsNone(s.encounter)
        self.assertIn("Escaped.", texts(s))
        self.assertFalse(any(cid.startswith("char_drone#") for cid in s.characters))

    def test_never_a_game_over(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            shutil.copytree(ROOT / "packs" / "test", pack)
            data = json.loads((pack / "characters.json").read_text())
            next(c for c in data["entries"] if c["id"] == PLAYER).pop("on_defeat")
            (pack / "characters.json").write_text(json.dumps(data))
            content = load_pack(pack)
            s = fight(2, content)
            cs = s.characters[PLAYER]
            s = s._replace(characters=freeze({**s.characters, PLAYER: cs._replace(pools=freeze({**cs.pools, "stat_health": 1}))}))
            s = encounter.take_turn(content, s, "action_strike", "char_drone#1")
        self.assertIsNone(s.encounter)
        self.assertFalse(me(s).down)
        self.assertEqual(stats.current(content, me(s), "stat_health"), 1)


class TestRound(unittest.TestCase):
    def test_order_by_priority_then_initiative(self):
        s = fight(2)
        s = encounter.take_turn(CONTENT, s, "action_strike", "char_drone#1")
        self.assertEqual(texts(s), ["Drone: Strike on Player.", "Player takes 3 damage.",           # drones are quicker
                                    "Drone: Strike on Juno.", "Juno takes 5 damage.",
                                    "Player: Strike on Drone.", "Drone takes 5 damage."])
        s = encounter.take_turn(CONTENT, s, "action_guard")
        self.assertEqual(texts(s)[0], "Player uses Guard.")                                                # priority 1 goes first
        self.assertIn("Player is unhurt.", texts(s))                                                      # Guard's armor holds

    def test_guard_blunts_the_hit(self):
        s = fight(1)
        before = hp(s)
        s = encounter.take_turn(CONTENT, s, "action_guard")
        self.assertEqual(hp(s), before)                       # armor 2 + 4 stops the drone's 5

    def test_cooldown(self):
        s = encounter.take_turn(CONTENT, fight(2), "action_guard")
        guard = next(t for t in encounter.tiles(CONTENT, s) if t.action == "action_guard")
        self.assertEqual((guard.available, guard.hint), (False, "Ready in 2."))   # cooldown 2: two whole rounds
        s = encounter.take_turn(CONTENT, s, "action_strike", encounter.living(s, "enemies")[0])
        guard = next(t for t in encounter.tiles(CONTENT, s) if t.action == "action_guard")
        self.assertEqual((guard.available, guard.hint), (False, "Ready in 1."))
        s = encounter.take_turn(CONTENT, s, "action_strike", encounter.living(s, "enemies")[0])
        self.assertTrue(next(t for t in encounter.tiles(CONTENT, s) if t.action == "action_guard").available)

    def test_overheat(self):
        s = set_pool(fight(2), PLAYER, "stat_heat", 7)
        s = encounter.take_turn(CONTENT, s, "action_strike", "char_drone#1")
        self.assertIn("Player overheats.", texts(s))
        self.assertEqual(me(s).pools["stat_heat"], 2)         # back to the constant load
        s = encounter.take_turn(CONTENT, s, "action_strike", encounter.living(s, "enemies")[0])
        self.assertIn("Player loses a turn.", texts(s))
        self.assertNotIn("Player uses Strike.", texts(s))

    def test_charges_and_consumed_items(self):
        s = fight(2)
        s = run(CONTENT, s, Ctx(self_id=PLAYER), [freeze({"op": "grant_xp", "skill": "skill_salvage", "amount": 30, "subject": "self"})])
        material = sum(i.count for i in me(s).inventory if i.item == "material_scrap")
        s = encounter.take_turn(CONTENT, s, "action_burn")
        self.assertEqual(sum(i.count for i in me(s).inventory if i.item == "material_scrap"), material - 2)
        self.assertTrue(any(st.status == "status_burning" for st in s.characters["char_drone#1"].statuses))
        burst = next(t for t in encounter.tiles(CONTENT, s) if t.action == "action_burn")
        self.assertEqual((burst.available, burst.hint), (False, "Used up."))

    def test_stunned_fighters_lose_their_action(self):
        s = fight(2)
        drone = s.characters["char_drone#1"]
        stunned = drone._replace(statuses=(StatusInst("status_stun", 1, 2),))
        s = s._replace(characters=freeze({**s.characters, "char_drone#1": stunned}))
        s = encounter.take_turn(CONTENT, s, "action_guard")
        self.assertIn("Drone loses a turn.", texts(s))

    def test_ai_flees_when_hurt(self):
        s = set_pool(fight(2), "char_drone#2", "stat_health", 1)
        s = encounter.take_turn(CONTENT, s, "action_guard")
        self.assertIn("Drone flees.", texts(s))
        self.assertIn("char_drone#2", s.encounter.fled)
        self.assertEqual(encounter.living(s, "enemies"), ["char_drone#1"])

    def test_ai_never_retreats_for_its_side(self):
        # The NPC ally only has the innate Retreat; it must not use it.
        s = fight(2)
        self.assertNotIn(NPC, s.encounter.intents)

    def test_save_mid_encounter(self):
        s = encounter.take_turn(CONTENT, fight(2), "action_strike", "char_drone#1")
        self.assertEqual(save.from_json(CONTENT, save.to_json(CONTENT, s)), s)


class TestReadableFights(unittest.TestCase):
    def test_a_fight_starts_on_a_clean_page(self):
        s = new_game(CONTENT, 2)._replace(encounter_request="enc_drones",
                                          messages=(Message("plain", "Something from before."),))
        s = encounter.begin(CONTENT, s)
        self.assertEqual(texts(s), ["Drones!", "Drones close in."])

    def test_the_log_is_labelled_with_its_round(self):
        s = encounter.take_turn(CONTENT, fight(2), "action_strike", "char_drone#1")
        self.assertEqual((s.encounter.round, s.encounter.log_round), (2, 1))
        frame = ANSI.sub("", render.render(CONTENT, s, 44, 60))
        self.assertIn("Drones · round 2", frame)
        self.assertIn("Round 1:", frame)
        log = frame.index("Round 1:")
        self.assertLess(frame.index("Drone: Strike on Player."), frame.index("Player: Strike on Drone."))
        self.assertGreater(frame.index("Drone: Strike on Player."), log)

    def test_the_end_is_an_after_action_screen(self):
        s, _ = strike_until_over(fight(2))
        self.assertIsNone(s.encounter)
        self.assertEqual(s.messages, ())                       # nothing bleeds onto the map
        self.assertEqual((s.debrief.title, s.debrief.result), ("Won.", "won"))
        self.assertTrue(any(m.text.startswith("Found:") for m in s.debrief.messages))
        frame = ANSI.sub("", render.render(CONTENT, s, 44, 60))
        self.assertIn("Won.", frame)
        self.assertIn(f"Round {s.debrief.round}:", frame)
        self.assertIn("Any key: continue", frame)
        s2, view, _ = app.handle(CONTENT, s, "w")
        self.assertIsNone(s2.debrief)
        self.assertEqual(s2.characters[PLAYER].at, s.characters[PLAYER].at)   # the key only closed the screen
        self.assertEqual(s2.messages, ())

    def test_follow_ups_wait_for_the_after_action_screen(self):
        from engine import events
        s = set_pool(fight(2), PLAYER, "stat_health", 1)
        s = events.settle(CONTENT, encounter.take_turn(CONTENT, s, "action_strike", "char_drone#1"))
        self.assertEqual(s.debrief.result, "lost")
        self.assertIn("event_rescue", s.event_requests)        # the rescue waits
        s, _, _ = app.handle(CONTENT, s, "x")
        self.assertIn("Someone drags you out.", [m.text for m in s.messages])

    def test_debrief_survives_a_save(self):
        s, _ = strike_until_over(fight(2))
        self.assertEqual(save.from_json(CONTENT, save.to_json(CONTENT, s)), s)


class TestEncounterScreen(unittest.TestCase):
    def test_frame(self):
        s = fight(2)
        frame = ANSI.sub("", render.render(CONTENT, s, 44, 60))
        for words in ("Drones · round 1", "1 Drone", "⚠ STRIKE Player", "1 Strike", "2 Guard", "══╡▓▓▓╞══", "1-3 act"):
            self.assertIn(words, frame)
        for line in frame.splitlines():
            self.assertEqual(len(line), 44, line)

    def test_keys_pick_tile_then_target(self):
        s = fight(2)
        s, view, _ = app.handle(CONTENT, s, "1")
        self.assertEqual(view.selected, 0)                    # two drones: waiting for a target
        self.assertIn("1-2 target", ANSI.sub("", render.render(CONTENT, s, 44, 60, selected=view.selected)))
        s, view, _ = app.handle(CONTENT, s, "2", view)
        self.assertIsNone(view.selected)
        self.assertEqual(s.encounter.round, 2)

    def test_world_actions_start_encounters(self):
        s = new_game(CONTENT, 1)
        s = s._replace(encounter_request="enc_drones")
        s, _, _ = app.handle(CONTENT, s, ".")
        self.assertIsNotNone(s.encounter)


if __name__ == "__main__":
    unittest.main()
