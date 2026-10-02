"""
The game state: everything that changes during play. Content (the pack) never
changes; the state refers to it by id.

The state is immutable: rules return a new state with ._replace(). Every value is
plain data (strings, numbers, tuples, read-only mappings), so it can be saved as JSON.
"""
from typing import Any, Mapping, NamedTuple, Optional, Tuple

from engine.content import Content
from engine.frozen import Record, freeze
from engine.rng import Rng

Pos = Tuple[int, int]  # (row, column)


class ItemInst(NamedTuple):
    """
    An item someone holds. Items with a condition, modifications or changes are
    unique and have count 1; plain items stack up to their 'stack'.
    """
    item: str                          # content item id
    count: int = 1
    condition: Optional[int] = None    # current condition, for items that wear
    mods: Tuple[str, ...] = ()         # modification ids applied
    changes: Tuple[Record, ...] = ()   # modify_item changes applied


class StatMod(NamedTuple):
    """A change to a stat from modify_stat. Permanent when turns_left is None."""
    stat: str
    amount: float
    turns_left: Optional[int] = None


class StatusInst(NamedTuple):
    status: str
    stacks: int = 1
    turns_left: Optional[int] = None   # None: until removed


class CharState(NamedTuple):
    """One character in play: the player, an NPC, or a spawned copy of a template."""
    id: str
    source: str                        # content character id (differs for template copies)
    location: Optional[str] = None
    at: Optional[Pos] = None
    frame: Optional[ItemInst] = None
    fitted: Tuple[ItemInst, ...] = ()
    implants: Tuple[ItemInst, ...] = ()
    inventory: Tuple[ItemInst, ...] = ()
    body_slots: Mapping[str, int] = freeze({})   # implant slot type -> unlocked count
    skills: Mapping[str, int] = freeze({})       # skill -> level
    xp: Mapping[str, int] = freeze({})           # skill -> experience
    designs: Tuple[str, ...] = ()
    rank: int = 0
    leader: Optional[str] = None                 # party leader, if travelling with someone
    visited: Tuple[str, ...] = ()
    pools: Mapping[str, float] = freeze({})      # pool stat -> current value
    mods: Tuple[StatMod, ...] = ()
    statuses: Tuple[StatusInst, ...] = ()
    down: bool = False                           # health reached 0


class Message(NamedTuple):
    kind: str   # plain, gain, danger, quiet
    text: str


class Ctx(NamedTuple):
    """
    Who is who while a condition or effect runs: 'self', 'target', 'this' (a
    placement), cast roles, and the item that satisfied the current requirement.
    """
    self_id: str
    target: Optional[str] = None
    this: Optional[str] = None
    roles: Mapping[str, str] = freeze({})
    used: Optional[Tuple[str, str, int]] = None   # (character, 'frame'|'fitted'|'implants'|'inventory', index)


class Pending(NamedTuple):
    """A choose effect waiting for the player: its options and the effects that follow."""
    prompt: Optional[str]
    options: Tuple[Record, ...]
    ctx: Ctx
    rest: Tuple[Tuple[Record, Ctx], ...]


class GameState(NamedTuple):
    player: str
    turn: int                                         # turns since day 1 began
    rng: Rng
    characters: Mapping[str, CharState]
    object_states: Mapping[str, str] = freeze({})     # placement -> state
    flags: Mapping[str, int] = freeze({})
    relations: Mapping[str, Mapping[str, int]] = freeze({})   # agent key -> agent key -> value
    messages: Tuple[Message, ...] = ()
    pending: Optional[Pending] = None                 # a choice waiting for the player
    encounter_request: Optional[str] = None           # set by start_encounter (milestone 4)
    event_requests: Tuple[str, ...] = ()              # queued by trigger_event (milestone 6)
    spawned: int = 0                                  # counter for template copy ids
    focus: Optional[Tuple[str, str]] = None           # ('placement'|'character', id) the menu is about
    used: Mapping[str, int] = freeze({})              # 'owner:interaction' -> day it was last used
    turns_owed: int = 0                               # time spent by effects, processed after the action
    storage: Mapping[str, Tuple[ItemInst, ...]] = freeze({})   # placement -> items stored in it
    encounter: Optional[Any] = None                   # engine.encounter.EncounterState while fighting
    triggers: Tuple[str, ...] = ()                    # event trigger moments waiting to be settled
    event_log: Mapping[str, int] = freeze({})         # event -> day it last fired


# --- Time ---------------------------------------------------------------------

def day_length(content: Content) -> int:
    return sum(p["turns"] for p in _phases(content))


def _phases(content: Content) -> Tuple[Record, ...]:
    return tuple(content.all("phase").values())


def day_of(content: Content, turn: int) -> int:
    return turn // day_length(content) + 1


def phase_of(content: Content, turn: int) -> str:
    into = turn % day_length(content)
    for phase in _phases(content):
        if into < phase["turns"]:
            return phase["id"]
        into -= phase["turns"]
    return _phases(content)[-1]["id"]


def turn_at(content: Content, day: int, phase: Optional[str]) -> int:
    turn = (day - 1) * day_length(content)
    for p in _phases(content):
        if p["id"] == phase:
            break
        turn += p["turns"]
    else:
        turn = (day - 1) * day_length(content)
    return turn


# --- Agents -------------------------------------------------------------------

def char_key(char_id: str) -> str:
    return f"character:{char_id}"


def faction_key(faction_id: str) -> str:
    return f"faction:{faction_id}"


# --- A new game ---------------------------------------------------------------

