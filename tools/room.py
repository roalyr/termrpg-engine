"""
The room editor: one location's layout and its ways out.

Pick a location, then move the cursor over its grid. Enter lists what can be done on
the tile under the cursor; each action also has a letter. Tiles (wall, floor,
nothing), the size, placing, moving and removing objects, the entry point, doors to
other locations and open edges. Everything else about a placement (state, contents,
interactions) stays in the JSON.

Nothing is written until you leave the room and say yes; then the checker runs.

  python3 -m tools.room packs/test_scifi     on its own
  python3 editor.py                    from the editor's menu
"""
import sys
from typing import Callable, List, Optional, Tuple

from lib.tiles import map_glyph, room_line
from lib import forms, screen
from tools.lib import colours, rooms
from tools.lib.tool import run_tool, save_safely
from tools.lib.packfiles import Found, PackFiles

Pos = Tuple[int, int]
MOVES = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}
TILE_WORDS = {"#": "wall", ".": "floor", " ": "nothing"}


class Room:
    name = "Room"
    about = "One location's layout: tiles, size, objects, the entry point, doors and open edges."

    def __init__(self, pack: PackFiles, look: screen.Look, location_id: Optional[str] = None,
                 single: bool = False):
        self.pack, self.look = pack, look
        self.single = single                   # opened on one room by another tool: leaving goes back to it
        self.closed = False
        self.notice = ""                       # the last word when leaving: what saving found
        self.found: Optional[Found] = None
        self.cursor: Pos = (0, 0)
        self.form = None                       # an open list, field or question
        self.after: Optional[Callable] = None  # what to do with the form's answer
        self.carrying: Optional[dict] = None   # a placement being moved
        self.picking: Optional[Tuple[Found, Pos, Callable]] = None   # choosing a tile in another location
        self.message: Tuple[str, str] = ("", "quiet")
        self.last_object: Optional[str] = None
        if location_id is not None:
            self.open(location_id)
        else:
            self.choose_location()

    # --- what's shown --------------------------------------------------------------

    @property
    def location(self) -> dict:
        return self.found.entry

    def open(self, location_id: str, at: Optional[Pos] = None) -> None:
        self.found = self.pack.find("locations", location_id)
        entry = self.pack.placement(self.location.get("entry", "")) if self.location.get("entry") else None
        width, height = rooms.size(self.location)
        self.cursor = at or (tuple(entry[1]["at"]) if entry else (height // 2, width // 2))
        self.carrying = None

    def ask(self, form, after: Callable) -> None:
        self.form, self.after = form, after

    def say(self, text: str, role: str = "quiet") -> None:
        self.message = (text, role)

    def choose_location(self, notice: str = "") -> None:
        choices = []
        for f in self.pack.entries("locations"):
            loc = f.entry
            region = self.pack.find("regions", loc.get("region", ""))
            width, height = rooms.size(loc)
            choices.append(forms.Choice(loc.get("name", loc["id"]), loc["id"],
                                        f"{width}×{height} · " + (region.entry.get("name", "") if region else ""),
                                        loc.get("description", "")))
        picker = forms.Picker(self.look, "Room · pick a location", choices,
                              self.found.entry["id"] if self.found else None)
        picker.notice = notice
        self.found = None
        self.ask(picker, lambda location_id: self.open(location_id))

    # --- drawing -------------------------------------------------------------------

    def render(self, columns: int, rows: int) -> str:
        look, width = self.look, screen.inner_width(self.look, columns)
        unsaved = " *" if self.pack.dirty else ""
        manifest = self.pack.manifest
        right = f"{manifest.get('name', self.pack.id)}{unsaved}"
        if self.form is not None:
            title = getattr(self.form, "title", None) or f"Room · {self.location.get('name', '')}"
            lines, focus = self.form.lines(width)
            notice = screen.quiet(look, getattr(self.form, "notice", ""), width)
            bands = [screen.title(look, title, right, width), notice + lines,
                     self.cut(self.form.about(), width), screen.hints(look, self.form.hints(), width)]
            return screen.draw(look, [b for b in bands if b], columns, rows, flex=1, focus=focus + len(notice)).text
        shown = self.picking[0].entry if self.picking else self.location
        heading = f"Pick a tile in {shown.get('name', '')}" if self.picking else f"Room · {shown.get('name', '')}"
        bands = [screen.title(look, heading, right, width), self.body(shown, width),
                 self.info(shown, width), screen.hints(look, self.hints(), width)]
        return screen.draw(look, [b for b in bands if b], columns, rows).text

    def cut(self, text: str, width: int, most: int = 3) -> List[str]:
        """A pick's description, cut to a few lines so the list keeps the room."""
        lines = screen.wrap(text, width) if text else []
        if len(lines) > most:
            lines = lines[:most - 1] + [lines[most - 1][:width - 1] + "…"]
        return [self.look.style.role(line, "quiet") for line in lines]

    def cell(self, location: dict, pos: Pos, people: dict) -> Tuple[str, object, str]:
        """The glyph on a tile, the pack's colour for it (or None) and its map role, as the game draws them."""
        if pos in people:
            person = people[pos]
            return person.get("glyph") or person.get("name", "?")[0], person.get("colour"), "map_person"
        placed = rooms.placement_at(location, pos)
        if placed is self.carrying:
            placed = None                                   # drawn where the cursor is instead
        if placed is None and self.carrying is not None and pos == self.cursor and location is self.location:
            placed = self.carrying
        if placed is not None:
            return rooms.glyph(self.pack, placed), rooms.colour(self.pack, placed), "map_exit" if placed.get("exit") else "map_object"
        grid = location["grid"]
        kind = rooms.tile(location, pos)
        if kind == "#":
            return grid["wall"], grid.get("wall_colour"), "map_wall"
        if kind == ".":
            return grid["floor"], grid.get("floor_colour"), "map_floor"
        return " ", None, "map_floor"

    def body(self, location: dict, width: int) -> List[str]:
        """The grid, and beside it what's in the room."""
        style, spec = self.look.style, location["grid"]
        grid_w, grid_h = rooms.size(location)
        people = rooms.characters_at(self.pack, location["id"])
        cell_width = self.look.ui.tokens["size"]["cell_width"]
        wall = map_glyph(style, spec["wall"], spec.get("wall_colour"), "map_wall")
        grid = []
        for r in range(grid_h):
            cells = []
            for c in range(grid_w):
                glyph, colour, role = self.cell(location, (r, c), people)
                cells.append(style.inverse(glyph if glyph.strip() else " ") if (r, c) == self.cursor
                             else map_glyph(style, glyph, colour, role))
            shows_wall = [self.cell(location, (r, c), people)[2] == "map_wall" for c in range(grid_w)]
            grid.append(room_line(cells, shows_wall, wall, cell_width))
        grid_width = grid_w + (grid_w - 1) * (cell_width - 1) + 2
        legend = self.legend(location, people)
        side = width - grid_width - 3
        lines = []
        for i in range(max(len(grid), len(legend))):
            left = screen.pad(grid[i] if i < len(grid) else "", grid_width)
            right = screen.pad(legend[i], side) if i < len(legend) and side > 3 else ""
            lines.append(left + (" " + self.look.glyphs["border"]["vertical"] + " " + right if right else ""))
        return lines

    def legend(self, location: dict, people: dict) -> List[str]:
        """Each kind of thing here once: its glyph (in its map colour) and name, where an exit leads, and how many."""
        style = self.look.style
        seen, counts, painted = [], {}, {}
        for p in location.get("placements", []):
            dest, _ = rooms.exit_target(p)
            zone = (p.get("exit") or {}).get("zone") if isinstance(p.get("exit"), dict) else None
            where = f" → {rooms.location_name(self.pack, dest)}" if dest else (f" → {zone}" if zone else "")
            glyph = rooms.glyph(self.pack, p)
            key = (glyph, f"{rooms.name(self.pack, p)}{where}")
            if key not in counts:
                seen.append(key)
                painted[key] = map_glyph(style, glyph, rooms.colour(self.pack, p), "map_exit" if p.get("exit") else "map_object")
            counts[key] = counts.get(key, 0) + 1
        lines = [f"{painted[k]} {k[1]}" + (f" ×{counts[k]}" if counts[k] > 1 else "") for k in seen]
        for c in people.values():
            glyph = c.get("glyph") or c.get("name", "?")[0]
            lines.append(f"{map_glyph(style, glyph, c.get('colour'), 'map_person')} {c.get('name', c['id'])}")
        return lines

    def info(self, location: dict, width: int) -> List[str]:
        """The tile under the cursor: what it is, what's on it, what's wrong; then the last message."""
        style = self.look.style
        pos = self.cursor
        lines = [f"[{pos[0]},{pos[1]}] {TILE_WORDS[rooms.tile(location, pos)]}"]
        placed = rooms.placement_at(location, pos)
        person = rooms.characters_at(self.pack, location["id"]).get(pos)
        if placed is not None:
            lines[0] += f" · {rooms.name(self.pack, placed)}"
            lines.append(style.role(placed.get("id", ""), "quiet"))
            dest, entry = rooms.exit_target(placed)
            if dest:
                lines.append(f"→ {rooms.location_name(self.pack, dest)}" + (style.role(f" ({entry})", "quiet") if entry else ""))
            if location.get("entry") == placed.get("id"):
                lines.append("Arrivals appear here.")
            for problem in rooms.problems(self.pack, location, pos):
                lines += [style.role(line, "danger") for line in screen.wrap(problem, width)]
        if person is not None:
            lines.append(f"{person.get('name', person['id'])} stands here " + style.role("(characters.json)", "quiet"))
        text, role = self.message
        if text:
            lines += [style.role(line, role) for line in screen.wrap(text, width)]
        return [line if len(line) <= width or "\x1b" in line else line[:width] for line in lines]

    def hints(self) -> List[str]:
        back = self.look.key("back")
        if self.picking:
            return ["←↑↓→ move", "Enter pick this tile", f"{back} cancel"]
        if self.carrying is not None:
            return ["←↑↓→ move", "Enter put it here", f"{back} cancel"]
        return ["←↑↓→ move", "Enter actions", f"{back} back"]

    # --- what can be done ----------------------------------------------------------

    def actions(self) -> List[tuple]:
        """(letter, label, function) for the tile under the cursor: only what works here."""
        location, pos = self.location, self.cursor
        here = rooms.tile(location, pos)
        placed = rooms.placement_at(location, pos)
        person = rooms.characters_at(self.pack, location["id"]).get(pos)
        side = rooms.side_of(location, pos)
        found = []
        if placed is None and person is None and here != " ":
            found.append(("p", "Place an object here", self.start_place))
        if placed is not None:
            dest, _ = rooms.exit_target(placed)
            if dest and rooms.partner(self.pack, placed):
                found.append(("g", f"Go to {rooms.location_name(self.pack, dest)}", self.go))
            if len(rooms.edge_group(location, placed)) == 1:
                found.append(("m", "Move it", self.start_move))
            found.append(("r", "Remove it", self.start_remove))
            if location.get("entry") == placed.get("id"):
                found.append(("e", "Arrivals: back to the centre", self.toggle_entry))
            else:
                found.append(("e", "Arrivals appear here", self.toggle_entry))
        if placed is None and side is not None and here == "#":
            found.append(("l", "Door to another location", self.start_door))
        if side is not None and not any(tuple(p["at"]) in set(rooms.side_tiles(location, side))
                                        for p in location.get("placements", [])):
            found.append(("o", f"Open the {side} side to…", self.start_edge))
        for kind in ("#", ".", " "):
            if kind == here or (person is not None and kind != "."):
                continue                                   # people stand on floor
            if kind == " " and placed is not None:
                continue
            found.append(("t" if kind == rooms.toggled(here) else "", f"Make it {TILE_WORDS[kind]}",
                          lambda kind=kind: self.set_tile(kind)))
        found.append(("c", "Colour…", self.start_colour))
        found.append(("z", "Room size…", self.start_size))
        if self.pack.dirty:
            found.append(("", "Save changes", self.save))
        return found

    def handle(self, key: str) -> bool:
        keep = self._handle(key)
        return keep and not self.closed

    def _handle(self, key: str) -> bool:
        if self.form is not None:
            result = self.form.handle(key)
            if result is forms.CANCEL:
                self.form = None
                if self.found is None:                     # the location list: leave the tool
                    return False
            elif result is not None:
                self.form, after = None, self.after
                after(result)
            return True
        action = self.look.action(key)
        if self.picking:
            return self.handle_pick(key, action)
        if action in MOVES:
            self.step(action)
        elif self.carrying is not None:
            if key == "enter":
                self.put_down()
            elif action in ("back", "quit"):
                self.carrying = None
                self.say("")
        elif action in ("back", "quit"):
            self.leave()
        elif key == "enter":
            choices = [forms.Choice(label, fn, letter.upper()) for letter, label, fn in self.actions()]
            self.ask(forms.Picker(self.look, "Actions", choices), lambda fn: fn())
        else:
            for letter, _, fn in self.actions():
                if letter and key.lower() == letter:
                    fn()
                    break
        return True

    def step(self, action: str) -> None:
        location = self.picking[0].entry if self.picking else self.location
        row, col = self.cursor[0] + MOVES[action][0], self.cursor[1] + MOVES[action][1]
        if rooms.inside(location, (row, col)):
            self.cursor = (row, col)
            self.say("")

    # --- placing and moving -------------------------------------------------------

    def object_choices(self) -> List[forms.Choice]:
        return [forms.Choice(f"{f.entry.get('glyph', '?')} {f.entry.get('name', f.entry['id'])}", f.entry["id"],
                             f.entry["id"], f.entry.get("description", "")) for f in self.pack.entries("objects")]

    def start_place(self) -> None:
        def done(object_id):
            placed = rooms.place(self.pack, self.found, object_id, self.cursor)
            self.last_object = object_id
            self.say(f"Placed {placed['id']}.")
        self.ask(forms.Picker(self.look, "Place which object?", self.object_choices(), self.last_object), done)

    def start_move(self) -> None:
        self.carrying = rooms.placement_at(self.location, self.cursor)
        self.say(f"Moving {rooms.name(self.pack, self.carrying)}.")

    def put_down(self) -> None:
        pos = self.cursor
        blocked = rooms.placement_at(self.location, pos)
        if blocked is not None and blocked is not self.carrying:
            return self.say("Something is already there.", "danger")
        if pos in rooms.characters_at(self.pack, self.location["id"]):
            return self.say("Someone stands there.", "danger")
        if rooms.tile(self.location, pos) == " ":
            return self.say("There's nothing to stand on there.", "danger")
        rooms.move(self.pack, self.found, self.carrying, pos)
        self.say(f"Moved {self.carrying['id']}.")
        self.carrying = None

    def start_remove(self) -> None:
        placed = rooms.placement_at(self.location, self.cursor)
        group = rooms.edge_group(self.location, placed)
        others = [rooms.partner(self.pack, p) for p in group]
        others = [o for o in others if o is not None]
        gone = group + [p for _, p in others]
        affected = [self.found] + [f for f, _ in others]
        own_entries = {f"{f.file}: entries[{i}].entry" for f in affected
                       for i, e in enumerate(self.pack.data[f.file]["entries"]) if e is f.entry}
        used = [use for p in gone for use in rooms.uses(self.pack, p["id"], skip=gone) if use not in own_entries]
        if used:
            files = sorted({use.split(":")[0] for use in used})
            return self.say(f"Not removed: still used in {', '.join(files)}.", "danger")
        if len(group) > 1:
            what = f"this open edge ({len(group)} tiles)"
        else:
            what = rooms.name(self.pack, placed)
        where = f" and the other side in {rooms.location_name(self.pack, others[0][0].entry['id'])}" if others else ""

        def done(_):
            rooms.remove(self.pack, self.found, group)
            for other_found in {id(f): f for f, _ in others}.values():
                rooms.remove(self.pack, other_found, [p for f, p in others if f is other_found])
            self.say(f"Removed {what}{where}.")
        self.ask(forms.Question(self.look, f"Remove {what}{where}?", [("y", "remove", True)]), done)

    def toggle_entry(self) -> None:
        placed = rooms.placement_at(self.location, self.cursor)
        clear = self.location.get("entry") == placed.get("id")
        rooms.set_entry(self.pack, self.found, None if clear else placed)
        self.say("Arrivals appear in the centre." if clear else f"Arrivals appear at {placed['id']}.")

    def start_colour(self) -> None:
        """Colours what's under the cursor: a person, this placement or every one of its object, or the room's walls or floor."""
        location, pos = self.location, self.cursor
        placed = rooms.placement_at(location, pos)
        person = next((f for f in self.pack.entries("characters") if f.entry.get("location") == location["id"]
                       and isinstance(f.entry.get("at"), list) and tuple(f.entry["at"]) == pos), None)
        targets = []                                   # (label, entry, file, field)
        if person is not None:
            targets.append((person.entry.get("name", person.entry["id"]), person.entry, person.file, "colour"))
        elif placed is not None:
            name = rooms.name(self.pack, placed)
            targets.append((f"This {name}", placed, self.found.file, "colour"))
            template = self.pack.find("objects", placed.get("object", ""))
            if template is not None:
                targets.append((f"Every {template.entry.get('name', template.entry['id'])}", template.entry,
                                template.file, "colour"))
        else:
            wall = rooms.tile(location, pos) == "#"
            targets.append(("The walls here" if wall else "The floor here", location["grid"], self.found.file,
                            "wall_colour" if wall else "floor_colour"))

        def colour(target):
            label, entry, file, field = target

            def done(chosen):
                if chosen is colours.DEFAULT:
                    entry.pop(field, None)
                else:
                    entry[field] = chosen
                self.pack.touch(file)
                self.say(f"{label}: {'the default colour' if chosen is colours.DEFAULT else chosen}.")
            colours.choose(self, f"Colour: {label}", done, entry.get(field), default="Default (the UI pack's)")
        if len(targets) == 1:
            return colour(targets[0])
        self.ask(forms.Picker(self.look, "Colour what?", [forms.Choice(t[0], t) for t in targets]), colour)

    def set_tile(self, kind: str) -> None:
        rooms.set_tile(self.pack, self.found, self.cursor, kind)
        self.say("")

    def start_size(self) -> None:
        width, height = rooms.size(self.location)

        def check(text):
            parts = text.lower().replace("×", "x").split("x")
            if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
                return "Write it as width x height, e.g. 7x7."
            w, h = (int(p) for p in parts)
            if not (3 <= w <= 12 and 3 <= h <= 10):
                return "3 to 12 tiles across, 3 to 10 down."
            return rooms.resize(self.pack, self.found, w, h) or ""

        def done(_):
            w, h = rooms.size(self.location)
            self.cursor = (min(self.cursor[0], h - 1), min(self.cursor[1], w - 1))
            self.say(f"The room is now {w}×{h}.")
        self.ask(forms.Field(self.look, "Size (width x height)", f"{width}x{height}", check,
                             "3 to 12 tiles across, 3 to 10 down. A custom shape keeps its top-left part."), done)

    def go(self) -> None:
        placed = rooms.placement_at(self.location, self.cursor)
        other_found, other = rooms.partner(self.pack, placed)
        self.found = other_found
        self.cursor = tuple(other["at"])
        self.say(f"In {self.location.get('name', '')}.")

    # --- doors and edges ----------------------------------------------------------

    def exit_object(self) -> Optional[str]:
        """The object to suggest for a way out: the last one used, or the pack's most common exit."""
        return self.last_object or rooms.common_exit_object(self.pack)

    def other_locations(self) -> List[forms.Choice]:
        return [forms.Choice(f.entry.get("name", f.entry["id"]), f.entry["id"], f"{rooms.size(f.entry)[0]}×{rooms.size(f.entry)[1]}",
                             f.entry.get("description", ""))
                for f in self.pack.entries("locations")
                if f.entry["id"] != self.location["id"] and not f.entry.get("template")]

    def start_door(self) -> None:
        home, side = self.cursor, rooms.side_of(self.location, self.cursor)

        def to_location(object_id):
            self.last_object = object_id
            self.ask(forms.Picker(self.look, "Door to which location?", self.other_locations()),
                     lambda location_id: pick_tile(object_id, location_id))

        def pick_tile(object_id, location_id):
            other = self.pack.find("locations", location_id)
            width, height = rooms.size(other.entry)
            start = rooms.free_wall_tile(other.entry, rooms.OPPOSITE[side]) or (0, width // 2)
            self.picking = (other, home, lambda pos: make(object_id, other, pos))
            self.cursor = start
            self.say("Pick the other side's tile.")

        def make(object_id, other, pos):
            a, b = rooms.link_door(self.pack, self.found, home, other, pos, object_id)
            self.say(f"Door made: {a['id']} ↔ {b['id']}.")
        self.ask(forms.Picker(self.look, "Door: which object?", self.object_choices(), self.exit_object()), to_location)

    def handle_pick(self, key: str, action: str) -> bool:
        other, home, then = self.picking
        if action in MOVES:
            self.step(action)
        elif action in ("back", "quit"):
            self.picking, self.cursor = None, home
            self.say("No door made.")
        elif key == "enter":
            pos = self.cursor
            if rooms.placement_at(other.entry, pos) is not None:
                self.say("Something is already there.", "danger")
            elif pos in rooms.characters_at(self.pack, other.entry["id"]):
                self.say("Someone stands there.", "danger")
            elif rooms.tile(other.entry, pos) == " ":
                self.say("There's nothing to stand on there.", "danger")
            else:
                self.picking, self.cursor = None, home
                then(pos)
        return True

    def start_edge(self) -> None:
        side = rooms.side_of(self.location, self.cursor)

        def to_location(object_id):
            self.last_object = object_id
            self.ask(forms.Picker(self.look, f"Open the {side} side to which location?", self.other_locations()),
                     lambda location_id: make(object_id, location_id))

        def make(object_id, location_id):
            other = self.pack.find("locations", location_id)
            problem = rooms.edge_problem(self.location, side, other.entry)
            if problem:
                return self.say(problem, "danger")
            made = rooms.open_edge(self.pack, self.found, side, other, object_id)
            self.say(f"The {side} side opens to {other.entry.get('name', '')}: {len(made) // 2} tiles each side.")
        self.ask(forms.Picker(self.look, "Open edge: which object for its tiles?", self.object_choices(),
                              self.exit_object()), to_location)

    # --- leaving ------------------------------------------------------------------

    def leave(self) -> None:
        if not self.pack.dirty or self.single:         # opened by another tool: that tool asks
            return self.finish()

        def done(answer):
            if answer == "save":
                self.save(back=True)
            else:
                self.pack.reload()
                self.finish("Changes discarded.")
        self.ask(forms.Question(self.look, "Save your changes?", [("y", "save", "save"), ("n", "discard", "discard")]),
                 done)

    def finish(self, notice: str = "") -> None:
        """Out of the room: back to the location list, or to the tool that opened it."""
        self.notice = notice
        if self.single:
            self.closed = True
        else:
            self.choose_location(notice)

    def save(self, back: bool = False) -> None:
        def write():
            written = self.pack.save()
            report = self.pack.check()
            verdict = f"Saved {len(written)} file(s). Checker: {len(report.errors)} error(s), {len(report.warnings)} warning(s)."
            if report.errors:
                verdict += " " + report.errors[0]
            if back:
                self.finish(verdict)
            else:
                self.say(verdict, "danger" if report.errors else "quiet")
        save_safely(self, write)


if __name__ == "__main__":
    sys.exit(run_tool(Room, sys.argv[1:]))
