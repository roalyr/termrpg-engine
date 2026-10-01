"""
What a character is right now, derived from content and state: stats, tags, size,
budgets and cargo. Nothing here is stored; it is computed on demand.

Sources of a character's stats: the body, the worn frame, fitted modules, implants
(all only while not broken), skill levels, and stat changes from effects. A pool
stat's derived value is its maximum; its current value lives in CharState.pools.
"""
from typing import Dict, Iterator, List, Mapping, Optional, Tuple

from engine.content import Content
from engine.frozen import Record, freeze
from engine.state import CharState, ItemInst

Slot = Tuple[str, int]  # ('frame'|'fitted'|'implants'|'inventory', index)


# --- Items ---------------------------------------------------------------------

def item_view(content: Content, inst: ItemInst) -> Dict:
    """An item as it is now: its content record with modifications and changes applied."""
    base = content.get("item", inst.item)
    view = {
        "id": inst.item, "kind": base["kind"], "name": base["name"], "size": base["size"],
        "holds_size": base.get("holds_size"), "slot_type": base.get("slot_type"),
        "tags": list(base.get("tags", ())), "stats": dict(base.get("stats", {})),
        "actions": list(base.get("actions", ())), "uses": dict(base.get("uses", {})),
        "max_condition": base.get("condition"), "stack": base.get("stack", 1),
    }
    suffixes: List[str] = []
    for mod_id in inst.mods:
        mod = content.get("modification", mod_id)
        adds = mod["adds"]
        _add_changes(view, adds.get("tags", ()), (), adds.get("stats", {}), adds.get("max_condition"))
        view["actions"] += [a for a in adds.get("actions", ()) if a not in view["actions"]]
        for budget, amount in adds.get("uses", {}).items():
            view["uses"][budget] = max(0, view["uses"].get(budget, 0) + amount)
        suffixes.append(mod["name"])
    for change in inst.changes:
        _add_changes(view, change.get("add_tags", ()), change.get("remove_tags", ()),
                     change.get("stats", {}), change.get("max_condition"))
        if change.get("name_suffix"):
            suffixes.append(change["name_suffix"])
    if suffixes:
        view["name"] = f"{view['name']} ({', '.join(suffixes)})"
    return view


def _add_changes(view: Dict, add_tags, remove_tags, stat_changes: Mapping, max_condition: Optional[int]) -> None:
    view["tags"] = [t for t in view["tags"] if t not in remove_tags] + [t for t in add_tags if t not in view["tags"]]
    for stat_id, amount in stat_changes.items():
        view["stats"][stat_id] = view["stats"].get(stat_id, 0) + amount
    if max_condition and view["max_condition"] is not None:
        view["max_condition"] += max_condition


def is_broken(inst: ItemInst) -> bool:
    return inst.condition is not None and inst.condition <= 0


def held(cs: CharState) -> Iterator[Tuple[Slot, ItemInst]]:
    """Every item a character has, with where it is: worn, fitted, implanted, then carried."""
    if cs.frame is not None:
        yield ("frame", 0), cs.frame
    for i, inst in enumerate(cs.fitted):
        yield ("fitted", i), inst
    for i, inst in enumerate(cs.implants):
        yield ("implants", i), inst
    for i, inst in enumerate(cs.inventory):
        yield ("inventory", i), inst


def active(cs: CharState) -> Iterator[Tuple[Slot, ItemInst]]:
    """Worn, fitted and implanted items that aren't broken: the ones that count."""
    for slot, inst in held(cs):
        if slot[0] != "inventory" and not is_broken(inst):
            yield slot, inst


def item_at(cs: CharState, slot: Slot) -> Optional[ItemInst]:
    where, index = slot
    if where == "frame":
        return cs.frame
    items = getattr(cs, where)
    return items[index] if 0 <= index < len(items) else None


def with_item(cs: CharState, slot: Slot, inst: Optional[ItemInst]) -> CharState:
    """The character with the item at a slot replaced (or removed, when inst is None)."""
    where, index = slot
    if where == "frame":
        return cs._replace(frame=inst)
    items = list(getattr(cs, where))
    if inst is None:
        items.pop(index)
    else:
        items[index] = inst
    return cs._replace(**{where: tuple(items)})


# --- Skills --------------------------------------------------------------------

