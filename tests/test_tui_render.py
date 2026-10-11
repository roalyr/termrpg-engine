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

from core.pack import validate_pack
from engine import atlas, build, context, encounter, events, journal, save, world
from engine.content import load_pack
from engine.effects import run
from engine.frozen import freeze
from engine.state import Ctx, Entry, Message, new_game
from tui import app, render, widgets
from lib.text import Style, visible_len
from lib.ui import UIPackError, default_ui, load_ui, ui_dir_for
from tui.widgets import Frame, item_details, option_text

ROOT = Path(__file__).resolve().parent.parent
CONTENT = load_pack(ROOT / "packs" / "test_scifi")
UI = default_ui()
ANSI = re.compile(r"\x1b\[[0-9;]*m")
SIZES = ((48, 24), (52, 30), (60, 40), (100, 60))


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


def requested(event_id):
    """A new game with an event fired: its card (and question) waiting."""
    return events.settle(CONTENT, new_game(CONTENT, 1)._replace(event_requests=(event_id,)))


def with_history():
    s, view = new_game(CONTENT, 1), app.View()
    for key in "wh" + "." * 40 + "wh":
        s, view, _ = app.handle(CONTENT, s, key, view, UI)
        if s.pending is not None:
            s, view, _ = app.handle(CONTENT, s, "1", view, UI)
    return s


def carrying_a_cutter():
    s = new_game(CONTENT, 1)
    return run(CONTENT, s, Ctx(self_id=s.player), [freeze({"op": "give_item", "item": "module_cutter", "count": 1, "subject": "self"})])


def bench_state():
    return walk(new_game(CONTENT, 1), "ss")               # the workbench in focus, below the start


def travelled():
    """A new game that has also been to Storage and the Crater rim (the Surface region)."""
    s = new_game(CONTENT, 1)
    me = s.characters[s.player]
    return s._replace(characters={**s.characters, s.player: me._replace(visited=me.visited + ("loc_storage", "loc_crater_rim"))})


def screens():
    """Every screen and panel, as (name, state, render options)."""
    return [
        ("walk", new_game(CONTENT, 1), {}),
        ("menu", menu_state(), {}),
        ("choice", choice_state(), {}),
        ("board", new_game(CONTENT, 1), {"panel": "pack"}),
        ("board picked", new_game(CONTENT, 1), {"panel": "pack", "selected": 3}),
        ("sheet", new_game(CONTENT, 1), {"screen": "character"}),
        ("inspect", bench_state(), {"panel": "inspect"}),
        ("fitting", bench_state(), {"screen": "fitting", "selected": 1}),
        ("fitting modify", bench_state(), {"screen": "fitting", "selected": 1, "panel": "modify"}),
        ("fitting details", bench_state(), {"screen": "fitting", "selected": 1, "panel": "item"}),
        ("fitting away", new_game(CONTENT, 1), {"screen": "fitting"}),
        ("talk", walk(new_game(CONTENT, 1), "as"), {"screen": "talk"}),
        ("card question", requested("event_grudge"), {}),
        ("card text", requested("event_rescue"), {}),
        ("history", with_history(), {"panel": "history"}),
        ("inspect scrolled", bench_state(), {"panel": "inspect", "scroll": 99}),
        ("encounter", encounter_state(), {}),
        ("picked", encounter_state(), {"selected": 1}),
        ("target", encounter_state(), {"selected": 0, "panel": "target"}),
        ("debrief", debrief_state(), {}),
        ("map", new_game(CONTENT, 1), {"screen": "map"}),
        ("map surface", travelled(), {"screen": "map", "page": 1, "cursor": (1, 0)}),
    ]


def plain(state, columns=52, rows=60, ui=UI, **options):
    return ANSI.sub("", render.render(CONTENT, state, columns, rows, ui=ui, **options))


def ui_with(case, **size):
    """The default UI pack with some size tokens changed, e.g. a smaller minimum screen."""
    tmp = tempfile.TemporaryDirectory()
    case.addCleanup(tmp.cleanup)
    ui_dir = Path(tmp.name) / "mine"
    shutil.copytree(ui_dir_for("default"), ui_dir)
    path = ui_dir / "tokens.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("size", {}).update(size)
    path.write_text(json.dumps(data), encoding="utf-8")
    return load_ui(ui_dir)


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
                self.assertNotIn("\x1b", render.render(CONTENT, state, 52, 60, colour=False, ui=UI, **options)
                                 .replace("\x1b[7m", "").replace("\x1b[0m", ""))

    def test_what_each_screen_shows(self):
        expected = {
            "walk": ["Workshop", "Lower deck", "Day 1", "WASD move", "P pack"],
            "menu": ["Door", "G Go to Storage - The door is closed.", "I Inspect", "X close"],
            "choice": ["The screen wakes.", "1 Check the logs", "1-2 choose"],
            "board": ["Carried:", "1 Medkit x3", "CRG 4/6", "1-4 pick", "P close"],
            "sheet": ["Salvage 1", "C close"],
            "encounter": ["Drones · round 1", "┌1───────┐", "Strike", "⚠ STRIKE", "1-3 pick", "Q quit"],
            "picked": ["┏2━━━━━━━┓", "Guard", "ARM +4 on yourself for 1 round.", "2 again: use", "X back"],
            "target": ["1-2 target", "X back"],
            "debrief": ["Won.", "Round", "Any key: continue"],
            "map": ["Map · Lower deck", "@───?", "You are here.", "Leads to: Storage", "M close"],
            "map surface": ["Map · Surface", "2 of 2", "Dust flat", "You haven't been here yet.", "] next region"],
        }
        for name, state, options in screens():
            for words in expected.get(name, []):
                with self.subTest(screen=name, words=words):
                    self.assertIn(words, plain(state, **options))

    def test_too_small(self):
        self.assertEqual(plain(new_game(CONTENT, 1), 47, 60).strip(), UI.word("terminal_too_small", columns=48, rows=24))
        self.assertIn("at least 48x24", plain(new_game(CONTENT, 1), 60, 23))


