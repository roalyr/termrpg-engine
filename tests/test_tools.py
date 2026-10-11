"""The pack tools: pack files, the shared look, the editor's menu and the overview tool, driven by keys."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import editor
from lib import term
from lib.text import visible_len
from tools import tools
from tools.lib import maps, rooms, screen
from tools.lib.packfiles import PackFiles, dumps
from tools.art import Art
from tools.entries import Entries
from tools.lib import glance, loadout, sources
from tools.loadout import Loadout
from tools.lib import fields, refs
from tools.map import Map
from tools.overview import Overview
from tools.room import Room

ROOT = Path(__file__).resolve().parent.parent
LOOK = screen.look(colour=False)
SIZES = ((48, 24), (60, 40), (100, 60))
TEST_PACK = ROOT / "packs" / "test_scifi"


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


    def test_knows_which_changed_files_were_changed_on_disk_too(self):
        pack = PackFiles(self.dir)
        location = next(pack.entries("locations"))
        location.entry["name"] = "Renamed"
        pack.touch(location.file)
        self.assertEqual(pack.changed_elsewhere(), [])
        path = self.dir / location.file
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assertEqual(pack.changed_elsewhere(), [location.file])
        pack.save()
        self.assertEqual(pack.changed_elsewhere(), [])         # what was saved is the new baseline


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

    def test_colours_for_a_placement_its_object_and_the_room(self):
        room = self.room()
        location = self.pack.find("locations", "loc_workshop").entry
        crate = next(p for p in location["placements"] if p["id"] == "workshop_crate")
        room.cursor = tuple(crate["at"])
        self.keys(room, "c", "enter", *"red", "enter")         # this crate only
        self.assertEqual(crate["colour"], "red")
        self.keys(room, "c", "down", "enter", *"violet", "enter")   # every crate
        self.assertEqual(self.pack.find("objects", crate["object"]).entry["colour"], "violet")
        room.cursor = (0, 0)
        self.keys(room, "c", *"grey", "enter")                 # a wall tile: the room's walls
        self.assertEqual(location["grid"]["wall_colour"], "grey")
        self.keys(room, "c", "up", "enter")                    # the list starts on grey; Default takes it away
        self.assertNotIn("wall_colour", location["grid"])
        room.cursor = (2, 2)
        self.keys(room, "c", *"terminal", "enter", "right", "right", "enter")   # from the 256-colour grid
        self.assertEqual(location["grid"]["floor_colour"], 2)
        self.assert_saved_clean()

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

    def test_a_file_changed_on_disk_is_not_overwritten_without_asking(self):
        art_file = self.tmp / "test" / "art.json"
        self.keys("enter", " ", "tab", " ", "x", "y")          # the list now; the edit is saved
        self.assertFalse(self.pack.dirty)
        self.keys("enter")
        self.art.cursor = (0, 0)                               # a see-through corner
        self.keys(" ")                                         # another edit
        self.assertTrue(self.pack.dirty)
        elsewhere = art_file.read_text(encoding="utf-8").replace('"notes"', '"notes" ', 1)
        art_file.write_text(elsewhere, encoding="utf-8")       # meanwhile someone else saves the file
        self.keys("x", "y")
        self.assertIn("art.json changed on disk", self.art.render(48, 24))
        self.keys("n")                                         # don't save: theirs is kept, ours stays open
        self.assertEqual(art_file.read_text(encoding="utf-8"), elsewhere)
        self.assertTrue(self.pack.dirty)
        self.assertIn("Not saved", self.art.render(48, 24))
        self.keys("x", "y", "o")                               # overwrite after all
        self.assertFalse(self.pack.dirty)
        self.assertNotEqual(art_file.read_text(encoding="utf-8"), elsewhere)

    def test_every_screen_fits(self):
        for setup in ((), ("enter",), ("enter", "enter"), ("enter", "n"), ("enter", "c")):
            self.art = Art(self.pack, LOOK)
            self.keys(*setup)
            for columns, rows in SIZES:
                fits(self, self.art.render(columns, rows), columns, rows)


class EntriesTest(unittest.TestCase):
    """The entries editor on a copy of the test pack: every field kind, the whole entry, ids; saved entries pass the checker."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(TEST_PACK, self.tmp / "test")
        self.pack = PackFiles(self.tmp / "test")
        self.edits = []                                          # what the text editor was given
        self.typed = None                                        # what it gives back

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def editor(self, kind="objects", entry="obj_crate"):
        ed = Entries(self.pack, LOOK, kind, entry)

        def edit_text(text, suffix=".txt"):
            self.edits.append(text)
            return self.typed(text) if callable(self.typed) else self.typed
        ed.edit_text = edit_text
        return ed

    def keys(self, ed, *keys):
        for key in keys:
            self.assertTrue(ed.handle(key), key)

    def field(self, ed, name):
        ed.selected = [s.name for s in ed.specs()].index(name)

    def saved_clean(self):
        self.pack.save()
        self.assertEqual(self.pack.check().errors, ())

    def test_kinds_then_entries_then_fields(self):
        ed = Entries(self.pack, LOOK)
        self.assertIn("Characters", ed.render(48, 24))
        self.keys(ed, *"objects", "enter", *"crate", "enter")
        text = ed.render(48, 24)
        self.assertIn("Objects · Crate", text)
        self.assertIn("glyph", text)
        self.keys(ed, "x")                                       # back to the objects
        self.assertIn("New…", ed.render(48, 24))
        self.keys(ed, "esc")                                     # back to the kinds
        self.assertFalse(ed.handle("esc"))                       # nothing changed: leaves

    def test_lines_flags_and_choices(self):
        ed = self.editor()
        crate = ed.entry
        self.field(ed, "name")
        self.keys(ed, "enter", *["backspace"] * 5, *"Box", "enter")
        self.assertEqual(crate["name"], "Box")
        self.field(ed, "solid")
        self.keys(ed, "enter")                                   # yes -> no: the default, so it's taken out
        self.assertNotIn("solid", crate)
        self.keys(ed, "enter")
        self.assertTrue(crate["solid"])
        self.field(ed, "size")
        self.keys(ed, "enter", *"room", "enter")                 # sizes by their vocabulary names
        self.assertEqual(crate["size"], 4)
        self.field(ed, "storage")
        self.keys(ed, "enter", *["backspace"] * 3, *"x", "enter")
        self.assertIn("A whole number.", ed.render(48, 24))
        self.keys(ed, "backspace", "enter")                      # empty: taken out
        self.assertNotIn("storage", crate)
        self.saved_clean()

    def test_references_and_lists_of_them(self):
        ed = self.editor("characters", "char_juno")
        juno = ed.entry
        self.field(ed, "art")
        self.keys(ed, "enter", *"drone", "enter")
        self.assertEqual(juno["art"], "art_drone")
        self.keys(ed, "enter", *"none", "enter")                 # "(none)" heads the list of an optional ref
        self.assertNotIn("art", juno)
        self.field(ed, "wants")
        before = list(juno.get("wants", []))
        self.keys(ed, "enter", *"add", "enter", *"filter", "enter")   # Add… then a tag
        self.assertEqual(juno["wants"], before + ["tag_filter"])
        self.keys(ed, *"tag_filter", "enter", "esc")             # Enter on it takes it out; Esc is done
        self.assertEqual(juno.get("wants", []), before)
        self.saved_clean()

    def test_long_text_and_json_go_to_the_text_editor(self):
        ed = self.editor()
        self.field(ed, "description")
        self.typed = "A crate.\n"
        self.keys(ed, "enter")
        self.assertEqual(ed.entry["description"], "A crate.")
        self.field(ed, "interactions")
        self.typed = "[ not json"
        self.keys(ed, "enter")
        self.assertIn("isn't valid JSON", ed.render(48, 24))
        self.typed = lambda text: text                            # edit again: given back the broken text
        self.keys(ed, "e")
        self.assertEqual(self.edits[-1], "[ not json")
        self.keys(ed, "n")
        self.typed = None                                         # the editor didn't save
        self.keys(ed, "enter")
        self.assertIn("editor didn't save", ed.render(48, 24))
        kick = [{"id": "kick", "label": "Kick it", "effects": [{"op": "message", "text": "Thud."}]}]
        self.typed = json.dumps(kick)
        self.keys(ed, "enter")
        self.assertEqual(ed.entry["interactions"], kick)
        self.saved_clean()

    def test_the_whole_entry_as_json_keeps_its_id(self):
        ed = self.editor()
        self.typed = lambda text: text.replace('"obj_crate"', '"obj_box"')
        self.keys(ed, "e", *"json", "enter")
        self.assertIn("Change the id with Rename", ed.render(48, 24))
        self.typed = lambda text: text.replace('"Crate"', '"Big crate"')
        self.keys(ed, "e", *"json", "enter")
        self.assertEqual(ed.entry["name"], "Big crate")
        self.saved_clean()

    def test_rename_changes_every_use(self):
        ed = self.editor()
        used = len(refs.uses(self.pack, "object", "obj_crate"))
        self.assertGreater(used, 0)
        self.keys(ed, "e", *"rename", "enter", *["backspace"] * 5, *"box", "enter")
        self.assertEqual(ed.entry["id"], "obj_box")
        self.assertEqual(refs.uses(self.pack, "object", "obj_crate"), [])
        self.assertEqual(len(refs.uses(self.pack, "object", "obj_box")), used)
        self.saved_clean()

    def test_renaming_the_start_location_changes_the_manifest(self):
        ed = self.editor("locations", self.pack.manifest["start"]["location"])
        old = ed.entry["id"]
        self.keys(ed, "e", *"rename", "enter", *["backspace"] * len(old), *"loc_home", "enter")
        self.assertEqual(self.pack.manifest["start"]["location"], "loc_home")
        self.saved_clean()
        self.assertEqual(json.loads((self.tmp / "test" / "pack.json").read_text())["start"]["location"], "loc_home")

    def test_new_duplicate_and_delete(self):
        ed = Entries(self.pack, LOOK, "items")
        self.keys(ed, *"new", "enter", *"gear", "enter", *"probe", "enter")
        self.assertEqual(ed.entry, {"id": "gear_probe", "kind": "gear"})
        self.assertIn("missing required field 'name'", ed.render(48, 24))
        self.keys(ed, "e", *"duplicate", "enter", "enter")
        self.assertEqual(ed.entry["id"], "gear_probe_2")
        self.keys(ed, "e", *"delete", "enter", "y")
        self.assertIsNone(self.pack.find("items", "gear_probe_2"))
        crate = self.editor()
        self.keys(crate, "e", *"delete", "enter")                # still placed in rooms
        self.assertIn("Still used", crate.render(48, 24))
        self.assertIsNotNone(self.pack.find("objects", "obj_crate"))

    def test_leaving_with_changes_asks(self):
        ed = Entries(self.pack, LOOK, "objects")
        self.keys(ed, *"crate", "enter")
        self.field(ed, "solid")
        self.keys(ed, "enter", "x", "esc", "esc")
        self.assertIn("Save your changes?", ed.render(48, 24))
        self.assertFalse(ed.handle("y"))                         # saved, and the tool closes
        self.assertFalse(self.pack.dirty)
        self.assertEqual(self.pack.check().errors, ())

    def test_every_kind_and_screen_fits(self):
        for kind in fields.EDITABLE_KINDS:
            first = next(self.pack.entries(kind), None)
            if first is None:
                continue
            ed = Entries(self.pack, LOOK, kind, first.entry["id"])
            for columns, rows in SIZES:
                fits(self, ed.render(columns, rows), columns, rows)
                for spec in ed.specs():
                    fields.summary(spec, ed.entry.get(spec.name), 30)


