"""
The world as a graph, for the map editor: regions and locations at their 'map' x/y,
the exits between them, and colour schemes that sort locations into kinds.

A colour scheme is a name and a function from a location to one of its statuses.
Each status has a palette colour, a mark (drawn instead of the colour when there is
none) and a few words. Add a scheme to SCHEMES and the map offers it.
"""
from collections import deque
from typing import Callable, Dict, List, NamedTuple, Optional, Set, Tuple

from tools.lib import rooms
from tools.lib.packfiles import PackFiles

Cell = Tuple[int, int]                      # (x, y) on a region's map


class Status(NamedTuple):
    key: str
    colour: Optional[str]                   # a palette colour; None for the plain look
    mark: str                               # the node's glyph without colour ('' keeps the usual one)
    word: str                               # in the legend
    about: str = ""                         # in the detail band


class Facts(NamedTuple):
    """What the schemes look at, worked out once per change."""
    exits: Dict[str, List[Tuple[dict, str]]]  # location -> its exit placements and where each leads
    reached: Set[str]                         # locations the start leads to
    hazards: Set[str]                         # tag ids marked as hazards
    checker: Dict[str, List[str]]             # location -> the checker's errors about it (as last saved)
    start: Optional[str]


def facts(pack: PackFiles, checker_errors=()) -> Facts:
    exits = {f.entry["id"]: list(rooms.links(pack, f.entry)) for f in pack.entries("locations")}
    start = pack.manifest.get("start", {}).get("location")
    reached, queue = set(), deque([start] if start else [])
    while queue:
        here = queue.popleft()
        if here in reached or here not in exits:
            continue
        reached.add(here)
        queue.extend(dest for _, dest in exits[here])
    hazards = {t["id"] for rel in pack.kinds.get("vocab", []) for t in pack.data[rel].get("tags", [])
               if isinstance(t, dict) and t.get("hazard")}
    labels = {}
    for f in pack.entries("locations"):
        index = pack.data[f.file]["entries"].index(f.entry)
        labels[f"{f.file}: entries[{index}]"] = f.entry["id"]
    checker: Dict[str, List[str]] = {}
    for error in checker_errors:
        for label, location_id in labels.items():
            if error.startswith(label + ".") or error.startswith(label + ":"):
                checker.setdefault(location_id, []).append(error)
    return Facts(exits, reached, hazards, checker, start)


def problems(pack: PackFiles, found: Facts, location: dict) -> List[str]:
    """What's wrong with a location, in plain words."""
    out = []
    for p in location.get("placements", []):
        for problem in rooms.problems(pack, location, tuple(p.get("at", (0, 0)))):
            out.append(f"{rooms.name(pack, p)}: {problem}")
    for p, dest_id in found.exits.get(location["id"], []):      # exits to a default entry: anything back?
        if dest_id in found.exits and not rooms.exit_target(p)[1] \
                and not any(back == location["id"] for _, back in found.exits[dest_id]):
            out.append(f"One way: {rooms.location_name(pack, dest_id)} doesn't lead back.")
    return sorted(set(out)) + found.checker.get(location["id"], [])


# --- colour schemes ------------------------------------------------------------------

VALIDITY = (
    Status("problem", "orange", "!", "problem", "Something here needs fixing."),
    Status("cut_off", "grey", "?", "cut off", "The start doesn't lead here."),
    Status("hazard", "yellow", "^", "hazard", "A hazard here."),
    Status("start", "green", "@", "start", "The game starts here."),
    Status("plain", None, "", "", ""),
)


def validity(pack: PackFiles, found: Facts, location: dict) -> str:
    if problems(pack, found, location):
        return "problem"
    if location["id"] not in found.reached:
        return "cut_off"
    if set(location.get("tags", [])) & found.hazards:
        return "hazard"
    if location["id"] == found.start:
        return "start"
    return "plain"


class Scheme(NamedTuple):
    name: str
    statuses: Tuple[Status, ...]          # in order of importance: a region shows its most important
    classify: Callable[[PackFiles, Facts, dict], str]

    def status(self, key: str) -> Status:
        return next(s for s in self.statuses if s.key == key)

    def worst(self, keys) -> str:
        """The most important of several statuses (for a region's node)."""
        order = [s.key for s in self.statuses]
        return min(keys, key=order.index) if keys else self.statuses[-1].key


SCHEMES = (Scheme("Validity", VALIDITY, validity),)


# --- regions and their maps ----------------------------------------------------------
# Each region is its own map: its locations at their x/y. Regions aren't drawn inside
# one another; the editor switches between them from a list, or by following exits.

def parent_of(pack: PackFiles, region_id: str) -> Optional[str]:
    found = pack.find("regions", region_id)
    return found.entry.get("parent") if found else None


def depth(pack: PackFiles, region_id: str) -> int:
    """How deep a region sits under parents (0 at the top), for indenting the list."""
    seen, current, n = set(), parent_of(pack, region_id), 0
    while current is not None and current not in seen:
        seen.add(current)
        current, n = parent_of(pack, current), n + 1
    return n


def members(pack: PackFiles, region_id: str) -> List[dict]:
    """A region's own locations (not its sub-regions'), templates aside."""
    return [f.entry for f in pack.entries("locations")
            if f.entry.get("region") == region_id and not f.entry.get("template")]


def nodes(pack: PackFiles, region_id: str) -> Dict[Cell, List[Tuple[str, dict]]]:
    """A region's placed locations, by cell: ('location', entry)."""
    found: Dict[Cell, List[Tuple[str, dict]]] = {}
    for entry in members(pack, region_id):
        if isinstance(entry.get("map"), dict):
            cell = (entry["map"].get("x", 0), entry["map"].get("y", 0))
            found.setdefault(cell, []).append(("location", entry))
    return found


def unplaced(pack: PackFiles, region_id: str) -> List[Tuple[str, dict]]:
    """A region's locations without a place on its map yet."""
    return [("location", entry) for entry in members(pack, region_id) if not isinstance(entry.get("map"), dict)]


def links(pack: PackFiles, found: Facts, region_id: str) -> Set[Tuple[Cell, Cell]]:
    """Pairs of cells on a region's map joined by an exit either way."""
    cell_of = {entry["id"]: cell for cell, here in nodes(pack, region_id).items() for _, entry in here}
    pairs = set()
    for source_id, cell in cell_of.items():
        for _, dest in found.exits.get(source_id, []):
            if dest in cell_of and cell_of[dest] != cell:
                pairs.add(tuple(sorted((cell, cell_of[dest]))))
    return pairs


def region_status(pack: PackFiles, found: Facts, scheme: Scheme, region_id: str) -> str:
    """The most important status among a region's own locations (all cut off: cut off)."""
    keys = {scheme.classify(pack, found, entry) for entry in members(pack, region_id)}
    if keys and keys <= {"cut_off"}:
        return "cut_off"
    return scheme.worst(keys - {"cut_off"})
