"""
Whether a character's loadout fits, as a pack writes it: which slots of the frame and
the body each module and implant takes, what the loadout provides and uses of power,
mass, heat and cargo, and what doesn't fit. The checker reports the problems as errors
and the loadout editor shows them, each in its own words, so both count the same way.

The rules: modules take the frame's slots and implants the body's, one each, by slot
type. Power and mass used by fitted gear must not go over what the body, frame, items
and reached skill levels provide; constant heat must stay below maximum heat; the
inventory's stacks must fit in cargo. (The game counts a running loadout itself, in
engine/stats.py: its items can be modified or broken, which a pack's can't.)
"""
from typing import Any, Dict, List, Mapping, NamedTuple, Optional

BUDGETS = ("power", "mass", "heat", "cargo")
HOSTS = {"module": "frame", "implant": "body"}           # an item kind -> what it's fitted into
GROUPS = {"module": "fitted", "implant": "implants"}     # an item kind -> the character's list of them


class Slot(NamedTuple):
    """One slot of a frame or a body, and the item in it (None when empty)."""
    host: str                 # 'frame' or 'body'
    slot_type: str            # '' for an item that isn't a module or implant
    item: Optional[str]
    index: int                # the item's place in 'fitted' or 'implants'; -1 when empty


class Problem(NamedTuple):
    """
    What doesn't fit, for the caller to put in words:
      'no_item'      item, worn as the frame or listed in 'group', isn't in the pack
      'not_frame'    item is worn as the frame but is of kind 'kind'
      'no_frame'     there are fitted modules but no frame
      'wrong_kind'   item in 'group' is of kind 'kind', not the one the list takes
      'no_slot'      no free 'slot_type' slot in the 'host' for item
      'over'         'role' uses 'used' of 'provided' (heat: reaches it)
    """
    what: str
    item: str = ""
    kind: Any = ""
    group: str = ""
    host: str = ""
    slot_type: str = ""
    role: str = ""
    used: float = 0
    provided: float = 0


class Loadout(NamedTuple):
    frame: Optional[str]          # the frame worn; None without one, or when it isn't a frame
    slots: List[Slot]             # the frame's slots, then the body's, by slot type
    extra: List[Slot]             # items with no free slot, or not of their list's kind
    used: Dict[str, float]        # power, mass, heat (constant load), cargo (inventory stacks)
    provided: Dict[str, float]    # each budget role the vocabulary has a stat for
    totals: Dict[str, float]      # every stat, totalled over body, frame, items and skill levels
    problems: List[Problem]


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def slot_counts(holder: Optional[Mapping]) -> Dict[str, int]:
    """Slot type -> how many, as a frame or a body lists them."""
    counts: Dict[str, int] = {}
    for slot in (holder or {}).get("slots", []) or []:
        if isinstance(slot, Mapping) and slot.get("slot_type"):
            counts[slot["slot_type"]] = counts.get(slot["slot_type"], 0) + slot.get("count", 1)
    return counts


def over(role: str, used: float, provided: float) -> bool:
    """Whether a budget doesn't fit: heat must stay below its maximum, the rest within."""
    if role == "heat":
        return bool(used) and used >= provided
    return used > provided


def loadout(char: Mapping, items: Mapping[str, Mapping], roles: Mapping[str, str],
            skills: Mapping[str, Mapping]) -> Loadout:
    """
    A character's loadout. 'items' and 'skills' are the pack's entries by id, 'roles' the
    vocabulary's budget roles (role -> stat id).
    """
    body = char.get("body", {}) if isinstance(char.get("body"), Mapping) else {}
    problems: List[Problem] = []
    frame = items.get(char.get("frame")) if "frame" in char else None
    if "frame" in char and (frame is None or frame.get("kind") != "frame"):
        if frame is not None:
            problems.append(Problem("not_frame", char["frame"], frame.get("kind")))
        elif char.get("frame"):
            problems.append(Problem("no_item", char["frame"], group="frame"))
        frame = None
    if char.get("fitted") and "frame" not in char:
        problems.append(Problem("no_frame"))
    worn: List[Mapping] = [body] + ([frame] if frame else [])
    slots: List[Slot] = []
    extra: List[Slot] = []
    used: Dict[str, float] = {"power": 0.0, "mass": 0.0, "heat": 0.0}
    for kind, host in HOSTS.items():
        capacity = slot_counts(frame if host == "frame" else body)
        filled: Dict[str, List[int]] = {t: [] for t in capacity}
        ids = char.get(GROUPS[kind], []) or []
        for index, item_id in enumerate(ids):
            item = items.get(item_id)
            if item is None or item.get("kind") != kind:
                extra.append(Slot(host, "", item_id, index))
                problems.append(Problem("wrong_kind", item_id, item.get("kind"), GROUPS[kind]) if item is not None
                                else Problem("no_item", item_id, group=GROUPS[kind]))
                continue
            worn.append(item)
            slot_type = item.get("slot_type", "")
            if len(filled.get(slot_type, [])) < capacity.get(slot_type, 0):
                filled[slot_type].append(index)
            else:
                extra.append(Slot(host, slot_type, item_id, index))
                problems.append(Problem("no_slot", item_id, kind, GROUPS[kind], host, slot_type))
            for budget, amount in (item.get("uses", {}) or {}).items():
                if _number(amount):
                    used[budget] = used.get(budget, 0.0) + amount
        for slot_type, count in capacity.items():
            taken = filled[slot_type]
            slots += [Slot(host, slot_type, ids[taken[n]], taken[n]) if n < len(taken) else Slot(host, slot_type, None, -1)
                      for n in range(count)]
    for skill_id, level in (char.get("skills", {}) or {}).items():         # skill levels add stats too
        for lv in (skills.get(skill_id) or {}).get("levels", []) or []:
            if isinstance(lv, Mapping) and isinstance(level, int) and lv.get("level", 0) <= level:
                worn.append(lv)
    totals: Dict[str, float] = {}
    for thing in worn:
        stats = thing.get("stats")
        for stat_id, value in (stats.items() if isinstance(stats, Mapping) else ()):
            if _number(value):
                totals[stat_id] = totals.get(stat_id, 0) + value
    stacks = 0
    for entry in char.get("inventory", []) or []:
        item = items.get(entry.get("item")) if isinstance(entry, Mapping) else None
        if item is not None:
            stacks += -(-entry.get("count", 1) // item.get("stack", 1))
    used["cargo"] = stacks
    provided = {role: totals.get(roles[role], 0) for role in BUDGETS if role in roles}
    for role, have in provided.items():
        if over(role, used[role], have):
            problems.append(Problem("over", role=role, used=used[role], provided=have))
    return Loadout(char.get("frame") if frame else None, slots, extra, used, provided, totals, problems)
