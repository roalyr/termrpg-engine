"""
Editing a location's layout as data: tiles, placements, doors and open edges. Works on
the plain dicts of a PackFiles and never names a pack's ids; every function that
changes a location marks its file as changed.

Tiles are '#' wall, '.' floor and ' ' nothing, as in the schema's 'rows'.

Two ways to connect locations:
- a door: one placement on a wall tile in each, each with an exit to the other;
- an open edge: every tile of a side (corners excepted) is a placement whose exit
  leads to the matching tile of the other location's opposite side. Stepping on one
  offers to go. Both sides must be the same length.
"""
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

from lib.tiles import tiles as tile_map
from tools.lib.packfiles import Found, PackFiles

Pos = Tuple[int, int]
SIDES = ("north", "east", "south", "west")
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}
STEP = {"north": (-1, 0), "south": (1, 0), "west": (0, -1), "east": (0, 1)}
PREFIXES = {"locations": "loc_", "objects": "obj_"}


# --- reading -------------------------------------------------------------------------

def size(location: dict) -> Tuple[int, int]:
    """(width, height)."""
    return location["grid"]["width"], location["grid"]["height"]


def tiles(location: dict) -> Dict[Pos, str]:
    """Every tile; a 'rows' that doesn't match the size reads as the default shape."""
    grid = location["grid"]
    found = tile_map(grid)
    return found if found is not None else tile_map({"width": grid["width"], "height": grid["height"]})


def tile(location: dict, pos: Pos) -> str:
    return tiles(location).get(tuple(pos), " ")


def inside(location: dict, pos: Pos) -> bool:
    width, height = size(location)
    return 0 <= pos[0] < height and 0 <= pos[1] < width


def placement_at(location: dict, pos: Pos) -> Optional[dict]:
    return next((p for p in location.get("placements", []) if tuple(p.get("at", ())) == tuple(pos)), None)


def characters_at(pack: PackFiles, location_id: str) -> Dict[Pos, dict]:
    """Unique characters standing in a location, by tile."""
    return {tuple(f.entry["at"]): f.entry for f in pack.entries("characters")
            if f.entry.get("location") == location_id and isinstance(f.entry.get("at"), list)}


def object_of(pack: PackFiles, placement: dict) -> dict:
    found = pack.find("objects", placement.get("object", ""))
    return found.entry if found else {}


def glyph(pack: PackFiles, placement: dict) -> str:
    return placement.get("glyph") or object_of(pack, placement).get("glyph") or "?"


def colour(pack: PackFiles, placement: dict):
    """The placement's map colour, or its object's; None leaves it to the UI pack."""
    return placement.get("colour", object_of(pack, placement).get("colour"))


def name(pack: PackFiles, placement: dict) -> str:
    return placement.get("name") or object_of(pack, placement).get("name") or placement.get("id", "?")


def location_name(pack: PackFiles, location_id: str) -> str:
    found = pack.find("locations", location_id)
    return found.entry.get("name", location_id) if found else location_id


def side_of(location: dict, pos: Pos) -> Optional[str]:
    """The side a border tile is on; None inside and on corners."""
    width, height = size(location)
    row, col = pos
    on = [s for s, hit in (("north", row == 0), ("south", row == height - 1),
                           ("west", col == 0), ("east", col == width - 1)) if hit]
    return on[0] if len(on) == 1 else None


def side_tiles(location: dict, side: str) -> List[Pos]:
    """A side's tiles in order, corners excepted."""
    width, height = size(location)
    if side in ("north", "south"):
        row = 0 if side == "north" else height - 1
        return [(row, c) for c in range(1, width - 1)]
    col = 0 if side == "west" else width - 1
    return [(r, col) for r in range(1, height - 1)]


def placement_ids(pack: PackFiles) -> set:
    return {p.get("id") for f in pack.entries("locations") for p in f.entry.get("placements", [])}


def stem(entry_id: str, kind: str) -> str:
    prefix = PREFIXES.get(kind, "")
    return entry_id[len(prefix):] if entry_id.startswith(prefix) else entry_id


def new_placement_id(pack: PackFiles, base: str, taken: Optional[set] = None) -> str:
    """'base', or 'base_2', 'base_3'… : unique across the pack."""
    taken = placement_ids(pack) if taken is None else taken
    if base not in taken:
        return base
    n = 2
    while f"{base}_{n}" in taken:
        n += 1
    return f"{base}_{n}"


def uses(pack: PackFiles, ident: str, skip: Sequence[dict] = ()) -> List[str]:
    """
    Where an id is used in the pack: 'file: path' for each use. The dicts in 'skip' (the
    entry that declares it, or placements about to be removed) are left out entirely.
    """
    found: List[str] = []
    skipped = {id(d) for d in skip}

    def walk(node, path: str, rel: str) -> None:
        if isinstance(node, dict):
            if id(node) in skipped:
                return
            for key, value in node.items():
                walk(value, f"{path}.{key}" if path else key, rel)
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{path}[{i}]", rel)
        elif node == ident:
            found.append(f"{rel}: {path}")

    walk(pack.manifest, "", "pack.json")
    for rel, data in pack.data.items():
        walk(data, "", rel)
    return found


