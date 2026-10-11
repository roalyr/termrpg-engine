"""
An entry at a glance, above its fields in the entries editor: for an item what kind
it is, what it uses and gives, and where the player gets it (in red when nowhere); for
an object its glyph in colour and in each state, its workshop, its storage and where
it's placed. Kinds without a glance show nothing.
"""
from typing import List

from lib import budgets
from lib.tiles import map_glyph
from tools.lib import loadout, screen, sources
from tools.lib.fields import ids
from tools.lib.packfiles import PackFiles

NOWHERE = "Nobody can get it: no loot, storage, gift, salvage or starting gear gives it."


def lines(pack: PackFiles, look: screen.Look, kind: str, entry: dict, width: int) -> List[str]:
    if kind == "items":
        return item_lines(pack, look, entry, width)
    if kind == "objects":
        return object_lines(pack, look, entry, width)
    return []


def item_lines(pack: PackFiles, look: screen.Look, item: dict, width: int) -> List[str]:
    style, words = look.style, loadout.vocab(pack)
    parts = [str(item.get("kind", "item")).capitalize()]
    if item.get("slot_type"):
        parts.append(f"{words.slot_types.get(item['slot_type'], {}).get('name', item['slot_type'])} slot")
    if item.get("slots"):
        counts = budgets.slot_counts(item)
        parts.append(", ".join(f"{words.slot_types.get(t, {}).get('name', t)}" + (f" x{n}" if n > 1 else "")
                               for t, n in counts.items()))
    numbers = loadout.uses_text(item, words)
    if numbers:
        parts.append(numbers)
    out = _join(parts, width)[:2]
    if not item.get("id"):
        return out
    found = sources.sources(pack, item["id"])
    if found:
        names = []
        for use in found:
            label = "fabricating it" if use.entry_id == item["id"] else use.name
            if label not in names:
                names.append(label)
        out += [style.role(line, "quiet") for line in screen.wrap("From: " + ", ".join(names), width)[:2]]
    else:
        out += [style.role(line, "danger") for line in screen.wrap(NOWHERE, width)]
    return out


def object_lines(pack: PackFiles, look: screen.Look, obj: dict, width: int) -> List[str]:
    style = look.style
    colour = obj.get("colour")
    states = obj.get("states", []) or []
    names = dict(ids(pack, "object_state"))
    glyph = obj.get("glyph", "?")
    head = map_glyph(style, glyph, colour, "map_object") + " " + str(obj.get("name", obj.get("id", "")))
    out = [head]
    if states:
        shown = "  ".join(map_glyph(style, (obj.get("state_glyphs") or {}).get(s, glyph), colour, "map_object")
                          + " " + str(names.get(s) or s) for s in states)
        if screen.visible_len(head) + 3 + screen.visible_len(shown) <= width:
            out = [head + "   " + shown]
        else:                                            # its own lines, wrapped between states
            out += screen.hints(look, shown.split("  "), width, styled=False)
    workshop = obj.get("workshop")
    if isinstance(workshop, dict):
        grade = workshop.get("max_grade")
        text = "Workshop: " + ", ".join(workshop.get("services", [])) \
            + (f", up to {dict(ids(pack, 'grade')).get(grade) or grade}" if grade else "")
        out += [style.role(line, "quiet") for line in screen.wrap(text, width)[:2]]
    facts = [f"Stores {obj['storage']} stacks"] if obj.get("storage") else []
    placed = [f.entry for f in pack.entries("locations")
              if any(p.get("object") == obj.get("id") for p in f.entry.get("placements", []))]
    count = sum(1 for loc in placed for p in loc.get("placements", []) if p.get("object") == obj.get("id"))
    if placed:
        facts.append(f"Placed {count}x: " + ", ".join(str(loc.get("name", loc.get("id"))) for loc in placed))
    else:
        facts.append("Not placed anywhere")
    out.append(_cut(look, " · ".join(facts), width))
    return out


def _join(parts: List[str], width: int, sep: str = " · ") -> List[str]:
    """Parts joined on lines, wrapped between parts (inside one only when it's wider than a line)."""
    out: List[str] = []
    for part in parts:
        if out and len(out[-1]) + len(sep) + len(part) <= width:
            out[-1] += sep + part
        else:
            out += screen.wrap(part, width)
    return out


def _cut(look: screen.Look, text: str, width: int) -> str:
    """One quiet line, cut with '…' when it runs over."""
    return look.style.role(text if len(text) <= width else text[:width - 1] + "…", "quiet")
