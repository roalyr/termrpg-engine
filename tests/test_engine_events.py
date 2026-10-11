"""
Milestone 6: the living world. Done when the grudge and off-screen rivalry events fire
with different casts under different seeds.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from engine import encounter, events, save, turns, world
from engine.content import load_pack
from engine.effects import choose_option, run
from engine.frozen import freeze
from engine.state import Ctx, new_game

ROOT = Path(__file__).resolve().parent.parent
CONTENT = load_pack(ROOT / "packs" / "test_scifi")
PLAYER = "char_player"
RIVALS = {"char_dov", "char_ilse", "char_tomas"}


def texts(state):
    return [m.text for m in state.messages]


def next_day(state, content=CONTENT):
    """Lets the rest of the day pass, then settles what the morning brings."""
    left = 60 - state.turn % 60
    return events.settle(content, turns.advance(content, state, left))


class TestCasting(unittest.TestCase):
    def test_grudge_casts_differ_by_seed(self):
        grudge = CONTENT.get("event", "event_grudge")
        sore = {events.cast(CONTENT, new_game(CONTENT, seed), grudge)[0]["sore"] for seed in range(1, 30)}
        self.assertEqual(sore, {"char_dov", "char_ilse"})       # only these two resent the player

    def test_rivalry_casts_differ_by_seed(self):
        rivalry = CONTENT.get("event", "event_offscreen")
        pairs = set()
        for seed in range(1, 30):
            roles, _ = events.cast(CONTENT, new_game(CONTENT, seed), rivalry)
            self.assertNotEqual(roles["a"], roles["b"])                 # one character, one role
            self.assertTrue({roles["a"], roles["b"]} <= RIVALS)          # rank 1 or more
            pairs.add((roles["a"], roles["b"]))
        self.assertGreater(len(pairs), 3)

    def test_optional_role_and_faction_views(self):
        grudge = CONTENT.get("event", "event_grudge")
        roles, _ = events.cast(CONTENT, new_game(CONTENT, 1), grudge)
        # The NPC has no view of the rival, but likes faction A (50), which the rival belongs to.
        self.assertEqual(roles["friend"], "char_juno")
        s = new_game(CONTENT, 1)
        npc = s.characters["char_juno"]._replace(location="loc_storage")
        s = s._replace(characters=freeze({**s.characters, "char_juno": npc}))
        roles, _ = events.cast(CONTENT, s, grudge)
        self.assertNotIn("friend", roles)                                # nobody here: the optional role stays empty
        self.assertIn("sore", roles)

    def test_required_role_missing_stops_the_event(self):
        s = new_game(CONTENT, 1)
        chars = {cid: cs._replace(rank=0) for cid, cs in s.characters.items()}
        s = s._replace(characters=freeze(chars))
        self.assertIsNone(events.cast(CONTENT, s, CONTENT.get("event", "event_offscreen"))[0])


class TestFiring(unittest.TestCase):
    def test_off_screen_rivalry_is_quiet_and_changes_the_world(self):
        s = new_game(CONTENT, 3)
        roles, _ = events.cast(CONTENT, s, CONTENT.get("event", "event_offscreen"))
        s = events.fire(CONTENT, s, "event_offscreen", manual=True)
        self.assertEqual(texts(s), [])                                     # notify: false
        a, b = f"character:{roles['a']}", f"character:{roles['b']}"
        self.assertEqual(s.relations[a][b], -10)
        self.assertEqual(s.relations[b][a], -10)                           # mutual

    def test_grudge_asks_the_player(self):
        s = events.fire(CONTENT, new_game(CONTENT, 3), "event_grudge", manual=True)
        self.assertTrue(any(t.startswith("Someone holds a grudge.") for t in texts(s)))
        self.assertIsNotNone(s.pending)
        sore = next(cid for cid in ("char_dov", "char_ilse")
                    if s.pending.ctx.roles.get("sore") == cid)
        s = choose_option(CONTENT, s, 0)                                   # apologise
        self.assertEqual(s.relations[f"character:{sore}"]["character:char_player"], -20)

    def test_cooldown_in_days(self):
        s = events.fire(CONTENT, new_game(CONTENT, 3), "event_grudge", manual=True)
        s = choose_option(CONTENT, s, 1)
        grudge = CONTENT.get("event", "event_grudge")
        for day, expected in ((1, False), (2, False), (3, False), (4, True)):
            at = s._replace(turn=(day - 1) * 60)
            self.assertEqual(events._available(CONTENT, at, grudge), expected, day)

    def test_repeat_false(self):
        s = events.fire(CONTENT, new_game(CONTENT, 1), "event_once", manual=True)
        s = events.fire(CONTENT, s, "event_once", manual=True)
        self.assertEqual(s.flags["flag_power"], 10)

    def test_manual_events_still_need_their_condition(self):
        s = run(CONTENT, new_game(CONTENT, 1), Ctx(self_id=PLAYER),
                [freeze({"op": "learn_design", "item": "module_shield", "subject": "self"})])
        before = s.characters[PLAYER].designs
        s = events.fire(CONTENT, s, "event_insight", manual=True)         # 'when' fails: already known
        self.assertEqual(s.characters[PLAYER].designs, before)


class TestRest(unittest.TestCase):
    def test_the_party_recovers_each_morning(self):
        s = new_game(CONTENT, 1)
        s = run(CONTENT, s, Ctx(self_id="char_juno"), [
            freeze({"op": "join_party", "subject": "self"}),
            freeze({"op": "damage", "amount": 999, "damage_type": "dmg_impact", "subject": "self"})])
        s = run(CONTENT, s, Ctx(self_id=PLAYER), [freeze({"op": "damage", "amount": 15, "damage_type": "dmg_impact", "subject": "self"})])
        self.assertTrue(s.characters["char_juno"].down)
        hurt = s.characters[PLAYER].pools["stat_health"]
        s = next_day(s)
        while s.pending is not None:                         # a morning question waits first
            s = events.settle(CONTENT, choose_option(CONTENT, s, 0))
        self.assertFalse(s.characters["char_juno"].down)
        self.assertGreater(s.characters["char_juno"].pools["stat_health"], 0)
        self.assertEqual(s.characters[PLAYER].pools["stat_health"], hurt + 10)


class TestTriggers(unittest.TestCase):
    def test_the_crate_restocks_each_morning(self):
        s = new_game(CONTENT, 1)
        s = world.move(CONTENT, s, "w")
        s = world.act(CONTENT, s, "h")
        self.assertEqual(s.object_states["workshop_crate"], "state_used")
        s = next_day(s)
        while s.pending is not None:                                       # answer any morning grudge
            s = events.settle(CONTENT, choose_option(CONTENT, s, 1))
        self.assertEqual(s.object_states["workshop_crate"], "state_closed")

    def test_arriving_somewhere(self):
        s = new_game(CONTENT, 1)
        for key in "aaww":
            s = world.move(CONTENT, s, key)
        s = world.act(CONTENT, s, "u")
        s = events.settle(CONTENT, world.act(CONTENT, s, "g"))
        self.assertIn("Machines hum somewhere below.", texts(s))
        self.assertEqual(s.flags["flag_power"], 1)

    def test_requested_events_fire_after_losing(self):
        s = new_game(CONTENT, 2)._replace(encounter_request="enc_drones")
        s = events.settle(CONTENT, s)
        self.assertIsNotNone(s.encounter)
        cs = s.characters[PLAYER]
        s = s._replace(characters=freeze({**s.characters, PLAYER: cs._replace(pools=freeze({**cs.pools, "stat_health": 1}))}))
        s = encounter.take_turn(CONTENT, s, "action_strike", "char_drone#1")
        s = events.settle(CONTENT, s._replace(debrief=None))  # leaving the after-action screen
        self.assertIn("Someone drags you out.", texts(s))
        self.assertEqual(s.event_requests, ())

    def test_nothing_fires_during_a_fight(self):
        s = new_game(CONTENT, 2)._replace(encounter_request="enc_drones")
        s = events.settle(CONTENT, s)
        s = s._replace(event_requests=("event_once",))
        s = events.settle(CONTENT, s)
        self.assertEqual(s.event_requests, ("event_once",))
        self.assertEqual(s.flags["flag_power"], 0)

    def test_a_choice_holds_the_rest_of_the_morning(self):
        # Seed search: a morning where the grudge fires and asks, so the restock must wait for the answer.
        for seed in range(1, 60):
            s = new_game(CONTENT, seed)._replace(object_states=freeze({**new_game(CONTENT, seed).object_states,
                                                                       "workshop_crate": "state_used"}))
            s = next_day(s)
            if s.pending is not None:
                break
        else:
            self.fail("no seed made the grudge fire")
        self.assertIn("event_restock", s.event_requests)
        self.assertEqual(s.object_states["workshop_crate"], "state_used")
        s = events.settle(CONTENT, choose_option(CONTENT, s, 1))
        self.assertEqual(s.object_states["workshop_crate"], "state_closed")

    def test_events_per_trigger_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            shutil.copytree(ROOT / "packs" / "test_scifi", pack)
            manifest = json.loads((pack / "pack.json").read_text())
            manifest["settings"] = {"events_per_trigger": 1}
            (pack / "pack.json").write_text(json.dumps(manifest))
            content = load_pack(pack)
        fired_counts = set()
        for seed in range(1, 15):
            s = next_day(new_game(content, seed), content)
            fired_counts.add(len(s.event_log))
        self.assertEqual(fired_counts, {1})

    def test_off_screen_characters_stay_off_the_map(self):
        s = new_game(CONTENT, 1)
        self.assertTrue(RIVALS <= set(s.characters))
        self.assertFalse(RIVALS & set(world.others_here(s)))

    def test_saves_keep_the_event_log(self):
        s = events.fire(CONTENT, new_game(CONTENT, 1), "event_once", manual=True)
        s = s._replace(triggers=("turn",))
        self.assertEqual(save.from_json(CONTENT, save.to_json(CONTENT, s)), s)


if __name__ == "__main__":
    unittest.main()
