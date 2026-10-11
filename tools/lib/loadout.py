"""
A character's loadout, worked out from the pack as it is in memory (saved or not): the
slots of the frame and the body and what fills them, what the loadout provides and uses
of power, mass, heat and cargo, its other stats, and what doesn't fit. The numbers are
counted the way the checker counts them, so a loadout this calls fine passes the check.
"""
from typing import Dict, List, NamedTuple, Optional

from tools.lib.packfiles import PackFiles

BUDGETS = ("power", "mass", "heat", "cargo")
HOSTS = {"module": "frame", "implant": "body"}
GROUPS = {"module": "fitted", "implant": "implants"}


class Slot(NamedTuple):
    """One slot of a frame or a body, and the item in it (None when empty)."""
    host: str                 # 'frame' or 'body'
    slot_type: str
    item: Optional[str]
    index: int                # the item's place in 'fitted' or 'implants'; -1 when empty


class Budget(NamedTuple):
    role: str
    name: str
    short: str
    used: float
    provided: float

    @property
    def over(self) -> bool:
        if self.role == "heat":
            return bool(self.used) and self.used >= self.provided
        return self.used > self.provided


class Sheet(NamedTuple):
    frame: Optional[str]
    slots: List[Slot]
    extra: List[Slot]         # fitted items with no free slot (or of the wrong kind)
    budgets: List[Budget]
    stats: Dict[str, float]   # the other stats, totalled
    problems: List[str]


class Vocab(NamedTuple):
    stats: Dict[str, dict]
    roles: Dict[str, str]     # role -> stat id
    slot_types: Dict[str, dict]


def vocab(pack: PackFiles) -> Vocab:
    merged: Dict[str, list] = {}
    for rel in pack.kinds.get("vocab", []):
        for key, value in pack.data[rel].items():
            if isinstance(value, list):
                merged.setdefault(key, []).extend(value)
    stats = {s["id"]: s for s in merged.get("stats", []) if isinstance(s, dict) and s.get("id")}
    roles = {s["role"]: i for i, s in stats.items() if s.get("role")}
    slot_types = {s["id"]: s for s in merged.get("slot_types", []) if isinstance(s, dict) and s.get("id")}
    return Vocab(stats, roles, slot_types)


def items(pack: PackFiles) -> Dict[str, dict]:
    return {f.entry["id"]: f.entry for f in pack.entries("items") if f.entry.get("id")}


def slot_counts(holder: Optional[dict]) -> Dict[str, int]:
    """Slot type -> how many, as a frame or a body lists them."""
    counts: Dict[str, int] = {}
    for slot in (holder or {}).get("slots", []) or []:
        if isinstance(slot, dict) and slot.get("slot_type"):
            counts[slot["slot_type"]] = counts.get(slot["slot_type"], 0) + slot.get("count", 1)
    return counts


def sheet(pack: PackFiles, char: dict) -> Sheet:
    known, words = items(pack), vocab(pack)
    body = char.get("body", {}) if isinstance(char.get("body"), dict) else {}
    frame = known.get(char.get("frame"))
    problems: List[str] = []
    if char.get("frame") and (frame is None or frame.get("kind") != "frame"):
        problems.append(f"'{char['frame']}' isn't a frame.")
        frame = None
    if char.get("fitted") and "frame" not in char:
        problems.append("Has fitted modules but wears no frame.")
    worn = [body] + ([frame] if frame else [])
    slots: List[Slot] = []
    extra: List[Slot] = []
    used = {"power": 0.0, "mass": 0.0, "heat": 0.0}
    for kind, host in HOSTS.items():
        capacity = slot_counts(frame if host == "frame" else body)
        filled: Dict[str, List[int]] = {t: [] for t in capacity}
        for index, item_id in enumerate(char.get(GROUPS[kind], []) or []):
            item = known.get(item_id)
            if item is None or item.get("kind") != kind:
                extra.append(Slot(host, "", item_id, index))
                problems.append(f"'{item_id}' isn't {'a module' if kind == 'module' else 'an implant'}." if item
                                else f"No item '{item_id}'.")
                continue
            worn.append(item)
            slot_type = item.get("slot_type", "")
            if len(filled.get(slot_type, [])) < capacity.get(slot_type, 0):
                filled[slot_type].append(index)
            else:
                extra.append(Slot(host, slot_type, item_id, index))
                problems.append(f"No free {_slot_name(words, slot_type)} slot in the {host} for {item.get('name', item_id)}.")
            for budget, amount in (item.get("uses", {}) or {}).items():
                used[budget] = used.get(budget, 0.0) + amount
        for slot_type, count in capacity.items():
            taken = filled[slot_type]
            ids = char.get(GROUPS[kind], [])
            slots += [Slot(host, slot_type, ids[taken[n]] if n < len(taken) else None, taken[n] if n < len(taken) else -1)
                      for n in range(count)]
    for skill_id, level in (char.get("skills", {}) or {}).items():         # skill levels add stats too
        skill = next((f.entry for f in pack.entries("skills") if f.entry.get("id") == skill_id), None)
        for lv in (skill or {}).get("levels", []) or []:
            if isinstance(lv, dict) and isinstance(level, int) and lv.get("level", 0) <= level:
                worn.append(lv)
    totals: Dict[str, float] = {}
    for thing in worn:
        for stat_id, value in (thing.get("stats", {}) or {}).items() if isinstance(thing.get("stats"), dict) else ():
            totals[stat_id] = totals.get(stat_id, 0) + value
    stacks = 0
    for entry in char.get("inventory", []) or []:
        item = known.get(entry.get("item")) if isinstance(entry, dict) else None
        if item is not None:
            stacks += -(-entry.get("count", 1) // item.get("stack", 1))
    used["cargo"] = stacks
    budgets = []
    for role in BUDGETS:
        stat_id = words.roles.get(role)
        if stat_id is None:
            continue
        stat = words.stats[stat_id]
        budget = Budget(role, stat.get("name", role), stat.get("short", role[:3].upper()), used[role],
                        totals.get(stat_id, 0))
        budgets.append(budget)
        if budget.over:
            if role == "heat":
                problems.append(f"Constant heat {budget.used:g} leaves no room below maximum heat {budget.provided:g}.")
            elif role == "cargo":
                problems.append(f"The inventory needs {budget.used:g} cargo stacks; the loadout carries {budget.provided:g}.")
            else:
                problems.append(f"Fitted gear needs {budget.used:g} {role}; the loadout provides {budget.provided:g}.")
    budget_stats = {words.roles[b.role] for b in budgets}
    others = {s: totals[s] for s in words.stats if s in totals and s not in budget_stats}
    return Sheet(char.get("frame") if frame else None, slots, extra, budgets, others, problems)


def _slot_name(words: Vocab, slot_type: str) -> str:
    return words.slot_types.get(slot_type, {}).get("name", slot_type)


def uses_text(item: dict, words: Vocab) -> str:
    """What an item uses and gives, in short: 'PWR 2 MAS 3 · ARM +2'."""
    shorts = {role: words.stats[i].get("short", role) for role, i in words.roles.items()}
    parts = [f"{shorts.get(k, k)} {v:g}" for k, v in (item.get("uses", {}) or {}).items()]
    gives = [f"{words.stats.get(k, {}).get('short', k)} {v:+g}" for k, v in (item.get("stats", {}) or {}).items()]
    return " · ".join(p for p in (" ".join(parts), " ".join(gives)) if p)
