"""The pack tools: reading and writing pack files, and the overview tool driven by keys."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.lib import term
from tools.lib.packfiles import PackFiles, dumps
from tools.overview import Overview

ROOT = Path(__file__).resolve().parent.parent
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


class OverviewTest(unittest.TestCase):
    def test_shows_the_pack_and_the_checker_and_quits(self):
        view = Overview(PackFiles(TEST_PACK))
        screen = view.render(60, 40)
        self.assertIn("Test pack", screen)
        self.assertIn("Checker: 0 error(s)", screen)
        self.assertTrue(view.handle("down"))
        self.assertFalse(view.handle("q"))

    def test_fits_a_small_screen(self):
        view = Overview(PackFiles(TEST_PACK))
        lines = view.render(30, 10).rstrip("\n").split("\n")
        self.assertLessEqual(len(lines), 10)
        self.assertTrue(all(len(line) <= 30 for line in lines))


if __name__ == "__main__":
    unittest.main()