def exit_target(placement: dict) -> Tuple[Optional[str], Optional[str]]:
    """(location, entry) an exit leads to."""
    exit_ = placement.get("exit") if isinstance(placement.get("exit"), dict) else {}
    return exit_.get("location"), exit_.get("entry")


def partner(pack: PackFiles, placement: dict) -> Optional[Tuple[Found, dict]]:
    """The placement an exit arrives at, if it leads back here: the other side of a door or edge tile."""
    _, entry = exit_target(placement)
    if not entry:
        return None
    found = pack.placement(entry)
    if found is None:
        return None
    back_location, back_entry = exit_target(found[1])
    return found if back_entry == placement.get("id") else None


def edge_group(location: dict, placement: dict) -> List[dict]:
    """The open edge a placement belongs to: the side's exits to the same place (one tile is a plain door)."""
    side = side_of(location, tuple(placement.get("at", (0, 0))))
    dest, _ = exit_target(placement)
    if side is None or dest is None:
        return [placement]
    group = [p for p in location.get("placements", [])
             if side_of(location, tuple(p.get("at", (0, 0)))) == side and exit_target(p)[0] == dest]
    return group if len(group) > 1 else [placement]


def links(pack: PackFiles, location: dict) -> Iterator[Tuple[dict, str]]:
    """Every exit placed in a location, with where it leads."""
    for p in location.get("placements", []):
        dest, _ = exit_target(p)
        zone = (p.get("exit") or {}).get("zone") if isinstance(p.get("exit"), dict) else None
        if dest or zone:
            yield p, dest or zone


def common_exit_object(pack: PackFiles) -> Optional[str]:
    """The object most often used for exits in the pack: the one to suggest for a new way out."""
    counts: Dict[str, int] = {}
    for f in pack.entries("locations"):
        for p, _ in links(pack, f.entry):
            counts[p.get("object")] = counts.get(p.get("object"), 0) + 1
    return max(counts, key=counts.get) if counts else None


def problems(pack: PackFiles, location: dict, pos: Pos) -> List[str]:
    """What's wrong on a tile, in plain words (the checker's rules, as you edit)."""
    found: List[str] = []
    here = tile(location, pos)
    placed = placement_at(location, pos)
    if placed is None:
        return found
    if here == " ":
        found.append("It stands on nothing: make this tile floor or wall.")
    if not object_of(pack, placed):
        found.append(f"Unknown object '{placed.get('object')}'.")
    dest, entry = exit_target(placed)
    if dest:
        if pack.find("locations", dest) is None:
            found.append(f"Leads to '{dest}', which doesn't exist.")
        elif entry and pack.placement(entry) is None:
            found.append(f"Arrives at '{entry}', which doesn't exist.")
        elif entry and partner(pack, placed) is None:
            found.append(f"One way: {location_name(pack, dest)} doesn't lead back here.")
    return found


# --- changing ------------------------------------------------------------------------

def default_tiles(width: int, height: int) -> Dict[Pos, str]:
    return tile_map({"width": width, "height": height})


def _write_tiles(found: Found, pack: PackFiles, shape: Dict[Pos, str]) -> None:
    grid = found.entry["grid"]
    width, height = grid["width"], grid["height"]
    if shape == default_tiles(width, height):
        grid.pop("rows", None)
    else:
        grid["rows"] = ["".join(shape[(r, c)] for c in range(width)) for r in range(height)]
    pack.touch(found.file)


def set_tile(pack: PackFiles, found: Found, pos: Pos, kind: str) -> None:
    shape = tiles(found.entry)
    shape[tuple(pos)] = kind
    _write_tiles(found, pack, shape)


def toggled(kind: str) -> str:
    """The quick change: wall and floor swap; nothing becomes floor."""
    return "." if kind != "." else "#"


def resize(pack: PackFiles, found: Found, width: int, height: int) -> Optional[str]:
    """A new size; a custom shape keeps its top-left part. Refused while something would fall outside."""
    location = found.entry
    outside = [p for p in location.get("placements", []) if not (p["at"][0] < height and p["at"][1] < width)]
    outside += [c for pos, c in characters_at(pack, location["id"]).items() if not (pos[0] < height and pos[1] < width)]
    if outside:
        names = ", ".join(e.get("name") or e.get("id", "?") for e in outside)
        return f"Move or remove first: {names}."
    old = tiles(location)
    old_width, old_height = size(location)
    fresh = default_tiles(width, height)
    custom = "rows" in location["grid"]
    location["grid"]["width"], location["grid"]["height"] = width, height
    shape = {pos: (old[pos] if custom and pos[0] < old_height - 1 and pos[1] < old_width - 1
                   and pos[0] < height - 1 and pos[1] < width - 1 else kind) for pos, kind in fresh.items()}
    _write_tiles(found, pack, shape)
    return None


