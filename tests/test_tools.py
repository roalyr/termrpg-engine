"""The pack tools: pack files, the shared look, the editor's menu and the overview tool, driven by keys."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import editor
from tui.text import visible_len
from tools import tools
from tools.lib import maps, rooms, screen, term
from tools.lib.packfiles import PackFiles, dumps
from tools.art import Art
from tools.map import Map
from tools.overview import Overview
from tools.room import Room

ROOT = Path(__file__).resolve().parent.parent
LOOK = screen.look(colour=False)
SIZES = ((48, 24), (60, 40), (100, 60))
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
    test.assertTrue(all(visible_len(line) <= columns for line in lines), text)


class LookTest(unittest.TestCase):
    def test_keys_mean_what_they_mean_in_the_game(self):
        self.assertEqual([LOOK.action(k) for k in ("up", "w", "s", "a", "d", "esc", "x", "q", "enter", "r")],
                         ["up", "up", "down", "left", "right", "back", "back", "quit", "enter", "r"])

    def test_draws_bands_in_a_border_and_scrolls_the_flexible_one(self):
        drawn = screen.draw(LOOK, [["Title"], [str(i) for i in range(50)], ["hints"]], 48, 24, flex=1, scroll=5)
        fits(self, drawn.text, 48, 24)
        lines = drawn.text.split("\n")
        self.assertTrue(lines[0].startswith("┌") and "Title" in lines[1])
        self.assertIn("5", lines[3])
        self.assertEqual(drawn.limit, 50 - (24 - 2 - 4))

    def test_too_small_a_terminal_says_so(self):
        self.assertIn("48x24", screen.draw(LOOK, [["x"]], 30, 10).text)


class EditorTest(unittest.TestCase):
    def test_opens_the_only_pack_and_lists_working_tools_then_quit(self):
        ed = editor.Editor(LOOK, [TEST_PACK])
        screen_text = ed.render(48, 24)
        self.assertIn("Test pack", screen_text)
        for tool in tools():
            self.assertIn(tool.name, screen_text)
        self.assertEqual(ed.entries()[-1][0], "Quit")

    def test_a_tool_runs_in_place_and_back_returns_to_the_menu(self):
        ed = editor.Editor(LOOK, [TEST_PACK])
        self.assertTrue(ed.handle(str(tools().index(Overview) + 1)))
        self.assertIsInstance(ed.tool, Overview)
        self.assertIn("Checker", ed.render(48, 24))
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
            self.assertIn("Open another pack", ed.render(48, 24))
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
        top = view.render(48, 24)
        for _ in range(50):
            view.handle("down")
        self.assertNotEqual(view.render(48, 24), top)
        self.assertGreater(view.scroll, 0)


if __name__ == "__main__":
    unittest.main()


class RoomTest(unittest.TestCase):
    """The room editor on a copy of the test pack: every change it makes passes the checker."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(TEST_PACK, self.tmp / "test")
        self.pack = PackFiles(self.tmp / "test")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def room(self, location_id="loc_workshop"):
        return Room(self.pack, LOOK, location_id)

    def keys(self, room, *keys):
        for key in keys:
            self.assertTrue(room.handle(key))

    def assert_saved_clean(self):
        self.pack.save()
        self.assertEqual(self.pack.check().errors, ())

    def test_starts_with_a_location_list_and_esc_leaves(self):
        room = Room(self.pack, LOOK)
        self.assertIn("Workshop", room.render(48, 24))
        self.assertTrue(room.handle("enter"))
        self.assertIn("Room · Workshop", room.render(48, 24))
        self.assertTrue(room.handle("x"))                     # back to the list, nothing changed
        self.assertFalse(room.handle("esc"))

    def test_a_door_to_another_room_leads_both_ways(self):
        room = self.room()
        room.cursor = (2, 5)                                  # the east wall
        self.keys(room, "l", "enter", "enter")                # the suggested object, the first location
        self.assertIn("Pick a tile in Storage", room.render(48, 24))
        self.keys(room, "enter")
        door = rooms.placement_at(room.location, (2, 5))
        other_found, other = rooms.partner(self.pack, door)
        self.assertEqual(other_found.entry["id"], "loc_storage")
        self.assertEqual(rooms.partner(self.pack, other)[1], door)
        self.keys(room, "g")                                  # go through it
        self.assertEqual(room.location["id"], "loc_storage")
        self.assert_saved_clean()

    def test_an_open_edge_joins_sides_tile_by_tile_and_goes_as_one(self):
        storage = self.pack.find("locations", "loc_storage")
        self.assertIsNotNone(rooms.edge_problem(storage.entry, "west", self.pack.find("locations", "loc_workshop").entry))
        self.assertIsNone(rooms.resize(self.pack, storage, 6, 6))
        room = self.room()
        room.cursor = (2, 5)
        self.keys(room, "o", "enter", "enter")
        edge = rooms.edge_group(room.location, rooms.placement_at(room.location, (2, 5)))
        self.assertEqual(len(edge), 4)
        self.assertTrue(all(rooms.partner(self.pack, p) for p in edge))
        self.assert_saved_clean()
        self.keys(room, "r", "y")
        self.assertEqual(rooms.side_of(room.location, (2, 5)), "east")
        self.assertFalse([p for p in room.location["placements"] if rooms.exit_target(p)[0] == "loc_storage"
                          and rooms.side_of(room.location, tuple(p["at"])) == "east"])
        self.assertFalse([p for p in storage.entry["placements"] if p["id"].startswith("storage_west")])
        self.assert_saved_clean()

    def test_something_still_used_elsewhere_is_not_removed(self):
        room = self.room()
        room.cursor = (1, 4)                                  # the crate: where the game starts
        self.keys(room, "r")
        self.assertIsNone(room.form)
        self.assertIn("pack.json", room.message[0])
        self.assertIsNotNone(rooms.placement_at(room.location, (1, 4)))

    def test_place_move_entry_and_tiles(self):
        room = self.room()
        room.cursor = (2, 2)
        self.keys(room, "p")
        room.form.filter = "crate"
        self.keys(room, "enter")
        placed = rooms.placement_at(room.location, (2, 2))
        self.assertEqual(placed["id"], "workshop_crate_2")
        self.keys(room, "m", "down", "enter", "e")
        self.assertEqual(placed["at"], [3, 2])
        self.assertEqual(room.location["entry"], "workshop_crate_2")
        room.cursor = (2, 3)
        self.keys(room, "t")
        self.assertEqual(rooms.tile(room.location, (2, 3)), "#")
        self.keys(room, "t")
        self.assertNotIn("rows", room.location["grid"])       # back to the plain shape
        self.assert_saved_clean()

    def test_resize_refuses_while_something_would_fall_outside(self):
        found = self.pack.find("locations", "loc_workshop")
        self.assertIn("Move or remove", rooms.resize(self.pack, found, 4, 4))
        self.assertEqual(rooms.size(found.entry), (6, 6))

    def test_leaving_with_changes_asks_and_discarding_reloads(self):
        room = self.room()
        room.cursor = (2, 2)
        self.keys(room, "t", "x")
        self.assertIn("Save your changes?", room.render(48, 24))
        self.keys(room, "n")
        self.assertFalse(self.pack.dirty)
        self.assertEqual(rooms.tile(self.pack.find("locations", "loc_workshop").entry, (2, 2)), ".")

    def test_every_screen_fits(self):
        room = self.room()
        for setup in ((), ("enter",), ("z",), ("x",)):
            room = self.room()
            room.cursor = (1, 4)
            self.keys(room, "r", *setup)
            for columns, rows in SIZES:
                fits(self, room.render(columns, rows), columns, rows)


