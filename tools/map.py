"""
The map editor: one region's map at a time. Each region is its own coordinate
system: its locations are glyphs at their 'map' x/y, and exits between neighbours
are drawn as lines. Switch regions from the region list, or by following an exit.
A colour scheme sorts the locations (Validity: problems, cut off from the start,
hazards, the start).

Enter lists what can be done on the cell under the cursor: edit the room, follow an
exit into the region it leads to, link to a neighbour (a door, or an open edge when
the sides match), move it, make a new location, or place one that has no position
yet. X goes back along the exits followed, then to the region list, and leaves from
there.

  python3 -m tools.map packs/test     on its own
  python3 editor.py                   from the editor's menu
"""
import re
import sys
from collections import Counter
from typing import Callable, Dict, List, Optional, Tuple

from lib import graph
from tools.lib import forms, maps, rooms, screen, term
from tools.lib.packfiles import PackFiles
from tools.room import Room

Cell = Tuple[int, int]
MOVES = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
SIDE_OF_STEP = {(0, -1): "north", (0, 1): "south", (-1, 0): "west", (1, 0): "east"}
NODE = "■"
NEW = object()                             # the region list's "New region" entry
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def cut(text: str, width: int) -> str:
    """One line, cut with '…' when longer than the width."""
    return text if len(text) <= width else text[:width - 1] + "…"