class TestFitting(unittest.TestCase):
    def test_low_priority_zones_drop_first(self):
        s = menu_state()
        self.assertIn("Locker", plain(s, 52, 60))            # the legend
        self.assertNotIn("Locker", plain(s, 52, 24))
        self.assertIn("I Inspect", plain(s, 52, 24))          # the menu stays

    def test_scroll_zones_keep_their_last_lines(self):
        s = new_game(CONTENT, 1)
        me = s.characters[s.player]
        s = s._replace(characters=freeze({**s.characters, s.player: me._replace(inventory=me.inventory * 2)}))
        tall, short = plain(s, 48, 60, panel="pack", selected=4), plain(s, 48, 24, panel="pack", selected=4)
        self.assertIn("Carried:", tall)
        self.assertNotIn("Carried:", short)                   # the top scrolled away
        self.assertIn("U Use", short)                         # the picked item's options stay
        self.assertIn("1-8 pick", short)                      # and the key hints

    def test_encounter_title_drops_on_short_terminals(self):
        s = encounter_state()
        self.assertIn("Drones · round 1", plain(s, 48, 30))
        self.assertNotIn("Drones · round 1", plain(s, 48, 24))
        self.assertIn("Strike", plain(s, 48, 24))


    def test_hints_wrap_between_entries(self):
        lines = plain(new_game(CONTENT, 1), 52, 60).splitlines()[-4:]
        self.assertGreater(len([line for line in lines if line.startswith("│ ")]), 1)   # the hints wrap
        for hint in ("WASD move", ". wait", "P pack", "F fitting", "C char", "Q quit"):
            self.assertTrue(any(hint in line for line in lines), hint)               # each one whole

    def test_kept_zones_stay_when_empty(self):
        lines = plain(new_game(CONTENT, 1), 52, 60).splitlines()
        self.assertFalse(any(a.startswith("├") and b.startswith("├") for a, b in zip(lines, lines[1:])))


    def test_short_encounters_switch_to_compact_widgets(self):
        s = new_game(CONTENT, 1)
        s = run(CONTENT, s, Ctx(self_id=s.player), [freeze({"op": "grant_xp", "skill": "skill_salvage", "amount": 30,
                                                             "subject": "self"})])          # unlocks a fourth tile
        s = encounter.begin(CONTENT, s._replace(encounter_request="enc_drones"))
        self.assertEqual(len(encounter.tiles(CONTENT, s)), 4)
        small = ui_with(self, min_rows=20)                       # a UI pack that allows 20 rows
        roomy, short = plain(s, 48, 40, ui=small), plain(s, 48, 20, ui=small)
        self.assertIn("┌1───────┐", roomy)                       # boxed tiles when there's room
        self.assertLessEqual(len(short.splitlines()), 20)
        self.assertIn("1 Strike ▲1  2 Guard ▲1", short)           # a list when there isn't
        self.assertIn("4 Retreat", short)
        self.assertIn("2 Drone", short)                          # every fighter still shown


