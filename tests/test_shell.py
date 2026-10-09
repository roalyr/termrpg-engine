"""
Milestone 7, step 8: the start screen, the save slots, the help screen and the quit question.
"""
import io
import json
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from engine import encounter, save, world
from engine.content import load_pack
from engine.state import new_game
from tui import app, render, shell
from tui.text import visible_len
from tui.ui import default_ui, load_ui, ui_dir_for

ROOT = Path(__file__).resolve().parent.parent
CONTENT = load_pack(ROOT / "packs" / "test")
UI = default_ui()
ANSI = re.compile(r"\x1b\[[0-9;]*m")


class Saves:
    """A temporary saves folder with some slots filled."""

    def __init__(self, test, filled=()):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        for number in filled:
            state = world.move(CONTENT, new_game(CONTENT, number), "a")
            save.save(CONTENT, state, shell.slot_path(self.dir, number))

    def slots(self):
        return shell.read_slots(CONTENT, self.dir, UI.tokens["size"]["save_slots"])


def draw(view, slots, columns=44, rows=60, colour=False, ui=UI):
    data = shell.ShellData(shell.entries(slots), slots, view.mode)
    return ANSI.sub("", render.render_shell(CONTENT, ui, view, data, columns, rows, colour))


class TestStartScreen(unittest.TestCase):
    def test_a_first_start_offers_a_new_game(self):
        slots = Saves(self).slots()
        frame = draw(shell.Shell(), slots)
        for words in ("Test pack", CONTENT.pack["version"], "▸1 New game", "2 Help", "3 Quit", "a workshop",
                      "1-3 choose"):
            self.assertIn(words, frame)
        self.assertNotIn("Continue", frame)
        self.assertNotIn("Load", frame)

    def test_continue_shows_what_it_resumes(self):
        saves = Saves(self, filled=(2,))
        frame = draw(shell.Shell(), saves.slots())
        self.assertIn("1 Continue", frame)
        self.assertIn("Slot 2 · Workshop · Day 1", frame)
        self.assertIn("3 Load", frame)

    def test_choices(self):
        saves = Saves(self, filled=(1, 2))
        slots = saves.slots()
        _, outcome = shell.handle(shell.Shell(), None, "1", slots)               # Continue: the latest save
        self.assertEqual(outcome[:2], ("play", shell.last_played(slots).path))
        _, outcome = shell.handle(shell.Shell(), None, "2", slots)               # New game: the empty slot
        self.assertEqual(outcome, ("play", shell.slot_path(saves.dir, 3), True))
        view, outcome = shell.handle(shell.Shell(), None, "3", slots)            # Load: the slots
        self.assertEqual((view.screen, view.mode, outcome), ("slots", "load", None))
        view, _ = shell.handle(shell.Shell(), "move_south", "s", slots)          # up and down move the pick
        self.assertEqual(view.selected, 1)
        _, outcome = shell.handle(view, None, "\n", slots)                       # Enter chooses it
        self.assertEqual(outcome[0], "play")
        _, outcome = shell.handle(shell.Shell(), "quit", "q", slots)
        self.assertEqual(outcome, "exit")

    def test_loading_a_slot(self):
        saves = Saves(self, filled=(2,))
        slots = saves.slots()
        view = shell.Shell("slots")
        frame = draw(view, slots)
        for words in ("Load a game", "1 Slot 1", "empty", "2 Slot 2", "Workshop · Day 1", "saved ", "X back"):
            self.assertIn(words, frame)
        same, outcome = shell.handle(view, None, "1", slots)                     # an empty slot: nothing to load
        self.assertIsNone(outcome)
        _, outcome = shell.handle(view, None, "2", slots)
        self.assertEqual(outcome, ("play", shell.slot_path(saves.dir, 2), False))
        back, _ = shell.handle(view, "close", "x", slots)
        self.assertEqual(back.screen, "start")

    def test_a_new_game_with_every_slot_used_asks_which_to_replace(self):
        saves = Saves(self, filled=(1, 2, 3))
        slots = saves.slots()
        view, outcome = shell.handle(shell.Shell(), None, "2", slots)
        self.assertEqual((view.screen, view.mode, outcome), ("slots", "new", None))
        self.assertIn("A used slot's game will be replaced.", draw(view, slots))
        _, outcome = shell.handle(view, None, "2", slots)
        self.assertEqual(outcome, ("play", shell.slot_path(saves.dir, 2), True))

    def test_an_unreadable_save(self):
        saves = Saves(self)
        shell.slot_path(saves.dir, 1).write_text("{broken", encoding="utf-8")
        slots = saves.slots()
        self.assertEqual((slots[0].used, slots[0].readable), (True, False))
        self.assertIn("can't be read", draw(shell.Shell("slots"), slots))
        self.assertNotIn("Continue", draw(shell.Shell(), slots))

    def test_every_shell_screen_fits(self):
        saves = Saves(self, filled=(1, 2, 3))
        slots = saves.slots()
        for view in (shell.Shell(), shell.Shell("slots"), shell.Shell("slots", mode="new"), shell.Shell("help")):
            for columns, rows in ((40, 20), (44, 30), (100, 60)):
                with self.subTest(screen=view.screen, mode=view.mode, size=(columns, rows)):
                    lines = draw(view, slots, columns, rows, colour=True).rstrip("\n").split("\n")
                    self.assertEqual({visible_len(line) for line in lines}, {columns})
                    self.assertLessEqual(len(lines), rows)