LOADOUT_ERRORS = ("equipped gear needs", "cargo stacks", "constant load", "no free", "not gear")


class LoadoutTest(unittest.TestCase):
    """The loadout editor on a copy of the test pack: its numbers and problems agree with the checker's."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(TEST_PACK, self.tmp / "test")
        self.pack = PackFiles(self.tmp / "test")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def keys(self, tool, *keys):
        for key in keys:
            self.assertTrue(tool.handle(key), key)

    def pick(self, tool, text):
        """Moves the selection to the first line starting with 'text'."""
        rows = tool.rows(loadout.sheet(self.pack, tool.char))
        tool.selected = next(i for i, r in enumerate(rows) if r.text.startswith(text))

    def checker_says(self):
        self.pack.save()
        return [e for e in self.pack.check().errors if any(words in e for words in LOADOUT_ERRORS)]

    def test_the_numbers_are_the_engines(self):
        player = self.pack.find("characters", "char_player").entry
        sheet = loadout.sheet(self.pack, player)
        numbers = {b.stat: (b.used, b.provided) for b in sheet.budgets}
        # light suit 6 power, 10 mass, 8 heat, 4 cargo, plus the body's 2 cargo; cutter 1/2, shield 3/3/2
        self.assertEqual(numbers, {"stat_power": (4, 6), "stat_mass": (5, 10), "stat_heat": (2, 8), "stat_cargo": (4, 6)})
        self.assertEqual(sheet.stats, {"stat_health": 30, "stat_armor": 2})
        self.assertEqual(sheet.size, 3)
        self.assertEqual([(s.slot_type, s.item) for s in sheet.slots],
                         [("slot_worn", "gear_light_suit"), ("slot_head", None), ("slot_hand", "gear_cutter"),
                          ("slot_hand", None), ("slot_back", "gear_shield")])
        self.assertEqual(sheet.problems, [])

    def test_problems_agree_with_the_checker(self):
        def items(pack):
            return {f.entry["id"]: f for f in pack.entries("items")}
        breakages = [
            lambda c, i: c.update(equipped=["gear_light_suit", "gear_shield", "gear_shield", "gear_cutter"]),  # one back slot
            lambda c, i: c.update(equipped=["gear_heavy_suit"], inventory=[{"item": "material_scrap", "count": 200}]),
            lambda c, i: i["gear_shield"].entry["uses"].update(stat_power=10, stat_heat=8),   # power, heat
            lambda c, i: c["equipped"].remove("gear_light_suit"),                              # tools, no suit
            lambda c, i: c["equipped"].extend(["gear_eye_implant", "gear_eye_implant"]),       # one head slot
        ]
        for n, breaking in enumerate(breakages):
            with self.subTest(n):
                shutil.rmtree(self.tmp / "test")
                shutil.copytree(TEST_PACK, self.tmp / "test")
                self.pack = PackFiles(self.tmp / "test")
                player = self.pack.find("characters", "char_player")
                breaking(player.entry, items(self.pack))
                self.pack.touch(player.file)
                self.pack.touch(items(self.pack)["gear_shield"].file)
                problems = loadout.sheet(self.pack, player.entry).problems
                self.assertTrue(problems)
                self.assertEqual(len(problems), len(self.checker_says()), problems)
        shutil.rmtree(self.tmp / "test")
        shutil.copytree(TEST_PACK, self.tmp / "test")
        self.pack = PackFiles(self.tmp / "test")
        self.assertEqual(self.checker_says(), [])
        for found in self.pack.entries("characters"):
            self.assertEqual(loadout.sheet(self.pack, found.entry).problems, [], found.entry["id"])

    def test_fill_a_slot_change_the_suit_and_carry(self):
        tool = Loadout(self.pack, LOOK, "char_player")
        char = tool.char
        self.pick(tool, "  Hand  (empty)")
        self.keys(tool, "enter", "enter")                        # the only hand gear: a second cutter
        self.assertEqual(char["equipped"], ["gear_light_suit", "gear_cutter", "gear_shield", "gear_cutter"])
        self.assertIn("PWR  ███████░ 5/6", tool.render(48, 24))
        self.pick(tool, "  Back  Shield")
        self.keys(tool, "r")
        self.assertEqual(char["equipped"], ["gear_light_suit", "gear_cutter", "gear_cutter"])
        self.pick(tool, "Suit    Light suit")
        self.keys(tool, "enter", *"heavy", "enter")
        self.assertEqual(char["equipped"], ["gear_heavy_suit", "gear_cutter", "gear_cutter"])
        self.pick(tool, "Scrap x12")
        self.keys(tool, "enter", "backspace", "backspace", *"200", "enter")
        self.assertEqual(char["inventory"][1], {"item": "material_scrap", "count": 200})
        text = tool.render(48, 24)
        self.assertIn("The inventory needs 22 cargo stacks", text)
        self.pick(tool, "Scrap x200")
        self.keys(tool, "enter", *["backspace"] * 3, "0", "enter")
        self.assertNotIn("material_scrap", [e["item"] for e in char["inventory"]])
        self.pick(tool, "Carry another item")
        self.keys(tool, "enter", *"odd", "enter", "backspace", "3", "enter")
        self.assertEqual(char["inventory"][-1], {"item": "material_odd_metal", "count": 3})
        self.keys(tool, "x", "esc")
        self.assertIn("Save your changes?", tool.render(48, 24))
        self.assertFalse(tool.handle("y"))
        self.assertEqual(self.pack.check().errors, ())

    def test_takes_off_and_puts_back_implants_and_suits(self):
        tool = Loadout(self.pack, LOOK, "char_juno")
        self.pick(tool, "Head  Eye")
        self.keys(tool, "r")
        self.assertNotIn("equipped", tool.char)
        self.pick(tool, "Head  (empty)")
        self.keys(tool, "enter", "enter")
        self.assertEqual(tool.char["equipped"], ["gear_eye_implant"])
        self.pick(tool, "Suit  (empty)")
        self.keys(tool, "enter", "enter")                        # the first suit offered: the light one
        self.assertEqual(tool.char["equipped"], ["gear_eye_implant", "gear_light_suit"])
        self.pick(tool, "Suit    Light suit")              # its hand and back slots now show under it
        self.keys(tool, "r")
        self.assertEqual(tool.char["equipped"], ["gear_eye_implant"])

    def test_opens_the_room_and_comes_back(self):
        tool = Loadout(self.pack, LOOK, "char_juno")
        self.keys(tool, "g")
        self.assertIn("Room · Workshop", tool.render(48, 24))
        self.assertEqual(tool.room.cursor, (3, 3))                # on Juno
        self.keys(tool, "x")
        self.assertIn("Loadout · Juno", tool.render(48, 24))

    def test_picture_shows_when_there_is_room(self):
        tool = Loadout(self.pack, LOOK, "char_juno")
        self.assertNotIn("█", tool.render(48, 24).split("Equipped")[0].replace("░", ""))
        self.assertIn("████", tool.render(48, 40))
        self.keys(tool, "v")
        self.assertNotIn("████", tool.render(48, 40))

    def test_every_character_and_screen_fits(self):
        for found in self.pack.entries("characters"):
            tool = Loadout(self.pack, LOOK, found.entry["id"])
            for columns, rows in SIZES:
                fits(self, tool.render(columns, rows), columns, rows)
        tool = Loadout(self.pack, LOOK)
        self.assertIn("Juno", tool.render(48, 24))
        self.assertFalse(tool.handle("esc"))


class SourcesTest(unittest.TestCase):
    """Where items come from and where entries are used; the glance above an item or object; jumping to a use."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(TEST_PACK, self.tmp / "test")
        self.pack = PackFiles(self.tmp / "test")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def add_item(self, entry):
        self.pack.add("items", dict({"kind": "material", "size": 0}, **entry))

    def said(self, item_id):
        return [(u.name, u.words) for u in sources.sources(self.pack, item_id)]

    def test_every_test_pack_item_can_be_had(self):
        for found in self.pack.entries("items"):
            self.assertTrue(sources.sources(self.pack, found.entry["id"]), found.entry["id"])

    def test_names_the_ways_to_get_scrap(self):
        said = self.said("material_scrap")
        for way in [("Cutter", "dismantling it yields it"), ("Player", "starts with it"),
                    ("loot_crate", "can be drawn from it"), ("loot_drone", "always in it")]:
            self.assertIn(way, said)
        others = [(u.name, u.words) for u in sources.item_uses(self.pack, "material_scrap") if not u.source]
        self.assertIn(("Cutter", "needed to make it"), others)
        self.assertIn(("Reinforced", "its material"), others)

    def test_an_item_nobody_gives_and_dead_ends(self):
        self.add_item({"id": "material_lost", "name": "Lost"})
        self.assertEqual(sources.item_uses(self.pack, "material_lost"), [])
        self.assertIn("Nobody can get it", "".join(glance.lines(self.pack, LOOK, "items", self.pack.find(
            "items", "material_lost").entry, 44)))
        # a table nothing rolls, dismantling something nobody has, a design nobody teaches: not sources
        self.pack.add("loot_tables", {"id": "loot_lost", "entries": [{"item": "material_lost"}]})
        self.add_item({"id": "misc_husk", "kind": "misc", "name": "Husk",
                       "dismantle": {"yields": [{"item": "material_lost"}]}})
        self.add_item({"id": "material_made", "name": "Made", "make": {"inputs": [{"item": "material_scrap"}]}})
        self.assertEqual(sources.sources(self.pack, "material_lost"), [])
        problems = {u.name: u.problem for u in sources.item_uses(self.pack, "material_lost")}
        self.assertEqual(problems, {"loot_lost": "but nothing rolls this table", "Husk": "but nobody can get that"})
        self.assertEqual(sources.sources(self.pack, "material_made"), [])
        self.pack.find("characters", "char_player").entry["designs"] = ["material_made"]
        self.assertEqual(self.said("material_made"), [("Made", "made once its design is known")])
        self.pack.find("characters", "char_drone").entry["loot"] = "loot_lost"
        self.assertEqual(self.said("material_lost"), [("loot_lost", "can be drawn from it")])

    def test_glances(self):
        def glance_of(kind, ident):
            return "\n".join(glance.lines(self.pack, LOOK, kind, self.pack.find(kind, ident).entry, 44))
        self.assertIn("Gear · Back slot · PWR 3 MAS 3 HT 2 · ARM +2", glance_of("items", "gear_shield"))
        self.assertIn("Gear · Suit slot · Hand x2, Back", glance_of("items", "gear_light_suit"))
        self.assertIn("◆ Door   ◆ closed  ◇ open", glance_of("objects", "obj_door"))
        self.assertIn("Workshop: equip, dismantle", glance_of("objects", "obj_bench"))
        self.assertIn("Stores 6 stacks · Placed 1x: Storage", glance_of("objects", "obj_bay"))
        self.pack.add("objects", {"id": "obj_spare", "name": "Spare", "glyph": "s"})
        self.assertIn("Not placed anywhere", glance_of("objects", "obj_spare"))
        self.assertEqual(glance.lines(self.pack, LOOK, "skills", next(self.pack.entries("skills")).entry, 44), [])

    def test_entries_lists_uses_and_goes_there_and_back(self):
        ed = Entries(self.pack, LOOK, "items", "material_scrap")
        self.assertIn("From: Cutter, Player", ed.render(48, 24))
        self.assertTrue(ed.handle("u"))
        text = ed.render(48, 24)
        self.assertIn("+ Player  starts with it", text)
        self.assertIn("Burn  uses it up", text)
        for key in ("enter",):                                      # the first: dismantling the Cutter
            self.assertTrue(ed.handle(key))
        self.assertEqual(ed.heading(), "Items · Cutter")
        self.assertTrue(ed.handle("x"))
        self.assertEqual(ed.heading(), "Items · Scrap")
        self.assertTrue(ed.handle("x"))
        self.assertIsNone(ed.found)                                 # then the item list, as before
        ed = Entries(self.pack, LOOK, "objects", "obj_crate")
        self.assertTrue(ed.handle("u"))
        self.assertIn("Workshop: Crate  placed there", ed.render(48, 24))
        self.pack.add("objects", {"id": "obj_spare", "name": "Spare", "glyph": "s"})
        ed = Entries(self.pack, LOOK, "objects", "obj_spare")
        self.assertTrue(ed.handle("u"))
        self.assertIn("Nothing uses obj_spare", ed.render(48, 24))