def new_game(content: Content, seed: int) -> GameState:
    """The state at the start of a new game, as the pack describes it."""
    from engine import stats  # stats needs the state types defined above

    start = content.pack["start"]
    characters = {}
    for char_id, char in content.all("character").items():
        if char.get("template"):
            continue
        characters[char_id] = character_from(content, char_id, char_id)
    player = characters[start["player"]]
    player = player._replace(location=start["location"],
                             at=entry_point(content, start["location"], start.get("entry")))
    characters[player.id] = player
    for char_id, cs in characters.items():
        if cs.location and cs.at is None:
            characters[char_id] = cs._replace(at=entry_point(content, cs.location, None))
        if cs.location:
            characters[char_id] = characters[char_id]._replace(visited=(cs.location,))

    relations = {}
    for char_id, char in content.all("character").items():
        if char_id in characters:
            for view in char.get("views", ()):
                key = agent_key_static(view["toward"], char_id, player.id)
                if key:
                    relations.setdefault(char_key(char_id), {})[key] = view["value"]

    object_states = {pid: p["state"] for pid, p in content.all("placement").items() if p.get("state")}
    storage = {}
    for pid, p in content.all("placement").items():
        items: Tuple[ItemInst, ...] = ()
        for entry in p.get("contents", ()):
            items = add_items(content, items, entry["item"], entry["count"])
        if items:
            storage[pid] = items
    flags = {fid: f.get("default", 0) for fid, f in content.all("flag").items()}
    state = GameState(
        player=player.id,
        turn=turn_at(content, start["day"], start.get("phase")),
        rng=Rng(seed),
        characters=freeze(characters),
        object_states=freeze(object_states),
        flags=freeze(flags),
        relations=freeze(relations),
        storage=freeze(storage),
    )
    return state._replace(characters=freeze({cid: stats.fill_pools(content, cs) for cid, cs in characters.items()}))


def character_from(content: Content, state_id: str, source_id: str) -> CharState:
    """A character as its content record describes it, before pools are filled."""
    char = content.get("character", source_id)
    body = char["body"]
    slots = {}
    for slot in body.get("slots", ()):
        slots[slot["slot_type"]] = slots.get(slot["slot_type"], 0) + slot["count"]
    inventory: Tuple[ItemInst, ...] = ()
    for entry in char.get("inventory", ()):
        inventory = add_items(content, inventory, entry["item"], entry["count"])
    skills = dict(char.get("skills", {}))
    xp = {skill_id: _xp_for_level(content, skill_id, level) for skill_id, level in skills.items()}
    return CharState(
        id=state_id,
        source=source_id,
        location=char.get("location"),
        at=tuple(char["at"]) if char.get("at") else None,
        frame=new_item(content, char["frame"]) if char.get("frame") else None,
        fitted=tuple(new_item(content, i) for i in char.get("fitted", ())),
        implants=tuple(new_item(content, i) for i in char.get("implants", ())),
        inventory=inventory,
        body_slots=freeze(slots),
        skills=freeze(skills),
        xp=freeze(xp),
        designs=tuple(char.get("designs", ())),
        rank=char.get("rank", 0),
        leader=char.get("leader"),
    )


def _xp_for_level(content: Content, skill_id: str, level: int) -> int:
    reached = [lv["xp"] for lv in content.get("skill", skill_id)["levels"] if lv["level"] <= level]
    return max(reached, default=0)


def agent_key_static(agent, self_id: str, player_id: str) -> Optional[str]:
    """The relation key of an agent written in content, where 'self' is the given character."""
    if agent == "self":
        return char_key(self_id)
    if agent == "player":
        return char_key(player_id)
    if isinstance(agent, Mapping):
        if "character" in agent:
            return char_key(agent["character"])
        if "faction" in agent:
            return faction_key(agent["faction"])
    return None  # 'target' means nothing in a starting view


def entry_point(content: Content, location_id: str, placement_id: Optional[str]) -> Pos:
    """
    Where an arrival appears: on the placement given (or the location's entry), or the
    grid centre. A solid placement can't be stood on, so arrivals land on the nearest
    free floor tile instead.
    """
    from engine import world  # world needs the state types defined above
    location = content.get("location", location_id)
    chosen = placement_id or location.get("entry")
    if chosen:
        spot = tuple(content.get("placement", chosen)["at"])
    else:
        grid = location["grid"]
        spot = (grid["height"] // 2, grid["width"] // 2)
    return world.nearest_standable(content, location_id, spot)


# --- Items --------------------------------------------------------------------

def new_item(content: Content, item_id: str) -> ItemInst:
    item = content.get("item", item_id)
    return ItemInst(item=item_id, condition=item.get("condition"))


def is_plain(content: Content, inst: ItemInst) -> bool:
    """Plain items stack: no condition, no modifications, no changes."""
    return inst.condition is None and not inst.mods and not inst.changes \
        and content.get("item", inst.item).get("condition") is None


def add_items(content: Content, inventory: Tuple[ItemInst, ...], item_id: str, count: int) -> Tuple[ItemInst, ...]:
    """Inventory with count more of an item: topping up plain stacks first, then new stacks."""
    item = content.get("item", item_id)
    items = list(inventory)
    if item.get("condition") is not None:
        return tuple(items) + tuple(new_item(content, item_id) for _ in range(count))
    limit = item.get("stack", 1)
    for i, inst in enumerate(items):
        if count <= 0:
            break
        if inst.item == item_id and is_plain(content, inst) and inst.count < limit:
            add = min(limit - inst.count, count)
            items[i] = inst._replace(count=inst.count + add)
            count -= add
    while count > 0:
        add = min(limit, count)
        items.append(ItemInst(item=item_id, count=add))
        count -= add
    return tuple(items)
