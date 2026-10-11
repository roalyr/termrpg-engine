"""
Whether a character's loadout fits, as a pack writes it: which slot each piece of gear
takes, what the loadout provides and uses of each budget, and what doesn't fit. The
checker reports the problems as errors and the loadout editor shows them, each in its
own words, so both count the same way.

The rules: slots come from the body and from equipped gear. Gear is placed in the order
it is listed: each piece takes a free slot of its type from the body or from gear placed
before it, then adds its own slots. What equipped gear uses of a budget stat must not go
over what the body, gear and reached skill levels provide; its constant load on a
filling pool must stay below the pool's maximum; the inventory's stacks must fit in
cargo. (The game counts a running loadout itself, in engine/stats.py: its items can be
modified or broken, which a pack's can't.)
"""
from typing import Any, Dict, Iterable, List, Mapping, NamedTuple, Optional, Sequence, Tuple

BODY = -1    # the host of a body slot


class Slot(NamedTuple):
    """One slot and the gear in it (None when empty)."""
    host: int                 # BODY, or the index in 'equipped' of the gear that adds the slot
    slot_type: str            # '' for gear with no free slot or that isn't gear
    item: Optional[str]
    index: int                # the gear's place in 'equipped'; -1 when empty


class Problem(NamedTuple):
    """
    What doesn't fit, for the caller to put in words:
      'no_item'      item listed in 'equipped' isn't in the pack
      'not_gear'     item listed in 'equipped' is of kind 'kind'
      'no_slot'      no free 'slot_type' slot for item
      'over'         stat 'stat' uses 'used' of 'provided' (a filling pool: reaches it;
                     the cargo stat: inventory stacks)
    """
    what: str
    item: str = ""
    kind: Any = ""
    slot_type: str = ""
    stat: str = ""
    used: float = 0
    provided: float = 0


class Loadout(NamedTuple):
    slots: List[Slot]             # the body's slots, then each placed gear's, in order
    extra: List[Slot]             # listed items with no free slot, or that aren't gear
    used: Dict[str, float]        # budget and filling-pool stat -> what gear uses; cargo stat -> stacks
    provided: Dict[str, float]    # the same stats -> what the loadout provides
    totals: Dict[str, float]      # every stat, totalled over body, gear and skill levels
    size: Optional[int]           # the largest worn_size of placed gear, else the body's size
    problems: List[Problem]


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def slot_counts(holder: Optional[Mapping]) -> Dict[str, int]:
    """Slot type -> how many, as a body or a piece of gear lists them."""
    counts: Dict[str, int] = {}
    for slot in (holder or {}).get("slots", []) or []:
        if isinstance(slot, Mapping) and slot.get("slot_type"):
            counts[slot["slot_type"]] = counts.get(slot["slot_type"], 0) + slot.get("count", 1)
    return counts


def over(fills: bool, used: float, provided: float) -> bool:
    """Whether a budget doesn't fit: a filling pool's load must stay below its maximum, the rest within."""
    if fills:
        return bool(used) and used >= provided
    return used > provided


def place(body_slots: Mapping[str, int], gear: Sequence[Optional[Mapping]]) -> Tuple[List[Slot], List[int]]:
    """
    Gear placed into slots, in order: the slots (body first, then each placed piece's),
    and the indexes of gear that found no free slot. None stands for something that isn't
    gear, which is never placed.
    """
    slots = [Slot(BODY, t, None, -1) for t, count in body_slots.items() for _ in range(count)]
    unplaced: List[int] = []
    for index, piece in enumerate(gear):
        free = next((n for n, s in enumerate(slots) if s.item is None and piece is not None
                     and s.slot_type == piece.get("slot_type")), None)
        if free is None:
            unplaced.append(index)
            continue
        slots[free] = slots[free]._replace(item=str(piece.get("id", "")), index=index)
        slots += [Slot(index, t, None, -1) for t, count in slot_counts(piece).items() for _ in range(count)]
    return slots, unplaced


def loadout(char: Mapping, items: Mapping[str, Mapping], stats: Mapping[str, Mapping],
            skills: Mapping[str, Mapping]) -> Loadout:
    """
    A character's loadout. 'items', 'stats' and 'skills' are the pack's entries by id (the
    vocabulary's stats for 'stats').
    """
    body = char.get("body", {}) if isinstance(char.get("body"), Mapping) else {}
    problems: List[Problem] = []
    ids = [i for i in (char.get("equipped", []) or [])]
    gear: List[Optional[Mapping]] = []
    for item_id in ids:
        item = items.get(item_id)
        if item is None:
            problems.append(Problem("no_item", item_id))
        elif item.get("kind") != "gear":
            problems.append(Problem("not_gear", item_id, item.get("kind")))
        gear.append(dict(item, id=item_id) if item is not None and item.get("kind") == "gear" else None)
    slots, unplaced = place(slot_counts(body), gear)
    extra = [Slot(BODY, (gear[i] or {}).get("slot_type", ""), ids[i], i) for i in unplaced]
    problems += [Problem("no_slot", ids[i], "gear", gear[i].get("slot_type", "")) for i in unplaced if gear[i]]

    placed = [gear[s.index] for s in slots if s.item is not None]
    worn: List[Mapping] = [body] + placed
    for skill_id, level in (char.get("skills", {}) or {}).items():         # skill levels add stats too
        for lv in (skills.get(skill_id) or {}).get("levels", []) or []:
            if isinstance(lv, Mapping) and isinstance(level, int) and lv.get("level", 0) <= level:
                worn.append(lv)
    totals: Dict[str, float] = {}
    for thing in worn:
        values = thing.get("stats")
        for stat_id, value in (values.items() if isinstance(values, Mapping) else ()):
            if _number(value):
                totals[stat_id] = totals.get(stat_id, 0) + value

    counted = [s for s, record in stats.items() if record.get("budget") or record.get("fills")]
    used: Dict[str, float] = {s: 0.0 for s in counted}
    for piece in placed:
        for stat_id, amount in (piece.get("uses", {}) or {}).items():
            if _number(amount):
                used[stat_id] = used.get(stat_id, 0.0) + amount
    cargo = next((s for s, record in stats.items() if record.get("role") == "cargo"), None)
    if cargo is not None:
        stacks = 0
        for entry in char.get("inventory", []) or []:
            item = items.get(entry.get("item")) if isinstance(entry, Mapping) else None
            if item is not None:
                stacks += -(-entry.get("count", 1) // item.get("stack", 1))
        used[cargo] = stacks
    provided = {s: totals.get(s, 0) for s in used}
    for stat_id, have in provided.items():
        if over(bool((stats.get(stat_id) or {}).get("fills")), used[stat_id], have):
            problems.append(Problem("over", stat=stat_id, used=used[stat_id], provided=have))
    sizes = [p["worn_size"] for p in placed if _number(p.get("worn_size"))]
    size = max(sizes) if sizes else body.get("size")
    return Loadout(slots, extra, used, provided, totals, size, problems)


def budget_stats(stats: Mapping[str, Mapping]) -> Iterable[str]:
    """The stats a loadout is measured against, in vocabulary order: budgets, filling pools, then cargo."""
    yield from (s for s, r in stats.items() if r.get("budget"))
    yield from (s for s, r in stats.items() if r.get("fills"))
    yield from (s for s, r in stats.items() if r.get("role") == "cargo")