def skill_levels(content: Content, cs: CharState) -> Iterator[Record]:
    """Every skill level the character has reached."""
    for skill_id, level in cs.skills.items():
        for lv in content.get("skill", skill_id)["levels"]:
            if lv["level"] <= level:
                yield lv


# --- Stats ---------------------------------------------------------------------

def stat(content: Content, cs: CharState, stat_id: str) -> float:
    """
    A stat's derived value (a pool's maximum): body + active items + skill levels +
    stat changes, kept within the stat's declared min and max.
    """
    body = content.get("character", cs.source)["body"]
    total = body.get("stats", {}).get(stat_id, 0)
    for _, inst in active(cs):
        total += item_view(content, inst)["stats"].get(stat_id, 0)
    for lv in skill_levels(content, cs):
        total += lv.get("stats", {}).get(stat_id, 0)
    total += sum(m.amount for m in cs.mods if m.stat == stat_id)
    return _clamp(content, stat_id, total)


def current(content: Content, cs: CharState, stat_id: str) -> float:
    """A pool's current value, or a value stat's derived value."""
    if is_pool(content, stat_id):
        return cs.pools.get(stat_id, stat(content, cs, stat_id))
    return stat(content, cs, stat_id)


def is_pool(content: Content, stat_id: str) -> bool:
    return content.get("stat", stat_id).get("kind") == "pool"


def _clamp(content: Content, stat_id: str, value: float) -> float:
    record = content.get("stat", stat_id)
    low = record.get("min", 0)
    value = max(low, value)
    if record.get("max") is not None:
        value = min(record["max"], value)
    return value


def fill_pools(content: Content, cs: CharState) -> CharState:
    """Pools at their starting values: full, except heat, which starts at the constant heat load."""
    heat = content.stat_roles.get("heat")
    pools = {}
    for stat_id in content.all("stat"):
        if is_pool(content, stat_id):
            pools[stat_id] = budget_used(content, cs, "heat") if stat_id == heat else stat(content, cs, stat_id)
    return cs._replace(pools=freeze(pools))


def clamp_pools(content: Content, cs: CharState) -> CharState:
    """Pools kept within their current maximum (after a loadout or stat change)."""
    pools = {s: min(v, stat(content, cs, s)) for s, v in cs.pools.items()}
    return cs._replace(pools=freeze(pools))


# --- Tags, size, budgets, cargo -------------------------------------------------

def own_tags(content: Content, cs: CharState, source: str) -> List[str]:
    """
    Tags from one source: 'fitted' (worn frame and fitted modules), 'carried'
    (inventory), 'body' (implants, skill levels and the character's own tags).
    Broken items give no tags.
    """
    tags: List[str] = []
    if source == "fitted":
        for (where, _), inst in active(cs):
            if where in ("frame", "fitted"):
                tags += item_view(content, inst)["tags"]
    elif source == "carried":
        for (where, _), inst in held(cs):
            if where == "inventory" and not is_broken(inst):
                tags += item_view(content, inst)["tags"]
    elif source == "body":
        for (where, _), inst in active(cs):
            if where == "implants":
                tags += item_view(content, inst)["tags"]
        for lv in skill_levels(content, cs):
            tags += list(lv.get("tags", ()))
        tags += list(content.get("character", cs.source).get("tags", ()))
    return tags


def size(content: Content, cs: CharState) -> int:
    """A character's size: their frame's size, or their body's without one."""
    if cs.frame is not None:
        return item_view(content, cs.frame)["size"]
    return content.get("character", cs.source)["body"]["size"]


def budget_provided(content: Content, cs: CharState, role: str) -> float:
    """What the loadout provides of a budget role: power, mass, heat (maximum) or cargo."""
    stat_id = content.stat_roles.get(role)
    return stat(content, cs, stat_id) if stat_id else 0


def budget_used(content: Content, cs: CharState, budget: str) -> float:
    """What fitted modules use of 'power', 'mass' or 'heat' (the constant heat load)."""
    return sum(item_view(content, inst)["uses"].get(budget, 0)
               for (where, _), inst in active(cs) if where == "fitted")


def cargo_free(content: Content, cs: CharState) -> int:
    """How many more item stacks the character can carry."""
    return int(budget_provided(content, cs, "cargo")) - len(cs.inventory)