class Map:
    name = "Map"
    about = "The world by region: where locations lie, how they connect, and what needs fixing."

    def __init__(self, pack: PackFiles, look: screen.Look):
        self.pack, self.look = pack, look
        self.scheme = maps.SCHEMES[0]
        self.errors = pack.check().errors
        start = pack.find("locations", pack.manifest.get("start", {}).get("location", ""))
        self.region: Optional[str] = None           # None: the region list
        self.cursor: Cell = (0, 0)
        self.view: Cell = (0, 0)
        self.form = None
        self.after: Optional[Callable] = None
        self.carrying: Optional[Tuple[str, dict]] = None
        self.room: Optional[Room] = None
        self.message: Tuple[str, str] = ("", "quiet")
        self.last_object: Optional[str] = None
        self.closed = False
        self.trail: List[Tuple[Optional[str], Cell]] = []   # where following exits came from, for X
        if start is not None and start.entry.get("region"):
            self.open_region(start.entry["region"])
        else:
            self.choose_region()

    # --- helpers --------------------------------------------------------------------

    def ask(self, form, after: Callable) -> None:
        self.form, self.after = form, after

    def say(self, text: str, role: str = "quiet") -> None:
        self.message = (text, role)

    def nodes(self) -> Dict[Cell, List[Tuple[str, dict]]]:
        return maps.nodes(self.pack, self.region)

    def home_cell(self) -> Cell:
        """Where the cursor starts in a region: the start location, or the first thing on the map."""
        found = self.nodes()
        start = self.pack.manifest.get("start", {}).get("location")
        for cell, here in found.items():
            if any(entry["id"] == start for _, entry in here):
                return cell
        return min(found, key=lambda c: (c[1], c[0])) if found else (0, 0)

    def region_name(self) -> str:
        found = self.pack.find("regions", self.region) if self.region else None
        return found.entry.get("name", self.region) if found else ""

    def open_region(self, region_id: str) -> None:
        self.region, self.view = region_id, (0, 0)
        self.cursor = self.home_cell()

    def choose_region(self) -> None:
        """The list of regions, nested ones indented under their parents; then New region."""
        facts = maps.facts(self.pack, self.errors)
        ordered, by_parent = [], {}
        for f in self.pack.entries("regions"):
            by_parent.setdefault(f.entry.get("parent"), []).append(f.entry)
        known = {f.entry["id"] for f in self.pack.entries("regions")}

        def add(parent):
            for entry in by_parent.get(parent, []):
                ordered.append(entry)
                add(entry["id"])
        add(None)
        ordered += [e for parent, es in by_parent.items() if parent is not None and parent not in known for e in es]
        choices = []
        for entry in ordered:
            count = len(maps.members(self.pack, entry["id"]))
            status = self.scheme.status(maps.region_status(self.pack, facts, self.scheme, entry["id"]))
            about = " ".join(filter(None, [status.about, entry.get("description", "")]))
            label = "  " * maps.depth(self.pack, entry["id"]) + entry.get("name", entry["id"])
            mark = f" {status.mark}" if status.mark and not self.look.style.colour else ""
            if self.look.style.colour and status.colour:
                label = self.look.style.colour_of(label, status.colour)
            choices.append(forms.Choice(label + mark, entry["id"], f"{count} locations", about))
        if "regions" in self.pack.kinds:
            choices.append(forms.Choice("New region…", NEW))
        came_from, self.region = self.region, None
        picker = forms.Picker(self.look, "Map · regions", choices, came_from)
        picker.regions = True
        self.ask(picker, lambda picked: self.start_new("region") if picked is NEW else self.open_region(picked))

    def at_cursor(self) -> Optional[Tuple[str, dict]]:
        here = self.nodes().get(self.cursor)
        return here[0] if here else None

    def status_of(self, facts: maps.Facts, entry: dict) -> maps.Status:
        return self.scheme.status(self.scheme.classify(self.pack, facts, entry))

    def extent(self) -> Cell:
        """The last cell the cursor may reach: one past everything placed."""
        cells = list(self.nodes()) or [(0, 0)]
        return max(c[0] for c in cells) + 1, max(c[1] for c in cells) + 1

    # --- drawing --------------------------------------------------------------------

    def render(self, columns: int, rows: int) -> str:
        if self.room is not None:
            return self.room.render(columns, rows)
        look, width = self.look, screen.inner_width(self.look, columns)
        title = screen.title(look, f"Map · {self.region_name()}",
                             self.pack.manifest.get("name", self.pack.id) + (" *" if self.pack.dirty else ""), width)
        if self.form is not None:
            heading = getattr(self.form, "title", "") or f"Map · {self.region_name()}"
            lines, focus = self.form.lines(width)
            about = screen.wrap(self.form.about(), width)[:3] if self.form.about() else []
            bands = [screen.title(look, heading, "", width), lines,
                     [look.style.role(line, "quiet") for line in about], screen.hints(look, self.form.hints(), width)]
            return screen.draw(look, [b for b in bands if b], columns, rows, flex=1, focus=focus).text
        facts = maps.facts(self.pack, self.errors)
        others = [self.detail(facts, width), self.legend(facts, width), screen.hints(look, self.hints(), width)]
        others = [b for b in others if b]
        body_rows = max(2, rows - len(title) - sum(len(b) for b in others) - (len(others) + 2) - 1)
        body = self.grid(facts, width, body_rows)
        return screen.draw(look, [title, body] + others, columns, rows).text

    def grid(self, facts: maps.Facts, width: int, height: int) -> List[str]:
        style = self.look.style
        found = self.nodes()
        across, down = graph.fit(width, height)
        self.view = graph.origin(self.cursor, self.view, across, down)
        glyphs = {}
        for x in range(self.view[0], self.view[0] + across):
            for y in range(self.view[1], self.view[1] + down):
                glyph = self.cell_glyph(facts, found.get((x, y)))
                glyphs[(x, y)] = style.inverse(screen.strip(glyph)) if (x, y) == self.cursor else glyph
        lines = graph.draw(glyphs, maps.links(self.pack, facts, self.region), self.view, across, down, self.extent())
        return lines[:height]

    def cell_glyph(self, facts: maps.Facts, here) -> str:
        style = self.look.style
        if self.carrying is not None and here and here[0][1] is self.carrying[1]:
            here = None
        if not here:
            return style.role("·", "quiet")
        status = self.status_of(facts, here[0][1])
        if len(here) > 1:
            return style.colour_of("‼", "orange") if style.colour else "‼"
        if not style.colour:                       # marks stand in for colours
            return status.mark or NODE
        return style.colour_of(NODE, status.colour) if status.colour else NODE

    def detail(self, facts: maps.Facts, width: int) -> List[str]:
        """The cell under the cursor: what's there, its status, what's wrong, where it leads."""
        style = self.look.style
        lines: List[str] = []
        here = self.nodes().get(self.cursor, [])
        if self.carrying is not None:
            lines.append(f"Moving {self.carrying[1].get('name', self.carrying[1]['id'])}.")
        elif not here:
            lines.append(style.role(f"[{self.cursor[0]},{self.cursor[1]}] empty", "quiet"))
        else:
            entry = here[0][1]
            status = self.status_of(facts, entry)
            width_, height_ = rooms.size(entry)
            lines.append(entry.get("name", entry["id"]) + style.role(f" · {width_}×{height_}", "quiet"))
            if len(here) > 1:
                lines.append(style.role(f"{len(here)} locations share this cell.", "danger"))
            if status.about:
                lines.append(style.colour_of(status.about, status.colour) if status.colour else status.about)
            problems = maps.problems(self.pack, facts, entry)
            if problems:
                more = f" (+{len(problems) - 1} more)" if len(problems) > 1 else ""
                lines.append(style.role(cut(problems[0] + more, width), "danger"))
            lines.append(style.role(cut(self.exits_words(facts, entry), width), "quiet"))
        text, role = self.message
        if text:
            said = screen.wrap(text, width)
            lines += [style.role(line, role) for line in said[:1] + ([cut(" ".join(said[1:]), width)] if said[1:] else [])]
        return lines[:5]

    def exits_words(self, facts: maps.Facts, location: dict) -> str:
        counts = Counter(dest for _, dest in facts.exits.get(location["id"], []))
        if not counts:
            return "No exits."
        names = []
        for dest, n in counts.items():
            other = self.pack.find("locations", dest)
            region = other.entry.get("region") if other else None
            elsewhere = region != location.get("region") and other is not None
            where = self.pack.find("regions", region) if elsewhere else None
            names.append(rooms.location_name(self.pack, dest) + (" (edge)" if n > 1 else "")
                         + (f" in {where.entry.get('name', region)}" if where else ""))
        return "Exits: " + ", ".join(names)

    def legend(self, facts: maps.Facts, width: int) -> List[str]:
        """The scheme's colours that appear on this map."""
        shown = {self.status_of(facts, entry).key for here in self.nodes().values() for _, entry in here}
        style, parts = self.look.style, []
        for status in self.scheme.statuses:
            if status.key in shown and status.word:
                sample = style.colour_of("■", status.colour) if style.colour else status.mark
                parts.append(sample + style.role(f" {status.word}", "quiet"))
        return screen.hints(self.look, parts, width, styled=False) if parts else []

    def hints(self) -> List[str]:
        back = self.look.key("back")
        if self.carrying is not None:
            return ["←↑↓→ move", "Enter put it here", f"{back} cancel"]
        return ["←↑↓→ move", "Enter actions", f"{back} " + ("back" if self.trail else "regions")]

    # --- keys -----------------------------------------------------------------------

    def actions(self) -> List[tuple]:
        here = self.at_cursor()
        found = []
        if here is None:
            found.append(("n", "New location here", self.start_new))
            if maps.unplaced(self.pack, self.region):
                found.append(("p", "Place one here…", self.start_place))
        else:
            found.append(("e", "Edit the room", self.edit_room))
            if self.exit_choices():
                found.append(("g", "Follow an exit…", self.start_follow))
            if self.neighbours():
                found.append(("l", "Link to a neighbour…", self.start_link))
            found.append(("m", "Move it", self.start_move))
        if len(maps.SCHEMES) > 1:
            found.append(("c", f"Colours: {self.scheme.name}", self.next_scheme))
        if self.pack.dirty:
            found.append(("", "Save changes", self.save))
        return found

    def handle(self, key: str) -> bool:
        if self.room is not None:
            if not self.room.handle(key):
                self.say(self.room.notice)
                if not self.pack.dirty:
                    self.errors = self.pack.check().errors
                self.room = None
            return True
        if self.form is not None:
            result = self.form.handle(key)
            if result is forms.CANCEL:
                listing, self.form = getattr(self.form, "regions", False), None
                if listing:                               # Esc on the region list: leave
                    self.leave()
                elif self.region is None:                 # a new region given up: back to the list
                    self.choose_region()
            elif result is not None:
                self.form, after = None, self.after
                after(result)
            return not self.closed
        action = self.look.action(key)
        if action in MOVES:
            step = MOVES[action]
            last = self.extent()
            self.cursor = (min(max(0, self.cursor[0] + step[0]), last[0]),
                           min(max(0, self.cursor[1] + step[1]), last[1]))
            self.say("")
        elif self.carrying is not None:
            if key == "enter":
                self.put_down()
            elif action in ("back", "quit"):
                self.carrying = None
                self.say("")
        elif action in ("back", "quit"):
            self.go_up()
        elif key == "enter":
            choices = [forms.Choice(label, fn, letter.upper()) for letter, label, fn in self.actions()]
            self.ask(forms.Picker(self.look, "Actions", choices), lambda fn: fn())
        else:
            for letter, _, fn in self.actions():
                if letter and key.lower() == letter:
                    fn()
                    break
        return not self.closed

    # --- moving around -------------------------------------------------------------

    def exit_choices(self) -> List[forms.Choice]:
        """The places the location under the cursor leads to, each once, with their region."""
        here = self.at_cursor()[1]
        seen, out = set(), []
        for _, dest in rooms.links(self.pack, here):
            other = self.pack.find("locations", dest)
            if other is None or dest in seen or dest == here["id"]:
                continue
            seen.add(dest)
            region = self.pack.find("regions", other.entry.get("region", ""))
            where = region.entry.get("name", "") if region else ""
            out.append(forms.Choice(other.entry.get("name", dest), dest, where, other.entry.get("description", "")))
        return out

    def start_follow(self) -> None:
        choices = self.exit_choices()
        if len(choices) == 1:
            return self.follow(choices[0].value)
        self.ask(forms.Picker(self.look, "Follow which exit?", choices), self.follow)

    def follow(self, location_id: str) -> None:
        """The map of the region an exit leads into, with the cursor on where it arrives."""
        other = self.pack.find("locations", location_id).entry
        self.trail.append((self.region, self.cursor))
        self.region, self.view = other.get("region"), (0, 0)
        place = other.get("map")
        if isinstance(place, dict):
            self.cursor = (place.get("x", 0), place.get("y", 0))
            self.say("")
        else:
            self.cursor = self.home_cell()
            self.say(f"{other.get('name', location_id)} has no place on this map yet: P places it.")

    def go_up(self) -> None:
        """Back along the exits followed; then the region list."""
        if self.trail:
            self.region, self.cursor = self.trail.pop()
            self.view = (0, 0)
            return self.say("")
        self.say("")
        self.choose_region()

    def edit_room(self) -> None:
        self.room = Room(self.pack, self.look, self.at_cursor()[1]["id"], single=True)

    def next_scheme(self) -> None:
        index = maps.SCHEMES.index(self.scheme)
        self.scheme = maps.SCHEMES[(index + 1) % len(maps.SCHEMES)]

    # --- placing ------------------------------------------------------------------

    def file_of(self, kind: str, entry: dict) -> str:
        return self.pack.find("locations", entry["id"]).file

    def set_cell(self, kind: str, entry: dict, cell: Cell) -> None:
        entry["map"] = {"x": cell[0], "y": cell[1]}
        self.pack.touch(self.file_of(kind, entry))

    def start_move(self) -> None:
        self.carrying = self.at_cursor()

    def put_down(self) -> None:
        if self.nodes().get(self.cursor) and self.nodes()[self.cursor][0][1] is not self.carrying[1]:
            return self.say("Something is already there.", "danger")
        kind, entry = self.carrying
        self.set_cell(kind, entry, self.cursor)
        self.carrying = None
        self.say(f"Moved {entry.get('name', entry['id'])}.")

    def start_place(self) -> None:
        choices = [forms.Choice(entry.get("name", entry["id"]), (kind, entry), entry["id"], entry.get("description", ""))
                   for kind, entry in maps.unplaced(self.pack, self.region)]

        def done(picked):
            self.set_cell(*picked, self.cursor)
            self.say(f"Placed {picked[1].get('name', picked[1]['id'])}.")
        self.ask(forms.Picker(self.look, "Place which?", choices), done)

    def start_new(self, kind: str = "location") -> None:
        namespace, prefix = ("regions", "reg_") if kind == "region" else ("locations", "loc_")
        taken = {f.entry["id"] for f in self.pack.entries(namespace)}

        def check_name(text):
            return "" if 0 < len(text.strip()) <= 32 else "A name, at most 32 characters."

        def check_id(text):
            if not ID_PATTERN.match(text):
                return "Lower case letters, digits and _, starting with a letter."
            return "That id is taken." if text in taken else ""

        def named(name):
            suggested = prefix + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
            make = self.create_region if kind == "region" else self.create
            self.ask(forms.Field(self.look, "Id", suggested, check_id, "Ids can't change later without care."),
                     lambda new_id: make(name.strip(), new_id))
        self.ask(forms.Field(self.look, f"Name of the new {kind}", "", check_name), named)

    def create_region(self, name: str, new_id: str) -> None:
        self.pack.add("regions", {"id": new_id, "name": name})
        self.open_region(new_id)
        self.say(f"Made {new_id}. N makes its first location.")

    def create(self, name: str, new_id: str) -> None:
        siblings = [f for f in self.pack.entries("locations") if f.entry.get("region") == self.region]
        every = list(self.pack.entries("locations"))
        sizes = Counter(rooms.size(f.entry) for f in siblings)
        width, height = sizes.most_common(1)[0][0] if sizes else (7, 7)
        floors = Counter(f.entry["grid"].get("floor") for f in every)
        walls = Counter(f.entry["grid"].get("wall") for f in every)
        entry = {"id": new_id, "name": name, "region": self.region,
                 "grid": {"width": width, "height": height,
                          "floor": floors.most_common(1)[0][0] if floors else ".",
                          "wall": walls.most_common(1)[0][0] if walls else "#"},
                 "map": {"x": self.cursor[0], "y": self.cursor[1]}}
        self.pack.add("locations", entry, siblings[0].file if siblings else None)
        self.say(f"Made {new_id}, {width}×{height}. Link it to its neighbours, then edit the room.")

    # --- linking ------------------------------------------------------------------

    def neighbours(self) -> List[Tuple[str, dict]]:
        """Locations in the cells next to the cursor: (side, location)."""
        found, out = self.nodes(), []
        for step, side in SIDE_OF_STEP.items():
            for kind, entry in found.get((self.cursor[0] + step[0], self.cursor[1] + step[1]), []):
                if kind == "location":
                    out.append((side, entry))
        return out

    def start_link(self) -> None:
        here = self.pack.find("locations", self.at_cursor()[1]["id"])
        choices = [forms.Choice(f"{side.title()}: {entry.get('name', entry['id'])}", (side, entry["id"]))
                   for side, entry in self.neighbours()]

        def kind_of_link(picked):
            side, other_id = picked
            other = self.pack.find("locations", other_id)
            problem = rooms.edge_problem(here.entry, side, other.entry)
            if problem:
                return pick_object(side, other, "door", note=f"(No open edge: {problem})")
            kinds = [forms.Choice("Door", "door", about="One placement on a wall tile in each, facing each other."),
                     forms.Choice("Open edge", "edge", about="The whole side opens onto the other's, tile by tile.")]
            self.ask(forms.Picker(self.look, "Which kind of link?", kinds), lambda kind: pick_object(side, other, kind))

        def pick_object(side, other, kind, note=""):
            choices = [forms.Choice(f"{f.entry.get('glyph', '?')} {f.entry.get('name', f.entry['id'])}",
                                    f.entry["id"], f.entry["id"], f.entry.get("description", ""))
                       for f in self.pack.entries("objects")]
            title = "Door: which object?" if kind == "door" else "Edge: which object for its tiles?"
            self.ask(forms.Picker(self.look, title, choices, self.last_object or rooms.common_exit_object(self.pack)),
                     lambda object_id: make(side, other, kind, object_id, note))

        def make(side, other, kind, object_id, note):
            self.last_object = object_id
            if kind == "edge":
                made = rooms.open_edge(self.pack, here, side, other, object_id)
                return self.say(f"Open edge to {other.entry.get('name', '')}: {len(made) // 2} tiles each side.")
            pos_a = rooms.free_wall_tile(here.entry, side)
            pos_b = rooms.free_wall_tile(other.entry, rooms.OPPOSITE[side])
            if pos_a is None or pos_b is None:
                full = here.entry if pos_a is None else other.entry
                return self.say(f"No free wall tile on that side of {full.get('name', '')}.", "danger")
            a, b = rooms.link_door(self.pack, here, pos_a, other, pos_b, object_id)
            self.say(f"Door made to {other.entry.get('name', '')}." + (f" {note}" if note else ""))
        self.ask(forms.Picker(self.look, "Link to which neighbour?", choices), kind_of_link)

    # --- leaving ------------------------------------------------------------------

    def leave(self) -> None:
        if not self.pack.dirty:
            self.closed = True
            return

        def done(answer):
            if answer == "save":
                self.save(then=self.close)
            else:
                self.pack.reload()
                self.close()
        self.ask(forms.Question(self.look, "Save your changes?", [("y", "save", "save"), ("n", "discard", "discard")]),
                 done)

    def close(self) -> None:
        self.closed = True

    def save(self, then: Optional[Callable[[], None]] = None) -> None:
        def write():
            written = self.pack.save()
            report = self.pack.check()
            self.errors = report.errors
            self.say(f"Saved {len(written)} file(s). Checker: {len(report.errors)} error(s), "
                     f"{len(report.warnings)} warning(s).", "danger" if report.errors else "quiet")
            if then:
                then()
        forms.save_safely(self, write)


if __name__ == "__main__":
    sys.exit(term.run_tool(Map, sys.argv[1:]))