class VocabularyTest(unittest.TestCase):
    """The vocabulary in the entries editor: sections as kinds, ids and numbers that every use follows, order."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(TEST_PACK, self.tmp / "test")
        self.pack = PackFiles(self.tmp / "test")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def keys(self, ed, *keys):
        for key in keys:
            self.assertTrue(ed.handle(key), key)

    def saved_clean(self):
        self.pack.save()
        self.assertEqual(self.pack.check().errors, ())

    def vocab(self, section):
        return [e for rel in self.pack.kinds["vocab"] for e in self.pack.data[rel][section]]

    def test_kinds_then_sections_then_entries_and_back(self):
        ed = Entries(self.pack, LOOK)
        self.keys(ed, *"vocab", "enter")
        text = ed.render(48, 24)
        self.assertIn("Relation levels  3", text)
        self.keys(ed, *"stats", "enter")
        self.assertIn("Initiative  stat_initiative", ed.render(48, 24))
        self.keys(ed, *"armor", "enter")
        self.assertEqual(ed.heading(), "Stats · Armor")
        self.assertIn("short       ARM", ed.render(48, 24))
        self.keys(ed, "x")                                       # back to the stats
        self.assertIn("New…", ed.render(48, 24))
        self.keys(ed, "esc")                                     # the sections
        self.assertIn("Vocabulary", ed.render(48, 24))
        self.keys(ed, "esc")                                     # the kinds
        self.assertIn("Vocabulary…", ed.render(48, 24))
        self.assertFalse(ed.handle("esc"))

    def test_renaming_a_stat_changes_every_use(self):
        used = len(refs.uses(self.pack, "stat", "stat_armor"))
        ed = Entries(self.pack, LOOK, "vocab.stats", "stat_armor")
        self.keys(ed, "enter", *["backspace"] * 5, *"defence", "enter")
        self.assertEqual(ed.ident, "stat_defence")
        self.assertIn(f"{used} use(s) changed", ed.render(48, 24))
        self.assertEqual(refs.uses(self.pack, "stat", "stat_armor"), [])
        self.assertEqual(len(refs.uses(self.pack, "stat", "stat_defence")), used)
        self.saved_clean()

    def test_a_size_is_a_number_every_use_follows(self):
        ed = Entries(self.pack, LOOK, "vocab.sizes", 4)
        self.assertEqual(ed.specs()[0].name, "size")
        self.assertIn("every use changes with it", ed.render(48, 24))
        uses = len(refs.uses(self.pack, "size", 4))
        self.assertGreater(uses, 0)
        self.keys(ed, "enter", "backspace", "3", "enter")         # taken
        self.assertIn("3 is taken.", ed.render(48, 24))
        self.keys(ed, "backspace", "9", "enter")
        self.assertEqual(ed.ident, 9)
        self.assertEqual(len(refs.uses(self.pack, "size", 9)), uses)
        self.assertEqual(refs.uses(self.pack, "size", 4), [])
        self.saved_clean()

    def test_new_duplicate_delete_and_order(self):
        ed = Entries(self.pack, LOOK, "vocab.tags")
        self.keys(ed, *"new", "enter")
        self.assertIn("tag_", ed.render(48, 24))
        self.keys(ed, *"spare", "enter")
        self.assertEqual(ed.entry, {"id": "tag_spare"})
        self.assertIn("missing required field 'name'", ed.render(48, 24))
        self.keys(ed, "down", "enter", *"a spare", "enter")
        self.keys(ed, "e", *"delete", "enter", "y")
        self.assertNotIn("tag_spare", [t["id"] for t in self.vocab("tags")])
        ed = Entries(self.pack, LOOK, "vocab.tags", "tag_tool")
        self.keys(ed, "e", *"delete", "enter")
        self.assertIn("Still used", ed.render(48, 24))
        ed = Entries(self.pack, LOOK, "vocab.ranks", 1)
        self.keys(ed, "e", *"duplicate", "enter", "enter")        # the next number: 2
        self.assertEqual(ed.ident, 2)
        self.keys(ed, "e", *"earlier", "enter")
        self.assertEqual([r["rank"] for r in self.vocab("ranks")], [0, 2, 1])
        self.keys(ed, "e", *"earlier", "enter", "e", *"earlier", "enter")
        self.assertIn("already first", ed.render(48, 24))
        phases = [p["id"] for p in self.vocab("phases")]
        ed = Entries(self.pack, LOOK, "vocab.phases", phases[0])
        self.keys(ed, "e", *"later", "enter")
        self.assertEqual([p["id"] for p in self.vocab("phases")], phases[::-1])
        self.saved_clean()

    def test_uses_name_vocabulary_entries_and_open_them(self):
        ed = Entries(self.pack, LOOK, "vocab.stats", "stat_armor")
        self.keys(ed, "u")
        text = ed.render(48, 24)
        self.assertIn("Impact  resisted by", text)
        self.assertIn("Shield  in its stats", text)
        self.keys(ed, "enter")                                   # Impact: a damage type
        self.assertEqual((ed.kind, ed.heading()), ("vocab.damage_types", "Damage types · Impact"))
        self.keys(ed, "x")
        self.assertEqual(ed.heading(), "Stats · Armor")

    def test_every_section_and_screen_fits(self):
        for kind in fields.vocab_kinds():
            first = next(self.pack.entries(kind), None)
            if first is None:
                continue
            ed = Entries(self.pack, LOOK, kind, first.entry.get(fields.key_field(kind)))
            self.assertIsNotNone(ed.found, kind)
            for columns, rows in SIZES:
                fits(self, ed.render(columns, rows), columns, rows)
