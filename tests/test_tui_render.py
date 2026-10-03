"""
The renderer reads the UI pack: every screen at the minimum size and wider, zones dropped
and scrolled to fit, and a custom UI pack changing keys, glyphs, words and layout.
"""
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from engine import encounter, world
from engine.content import load_pack
from engine.effects import run
from engine.frozen import freeze
from engine.state import Ctx, new_game
from tui import app, render
from tui.text import Style, visible_len
from tui.ui import UIPackError, default_ui, load_ui, ui_dir_for
from tui.widgets import option_text

ROOT = Path(__file__).resolve().parent.parent
CONTENT = load_pack(ROOT / "packs" / "test")
UI = default_ui()
ANSI = re.compile(r"\x1b\[[0-9;]*m")
SIZES = ((40, 20), (44, 30), (60, 40), (100, 60))


def walk(state, sequence):
    for key in sequence:
        state = world.move(CONTENT, state, key)
    return state


def menu_state():
    return walk(new_game(CONTENT, 1), "aaww")              # next to the door to room B


def choice_state():
    s = new_game(CONTENT, 1)
    return run(CONTENT, s, Ctx(self_id=s.player), CONTENT.get("object", "obj_terminal")["interactions"][0]["effects"])


def encounter_state():
    return encounter.begin(CONTENT, new_game(CONTENT, 2)._replace(encounter_request="enc_drones"))


def debrief_state():
    s = encounter_state()
    while s.encounter is not None:
        s = encounter.take_turn(CONTENT, s, "action_strike", encounter.living(s, "enemies")[0])
    return s


def screens():
    """Every screen and panel, as (name, state, render options)."""
    return [
        ("walk", new_game(CONTENT, 1), {}),
        ("menu", menu_state(), {}),
        ("choice", choice_state(), {}),
        ("board", new_game(CONTENT, 1), {"panel": "pack"}),
        ("board picked", new_game(CONTENT, 1), {"panel": "pack", "selected": 3}),
        ("sheet", new_game(CONTENT, 1), {"panel": "character"}),
        ("encounter", encounter_state(), {}),
        ("target", encounter_state(), {"selected": 0}),
        ("debrief", debrief_state(), {}),
    ]


def plain(state, columns=44, rows=60, ui=UI, **options):
    return ANSI.sub("", render.render(CONTENT, state, columns, rows, ui=ui, **options))


class TestEveryScreen(unittest.TestCase):
    def test_frames_are_exactly_the_terminal_width_and_fit_its_height(self):
        for name, state, options in screens():
            for columns, rows in SIZES:
                with self.subTest(screen=name, size=(columns, rows)):
                    frame = render.render(CONTENT, state, columns, rows, ui=UI, **options)
                    lines = frame.rstrip("\n").split("\n")
                    self.assertEqual({visible_len(line) for line in lines}, {columns})
                    self.assertLessEqual(len(lines), rows)

    def test_same_state_same_frame(self):
        for name, state, options in screens():
            with self.subTest(screen=name):
                self.assertEqual(plain(state, **options), plain(state, **options))

    def test_plain_text_has_no_escapes(self):
        for name, state, options in screens():
            with self.subTest(screen=name):
                self.assertNotIn("\x1b", render.render(CONTENT, state, 44, 60, colour=False, ui=UI, **options)
                                 .replace("\x1b[7m", "").replace("\x1b[0m", ""))

    def test_what_each_screen_shows(self):
        expected = {
            "walk": ["Room A", "Region A1", "Day 1", "WASD move", "P pack"],
            "menu": ["Door", "G Go to Room B - The door is closed.", "I Inspect", "X close"],
            "choice": ["Pick one.", "1 Option A", "1-2 choose"],
            "board": ["Fitted:", "Carried:", "1 Frame A", "] page"],
            "sheet": ["Skill A 1", "C close"],
            "encounter": ["Drones · round 1", "1 Strike", "⚠ STRIKE", "1-3 act", "Q quit"],
            "target": ["1-2 target", "X back"],
            "debrief": ["Won.", "Round", "Any key: continue"],
        }
        for name, state, options in screens():
            for words in expected.get(name, []):
                with self.subTest(screen=name, words=words):
                    self.assertIn(words, plain(state, **options))

    def test_too_small(self):
        self.assertEqual(plain(new_game(CONTENT, 1), 39, 60).strip(), UI.word("terminal_too_small", columns=40, rows=20))
        self.assertIn("at least 40x20", plain(new_game(CONTENT, 1), 60, 19))