class MapTest(unittest.TestCase):
    """The map editor on a copy of the test pack: regions, the Validity colours, new locations and links."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(TEST_PACK, self.tmp / "test")
        self.pack = PackFiles(self.tmp / "test")
        self.map = Map(self.pack, LOOK)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def keys(self, *keys):
        for key in keys:
            self.assertTrue(self.map.handle(key), key)

    def validity(self, location_id):
        facts = maps.facts(self.pack, self.pack.check().errors)
        return maps.validity(self.pack, facts, self.pack.find("locations", location_id).entry)

    def new_location(self, name):
        self.keys("n", *name, "enter", "enter")
        return self.pack.find("locations", "loc_" + name.lower().replace(" ", "_"))

    def test_opens_on_the_start_and_switches_regions_from_a_list(self):
        text = self.map.render(48, 24)
        self.assertIn("Map · Lower deck", text)
        self.assertIn("Workshop · 6×6", text)
        self.keys("x")
        listing = self.map.render(48, 24)
        self.assertIn("Map · regions", listing)
        self.assertIn("Station", listing)
        self.assertIn("  Lower deck", listing)                # nested under its parent
        self.keys("up", "enter")                              # Station: its own map, no rooms placed
        self.assertIn("Map · Station", self.map.render(48, 24))
        self.assertNotIn("Workshop", self.map.render(48, 24))
        self.keys("x")
        self.assertFalse(self.map.handle("esc"))              # Esc on the list leaves

    def test_validity_sorts_start_hazard_cut_off_and_problems(self):
        self.assertEqual(self.validity("loc_workshop"), "start")
        self.assertEqual(self.validity("loc_storage"), "hazard")
        self.keys("down")
        found = self.new_location("East field")
        self.assertEqual(self.validity(found.entry["id"]), "cut_off")
        storage = self.pack.find("locations", "loc_storage")
        storage.entry["placements"][0]["exit"]["entry"] = "workshop_crate"      # leads somewhere that doesn't lead back
        self.assertEqual(self.validity("loc_storage"), "problem")

    def test_a_new_location_linked_to_its_neighbour_is_reached_and_saves_clean(self):
        self.keys("down")
        found = self.new_location("East field")
        self.assertEqual(found.entry["map"], {"x": 0, "y": 1})
        self.assertEqual(found.entry["region"], "reg_lower_deck")
        self.keys("up", "l", "enter", "enter")                # the south neighbour, as a door
        self.assertEqual(self.validity(found.entry["id"]), "plain")
        self.assertIn("│", self.map.render(48, 24))           # the link is drawn
        self.pack.save()
        self.assertEqual(self.pack.check().errors, ())

    def test_neighbours_of_the_same_size_can_open_an_edge(self):
        self.keys("right", "right")
        first = self.new_location("Plain")
        self.keys("down")
        second = self.new_location("Ridge")
        self.keys("l", "enter", "down", "enter", "enter")    # north neighbour, open edge, the suggested object
        edge = [p for p in second.entry["placements"] if rooms.side_of(second.entry, tuple(p["at"])) == "north"]
        self.assertEqual(len(edge), rooms.size(second.entry)[0] - 2)
        self.assertTrue(all(rooms.partner(self.pack, p)[0].entry is first.entry for p in edge))
        self.pack.save()
        self.assertEqual(self.pack.check().errors, ())

    def test_move_and_edit_the_room_in_place(self):
        self.keys("m", "down", "enter")
        self.assertEqual(self.pack.find("locations", "loc_workshop").entry["map"], {"x": 0, "y": 1})
        self.keys("e")
        self.assertIn("Room · Workshop", self.map.render(48, 24))
        self.keys("x")                                        # back to the map, no question
        self.assertIn("Map · Lower deck", self.map.render(48, 24))
        self.keys("x", "esc")                                 # the region list, then leaving asks
        self.assertIn("Save your changes?", self.map.render(48, 24))

    def test_every_screen_fits(self):
        for setup in ((), ("enter",), ("x",), ("l",), ("down", "n")):
            self.map = Map(self.pack, LOOK)
            self.keys(*setup)
            for columns, rows in SIZES:
                fits(self, self.map.render(columns, rows), columns, rows)


class MapRegionsTest(unittest.TestCase):
    """Regions as separate maps: made from the list, filled, joined by exits and followed."""

    def test_a_new_region_with_a_location_linked_to_another_region(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copytree(TEST_PACK, tmp / "test")
            pack = PackFiles(tmp / "test")
            view = Map(pack, LOOK)
            view.handle("x")                                      # the region list; New region is last
            view.form.filter = "new"
            for key in ("enter", *"Tunnels", "enter", "enter", "n", *"Tunnel one", "enter", "enter"):
                self.assertTrue(view.handle(key), key)
            region = pack.find("regions", "reg_tunnels")
            self.assertEqual(region.entry, {"id": "reg_tunnels", "name": "Tunnels"})
            tunnel = pack.find("locations", "loc_tunnel_one")
            self.assertEqual(tunnel.entry["region"], "reg_tunnels")
            view.handle("e")                                      # a door to the workshop, from the room editor
            view.room.cursor = (0, 3)
            for key in ("l", "enter"):
                view.handle(key)
            view.room.form.filter = "workshop"
            for key in ("enter",):
                view.handle(key)
            view.room.cursor = (5, 3)
            view.handle("enter")
            view.handle("x")
            self.assertIn("Workshop in Lower deck", view.render(60, 30))
            view.handle("g")                                      # follow the exit: the workshop's map
            self.assertIn("Map · Lower deck", view.render(48, 24))
            self.assertEqual(view.at_cursor()[1]["id"], "loc_workshop")
            view.handle("x")                                      # and back along it
            self.assertIn("Map · Tunnels", view.render(48, 24))
            pack.save()
            self.assertEqual(pack.check().errors, ())
        finally:
            shutil.rmtree(tmp)


class ArtTest(unittest.TestCase):
    """The art editor on a copy of the test pack: painting, colours, new pictures; saved pictures pass the checker."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(TEST_PACK, self.tmp / "test")
        self.pack = PackFiles(self.tmp / "test")
        self.art = Art(self.pack, LOOK)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def keys(self, *keys):
        for key in keys:
            self.assertTrue(self.art.handle(key), key)

    def saved_clean(self):
        self.pack.save()
        self.assertEqual(self.pack.check().errors, ())

    def test_lists_pictures_with_who_uses_them_and_esc_leaves(self):
        text = self.art.render(48, 24)
        self.assertIn("art_juno", text)
        self.assertIn("24×24 · Juno", text)
        self.assertIn("New picture…", text)
        self.assertFalse(self.art.handle("esc"))

    def test_paint_with_mirror_then_undo(self):
        self.keys("enter")                                    # art_player
        before = list(self.art.picture["rows"])
        self.art.cursor = (0, 0)
        self.keys("m", " ")
        self.assertEqual(self.art.picture["rows"][0][0], self.art.current)
        self.assertEqual(self.art.picture["rows"][0][15], self.art.current)
        self.keys("u")
        self.assertEqual(self.art.picture["rows"], before)

    def test_tab_steps_through_the_palette_and_see_through(self):
        self.keys("enter")
        letters = list(self.art.picture["palette"]) + ["."]
        seen = []
        for _ in letters:
            seen.append(self.art.current)
            self.keys("tab")
        self.assertEqual(seen, letters)
        self.art.cursor = (8, 8)
        self.keys("k")
        self.assertEqual(self.art.current, self.art.letter_at(8, 8))

    def test_colours_named_and_from_the_grid(self):
        self.keys("enter", "n", "enter")                      # a new colour: grey
        letter = self.art.current
        self.assertEqual(self.art.picture["palette"][letter], "grey")
        self.keys("c")
        self.art.form.filter = "terminal"
        self.keys("enter", "right", "right", "down", "enter")
        self.assertEqual(self.art.picture["palette"][letter], 34)
        self.saved_clean()

    def test_removing_a_colour_clears_its_pixels(self):
        self.keys("enter")
        letter = self.art.current
        self.art.form = None
        self.art.remove_colour()
        self.assertNotIn(letter, self.art.picture["palette"])
        self.assertFalse(any(letter in row for row in self.art.picture["rows"]))
        self.saved_clean()

    def test_a_new_picture_used_by_nobody_can_be_resized_and_deleted(self):
        self.art.form.filter = "new"
        self.keys("enter", "backspace", "backspace", "backspace", "backspace", *"art_rock", "enter")
        self.assertEqual(self.art.picture["id"], "art_rock")
        self.assertEqual(len(self.art.picture["rows"]), 24)
        self.keys("z", *("backspace",) * 5, *"20x8", "enter")
        self.assertEqual((len(self.art.picture["rows"][0]), len(self.art.picture["rows"])), (20, 8))
        self.saved_clean()
        self.keys("enter")
        self.art.form.filter = "delete"
        self.keys("enter", "y")
        self.assertIsNone(self.pack.find("art", "art_rock"))
        self.saved_clean()

    def test_leaving_with_changes_asks(self):
        self.keys("enter", " ", "tab", " ", "x")
        self.assertIn("Save your changes?", self.art.render(48, 24))
        self.keys("n")
        self.assertFalse(self.pack.dirty)

    def test_every_screen_fits(self):
        for setup in ((), ("enter",), ("enter", "enter"), ("enter", "n"), ("enter", "c")):
            self.art = Art(self.pack, LOOK)
            self.keys(*setup)
            for columns, rows in SIZES:
                fits(self, self.art.render(columns, rows), columns, rows)