class TestSubWindows(unittest.TestCase):
    """The shared panel: Inspect in it, contextual up and down, scrolling with a slider."""

    def open_inspect(self, state):
        _, view, _ = app.handle(CONTENT, state, "i", app.View(), UI)
        return view

    def test_inspect_opens_the_panel(self):
        s = bench_state()
        view = self.open_inspect(s)
        self.assertEqual(view.panel, "inspect")
        frame = plain(s, 52, 60, panel="inspect")
        self.assertIn("Workbench", frame)
        self.assertIn("A proper workbench", frame)
        self.assertNotIn("I Inspect", frame)                       # one focus: the menu steps back
        self.assertIn("X close", frame)
        self.assertNotIn("scroll", frame)                          # it all fits: nothing to scroll

    def test_inspect_shows_a_state_and_a_title(self):
        door = walk(new_game(CONTENT, 1), "aaww")
        self.assertIn("closed", plain(door, panel="inspect"))
        juno = walk(new_game(CONTENT, 1), "as")
        frame = plain(juno, panel="inspect")
        self.assertIn("Scrap trader", frame)
        self.assertIn("Deals in whatever", frame)

    def test_long_pages_scroll_with_a_slider(self):
        s = bench_state()
        limit = render.max_scroll(CONTENT, s, 48, 24, "inspect")
        self.assertGreater(limit, 0)
        top, bottom = plain(s, 48, 24, panel="inspect"), plain(s, 48, 24, panel="inspect", scroll=limit)
        self.assertIn("↑↓ scroll", top)
        self.assertIn("A proper workbench", top)
        self.assertNotIn("common-grade gear", top)
        self.assertIn("common-grade gear", bottom)
        self.assertNotIn("A proper workbench", bottom)
        self.assertEqual(plain(s, 48, 24, panel="inspect", scroll=999), bottom)   # kept within the content
        thumb, track = UI.tokens["glyphs"]["slider_thumb"], UI.tokens["glyphs"]["slider_track"]
        rows = [line for line in top.splitlines() if line.endswith(thumb + " │") or line.endswith(track + " │")]
        self.assertGreaterEqual(len(rows), 3)
        self.assertTrue(rows[0].endswith(thumb + " │"))            # at the top, the thumb is at the top
        self.assertTrue(rows[-1].endswith(track + " │"))

    def test_up_and_down_scroll_until_closed(self):
        s = bench_state()
        view = self.open_inspect(s)
        for key in ("s", "\x1b[B", "s"):                         # down: W/S and the arrows
            moved, view, _ = app.handle(CONTENT, s, key, view, UI)
            self.assertEqual(moved.characters[s.player].at, s.characters[s.player].at)
        self.assertEqual(view.scroll, 3)
        _, view, _ = app.handle(CONTENT, s, "w", view, UI)
        self.assertEqual(view.scroll, 2)
        _, same, _ = app.handle(CONTENT, s, "a", view, UI)        # left and right do nothing
        self.assertEqual(same, view)
        after, view, _ = app.handle(CONTENT, s, "x", view, UI)    # close: back to the thing's menu
        self.assertEqual(view, app.View())
        self.assertEqual(after.focus, s.focus)
        self.assertIn("I Inspect", plain(after))
        moved, _, _ = app.handle(CONTENT, after, "w", view, UI)   # closed: up moves again
        self.assertNotEqual(moved.characters[s.player].at, s.characters[s.player].at)

    def test_the_character_sheet_scrolls_and_closes_with_its_key(self):
        s = new_game(CONTENT, 1)
        _, view, _ = app.handle(CONTENT, s, "c", app.View(), UI)
        moved, view, _ = app.handle(CONTENT, s, "s", view, UI)
        self.assertEqual((moved.characters[s.player].at, view.screen, view.scroll),
                         (s.characters[s.player].at, "character", 1))
        _, view, _ = app.handle(CONTENT, s, "c", view, UI)
        self.assertEqual(view, app.View())

    def test_the_pack_panel_turns_pages_with_up_and_down(self):
        s = new_game(CONTENT, 1)
        me = s.characters[s.player]
        s = s._replace(characters=freeze({**s.characters, s.player: me._replace(
            inventory=me.inventory * 3)}))                       # more than a page of entries
        self.assertIn("↑↓ page", plain(s, panel="pack"))
        view = app.View("pack")
        moved, view, _ = app.handle(CONTENT, s, "s", view, UI)
        self.assertEqual((view.panel, view.page), ("pack", 1))
        self.assertEqual(moved.characters[s.player].at, s.characters[s.player].at)
        _, view, _ = app.handle(CONTENT, s, "w", view, UI)
        self.assertEqual(view.page, 0)

    def test_a_pack_can_turn_the_slider_off(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            ui_dir = Path(tmp.name) / "mine"
            shutil.copytree(ui_dir_for("default"), ui_dir)
            path = ui_dir / "screens.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            for zone in data["world"]:
                for part in zone["content"].get("stack", []):
                    if part.get("widget") == "panel":
                        part["slider"] = False
            path.write_text(json.dumps(data), encoding="utf-8")
            frame = plain(bench_state(), 48, 24, ui=load_ui(ui_dir), panel="inspect")
            self.assertNotIn(UI.tokens["glyphs"]["slider_thumb"] + " │", frame)
            self.assertIn("↑↓ scroll", frame)                      # it still scrolls
        finally:
            tmp.cleanup()


class TestItemDetails(unittest.TestCase):
    """Step 2: an item's details, from the pack panel, in the shared panel."""

    def pick(self, state, item_id, group=None):
        slots = build.pack_slots(CONTENT, state)
        return next(i for i, slot in enumerate(slots)
                    if (group is None or slot[0] == group)
                    and getattr(build.entry_at(CONTENT, state, slot), "item", build.entry_at(CONTENT, state, slot)) == item_id)

    def test_details_open_from_a_picked_item_and_go_back(self):
        s = carrying_a_cutter()
        picked = self.pick(s, "module_cutter")
        self.assertIn("I Details", plain(s, panel="pack", selected=picked))
        _, view, _ = app.handle(CONTENT, s, "i", app.View("pack", picked), UI)
        self.assertEqual((view.panel, view.selected), ("item", picked))
        frame = plain(s, panel="item", selected=picked)
        for words in ("Cutter", "Module · Hand slot", "Condition 4/4", "A hand cutter", "Uses", "PWR 1  MAS 2",
                      "Counts as", "a tool", "Strike", "1 free of 1", "Takes apart", "Scrap x2", "design not known",
                      "Scrap for +2", "X back"):
            self.assertIn(words, frame)
        self.assertNotIn("I Details", frame)                    # one focus: the board steps back
        _, back, _ = app.handle(CONTENT, s, "x", view, UI)
        self.assertEqual(back, app.View("pack", picked, 0))
        _, closed, _ = app.handle(CONTENT, s, "p", view, UI)
        self.assertEqual(closed, app.View())

    def test_stored_gear_shows_what_it_needs(self):
        s = walk(run(CONTENT, new_game(CONTENT, 1), Ctx(self_id="char_player"),
                     [freeze({"op": "move_to", "location": "loc_storage", "subject": "self"})]), "ssa")
        frame = plain(s, panel="item", selected=self.pick(s, "frame_heavy", "storage"))
        for words in ("Heavy suit", "Suit · Fine", "Needs", "Salvage 2", "an air filter", "Hand x2, Back x3", "large"):
            self.assertIn(words, frame)

    def test_mods_designs_and_broken_items(self):
        s = run(CONTENT, new_game(CONTENT, 1), Ctx(self_id="char_player"), [
            freeze({"op": "learn_design", "item": "module_cutter", "subject": "self"}),
            freeze({"op": "wear", "pick": {"item": "module_cutter"}, "amount": 99, "subject": "self"})])
        me = s.characters[s.player]
        modded = me.frame._replace(mods=("mod_reinforced",))
        s = s._replace(characters=freeze({**s.characters, s.player: me._replace(frame=modded)}))
        frame = plain(s, panel="item", selected=0, screen="fitting")      # fitted gear: from the fitting screen
        self.assertIn("Light suit (Reinforced)", frame)
        self.assertIn("Reinforced, 1 free of 2", frame)
        self.assertIn("ARM +1", frame)
        cutter = plain(s, panel="item", selected=1, screen="fitting")
        self.assertIn("Broken", cutter)
        self.assertIn("design known", cutter)

    def test_every_item_has_details_that_fit(self):
        frame = Frame(CONTENT, new_game(CONTENT, 1), UI, Style(False, UI.tokens["styles"]), "world", panel="item")
        for item_id in CONTENT.all("item"):
            with self.subTest(item=item_id):
                self.assertTrue(CONTENT.get("item", item_id).get("description"))
                lines = item_details(frame, item_id, 34)          # as a design: no instance needed
                self.assertTrue(all(visible_len(line) <= 34 for line in lines))

    def test_long_details_scroll(self):
        s = carrying_a_cutter()
        picked = self.pick(s, "module_cutter")
        self.assertGreater(render.max_scroll(CONTENT, s, 48, 24, "item", picked), 0)
        self.assertIn("↑↓ scroll", plain(s, 48, 24, panel="item", selected=picked))


class TestFittingScreen(unittest.TestCase):
    """Step 3: the fitting screen, where planning and building happen."""

    def open(self, state):
        _, view, _ = app.handle(CONTENT, state, "f", app.View(), UI)
        return view

    def test_empty_slots_are_listed_but_never_picked(self):
        s = bench_state()
        frame = plain(s, screen="fitting")
        self.assertEqual(frame.count("· empty"), 2)                 # a free hand slot, the free head slot
        view = self.open(s)
        seen = []
        for _ in range(6):
            row = build.fitting_rows(CONTENT, s)[widgets.picks(CONTENT, s)[view.selected]]
            seen.append(row.slot)
            _, view, _ = app.handle(CONTENT, s, "s", view, UI)
        self.assertNotIn(None, seen)
        self.assertEqual(view.selected, len(widgets.picks(CONTENT, s)) - 1)   # stops at the last

    def test_away_from_a_workshop_it_is_for_planning(self):
        s = new_game(CONTENT, 1)
        frame = plain(s, screen="fitting", selected=1)
        self.assertIn("Planning only", frame)
        self.assertIn("R Remove - Needs a refit workshop.", frame)
        after, _, _ = app.handle(CONTENT, s, "r", app.View(screen="fitting", selected=1), UI)
        self.assertEqual(after.characters[s.player].fitted, s.characters[s.player].fitted)

    def test_gear_fits_straight_from_storage(self):
        s = walk(run(CONTENT, new_game(CONTENT, 1), Ctx(self_id="char_player"),
                     [freeze({"op": "move_to", "location": "loc_storage", "subject": "self"})]), "ssa")
        rows = build.fitting_rows(CONTENT, s)
        pickable = widgets.picks(CONTENT, s)
        eye = next(n for n, i in enumerate(pickable) if rows[i].where and
                   build.entry_at(CONTENT, s, rows[i].slot).item == "implant_eye")
        self.assertIn("in Suit bay", plain(s, screen="fitting", selected=eye))
        s, view, _ = app.handle(CONTENT, s, "f", app.View(screen="fitting", selected=eye), UI)
        self.assertIn("Fitted Eye implant.", [m.text for m in s.messages])
        self.assertEqual([i.item for i in s.storage["storage_bay"]], ["frame_heavy"])
        row = build.fitting_rows(CONTENT, s)[widgets.picks(CONTENT, s)[view.selected]]
        self.assertEqual((row.group, row.slot_type), ("worn", "slot_head"))   # the pick followed it

    def test_what_an_action_would_change_and_why_not(self):
        s = run(CONTENT, bench_state(), Ctx(self_id="char_player"), [
            freeze({"op": "give_item", "item": "module_cutter", "count": 1, "subject": "self"}),
            freeze({"op": "modify_stat", "stat": "stat_power", "amount": -2, "subject": "self"})])
        spare = len(widgets.picks(CONTENT, s)) - 1
        frame = plain(s, screen="fitting", selected=spare)
        self.assertIn("Fit: PWR 4→5/4", frame)
        self.assertIn("F Fit - ", frame)                              # greyed out, with the reason
        coloured = render.render(CONTENT, s, 52, 60, screen="fitting", selected=spare, ui=UI)
        self.assertIn(Style(True, UI.tokens["styles"]).role("PWR 4→5/4", "danger"), coloured)

    def test_modify_applies_with_a_digit(self):
        s = bench_state()
        view = self.open(s)._replace(selected=1)                      # the cutter
        _, view, _ = app.handle(CONTENT, s, "m", view, UI)
        self.assertEqual(view.panel, "modify")
        self.assertIn("1 Reinforced", plain(s, screen="fitting", selected=1, panel="modify"))
        s, view, _ = app.handle(CONTENT, s, "1", view, UI)
        self.assertIsNone(view.panel)
        self.assertEqual(s.characters[s.player].fitted[0].mods, ("mod_reinforced",))

    def test_details_and_back(self):
        s = bench_state()
        view = self.open(s)._replace(selected=1)
        _, view, _ = app.handle(CONTENT, s, "i", view, UI)
        self.assertEqual((view.screen, view.panel), ("fitting", "item"))
        self.assertIn("A hand cutter", plain(s, screen="fitting", selected=1, panel="item"))
        _, view, _ = app.handle(CONTENT, s, "x", view, UI)
        self.assertEqual((view.screen, view.panel, view.selected), ("fitting", None, 1))
        _, view, _ = app.handle(CONTENT, s, "x", view, UI)
        self.assertEqual(view, app.View())

    def test_the_pick_shows_without_colour(self):
        frame = render.render(CONTENT, bench_state(), 52, 60, colour=False, screen="fitting", selected=1, ui=UI)
        self.assertIn(UI.tokens["glyphs"]["cursor"] + "   Hand  2 Cutter", frame)


class TestCharacterScreen(unittest.TestCase):
    """Step 4: the character screen, with the art zone for the character's picture."""

    def frame(self, state, columns=52, rows=60, **kw):
        return plain(state, columns, rows, screen="character", **kw)

    def pack_copy(self, change, file="characters.json", entry_id="char_player"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name) / "test"
        shutil.copytree(ROOT / "packs" / "test_scifi", folder)
        path = folder / file
        data = json.loads(path.read_text(encoding="utf-8"))
        change(next(e for e in data["entries"] if e["id"] == entry_id))
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return folder

    def test_the_portrait_is_drawn_in_half_block_pixels(self):
        s = new_game(CONTENT, 1)
        coloured = render.render(CONTENT, s, 52, 60, screen="character", ui=UI)
        style = Style(True, UI.tokens["styles"])
        self.assertIn(style.pixels("▀", 255, 31), coloured)          # a glint over the visor: two colours in one cell
        self.assertIn(style.pixels("█", 166, None), coloured)        # the suit: both halves the same colour
        frame = self.frame(s)
        self.assertIn("▄▄██████▄▄", frame)                            # without colour, the shape
        width = UI.tokens["size"]["art_width"] + 2
        self.assertIn("┌" + "─" * (width - 2) + "┐", frame)

    def test_without_a_picture_the_zone_is_kept(self):
        content = load_pack(self.pack_copy(lambda player: player.pop("art")))
        frame = ANSI.sub("", render.render(content, new_game(content, 1), 52, 60, screen="character", ui=UI))
        lines = frame.splitlines()
        box = [line for line in lines if line.startswith("││")]
        self.assertEqual(len(box), UI.tokens["size"]["art_height"] // 2)
        self.assertTrue(any("P" in line[:20] for line in box))       # the initial, in the middle

    def test_the_checker_reads_pictures(self):
        def broken(picture):
            picture["rows"][0] += "x"
        errors = validate_pack(self.pack_copy(broken, "art.json", "art_player")).errors
        self.assertTrue(any("rows have different lengths" in e for e in errors), errors)
        self.assertTrue(any("not in the palette: x" in e for e in errors), errors)

    def test_skills_show_progress_and_what_comes_next(self):
        s = new_game(CONTENT, 1)
        frame = self.frame(s)
        self.assertIn("Salvage 1", frame)
        self.assertIn("0/30", frame)
        self.assertIn("next, 2: Unlocks Burn.", frame)
        s = run(CONTENT, s, Ctx(self_id=s.player), [freeze({"op": "grant_xp", "skill": "skill_salvage", "amount": 45,
                                                             "subject": "self"})])
        frame = self.frame(s)
        self.assertIn("Salvage 2", frame)
        self.assertIn("45/90", frame)
        self.assertIn("next, 3: Tougher.", frame)

    def test_stats_conditions_party_and_standing(self):
        s = new_game(CONTENT, 1)
        s = run(CONTENT, s, Ctx(self_id=s.player), [
            freeze({"op": "apply_status", "status": "status_burning", "duration": 3, "subject": "self"})])
        s = run(CONTENT, s, Ctx(self_id="char_juno"), [freeze({"op": "join_party", "subject": "self"})])
        frame = self.frame(s)
        for words in ("ARM 2", "INI 0", "Burning", "3 turns left", "Juno", "Rank: Newcomer",
                      "Station crew: neutral (0)"):
            self.assertIn(words, frame)
        self.assertNotIn("Travelling alone", frame)
        s = run(CONTENT, s, Ctx(self_id="char_juno"), [
            freeze({"op": "damage", "amount": 999, "damage_type": "dmg_impact", "subject": "self"})])
        self.assertIn("down", self.frame(s))

    def test_it_scrolls_on_small_screens(self):
        s = new_game(CONTENT, 1)
        limit = render.max_scroll(CONTENT, s, 48, 24, screen="character")
        self.assertGreater(limit, 0)
        self.assertIn("↑↓ scroll", self.frame(s, 48, 24))
        self.assertIn("Station crew", self.frame(s, 48, 24, scroll=limit))
        self.assertNotIn("Station crew", self.frame(s, 48, 24))

    def test_the_art_zone_size_comes_from_the_ui_pack(self):
        frame = plain(new_game(CONTENT, 1), ui=ui_with(self, art_width=20, art_height=14), screen="character")
        self.assertIn("┌" + "─" * 20 + "┐", frame)
        self.assertEqual(len([line for line in frame.splitlines() if line.startswith("││")]), 7)


class TestConversation(unittest.TestCase):
    """Step 5: talking to someone on the conversation screen."""

    def talking(self):
        s = walk(new_game(CONTENT, 1), "as")                   # Juno in focus
        turn = s.turn
        s, view, _ = app.handle(CONTENT, s, "t", app.View(), UI)
        self.assertEqual(s.turn, turn + 1)                     # talking takes a turn
        return s, view

    def frame(self, s, view, columns=52, rows=60):
        return plain(s, columns, rows, screen=view.screen, log=view.log, scroll=view.scroll)

    def test_talk_opens_the_conversation(self):
        s, view = self.talking()
        self.assertEqual(view.screen, "talk")
        frame = self.frame(s, view)
        for words in ("Talking · Juno", "Workshop", "Scrap trader", "Trust: neutral (10)", "Juno: “Hello.”",
                      "1 Trade", "You give  Keycard", "You get   Medkit x2",
                      "2 Recruit - Doesn't trust you enough.", "3 Leave", "1-3 answer", "X leave"):
            self.assertIn(words, frame)
        coloured = render.render(CONTENT, s, 52, 60, screen="talk", ui=UI)
        self.assertIn(Style(True, UI.tokens["styles"]).pixels("█", 130, None), coloured)   # Juno's hair

    def test_answers_are_kept_with_what_changed_hands(self):
        s, view = self.talking()
        s, view, _ = app.handle(CONTENT, s, "1", view, UI)
        self.assertEqual(view.screen, "talk")
        frame = self.frame(s, view)
        for words in ("You: Trade", "Lost: Keycard.", "Got: Medkit x2.", "Trust: neutral (30)", "2 Recruit\n"):
            self.assertIn(words.rstrip("\n"), frame)
        self.assertNotIn("Doesn't trust you enough", frame)

    def test_a_recruit_keeps_talking(self):
        s, view = self.talking()
        s, view, _ = app.handle(CONTENT, s, "1", view, UI)
        s, view, _ = app.handle(CONTENT, s, "2", view, UI)
        self.assertIn("char_juno", context.party_of(s, s.player))
        frame = self.frame(s, view)
        for words in ("You: Recruit", "Juno joins Player.", "Juno: “Lead on.”", "2 Leave"):
            self.assertIn(words, frame)
        self.assertNotIn("Recruit -", frame)

    def test_leaving(self):
        s, view = self.talking()
        _, left, _ = app.handle(CONTENT, s, "3", view, UI)
        self.assertEqual(left, app.View())
        after, left, _ = app.handle(CONTENT, s, "x", view, UI)
        self.assertEqual(left, app.View())
        self.assertEqual(after.focus, s.focus)                 # back to Juno's menu

    def test_looking_back_through_a_long_conversation(self):
        s, view = self.talking()
        history = tuple(Message("plain", f"Line {i}.") for i in range(30))
        newest = plain(s, 48, 24, screen="talk", log=history)
        self.assertIn("3 Leave", newest)
        self.assertNotIn("Line 0.", newest)
        self.assertIn("↑↓ scroll", newest)
        oldest = plain(s, 48, 24, screen="talk", log=history, scroll=99)
        self.assertIn("Line 0.", oldest)
        _, back, _ = app.handle(CONTENT, s, "w", view._replace(log=history), UI)
        self.assertEqual(back.scroll, 1)

    def test_what_a_trade_gives_and_takes(self):
        gives, gets = widgets.exchange(CONTENT, freeze({"effects": [
            {"op": "take_item", "item": "misc_keycard", "count": 1},
            {"op": "give_item", "item": "consumable_medkit", "count": {"min": 1, "max": 3}},
            {"op": "give_item", "item": "material_scrap", "count": 2, "subject": "target"},
            {"op": "message", "text": "Deal."}]}))
        self.assertEqual((gives, gets), (["Keycard", "Scrap x2"], ["Medkit x1-3"]))


class TestMessages(unittest.TestCase):
    """Step 6: the message history, kept with the game, and event cards."""

    def test_every_key_adds_what_it_said_to_the_journal(self):
        s = with_history()
        self.assertEqual([e.text for e in s.journal], ["Empty.", "Night shift.", "Already searched."])
        self.assertEqual(s.journal[0].turn, 2)                          # stamped with the turn
        s2, _, _ = app.handle(CONTENT, s, "p", app.View(), UI)         # a key that says nothing adds nothing
        self.assertEqual(s2.journal, s.journal)

    def test_a_fight_ends_in_the_journal(self):
        s, view = encounter_state(), app.View()
        for _ in range(40):
            if s.encounter is None:
                break
            s, view, _ = app.handle(CONTENT, s, "1", view, UI)          # Strike, and a target when asked
        texts = [e.text for e in s.journal]
        self.assertIn("Won.", texts)
        self.assertTrue(any(t.startswith("Found:") for t in texts))

    def test_the_journal_is_saved_and_capped(self):
        s = with_history()
        self.assertEqual(save.from_json(CONTENT, save.to_json(CONTENT, s)).journal, s.journal)
        many = s._replace(messages=tuple(Message("plain", f"Line {i}.") for i in range(250)))
        capped = journal.record(s._replace(messages=()), many)
        self.assertEqual(len(capped.journal), journal.JOURNAL_SIZE)
        self.assertEqual(capped.journal[-1].text, "Line 249.")

    def test_the_history_panel(self):
        s = with_history()
        _, view, _ = app.handle(CONTENT, s, "l", app.View(), UI)
        self.assertEqual(view.panel, "history")
        frame = plain(s, panel="history")
        for words in ("Message log", "Day 1 · Day shift", "Empty.", "Day 1 · Night shift", "Already searched.", "X close"):
            self.assertIn(words, frame)
        self.assertNotIn("WASD move", frame)
        _, closed, _ = app.handle(CONTENT, s, "x", view, UI)
        self.assertEqual(closed, app.View())
        self.assertIn("Nothing yet.", plain(new_game(CONTENT, 1), panel="history"))

    def test_the_history_keeps_the_newest_in_view_and_looks_back(self):
        s = with_history()._replace(journal=tuple(Entry(1, "plain", f"Line {i}.") for i in range(30)))
        newest = plain(s, 48, 24, panel="history")
        self.assertIn("Line 29.", newest)
        self.assertNotIn("Line 0.", newest)
        self.assertIn("↑↓ scroll", newest)
        self.assertIn("Line 0.", plain(s, 48, 24, panel="history", scroll=99))
        _, view, _ = app.handle(CONTENT, s, "w", app.View("history"), UI)
        self.assertEqual(view.scroll, 1)

    def test_a_question_opens_as_a_card(self):
        s = requested("event_grudge")
        frame = plain(s)
        for words in ("Grudge", "Someone holds a grudge.", "What do you do?", "1 Apologise", "2 Ignore it", "1-2 choose"):
            self.assertIn(words, frame)
        self.assertNotIn("Locker", frame.split("Grudge")[1])            # one focus: the card
        s, view, _ = app.handle(CONTENT, s, "2", app.View(), UI)
        self.assertIsNone(s.pending)
        self.assertIsNone(s.card)

    def test_any_question_is_a_card_titled_with_its_thing(self):
        s = walk(run(CONTENT, new_game(CONTENT, 1), Ctx(self_id="char_player"),
                     [freeze({"op": "move_to", "location": "loc_storage", "subject": "self"})]), "ssdd")
        s, _, _ = app.handle(CONTENT, s, "r", app.View(), UI)           # use the terminal
        self.assertIsNotNone(s.pending)
        frame = plain(s)
        self.assertIn("Terminal", frame)
        self.assertIn("1 Check the logs", frame)

    def test_a_long_text_is_a_card_any_key_continues(self):
        s = requested("event_rescue")
        frame = plain(s)
        self.assertIn("Rescue", frame)
        self.assertIn("Nobody's around", frame)
        self.assertIn("Any key: continue", frame)
        scrolled, view, _ = app.handle(CONTENT, s, "s", app.View(), UI)  # down scrolls, it doesn't move
        self.assertEqual((scrolled.card, view.scroll), (s.card, 1))
        after, view, _ = app.handle(CONTENT, s, "a", app.View(), UI)    # anything else continues
        self.assertIsNone(after.card)
        self.assertEqual(after.characters[after.player].at, s.characters[s.player].at)   # and only continues

    def test_a_short_text_stays_in_the_log(self):
        s = walk(new_game(CONTENT, 1), "aaww")
        s, _, _ = app.handle(CONTENT, s, "u", app.View(), UI)           # open the door
        s, _, _ = app.handle(CONTENT, s, "g", app.View(), UI)           # into Storage: the arrival event
        self.assertEqual(s.card.title, "Arrival")
        frame = plain(s)
        self.assertIn("Machines hum somewhere below.", frame)
        self.assertNotIn("Any key: continue", frame)
        moved, _, _ = app.handle(CONTENT, s, "s", app.View(), UI)       # the next key just acts
        self.assertIsNone(moved.card)
        self.assertNotEqual(moved.characters[s.player].at, s.characters[s.player].at)

    def test_quiet_events_make_no_card(self):
        s = events.settle(CONTENT, new_game(CONTENT, 1)._replace(event_requests=("event_restock",)))
        self.assertIsNone(s.card)

    def test_the_card_size_comes_from_the_ui_pack(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ui_dir = Path(tmp.name) / "mine"
        shutil.copytree(ui_dir_for("default"), ui_dir)
        path = ui_dir / "tokens.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("size", {})["card_min_lines"] = 0
        path.write_text(json.dumps(data), encoding="utf-8")
        s = walk(new_game(CONTENT, 1), "aaww")
        s, _, _ = app.handle(CONTENT, s, "u", app.View(), UI)
        s, _, _ = app.handle(CONTENT, s, "g", app.View(), UI)
        self.assertIn("Any key: continue", plain(s, ui=load_ui(ui_dir)))   # now even a short text is a card


class TestFightScreen(unittest.TestCase):
    """Step 6: picking an action, its details in words, targets in the fighters column."""

    def burn_ready(self):
        s = run(CONTENT, new_game(CONTENT, 1), Ctx(self_id="char_player"),
                [freeze({"op": "grant_xp", "skill": "skill_salvage", "amount": 30, "subject": "self"})])
        return encounter.begin(CONTENT, s._replace(encounter_request="enc_drones"))

    def test_a_digit_picks_the_same_digit_uses(self):
        s = encounter_state()
        s1, view, _ = app.handle(CONTENT, s, "2", app.View(), UI)
        self.assertEqual((view.selected, s1.encounter.round), (1, 1))           # picked, not used
        _, other, _ = app.handle(CONTENT, s1, "3", view, UI)
        self.assertEqual(other.selected, 2)                                     # another digit picks another
        _, gone, _ = app.handle(CONTENT, s1, "x", view, UI)
        self.assertEqual(gone, app.View())                                      # X lets go
        s2, view, _ = app.handle(CONTENT, s1, "2", view, UI)
        self.assertEqual((view, s2.encounter.round), (app.View(), 2))           # the same digit uses it

    def test_an_unusable_action_says_why(self):
        s = encounter_state()
        s, view, _ = app.handle(CONTENT, s, "2", app.View(), UI)
        s, view, _ = app.handle(CONTENT, s, "2", view, UI)                      # Guard: now cooling down
        frame = plain(s, selected=1)
        self.assertIn("Can't use it now: Ready in 2.", frame)
        same, view, _ = app.handle(CONTENT, s, "2", app.View(selected=1), UI)
        self.assertEqual((same.encounter.round, view.selected), (s.encounter.round, 1))

    def test_details_in_words(self):
        s = self.burn_ready()
        strike = plain(s, selected=0)
        self.assertIn("heat 1", strike)
        self.assertIn("0.5×PWR+2 impact damage to one enemy.", strike)
        burn = plain(s, selected=2)
        for words in ("heat 3-4", "1 of 1 uses left", "uses Scrap x2", "2×Salvage toxic damage to every enemy",
                      "on every enemy for 3 rounds."):
            self.assertIn(words, burn)
        retreat = plain(s, 72, 60, selected=3)
        self.assertIn("acts late", retreat)
        self.assertIn("60% chance: you get away and the fight ends.", retreat)

    def test_tile_names_fit(self):
        s = self.burn_ready()
        frame = plain(s)
        self.assertIn("│Retreat │", frame)
        self.assertTrue(all(len(t.label) <= UI.tokens["size"]["tile_width"] - 2 for t in encounter.tiles(CONTENT, s)))
        self.assertIn("▲3-4 ×1", frame)                                          # heat and uses left
        self.assertIn("▲1 ⟳2", frame)                                            # heat and cooldown

    def test_fighters_show_their_statuses(self):
        s = encounter_state()
        drone = encounter.living(s, "enemies")[0]
        s = run(CONTENT, s, Ctx(self_id=drone), [freeze({"op": "apply_status", "status": "status_burning",
                                                         "duration": 3, "subject": "self"})])
        self.assertIn("Burning 3", plain(s))

    def test_targets_are_marked_and_nothing_moves(self):
        s = encounter_state()
        normal, aiming = plain(s, selected=0), plain(s, selected=0, panel="target")
        self.assertIn("▸1 Drone", aiming)
        self.assertIn("▸2 Drone", aiming)
        self.assertIn("1-2 target", aiming)
        column = lambda frame: next(line.index("Drone") for line in frame.splitlines() if "Drone " in line)
        self.assertEqual(column(normal), column(aiming))

    def test_the_pick_shows_without_colour(self):
        frame = render.render(CONTENT, encounter_state(), 52, 60, colour=False, selected=1, ui=UI)
        self.assertIn("┏2━━━━━━━┓", frame)

    def test_details_fit_the_smallest_screen(self):
        frame = plain(encounter_state(), 48, 24, selected=1)
        self.assertIn("ARM +4 on yourself for 1 round.", frame)
        self.assertIn("2 again: use", frame)


class TestPolish(unittest.TestCase):
    """Step 9: the polish pass."""

    def test_wrapped_options_hang_under_their_text(self):
        narrow = ui_with(self, min_columns=40, side_min_width=10)   # a UI pack that allows 40 columns
        frame = plain(walk(new_game(CONTENT, 1), "as"), 40, 30, ui=narrow, screen="talk")
        self.assertIn("│ 2 Recruit - Doesn't trust you", frame)
        self.assertIn("│   enough.", frame)

    def test_the_pack_panel_shows_the_pick_with_what_it_can_do(self):
        frame = plain(new_game(CONTENT, 1), 48, 24, panel="pack", selected=0)
        lines = frame.splitlines()
        medkit = next(i for i, line in enumerate(lines) if "1 Medkit" in line)
        self.assertIn("U Use", lines[medkit + 1])                    # the options sit under the pick
        self.assertIn("I Details", lines[medkit + 2])

    def test_lists_keep_room_on_short_terminals(self):
        frame = plain(bench_state(), 48, 24, screen="fitting", selected=1)
        self.assertIn("1 Light suit", frame)
        self.assertIn("Hand  2 Cutter", frame)
        self.assertIn("Hand  · empty", frame)
        self.assertIn("R Remove", frame)

    def test_a_question_card_opens_on_the_question(self):
        s = requested("event_grudge")
        frame = plain(s, 48, 24)
        self.assertIn("1 Apologise", frame)
        self.assertIn("2 Ignore it", frame)
        self.assertNotIn("Grudge", frame)
        _, view, _ = app.handle(CONTENT, s, "w", app.View(), UI)      # up looks back to the text
        self.assertIn("Grudge", plain(s, 48, 24, scroll=view.scroll + 6))

    def test_item_names_in_their_grades_colour(self):
        style = Style(True, UI.tokens["styles"])
        frame = render.render(CONTENT, new_game(CONTENT, 1), 52, 60, panel="pack", ui=UI)
        common = CONTENT.get("grade", "grade_common")["colour"]
        self.assertIn(style.colour_of("Scrap", common), frame)
        self.assertNotIn(style.colour_of("Medkit", common), frame)    # ungraded: as it is
        fine = CONTENT.get("grade", "grade_fine")["colour"]
        fitting = render.render(CONTENT, bench_state(), 52, 60, screen="fitting", selected=2, ui=UI)
        self.assertIn(style.colour_of("Shield", fine), fitting)
        picked = render.render(CONTENT, new_game(CONTENT, 1), 52, 60, panel="pack", selected=1, ui=UI)
        self.assertIn(style.key("2 Scrap x10"), picked)              # the highlight isn't broken by the colour

    def test_counts_read_naturally(self):
        s = run(CONTENT, new_game(CONTENT, 1), Ctx(self_id="char_player"), [
            freeze({"op": "apply_status", "status": "status_burning", "duration": 1, "subject": "self"})])
        self.assertIn("1 turn left", plain(s, screen="character"))


class TestWorkshopMenu(unittest.TestCase):
    def test_a_workshop_offers_the_fitting_board_on_the_uis_fitting_key(self):
        frame = plain(bench_state(), 52, 40)
        self.assertIn("F Open the fitting board", frame)
        s, view, _ = app.handle(CONTENT, bench_state(), UI.bindings["fitting"], app.View(), UI)
        self.assertEqual(view.screen, "fitting")
        self.assertNotIn("fitting board", plain(menu_state(), 52, 40))     # a door isn't a workshop


class TestMap(unittest.TestCase):
    """The room: walls joined into solid runs, glyphs coloured by role or by the pack."""

    def coloured(self, state):
        return render.render(CONTENT, state, 52, 30, ui=UI)

    def test_walls_are_solid_and_tiles_stay_in_columns(self):
        frame = plain(new_game(CONTENT, 1), 52, 30)
        self.assertIn("│░░░░ ◆ ░░░░░░│", frame)                 # the door breaks the wall's run
        self.assertIn("│░░ § · · ⊞ ░░│", frame)                 # side walls two glyphs wide

    def test_an_open_edge_leads_on_and_is_listed_once(self):
        s = run(CONTENT, new_game(CONTENT, 1), Ctx(self_id="char_player"),
                [freeze({"op": "move_to", "location": "loc_crater_rim", "subject": "self"})])
        frame = plain(s, 48, 30)
        self.assertEqual(frame.count("Dust flat"), 1)               # eight edge tiles, one legend entry
        self.assertIn("│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│", frame)      # the full 12-tile width
        rows = [line for line in frame.splitlines() if line.startswith("││▓▓ ·")]
        self.assertTrue(rows and all("· ││" in line for line in rows), rows)          # the east side is open
        s = walk(s, "w" + "d" * 6)                                 # onto the east edge
        self.assertIn("G Go to Dust flat", plain(s, 48, 30))
        s, _, _ = app.handle(CONTENT, s, "g", app.View(), UI)
        me = s.characters[s.player]
        self.assertEqual((me.location, me.at), ("loc_dust_flat", (4, 0)))   # the matching tile on the far side
        s, _, _ = app.handle(CONTENT, walk(s, "d"), "a", app.View(), UI)
        self.assertIn("G Go to Crater rim", plain(s, 48, 30))

    def test_glyphs_take_their_roles_colour(self):
        frame = self.coloured(new_game(CONTENT, 1))
        self.assertIn("\x1b[38;5;80m◆", frame)                  # an exit
        self.assertIn("\x1b[38;5;221m⊞", frame)                 # an object
        self.assertIn("\x1b[1;38;5;255mJ", frame)               # a neutral person
        self.assertIn("\x1b[2;38;5;245m·", frame)               # the floor
        self.assertIn("\x1b[7;1;38;5;255m@", frame)             # the player, inverse

    def test_the_packs_colour_wins(self):
        frame = self.coloured(new_game(CONTENT, 1))
        self.assertIn("\x1b[38;5;141m§", frame)                 # the placement's own colour
        storage = run(CONTENT, new_game(CONTENT, 1), Ctx(self_id="char_player"),
                      [freeze({"op": "move_to", "location": "loc_storage", "subject": "self"})])
        frame = self.coloured(storage)
        self.assertIn("\x1b[38;5;244m", frame)                  # the room's wall colour
        self.assertIn("\x1b[38;5;240m", frame)                  # and floor colour
        self.assertIn("\x1b[38;5;114m", frame)                  # the terminal's object colour (green)

    def test_people_are_coloured_by_how_they_see_the_player(self):
        s = new_game(CONTENT, 1)
        cross = run(CONTENT, s, Ctx(self_id="char_juno"),
                    [freeze({"op": "change_relation", "of": "self", "toward": {"character": s.player}, "amount": -40})])
        self.assertIn("\x1b[38;5;203mJ", self.coloured(cross))  # hostile

    def test_the_legend_shows_glyphs_in_their_map_colours(self):
        legend = [line for line in self.coloured(new_game(CONTENT, 1)).splitlines() if "Crate" in line]
        self.assertIn("\x1b[38;5;221m⊞", legend[0])

    def test_narrow_status_bars_keep_their_numbers(self):
        frame = Frame(CONTENT, new_game(CONTENT, 1), UI, Style(False, UI.tokens["styles"]), "world")
        lines = widgets.status(frame, 14, {})
        self.assertTrue(any(line.startswith("HP") and line.endswith("30/30") for line in lines), lines)
        self.assertTrue(all(visible_len(line) <= 14 for line in lines if line.startswith(("HP", "HT"))), lines)


class TestRegionMap(unittest.TestCase):
    """M opens the map of what the player knows: places been to, where their exits lead, region by region."""

    def keys(self, state, view, keys):
        for key in keys:
            state, view, _ = app.handle(CONTENT, state, key, view, UI)
        return state, view

    def test_a_new_game_knows_its_room_and_where_its_exits_lead(self):
        s = new_game(CONTENT, 1)
        self.assertEqual(atlas.known(CONTENT, s), {"loc_workshop": "here", "loc_storage": "known"})
        shown = atlas.region_map(CONTENT, s, "reg_lower_deck")
        self.assertEqual({c: p.kind for c, p in shown.places.items()}, {(0, 0): "here", (1, 0): "known"})
        self.assertEqual(shown.links, {((0, 0), (1, 0))})
        self.assertEqual(atlas.regions(CONTENT, s), ["reg_lower_deck"])

    def test_places_been_to_widen_the_map(self):
        s = travelled()
        self.assertEqual(atlas.regions(CONTENT, s), ["reg_lower_deck", "reg_surface"])
        deck = atlas.region_map(CONTENT, s, "reg_lower_deck")
        self.assertEqual(deck.places[(1, 0)].kind, "visited")
        self.assertEqual(deck.elsewhere, ("loc_crater_rim",))
        surface = atlas.region_map(CONTENT, s, "reg_surface")
        self.assertEqual({c: p.kind for c, p in surface.places.items()}, {(0, 0): "visited", (1, 0): "known"})
        self.assertEqual(surface.links, {((0, 0), (1, 0))})     # eight edge tiles, one way

    def test_keys_open_move_page_and_close(self):
        s, view = self.keys(travelled(), app.View(), "m")
        self.assertEqual((view.screen, view.page, view.cursor), ("map", 0, (0, 0)))
        s, view = self.keys(s, view, "dd")                      # stops at the last place
        self.assertEqual(view.cursor, (1, 0))
        self.assertIn("Storage", plain(s, screen="map", page=view.page, cursor=view.cursor))
        s, view = self.keys(s, view, "]")
        self.assertEqual((view.page, view.cursor), (1, (0, 0)))
        self.assertIn("Map · Surface", plain(s, screen="map", page=view.page, cursor=view.cursor))
        s, view = self.keys(s, view, "]")
        self.assertEqual(view.page, 0)
        s, view = self.keys(s, view, "m")
        self.assertIsNone(view.screen)
        s, view = self.keys(s, app.View(), "mx")
        self.assertIsNone(view.screen)
        self.assertEqual(s.turn, travelled().turn)                # looking at the map takes no time

    def test_next_region_shows_only_with_two(self):
        self.assertNotIn("next region", plain(new_game(CONTENT, 1), screen="map"))

    def test_help_and_walk_hints_name_the_key(self):
        self.assertIn("M map", plain(new_game(CONTENT, 1)))
        self.assertIn("map", UI.word("key_map"))

    def test_m_still_lists_modifications_on_the_fitting_screen(self):
        s, view = self.keys(bench_state(), app.View(), "f")
        rows = build.fitting_rows(CONTENT, s)
        tool = next(n for n, i in enumerate(widgets.picks(CONTENT, s)) if rows[i].slot is not None
                    and build.entry_at(CONTENT, s, rows[i].slot) is not None
                    and any(o.kind == "modify" for o in build.item_options(CONTENT, s, rows[i].slot, UI.bound_keys,
                                                                            "fitting")))
        s, view = self.keys(s, view._replace(selected=tool), "m")
        self.assertEqual((view.screen, view.panel), ("fitting", "modify"))


class TestEngineOptionsAreWordedByTheUI(unittest.TestCase):
    def test_built_in_options_have_no_label(self):
        options = {o.kind: o for o in world.menu(CONTENT, menu_state()).options}
        self.assertIsNone(options["go"].label)
        self.assertEqual(dict(options["go"].params), {"destination": "Storage"})
        self.assertEqual(option_text(UI, options["go"]), "Go to Storage")
        self.assertEqual(options["interaction"].label, "Open")    # the content's own label

    def test_round_end_is_a_heading(self):
        s = encounter_state()
        s = run(CONTENT, s, Ctx(self_id=s.player), [freeze(
            {"op": "apply_status", "status": "status_burning", "subject": "self", "duration": 3})])
        s = encounter.take_turn(CONTENT, s, "action_guard")         # the status ticks at the round's end
        self.assertIn(("heading", "round_end"), [(m.kind, m.text) for m in s.messages])
        self.assertIn("End of round", plain(s))


class TestEngineDefaults(unittest.TestCase):
    def test_engine_default_bindings_match_the_default_ui_pack(self):
        # The engine avoids these keys when no UI pack is passed in; they must be the standard ones.
        self.assertEqual(world.STANDARD_BINDINGS, UI.bound_keys)

    def test_menu_keys_are_drawn_in_the_key_style(self):
        frame = render.render(CONTENT, menu_state(), 52, 60, ui=UI)
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
        self.change("keys.json", lambda d: d.setdefault("bindings", {}).update(pack="n", move_west="j"))
        ui = load_ui(self.dir)
        s = new_game(CONTENT, 1)
        self.assertIn("N pack", plain(s, ui=ui))
        self.assertIn("WJSD move", plain(s, ui=ui))
        _, view, _ = app.handle(CONTENT, s, "n", app.View(), ui)
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
        self.assertIn("G Enter Storage", frame)
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
            code = app.run(ROOT / "packs" / "test_scifi", Path(self.tmp.name) / "save.json", 1, True, ui_dir=self.dir)
        self.assertEqual(code, 1)
        self.assertIn("the engine's key for 'fit'", out.getvalue())


if __name__ == "__main__":
    unittest.main()
