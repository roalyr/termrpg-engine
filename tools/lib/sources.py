"""
Where an entry is used, in words, and for items where the player can get them.

Every use is found the way the checker finds references (tools.lib.refs) and named by
the entry it sits in: a crate's contents, a trade's give_item, a loot table, another
item's salvage. For an item, the uses that put it in the player's hands are its
sources: loot that something rolls, storage contents, gifts and trades, salvage, the
player's starting gear, and its own design when the player can learn it. An item with
no source can't be had in play.
"""
from typing import Any, List, NamedTuple, Optional, Tuple

from core.pack import KIND_NAMESPACES
from tools.lib import refs
from tools.lib.packfiles import PackFiles

class Use(NamedTuple):
    kind: str                 # the kind of the entry it sits in ('objects', 'loot_tables'…), or 'pack'
    entry_id: str             # that entry's id ('' for pack.json)
    name: str                 # how to call it: 'Crate', 'Juno', 'Storage: Locker'
    words: str                # what the use is: 'holds it at the start'
    source: bool = False      # puts the item in the player's hands
    problem: str = ""         # why a would-be source doesn't work


def _kind_of(pack: PackFiles, rel: str) -> str:
    if rel == "pack.json":
        return "pack"
    return next((kind for kind, files in pack.kinds.items() if rel in files), "")


def _steps(path: str) -> List[Any]:
    return refs._steps(path)


def _node(data: Any, steps: List[Any]) -> Any:
    for step in steps:
        data = data[step]
    return data


def _name(entry: dict) -> str:
    return entry.get("name") or entry.get("id", "?")


def _owner(pack: PackFiles, rel: str, steps: List[Any]) -> Tuple[str, str, str]:
    """(kind, id, name) of the entry a path sits in; a placement is named with its location."""
    kind = _kind_of(pack, rel)
    if kind == "pack" or len(steps) < 2 or steps[0] != "entries":
        return kind, "", "the pack's start" if kind == "pack" else rel
    entry = pack.data[rel]["entries"][steps[1]]
    name = _name(entry)
    if kind == "locations" and len(steps) > 3 and steps[2] == "placements":
        placed = entry["placements"][steps[3]]
        thing = pack.find("objects", placed.get("object", ""))
        name = f"{name}: {placed.get('name') or (_name(thing.entry) if thing else placed.get('id', '?'))}"
    return kind, entry.get("id", ""), name


def _effect_of(data: Any, steps: List[Any]) -> Optional[dict]:
    """The innermost effect or check (a dict with 'op' or 'check') around a path."""
    for cut in range(len(steps) - 1, -1, -1):
        node = _node(data, steps[:cut])
        if isinstance(node, dict) and ("op" in node or "check" in node):
            return node
    return None


def describe(pack: PackFiles, rel: str, path: str) -> Use:
    """One use of an id, in words."""
    steps = _steps(path)
    kind, entry_id, name = _owner(pack, rel, steps)
    data = pack.manifest if rel == "pack.json" else pack.data[rel]
    keys = [s for s in steps if isinstance(s, str)]
    effect = _effect_of(data, steps)
    op = effect.get("op") or effect.get("check") if effect else None
    if op:
        return Use(kind, entry_id, name, {"give_item": "gives it", "take_item": "takes it",
                                          "has_item": "asks for it", "learn_design": "teaches its design",
                                          "roll_loot": "rolls it", "knows_design": "asks if its design is known"}.get(op, f"{op}"))
    if "contents" in keys:
        return Use(kind, entry_id, name, "holds it at the start")
    if "salvage" in keys:
        return Use(kind, entry_id, name, "dismantling it yields it")
    for key, words in (("fabricate", "needed to fabricate it"), ("repair", "needed to repair it"),
                       ("material", "its material"), ("consumes", "uses it up"), ("fit_requires", "needed to fit it"),
                       ("always", "always in it"), ("entries", "can be drawn from it"), ("designs", "knows its design"),
                       ("inventory", "carries it"), ("fitted", "has it fitted"), ("implants", "has it implanted"),
                       ("frame", "wears it"), ("loot", "drops it"), ("placements", "placed there"),
                       ("object_pool", "may turn up there"), ("allies", "fights beside the player"),
                       ("enemies", "fights in it"), ("spawns", "may turn up there")):
        if key in keys[1:]:
            return Use(kind, entry_id, name, words)
    return Use(kind, entry_id, name, path.split(".", 1)[-1] if "." in path else path)


def uses(pack: PackFiles, namespace: str, ident: Any) -> List[Use]:
    """Every use of an id, in words, in pack order."""
    return [describe(pack, rel, path) for rel, path in refs.uses(pack, namespace, ident)]


def player_id(pack: PackFiles) -> str:
    start = pack.manifest.get("start", {})
    return start.get("player", "") if isinstance(start, dict) else ""


def rolled(pack: PackFiles, table_id: str, seen: Optional[set] = None) -> List[Use]:
    """What rolls a loot table: characters that drop it, encounters, roll_loot effects, tables that roll it."""
    seen = (seen or set()) | {table_id}
    found = []
    for use in uses(pack, KIND_NAMESPACES["loot_tables"], table_id):
        if use.kind == "loot_tables":
            if use.entry_id not in seen and rolled(pack, use.entry_id, seen):
                found.append(use)
        else:
            found.append(use)
    return found


def item_uses(pack: PackFiles, item_id: str, seen: Optional[set] = None) -> List[Use]:
    """Every use of an item, its sources marked (first), and would-be sources that don't work with their problem."""
    seen = (seen or set()) | {item_id}
    player = player_id(pack)
    marked = []
    for use in uses(pack, KIND_NAMESPACES["items"], item_id):
        source, problem = False, ""
        if use.words in ("gives it", "holds it at the start"):
            source = True
        elif use.words == "dismantling it yields it":
            source = use.entry_id not in seen and bool(sources(pack, use.entry_id, seen))
            problem = "" if source else "but nobody can get that"
        elif use.kind == "loot_tables" and use.words in ("always in it", "can be drawn from it"):
            source = bool(rolled(pack, use.entry_id))
            problem = "" if source else "but nothing rolls this table"
        elif use.kind == "characters" and use.entry_id == player and use.words in ("carries it", "has it fitted",
                                                                                 "has it implanted", "wears it"):
            source = True
            use = use._replace(words="starts with it")
        marked.append(use._replace(source=source, problem=problem))
    item = next((f.entry for f in pack.entries("items") if f.entry.get("id") == item_id), {})
    if item.get("fabricate"):
        learnt = [u for u in marked if u.words in ("teaches its design", "knows its design")
                  and (u.words == "teaches its design" or u.entry_id == player)]
        dismantled = item.get("salvage", {}).get("learn_requires") is not None if isinstance(item.get("salvage"), dict) else False
        if learnt or (dismantled and any(u.source for u in marked)):
            marked.insert(0, Use("items", item_id, _name(item), "fabricated once its design is known", True))
        else:
            marked.append(Use("items", item_id, _name(item), "can be fabricated", False,
                              "but nothing teaches its design"))
    return sorted(marked, key=lambda u: not u.source)


def sources(pack: PackFiles, item_id: str, seen: Optional[set] = None) -> List[Use]:
    return [u for u in item_uses(pack, item_id, seen) if u.source]
