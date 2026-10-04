"""
Milestone 2: the walkable world. The playthrough test is the milestone's 'done when':
walk room A to room B, open doors, search the crate, take hazard damage, talk to the
NPC and recruit them.
"""
import io
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from engine import save, stats, turns, world
from engine.content import load_pack
from engine.effects import run
from engine.frozen import freeze
from engine.state import Ctx, StatusInst, new_game
from tui import app, render
from tui.text import Style
from tui.ui import default_ui
from tui.widgets import option_text

UI = default_ui()

ROOT = Path(__file__).resolve().parent.parent
CONTENT = load_pack(ROOT / "packs" / "test")
PLAYER, NPC = "char_player", "char_juno"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def keys(state, sequence):
    for key in sequence:
        if key in world.DIRECTIONS:
            state = world.move(CONTENT, state, key)
        else:
            state = world.act(CONTENT, state, key)
    return state


def me(state):
    return state.characters[state.player]


def health(state):
    return stats.current(CONTENT, me(state), "stat_health")


def option(state, label):
    return next(o for o in world.menu(CONTENT, state).options if option_text(UI, o) == label)


def texts(state):
    return [m.text for m in state.messages]


class TestPlaythrough(unittest.TestCase):
    def test_the_test_pack_is_playable(self):
        s = new_game(CONTENT, 1)
        self.assertEqual(me(s).at, (2, 4))

        # Walk to the closed door and open it with the fitted tool, which wears.
        s = keys(s, "aaww")
        self.assertEqual(me(s).at, (0, 2))
        self.assertEqual(s.focus, ("placement", "workshop_door"))
        self.assertFalse(option(s, "Go to Storage").available)
        self.assertEqual(option(s, "Go to Storage").hint, "The door is closed.")
        s = keys(s, "u")
        self.assertEqual(s.object_states["workshop_door"], "state_open")
        self.assertEqual(me(s).fitted[0].condition, 3)

        # Through to room B: the hazard hurts every turn there.
        s = keys(s, "g")
        self.assertEqual((me(s).location, me(s).at), ("loc_storage", (0, 3)))
        self.assertIn("You enter Storage.", texts(s))
        before = health(s)
        s = keys(s, "s")
        self.assertLess(health(s), before)

        # And back.
        s = keys(s, "wg")
        self.assertEqual(me(s).location, "loc_workshop")

        # The crate is solid: bump it to focus, then search once a day.
        s = keys(s, "sdd")                                      # the second step east bumps it
        self.assertEqual(me(s).at, (1, 3))
        self.assertEqual(s.focus, ("placement", "workshop_crate"))
        turn = s.turn
        s = keys(s, "f")
        self.assertEqual(s.turn, turn + 2)                    # searching takes two turns
        self.assertEqual(s.object_states["workshop_crate"], "state_used")
        self.assertFalse(option(s, "Search").available)

        # The NPC: bump to focus, talk, trade the key, then recruit.
        s = keys(s, "ss")
        self.assertEqual(s.focus, ("character", NPC))
        s = keys(s, "t")
        self.assertIn("Juno: Hello.", texts(s))
        recruit = option(s, "Recruit")
        self.assertFalse(recruit.available)                   # not trusted yet
        s = keys(s, "b")
        self.assertIn("Got: Medkit x2.", texts(s))
        s = keys(s, option(s, "Recruit").key)
        self.assertEqual(me(s).id, PLAYER)
        self.assertEqual(s.characters[NPC].leader, PLAYER)

        # The NPC now travels with the player and moves with them.
        s = keys(s, "a")
        self.assertEqual(s.characters[NPC].at, me(s).at)
        self.assertNotIn(NPC, world.others_here(s))

        # The whole game survives a save.
        self.assertEqual(save.from_json(CONTENT, save.to_json(CONTENT, s)), s)


class TestMovement(unittest.TestCase):
    def test_walls_do_nothing(self):
        s = new_game(CONTENT, 1)
        s = keys(s, "d")                                       # (2, 5) is the east wall
        self.assertEqual((me(s).at, s.turn, s.messages), ((2, 4), 0, ()))

    def test_each_step_is_a_turn(self):
        s = keys(new_game(CONTENT, 1), "aa")
        self.assertEqual(s.turn, 2)

    def test_out_of_reach_closes_the_menu(self):
        s = keys(new_game(CONTENT, 1), "w")                  # bump the crate
        self.assertIsNotNone(world.menu(CONTENT, s))
        s = keys(s, "aa")
        self.assertIsNone(world.menu(CONTENT, s))

    def test_reserved_keys_are_reassigned(self):
        s = keys(new_game(CONTENT, 1), "as")                 # step west, bump the NPC below
        labels = {option_text(UI, o): o.key for o in world.menu(CONTENT, s).options}
        self.assertEqual(labels["Talk"], "t")
        self.assertNotEqual(labels["Recruit"], "t")