class TestFitting(unittest.TestCase):
    def test_low_priority_zones_drop_first(self):
        s = menu_state()
        self.assertIn("Locker", plain(s, 44, 60))            # the legend
        self.assertNotIn("Locker", plain(s, 44, 20))
        self.assertIn("I Inspect", plain(s, 44, 20))          # the menu stays

    def test_scroll_zones_keep_their_last_lines(self):
        s = new_game(CONTENT, 1)
        tall, short = plain(s, 40, 60, panel="pack", selected=3), plain(s, 40, 20, panel="pack", selected=3)
        self.assertIn("Fitted:", tall)
        self.assertNotIn("Fitted:", short)                    # the top scrolled away
        self.assertIn("U Use", short)                         # the picked item's options stay
        self.assertIn("1-7 pick", short)                      # and the key hints

    def test_encounter_title_drops_on_short_terminals(self):
        s = encounter_state()
        self.assertIn("Drones · round 1", plain(s, 40, 30))
        self.assertNotIn("Drones · round 1", plain(s, 40, 20))
        self.assertIn("1 Strike", plain(s, 40, 20))


    def test_hints_wrap_between_entries(self):
        lines = plain(new_game(CONTENT, 1), 44, 60).splitlines()
        self.assertIn("│ Q quit", "\n".join(lines))                  # moved whole to the next line
        self.assertFalse(any(line.rstrip(" │").endswith(" Q") for line in lines))

    def test_kept_zones_stay_when_empty(self):
        lines = plain(new_game(CONTENT, 1), 44, 60).splitlines()
        self.assertFalse(any(a.startswith("├") and b.startswith("├") for a, b in zip(lines, lines[1:])))


    def test_short_encounters_switch_to_compact_widgets(self):
        s = new_game(CONTENT, 1)
        s = run(CONTENT, s, Ctx(self_id=s.player), [freeze({"op": "grant_xp", "skill": "skill_a", "amount": 30,
                                                             "subject": "self"})])          # unlocks a fourth tile
        s = encounter.begin(CONTENT, s._replace(encounter_request="enc_drones"))
        self.assertEqual(len(encounter.tiles(CONTENT, s)), 4)
        roomy, short = plain(s, 40, 40), plain(s, 40, 20)
        self.assertIn("┌────────┐", roomy)                       # boxed tiles when there's room
        self.assertLessEqual(len(short.splitlines()), 20)
        self.assertIn("1 Strike ▲1  2 Guard ▲1", short)           # a list when there isn't
        self.assertIn("4 Retreat", short)
        self.assertIn("2 Drone", short)                          # every fighter still shown


class TestEngineOptionsAreWordedByTheUI(unittest.TestCase):
    def test_built_in_options_have_no_label(self):
        options = {o.kind: o for o in world.menu(CONTENT, menu_state()).options}
        self.assertIsNone(options["go"].label)
        self.assertEqual(dict(options["go"].params), {"destination": "Room B"})
        self.assertEqual(option_text(UI, options["go"]), "Go to Room B")
        self.assertEqual(options["interaction"].label, "Open")    # the content's own label

    def test_round_end_is_a_heading(self):
        s = encounter_state()
        s = run(CONTENT, s, Ctx(self_id=s.player), [freeze(
            {"op": "apply_status", "status": "status_dot", "subject": "self", "duration": 3})])
        s = encounter.take_turn(CONTENT, s, "action_guard")         # the status ticks at the round's end
        self.assertIn(("heading", "round_end"), [(m.kind, m.text) for m in s.messages])
        self.assertIn("End of round", plain(s))


class TestEngineDefaults(unittest.TestCase):
    def test_engine_default_bindings_match_the_default_ui_pack(self):
        # The engine avoids these keys when no UI pack is passed in; they must be the standard ones.
        self.assertEqual(world.STANDARD_BINDINGS, UI.bound_keys)

    def test_menu_keys_are_drawn_in_the_key_style(self):
        frame = render.render(CONTENT, menu_state(), 44, 60, ui=UI)
        self.assertIn(Style(True, UI.tokens["styles"]).key("U"), frame)
        self.assertIn("\x1b[7;", frame)


class TestCustomUIPack(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "mine"
        shutil.copytree(ui_dir_for("default"), self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def change(self, name, change):
        path = self.dir / name
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_rebound_keys_change_the_hints_and_the_input(self):
        self.change("keys.json", lambda d: d.setdefault("bindings", {}).update(pack="m", move_west="j"))
        ui = load_ui(self.dir)
        s = new_game(CONTENT, 1)
        self.assertIn("M pack", plain(s, ui=ui))
        self.assertIn("WJSD move", plain(s, ui=ui))
        _, view, _ = app.handle(CONTENT, s, "m", app.View(), ui)
        self.assertEqual(view.panel, "pack")
        _, view, _ = app.handle(CONTENT, s, "p", app.View(), ui)
        self.assertIsNone(view.panel)
        moved, _, _ = app.handle(CONTENT, s, "j", app.View(), ui)
        self.assertEqual(moved.characters[s.player].at[1], s.characters[s.player].at[1] - 1)

    def test_interaction_keys_avoid_the_bindings(self):
        s = menu_state()
        self.assertEqual(next(o.key for o in world.menu(CONTENT, s).options if o.label == "Open"), "u")
        moved = next(o.key for o in world.menu(CONTENT, s, frozenset("u")).options if o.label == "Open")
        self.assertNotIn(moved, {"u", "g", "t", "i"})

    def test_glyphs_words_and_layout(self):
        self.change("tokens.json", lambda d: d.setdefault("glyphs", {}).update(player="&"))
        self.change("words.json", lambda d: d.setdefault("engine", {}).update(go_to="Enter {destination}"))
        self.change("screens.json", lambda d: d.update(world=[z for z in d["world"]
                                                              if z["content"] != {"widget": "legend"}]))
        ui = load_ui(self.dir)
        s = menu_state()
        frame = plain(s, ui=ui)
        self.assertIn("G Enter Room B", frame)
        self.assertNotIn("Locker", frame)
        self.assertIn("&", plain(new_game(CONTENT, 1), ui=ui))

    def test_invalid_packs_are_refused(self):
        self.change("keys.json", lambda d: d.setdefault("bindings", {}).update(pack="g"))
        with self.assertRaises(UIPackError) as caught:
            load_ui(self.dir)
        self.assertIn("the engine's key for 'go'", str(caught.exception))

    def test_play_refuses_a_broken_ui_pack(self):
        self.change("keys.json", lambda d: d.setdefault("bindings", {}).update(pack="f"))
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            code = app.run(ROOT / "packs" / "test", Path(self.tmp.name) / "save.json", 1, True, ui_dir=self.dir)
        self.assertEqual(code, 1)
        self.assertIn("the engine's key for 'fit'", out.getvalue())


if __name__ == "__main__":
    unittest.main()
