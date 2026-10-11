"""
What the player knows of the world's map: the places they've been, and the places the
exits of those lead to that they haven't been to yet. Regions are mapped one at a
time, each location at its region's 'map' x/y; locations without one aren't drawn.
"""
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

from engine.content import Content
from engine.state import GameState

Cell = Tuple[int, int]


class Place(NamedTuple):
    location: str
    cell: Cell
    kind: str                     # 'here', 'visited' or 'known' (an exit leads there; not been yet)


class RegionMap(NamedTuple):
    region: str
    places: Dict[Cell, Place]
    links: Set[Tuple[Cell, Cell]]
    elsewhere: Tuple[str, ...]    # known locations in other regions an exit from here leads to


def exits(content: Content) -> Dict[str, List[str]]:
    """Where each location's exits lead, each once, in placement order (exits into zones aside)."""
    found: Dict[str, List[str]] = {}
    for p in content.all("placement").values():
        dest = (p.get("exit") or {}).get("location")
        if dest and dest in content.all("location") and dest not in found.setdefault(p["location"], []):
            found[p["location"]].append(dest)
    return found


def _cell(content: Content, location_id: str) -> Optional[Cell]:
    spot = content.get("location", location_id).get("map")
    return (spot["x"], spot["y"]) if spot else None


def known(content: Content, state: GameState, leads: Optional[Dict[str, List[str]]] = None) -> Dict[str, str]:
    """Every location the player knows of: 'here', 'visited' or 'known'."""
    leads = exits(content) if leads is None else leads
    me = state.characters[state.player]
    kinds = {loc: "visited" for loc in me.visited if loc in content.all("location")}
    for loc in list(kinds):
        for dest in leads.get(loc, []):
            kinds.setdefault(dest, "known")
    kinds[me.location] = "here"
    return kinds


def regions(content: Content, state: GameState) -> List[str]:
    """Regions with a place the player has been to: theirs first, then in the pack's order."""
    here = content.get("location", state.characters[state.player].location)["region"]
    been = {content.get("location", loc)["region"] for loc, kind in known(content, state).items() if kind != "known"}
    return [here] + [r for r in content.all("region") if r in been and r != here]


def start_cell(content: Content, state: GameState, region_map_: "RegionMap") -> Cell:
    """Where the map's cursor starts: on the player, else on the first place of the region, else the corner."""
    here = next((cell for cell, p in region_map_.places.items() if p.kind == "here"), None)
    if here is not None:
        return here
    return min(region_map_.places, key=lambda c: (c[1], c[0])) if region_map_.places else (0, 0)


def region_map(content: Content, state: GameState, region_id: str) -> RegionMap:
    leads = exits(content)
    kinds = known(content, state, leads)
    places: Dict[Cell, Place] = {}
    elsewhere: List[str] = []
    for loc, kind in kinds.items():
        record = content.get("location", loc)
        cell = _cell(content, loc)
        if record["region"] == region_id and cell is not None and (cell not in places or kind == "here"):
            places[cell] = Place(loc, cell, kind)
    cell_of = {p.location: cell for cell, p in places.items()}
    links: Set[Tuple[Cell, Cell]] = set()
    for loc, kind in kinds.items():
        if kind == "known":
            continue                                       # its exits aren't known yet
        for dest in leads.get(loc, []):
            if loc in cell_of and dest in cell_of and cell_of[loc] != cell_of[dest]:
                links.add(tuple(sorted((cell_of[loc], cell_of[dest]))))
            elif loc in cell_of and content.get("location", dest)["region"] != region_id and dest not in elsewhere:
                elsewhere.append(dest)
    return RegionMap(region_id, places, links, tuple(elsewhere))