class TestHelp(unittest.TestCase):
    def test_keys_how_it_works_and_the_games_help(self):
        frame = draw(shell.Shell("help"), Saves(self).slots(), 72, 60)
        for words in ("Keys", "WASD, arrows", "move", "F", "fitting", "L", "messages", "X, Esc", "close",
                      "1-9", "How it works", "Walk into things", "Test pack", "mind the gas"):
            self.assertIn(words, frame)

    def test_rebinding_changes_the_help(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ui_dir = Path(tmp.name) / "mine"
        shutil.copytree(ui_dir_for("default"), ui_dir)
        path = ui_dir / "keys.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["bindings"]["history"] = "j"
        path.write_text(json.dumps(data), encoding="utf-8")
        frame = draw(shell.Shell("help"), Saves(self).slots(), 72, 60, ui=load_ui(ui_dir))
        self.assertTrue(any(line.strip("│ ").startswith("J") and "messages" in line for line in frame.splitlines()))

    def test_it_scrolls(self):
        slots = Saves(self).slots()
        view = shell.Shell("help")
        data = shell.ShellData(shell.entries(slots), slots, "load")
        self.assertGreater(render.shell_scroll_limit(CONTENT, UI, view, data, 40, 20), 0)
        self.assertIn("↑↓ scroll", draw(view, slots, 40, 20))
        moved, _ = shell.handle(view, "move_south", "s", slots)
        self.assertEqual(moved.scroll, 1)
        back, _ = shell.handle(view, "close", "x", slots)
        self.assertEqual(back, shell.Shell())


class TestQuitting(unittest.TestCase):
    def test_q_asks_from_anywhere_and_n_goes_back(self):
        s = encounter.begin(CONTENT, new_game(CONTENT, 1)._replace(encounter_request="enc_drones"))
        picked = app.View(selected=1)
        _, asked, quit_now = app.handle(CONTENT, s, "q", picked, UI)
        self.assertEqual((asked.screen, quit_now), ("quit", False))
        frame = ANSI.sub("", render.render(CONTENT, s, 44, 30, screen="quit"))
        self.assertIn("Quit to the start screen?", frame)
        self.assertIn("Y yes  N no", frame)
        _, back, _ = app.handle(CONTENT, s, "n", asked, UI)
        self.assertEqual(back, picked)                                            # the pick is kept
        _, back, _ = app.handle(CONTENT, s, "\x1b", asked, UI)
        self.assertEqual(back, picked)
        _, _, quit_now = app.handle(CONTENT, s, "y", asked, UI)
        self.assertTrue(quit_now)

    def test_the_program_round_trip(self):
        saves = Saves(self)
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO("1aqy" + "1" + "qy" + "5")), redirect_stdout(out):
            code = app.run(ROOT / "packs" / "test", seed=1, colour=False, saves_dir=saves.dir)
        self.assertEqual(code, 0)
        self.assertTrue(shell.slot_path(saves.dir, 1).exists())
        printed = ANSI.sub("", out.getvalue())
        self.assertIn("Continue", printed)                                        # back on the start screen
        self.assertEqual(printed.count("Saved."), 2)                              # two games played, both saved

    def test_straight_into_a_slot(self):
        saves = Saves(self)
        path = saves.dir / "two.json"
        with mock.patch("sys.stdin", io.StringIO("a")), redirect_stdout(io.StringIO()):
            code = app.run(ROOT / "packs" / "test", path, seed=1, fresh=True, colour=False)
        self.assertEqual(code, 0)
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