class TestTurns(unittest.TestCase):
    def test_statuses_tick_and_expire(self):
        s = new_game(CONTENT, 1)
        s = run(CONTENT, s, Ctx(self_id=PLAYER), [freeze(
            {"op": "apply_status", "status": "status_burning", "subject": "self", "duration": 2, "stacks": 2})])
        start = health(s)
        s = turns.advance(CONTENT, s, 1)
        self.assertEqual(me(s).statuses, (StatusInst("status_burning", 2, 1),))
        self.assertLess(health(s), start)
        s = turns.advance(CONTENT, s, 1)
        self.assertEqual(me(s).statuses, ())
        self.assertIn("Player: Burning ends.", texts(s))

    def test_timed_stat_changes_end(self):
        s = new_game(CONTENT, 1)
        s = run(CONTENT, s, Ctx(self_id=PLAYER), [freeze(
            {"op": "modify_stat", "stat": "stat_armor", "amount": 5, "duration": 2, "subject": "self"})])
        self.assertEqual(stats.stat(CONTENT, me(s), "stat_armor"), 7)
        s = turns.advance(CONTENT, s, 2)
        self.assertEqual(stats.stat(CONTENT, me(s), "stat_armor"), 2)

    def test_spend_time_is_paid(self):
        s = new_game(CONTENT, 1)
        s = run(CONTENT, s, Ctx(self_id=PLAYER), [freeze({"op": "spend_time", "turns": 5})])
        s = turns.advance(CONTENT, s, 1)
        self.assertEqual((s.turn, s.turns_owed), (6, 0))

    def test_phase_and_day_messages(self):
        s = turns.advance(CONTENT, new_game(CONTENT, 1), 30)
        self.assertIn("Night shift.", texts(s))
        s = turns.advance(CONTENT, s._replace(messages=()), 30)
        self.assertIn("Day 2.", texts(s))

    def test_daily_interactions_come_back(self):
        s = keys(new_game(CONTENT, 1), "w")                  # focus the crate
        s = s._replace(object_states=freeze({**s.object_states}))
        s = keys(s, "f")
        self.assertEqual(option(s, "Search").hint, "Already searched.")
        # The crate's own state keeps it closed until something restocks it; with the state
        # reset by hand, the daily limit alone still blocks it today and frees it tomorrow.
        s = s._replace(object_states=freeze({**s.object_states, "workshop_crate": "state_closed"}))
        self.assertEqual(option(s, "Search").hint, "Already done.")
        s = turns.advance(CONTENT, s, 60)
        self.assertTrue(option(s, "Search").available)


class TestSave(unittest.TestCase):
    def test_file_round_trip_and_refusals(self):
        s = keys(new_game(CONTENT, 3), "aaww")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "slot.json"
            save.save(CONTENT, s, path)
            self.assertEqual(save.load(CONTENT, path), s)
            text = path.read_text()
            with self.assertRaisesRegex(save.SaveError, "for pack 'other'"):
                save.from_json(CONTENT, text.replace('"pack": "test"', '"pack": "other"'))
            with self.assertRaisesRegex(save.SaveError, "version 9.0.0"):
                save.from_json(CONTENT, text.replace(f'"pack_version": "{CONTENT.pack["version"]}"', '"pack_version": "9.0.0"'))

    def test_pending_choice_survives_a_save(self):
        s = keys(new_game(CONTENT, 1), "ddd")
        s = run(CONTENT, s, Ctx(self_id=PLAYER), CONTENT.get("object", "obj_terminal")["interactions"][0]["effects"])
        self.assertIsNotNone(s.pending)
        self.assertEqual(save.from_json(CONTENT, save.to_json(CONTENT, s)), s)


class TestInspect(unittest.TestCase):
    def test_inspect_explains_what_a_thing_does(self):
        s = world.act(CONTENT, keys(new_game(CONTENT, 1), "ss"), "i")       # the workbench below the start
        text = texts(s)[-1]
        for word in ("repair", "take items apart", "make items", "modify", "common-grade"):
            self.assertIn(word, text)

    def test_inspecting_a_person_gives_name_title_and_description(self):
        s = world.act(CONTENT, keys(new_game(CONTENT, 1), "as"), "i")       # Juno, below-left
        self.assertTrue(texts(s)[-1].startswith("Juno - Scrap trader. Deals in"))

    def test_every_object_says_what_it_is(self):
        for object_id, record in CONTENT.all("object").items():
            if object_id != "obj_passage":                                 # its placement describes it
                self.assertGreater(len(record.get("description", "")), 60, object_id)


