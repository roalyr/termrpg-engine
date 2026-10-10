"""The pack tools: pack files, the shared look, the editor's menu and the overview tool, driven by keys."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import editor
from tools import tools
from tools.lib import screen, term
from tools.lib.packfiles import PackFiles, dumps
from tools.overview import Overview

ROOT = Path(__file__).resolve().parent.parent
LOOK = screen.look(colour=False)
SIZES = ((40, 20), (60, 40), (100, 60))
TEST_PACK = ROOT / "packs" / "test"


class PackFilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.dir = self.tmp / "test"
        shutil.copytree(TEST_PACK, self.dir)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_every_pack_file_round_trips_byte_for_byte(self):
        pack = PackFiles(self.dir)
        for rel, data in pack.data.items():
            self.assertEqual(dumps(data), (self.dir / rel).read_text(encoding="utf-8"), rel)

    def test_finds_entries_and_placements_with_their_files(self):
        pack = PackFiles(self.dir)
        location = next(pack.entries("locations"))
        self.assertEqual(pack.find("locations", location.entry["id"]), location)
        placement = location.entry["placements"][0]
        found, p = pack.placement(placement["id"])
        self.assertEqual((found.entry["id"], p), (location.entry["id"], placement))
        self.assertIsNone(pack.find("locations", "no_such_id"))

    def test_saves_only_changed_files_and_checks_them(self):
        pack = PackFiles(self.dir)
        self.assertEqual(pack.save(), [])
        location = next(pack.entries("locations"))
        location.entry["name"] = "Renamed"
        pack.touch(location.file)
        self.assertEqual(pack.save(), [location.file])
        self.assertEqual(json.loads((self.dir / location.file).read_text())["entries"][0]["name"], "Renamed")
        self.assertTrue(pack.check().ok)
        location.entry["no_such_field"] = 1
        pack.touch(location.file)
        pack.save()
        self.assertFalse(pack.check().ok)


class TermTest(unittest.TestCase):
    def test_key_names(self):
        self.assertEqual([term.key_name(k) for k in ("\x1b[A", "\r", "\x1b", "\x7f", "x")],
                         ["up", "enter", "esc", "backspace", "x"])


def fits(test, text, columns, rows):
    lines = text.rstrip("\n").split("\n")
    test.assertLessEqual(len(lines), rows)
    test.assertTrue(all(len(line) <= columns for line in lines), text)


class LookTest(unittest.TestCase):
    def test_keys_mean_what_they_mean_in_the_game(self):
        self.assertEqual([LOOK.action(k) for k in ("up", "w", "s", "a", "d", "esc", "x", "q", "enter", "r")],
                         ["up", "up", "down", "left", "right", "back", "back", "quit", "enter", "r"])

    def test_draws_bands_in_a_border_and_scrolls_the_flexible_one(self):
        drawn = screen.draw(LOOK, [["Title"], [str(i) for i in range(50)], ["hints"]], 40, 20, flex=1, scroll=5)
        fits(self, drawn.text, 40, 20)
        lines = drawn.text.split("\n")
        self.assertTrue(lines[0].startswith("┌") and "Title" in lines[1])
        self.assertIn("5", lines[3])
        self.assertEqual(drawn.limit, 50 - (20 - 2 - 4))

    def test_too_small_a_terminal_says_so(self):
        self.assertIn("40x20", screen.draw(LOOK, [["x"]], 30, 10).text)


class EditorTest(unittest.TestCase):
    def test_opens_the_only_pack_and_lists_working_tools_then_quit(self):
        ed = editor.Editor(LOOK, [TEST_PACK])
        screen_text = ed.render(40, 20)
        self.assertIn("Test pack", screen_text)
        for tool in tools():
            self.assertIn(tool.name, screen_text)
        self.assertEqual(ed.entries()[-1][0], "Quit")

    def test_a_tool_runs_in_place_and_back_returns_to_the_menu(self):
        ed = editor.Editor(LOOK, [TEST_PACK])
        self.assertTrue(ed.handle("1"))
        self.assertIsNotNone(ed.tool)
        self.assertIn("Checker", ed.render(40, 20))
        self.assertTrue(ed.handle("x"))
        self.assertIsNone(ed.tool)
        self.assertFalse(ed.handle("x"))

    def test_picks_a_pack_first_when_there_are_several(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            for name in ("one", "two"):
                shutil.copytree(TEST_PACK, tmp / name)
            ed = editor.Editor(LOOK, editor.find_packs(tmp))
            self.assertIsNone(ed.pack)
            self.assertFalse(ed.handle("x"))                 # nothing open: back quits
            ed.handle("down")
            ed.handle("enter")
            self.assertEqual(ed.pack.dir.name, "two")
            self.assertIn("Open another pack", ed.render(40, 20))
        finally:
            shutil.rmtree(tmp)

    def test_every_screen_fits(self):
        ed = editor.Editor(LOOK, [TEST_PACK, TEST_PACK])
        for columns, rows in SIZES:
            fits(self, ed.render(columns, rows), columns, rows)


class OverviewTest(unittest.TestCase):
    def test_shows_the_pack_and_the_checker_and_leaves(self):
        view = Overview(PackFiles(TEST_PACK), LOOK)
        text = view.render(60, 40)
        self.assertIn("Test pack", text)
        self.assertIn("Checker: 0 error(s)", text)
        self.assertTrue(view.handle("down"))
        self.assertTrue(view.handle("r"))
        self.assertFalse(view.handle("q"))

    def test_fits_every_size_and_scrolls(self):
        view = Overview(PackFiles(TEST_PACK), LOOK)
        for columns, rows in SIZES:
            fits(self, view.render(columns, rows), columns, rows)
        top = view.render(40, 20)
        for _ in range(50):
            view.handle("down")
        self.assertNotEqual(view.render(40, 20), top)
        self.assertGreater(view.scroll, 0)


if __name__ == "__main__":
    unittest.main()