def place(pack: PackFiles, found: Found, object_id: str, pos: Pos, base: Optional[str] = None) -> dict:
    """A new placement of an object; its id is the location's name and the object's: 'workshop_crate'."""
    base = base or f"{stem(found.entry['id'], 'locations')}_{stem(object_id, 'objects')}"
    placement = {"id": new_placement_id(pack, base), "object": object_id, "at": [pos[0], pos[1]]}
    found.entry.setdefault("placements", []).append(placement)
    pack.touch(found.file)
    return placement


def move(pack: PackFiles, found: Found, placement: dict, pos: Pos) -> None:
    placement["at"] = [pos[0], pos[1]]
    pack.touch(found.file)


def remove(pack: PackFiles, found: Found, gone: List[dict]) -> None:
    """Removes placements from a location (and its entry, if it was one of them)."""
    ids = {p["id"] for p in gone}
    found.entry["placements"] = [p for p in found.entry.get("placements", []) if p.get("id") not in ids]
    if not found.entry["placements"]:
        del found.entry["placements"]
    if found.entry.get("entry") in ids:
        del found.entry["entry"]
    pack.touch(found.file)


def set_entry(pack: PackFiles, found: Found, placement: Optional[dict]) -> None:
    if placement is None:
        found.entry.pop("entry", None)
    else:
        found.entry["entry"] = placement["id"]
    pack.touch(found.file)


def free_wall_tile(location: dict, side: str, occupied: Optional[set] = None) -> Optional[Pos]:
    """A free wall tile on a side with free floor inside it, as near the middle as possible."""
    shape = tiles(location)
    occupied = occupied if occupied is not None else {tuple(p["at"]) for p in location.get("placements", [])}
    line = side_tiles(location, side)
    middle = (len(line) - 1) / 2
    inward = STEP[OPPOSITE[side]]
    for pos in sorted(line, key=lambda p: abs(line.index(p) - middle)):
        ahead = (pos[0] + inward[0], pos[1] + inward[1])
        if shape.get(pos) == "#" and pos not in occupied and ahead not in occupied and shape.get(ahead) == ".":
            return pos
    return None


def link_door(pack: PackFiles, a: Found, pos_a: Pos, b: Found, pos_b: Pos, object_id: str) -> Tuple[dict, dict]:
    """A door in each location, each leading to the other: 'workshop_door_storage', 'storage_door_workshop'."""
    stem_a, stem_b, obj = stem(a.entry["id"], "locations"), stem(b.entry["id"], "locations"), stem(object_id, "objects")
    taken = placement_ids(pack)
    id_a = new_placement_id(pack, f"{stem_a}_{obj}_{stem_b}", taken)
    id_b = new_placement_id(pack, f"{stem_b}_{obj}_{stem_a}", taken | {id_a})
    door_a = {"id": id_a, "object": object_id, "at": list(pos_a), "exit": {"location": b.entry["id"], "entry": id_b}}
    door_b = {"id": id_b, "object": object_id, "at": list(pos_b), "exit": {"location": a.entry["id"], "entry": id_a}}
    a.entry.setdefault("placements", []).append(door_a)
    b.entry.setdefault("placements", []).append(door_b)
    pack.touch(a.file)
    pack.touch(b.file)
    return door_a, door_b


def edge_problem(a: dict, side: str, b: dict) -> Optional[str]:
    """Why two sides can't be joined as an open edge, or None."""
    line_a, line_b = side_tiles(a, side), side_tiles(b, OPPOSITE[side])
    if len(line_a) != len(line_b):
        return f"The sides differ in length ({len(line_a)} and {len(line_b)} tiles): use a door instead."
    for location, line in ((a, line_a), (b, line_b)):
        taken = [p for p in location.get("placements", []) if tuple(p["at"]) in set(line)]
        if taken:
            return f"{location.get('name', location['id'])}: that side already has {taken[0].get('id')}."
    return None


def open_edge(pack: PackFiles, a: Found, side: str, b: Found, object_id: str) -> List[dict]:
    """Joins a side of 'a' to the opposite side of 'b', tile by tile: 'field_east_1' ↔ 'plain_west_1'."""
    stem_a, stem_b = stem(a.entry["id"], "locations"), stem(b.entry["id"], "locations")
    other = OPPOSITE[side]
    taken = placement_ids(pack)
    made = []
    for n, (pos_a, pos_b) in enumerate(zip(side_tiles(a.entry, side), side_tiles(b.entry, other)), start=1):
        id_a = new_placement_id(pack, f"{stem_a}_{side}_{n}", taken)
        id_b = new_placement_id(pack, f"{stem_b}_{other}_{n}", taken | {id_a})
        taken |= {id_a, id_b}
        tile_a = {"id": id_a, "object": object_id, "at": list(pos_a), "exit": {"location": b.entry["id"], "entry": id_b}}
        tile_b = {"id": id_b, "object": object_id, "at": list(pos_b), "exit": {"location": a.entry["id"], "entry": id_a}}
        a.entry.setdefault("placements", []).append(tile_a)
        b.entry.setdefault("placements", []).append(tile_b)
        made += [tile_a, tile_b]
    pack.touch(a.file)
    pack.touch(b.file)
    return made