class TestScreen(unittest.TestCase):
    def frame(self, state, columns=44, **kw):
        return ANSI.sub("", render.render(CONTENT, state, columns, 60, **kw))

    def test_frame_fits_the_width(self):
        s = keys(new_game(CONTENT, 1), "aaww")
        for columns in (40, 44, 60):
            for line in self.frame(s, columns).splitlines():
                self.assertEqual(len(line), columns, line)

    def test_frame_shows_the_world_in_the_packs_words(self):
        f = self.frame(keys(new_game(CONTENT, 1), "aaww"))
        for words in ("Workshop", "Lower deck", "Day 1 · Day shift", "HP", "Door", "Go to Storage", "Inspect", "J Juno"):
            self.assertIn(words, f)

    def test_hazards_shown_in_the_header(self):
        f = self.frame(keys(new_game(CONTENT, 1), "aawwug"))
        self.assertIn("gas leak", f)

    def test_panels_and_choices(self):
        s = new_game(CONTENT, 1)
        self.assertIn("Carried:", self.frame(s, panel="pack"))
        self.assertIn("Salvage 1", self.frame(s, panel="character"))
        s = run(CONTENT, s, Ctx(self_id=PLAYER), CONTENT.get("object", "obj_terminal")["interactions"][0]["effects"])
        f = self.frame(s)
        self.assertIn("1 Check the logs", f)
        self.assertIn("1-2 choose", f)

    def test_too_small(self):
        self.assertIn("at least 40x20", render.render(CONTENT, new_game(CONTENT, 1), 30, 60))


class TestPlaytestFixes(unittest.TestCase):
    def test_unavailable_choice_options_are_marked(self):
        s = run(CONTENT, new_game(CONTENT, 1), Ctx(self_id=PLAYER),
                CONTENT.get("object", "obj_terminal")["interactions"][0]["effects"])
        coloured = render.render(CONTENT, s, 44, 60)
        frame = ANSI.sub("", coloured)
        self.assertIn("2 Reroute power - Needs the power on.", frame)      # the power on is 0: unavailable, with its hint
        self.assertIn(Style(True, UI.tokens["styles"]).role("2 Reroute power - Needs the power on.", "unavailable"), coloured)   # and greyed
        self.assertEqual(s.rng, run(CONTENT, new_game(CONTENT, 1), Ctx(self_id=PLAYER),
                                    CONTENT.get("object", "obj_terminal")["interactions"][0]["effects"]).rng)

    def test_training_console(self):
        s = keys(new_game(CONTENT, 1), "aaaw")                   # bump the console at (1, 1)
        self.assertEqual(s.focus, ("placement", "workshop_trainer"))
        s = keys(s, "u")
        self.assertIn("Salvage 2! Unlocks Burn.", texts(s))

    def test_med_station_heals_the_party_and_revives(self):
        s = new_game(CONTENT, 1)
        npc = s.characters[NPC]                                  # a companion who went down
        s = s._replace(characters=freeze({**s.characters, NPC: npc._replace(
            leader=PLAYER, down=True, pools=freeze({**npc.pools, "stat_health": 0}))}))
        s = keys(s, "aaww")                                      # to the door, with the NPC in tow
        s = keys(s, "ugssaw")                                    # open, go through, to (2, 2), bump the station
        self.assertEqual(s.focus, ("placement", "storage_medbay"))
        s = keys(s, "u")
        self.assertIn("Everyone is patched up.", texts(s))
        self.assertFalse(s.characters[NPC].down)
        # Healed to 10; then the turn ends and Storage's hazard hits the unsuited NPC once.
        self.assertEqual(stats.current(CONTENT, s.characters[NPC], "stat_health"), 9)


class TestApp(unittest.TestCase):
    def test_handle_keys(self):
        s = new_game(CONTENT, 1)
        s, view, quit_now = app.handle(CONTENT, s, "p")
        self.assertEqual((view.panel, quit_now), ("pack", False))
        s, view, _ = app.handle(CONTENT, s, "a", view)
        self.assertIsNone(view.panel)
        s, _, _ = app.handle(CONTENT, s, ".")
        self.assertEqual(s.turn, 2)
        _, _, quit_now = app.handle(CONTENT, s, "q")
        self.assertTrue(quit_now)

    def test_choice_keys(self):
        s = run(CONTENT, new_game(CONTENT, 1), Ctx(self_id=PLAYER),
                CONTENT.get("object", "obj_terminal")["interactions"][0]["effects"])
        s, _, _ = app.handle(CONTENT, s, "w")                # ignored while a choice waits
        self.assertIsNotNone(s.pending)
        s, _, _ = app.handle(CONTENT, s, "1")
        self.assertIsNone(s.pending)

    def test_scripted_game_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "slot.json"
            with mock.patch("sys.stdin", io.StringIO("aawwu q")), redirect_stdout(io.StringIO()) as out:
                code = app.run(ROOT / "packs" / "test", path, seed=1, fresh=True, colour=False)
            self.assertEqual(code, 0)
            self.assertIn("Saved.", out.getvalue())
            state = save.load(CONTENT, path)
            self.assertEqual(state.object_states["workshop_door"], "state_open")


if __name__ == "__main__":
    unittest.main()
