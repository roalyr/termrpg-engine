"""
The walkable world: tiles, movement, what the player is looking at, and the menu of
things they can do with it.

Walking onto a non-solid placement (a door, a tap) puts it in focus. Bumping into a
solid object or another character puts them in focus without moving. The menu lists
what can be done with the focused thing: its interactions, 'go' for exits, 'talk'
for people with dialogue, and 'inspect'. Every action returns the new state; the
turns it takes are processed by engine.turns.
"""
from collections import deque
from typing import List, Mapping, NamedTuple, Optional, Tuple

from engine import conditions, context, stats, turns
from engine.content import Content
from engine.effects import run
from engine.frozen import Record, freeze
from engine.state import Ctx, GameState, Message, Pos

DIRECTIONS = {"w": (-1, 0), "s": (1, 0), "a": (0, -1), "d": (0, 1)}
RESERVED_KEYS = set("wasdixqpcgt") | set("1234")
SPARE_KEYS = "ufrbehjklmnoyvz"


# --- Tiles -------------------------------------------------------------------------

def tile(content: Content, location_id: str, pos: Pos) -> str:
    """'#' wall, '.' floor, ' ' nothing (also outside the grid)."""
    grid = content.get("location", location_id)["grid"]
    row, col = pos
    if not (0 <= row < grid["height"] and 0 <= col < grid["width"]):
        return " "
    if grid.get("rows"):
        return grid["rows"][row][col]
    edge = row in (0, grid["height"] - 1) or col in (0, grid["width"] - 1)
    return "#" if edge else "."


def placement_at(content: Content, location_id: str, pos: Pos) -> Optional[Record]:
    for p in content.all("placement").values():
        if p["location"] == location_id and tuple(p["at"]) == tuple(pos):
            return p
    return None


def standable(content: Content, location_id: str, pos: Pos) -> bool:
    """Floor without a solid object, or a wall tile holding a non-solid placement (a door)."""
    placed = placement_at(content, location_id, pos)
    if placed is not None:
        return not placed.get("solid", False) and tile(content, location_id, pos) != " "
    return tile(content, location_id, pos) == "."


def nearest_standable(content: Content, location_id: str, start: Pos) -> Pos:
    """The start tile if it can be stood on, otherwise the closest floor tile that can."""
    if standable(content, location_id, start):
        return start
    seen, queue = {start}, deque([start])
    while queue:
        row, col = queue.popleft()
        for dr, dc in DIRECTIONS.values():
            nxt = (row + dr, col + dc)
            if nxt in seen or tile(content, location_id, nxt) == " ":
                continue
            if tile(content, location_id, nxt) == "." and standable(content, location_id, nxt):
                return nxt
            seen.add(nxt)
            queue.append(nxt)
    return start


def others_here(state: GameState) -> List[str]:
    """Characters in the player's location who aren't travelling with the player."""
    player = state.characters[state.player]
    party = set(context.party_of(state, state.player))
    return [cid for cid, cs in state.characters.items()
            if cid not in party and cs.location == player.location and cs.at is not None]


def character_at(state: GameState, pos: Pos) -> Optional[str]:
    for cid in others_here(state):
        if tuple(state.characters[cid].at) == tuple(pos):
            return cid
    return None


# --- Movement --------------------------------------------------------------------------

def _with_player(state: GameState, **changes) -> GameState:
    chars = dict(state.characters)
    chars[state.player] = chars[state.player]._replace(**changes)
    return state._replace(characters=freeze(chars))


def _focus_at(content: Content, state: GameState, pos: Pos) -> Optional[Tuple[str, str]]:
    placed = placement_at(content, state.characters[state.player].location, pos)
    return ("placement", placed["id"]) if placed else None


def move(content: Content, state: GameState, key: str) -> GameState:
    """
    One step. Bumping into a person or a solid object focuses them; walls do nothing at
    all (no time, no message); a step costs one turn.
    """
    if state.pending is not None or key not in DIRECTIONS:
        return state
    player = state.characters[state.player]
    dr, dc = DIRECTIONS[key]
    target = (player.at[0] + dr, player.at[1] + dc)
    who = character_at(state, target)
    if who:
        return state._replace(focus=("character", who), messages=())
    placed = placement_at(content, player.location, target)
    if placed is not None and placed.get("solid"):
        return state._replace(focus=("placement", placed["id"]), messages=())
    if not standable(content, player.location, target):
        return state
    state = state._replace(messages=())
    for member in context.party_of(state, state.player)[1:]:
        chars = dict(state.characters)
        chars[member] = chars[member]._replace(at=target)
        state = state._replace(characters=freeze(chars))
    state = _with_player(state, at=target)._replace(focus=_focus_at(content, state, target))
    return turns.advance(content, state, 1)


# --- The menu ----------------------------------------------------------------------------

class Option(NamedTuple):
    key: str
    label: str
    available: bool
    hint: Optional[str]
    kind: str                        # 'interaction', 'go', 'talk', 'inspect'
    interaction: Optional[Record]


class Menu(NamedTuple):
    title: str
    options: Tuple[Option, ...]


def focus_name(content: Content, state: GameState) -> Optional[str]:
    if state.focus is None:
        return None
    kind, ref = state.focus
    if kind == "placement":
        return content.get("placement", ref)["name"]
    return content.get("character", state.characters[ref].source)["name"]


def _ctx_for(state: GameState) -> Ctx:
    kind, ref = state.focus
    if kind == "placement":
        return Ctx(self_id=state.player, this=ref)
    return Ctx(self_id=state.player, target=ref)


def _usage_key(state: GameState, interaction_id: str) -> str:
    return f"{state.focus[0]}:{state.focus[1]}:{interaction_id}"


def _used_up(content: Content, state: GameState, interaction: Record) -> bool:
    last = state.used.get(_usage_key(state, interaction["id"]))
    if last is None:
        return False
    if interaction["repeat"] == "once":
        return True
    return interaction["repeat"] == "daily" and last == turns.today(content, state)


def _interactions(content: Content, state: GameState) -> Tuple[Record, ...]:
    kind, ref = state.focus
    if kind == "placement":
        return content.get("placement", ref).get("interactions", ())
    return content.get("character", state.characters[ref].source).get("interactions", ())


def menu(content: Content, state: GameState) -> Optional[Menu]:
    """What the player can do with the focused thing, or None with nothing in focus."""
    if state.focus is None or not _in_reach(content, state):
        return None
    ctx = _ctx_for(state)
    options: List[Option] = []
    taken = set()
    for interaction in _interactions(content, state):
        shown, state = conditions.holds(content, state, ctx, interaction.get("shown_if"))
        if not shown:
            continue
        ok, state = conditions.holds(content, state, ctx, interaction.get("requires"))
        hint = content.text(interaction["hint"]) if not ok and interaction.get("hint") else None
        if ok and _used_up(content, state, interaction):
            ok, hint = False, content.message("already_used")
        key = _assign_key(interaction.get("key"), taken)
        taken.add(key)
        options.append(Option(key, content.text(interaction["label"]), ok, hint, "interaction", interaction))
    kind, ref = state.focus
    if kind == "placement" and content.get("placement", ref).get("exit"):
        exit_ = content.get("placement", ref)["exit"]
        ok, state = conditions.holds(content, state, ctx, exit_.get("requires"))
        label = content.text(exit_["label"]) if exit_.get("label") else \
            content.message("go_to", destination=_destination_name(content, exit_))
        hint = content.text(exit_["hint"]) if not ok and exit_.get("hint") else None
        options.append(Option("g", label, ok, hint, "go", None))
    if kind == "character" and content.get("character", state.characters[ref].source).get("talk"):
        options.append(Option("t", content.message("talk"), True, None, "talk", None))
    options.append(Option("i", content.message("inspect"), True, None, "inspect", None))
    return Menu(focus_name(content, state), tuple(options))


def _assign_key(wanted: Optional[str], taken: set) -> str:
    if wanted and wanted not in RESERVED_KEYS and wanted not in taken:
        return wanted
    return next(k for k in SPARE_KEYS if k not in taken)


def _destination_name(content: Content, exit_: Record) -> str:
    if exit_.get("location"):
        return content.get("location", exit_["location"])["name"]
    return content.get("zone", exit_["zone"])["name"]


def _in_reach(content: Content, state: GameState) -> bool:
    """The focused thing is on the player's tile or next to it, in the same location."""
    player = state.characters[state.player]
    kind, ref = state.focus
    if kind == "placement":
        placed = content.get("placement", ref)
        where, at = placed["location"], placed["at"]
    else:
        cs = state.characters[ref]
        where, at = cs.location, cs.at
    if where != player.location or at is None:
        return False
    return abs(at[0] - player.at[0]) + abs(at[1] - player.at[1]) <= 1


# --- Acting --------------------------------------------------------------------------------

def act(content: Content, state: GameState, key: str) -> GameState:
    """Does the menu option with this key. Unavailable options show their hint and take no time."""
    current = menu(content, state)
    if current is None or state.pending is not None:
        return state
    option = next((o for o in current.options if o.key == key), None)
    if option is None:
        return state
    state = state._replace(messages=())
    if not option.available:
        return _say(state, "plain", option.hint or content.message("unavailable"))
    if option.kind == "inspect":
        return _say(state, "quiet", _description(content, state))
    if option.kind == "talk":
        return _talk(content, state)
    if option.kind == "go":
        return _go(content, state)
    return _interact(content, state, option.interaction)


def _say(state: GameState, kind: str, text: str) -> GameState:
    return state._replace(messages=state.messages + (Message(kind, text),))


def _description(content: Content, state: GameState) -> str:
    kind, ref = state.focus
    if kind == "placement":
        record = content.get("placement", ref)
        return content.text(record.get("description") or record["name"])
    record = content.get("character", state.characters[ref].source)
    parts = [record["name"]] + ([content.text(record["title"])] if record.get("title") else [])
    text = " - ".join(parts)
    return f"{text}. {content.text(record['description'])}" if record.get("description") else text


def _interact(content: Content, state: GameState, interaction: Record) -> GameState:
    ctx = _ctx_for(state)._replace(used=used_item(content, state, _ctx_for(state), interaction.get("requires")))
    used = dict(state.used)
    used[_usage_key(state, interaction["id"])] = turns.today(content, state)
    state = state._replace(used=freeze(used))
    state = run(content, state, ctx, interaction["effects"])
    return turns.advance(content, state, interaction["time"])


def _go(content: Content, state: GameState) -> GameState:
    placed = content.get("placement", state.focus[1])
    exit_ = placed["exit"]
    state = state._replace(focus=None)
    state = run(content, state, Ctx(self_id=state.player, this=placed["id"]),
                [freeze({"op": "move_to", "location": exit_["location"], "subject": "self",
                         **({"entry": exit_["entry"]} if exit_.get("entry") else {})})])
    player = state.characters[state.player]
    state = state._replace(focus=_focus_at(content, state, player.at))
    return turns.advance(content, state, exit_["time"])


def _talk(content: Content, state: GameState) -> GameState:
    speaker = state.focus[1]
    record = content.get("character", state.characters[speaker].source)
    ctx = Ctx(self_id=speaker, target=state.player)
    for line in record["talk"]:
        ok, state = conditions.holds(content, state, ctx, line.get("when"))
        if ok:
            state = _say(state, "quiet", f"{record['name']}: {content.text(line['text'])}")
            state = run(content, state, ctx, line.get("effects", ()))
            break
    return turns.advance(content, state, 1)


def wait(content: Content, state: GameState) -> GameState:
    """Lets one turn pass."""
    return turns.advance(content, state._replace(messages=()), 1)


# --- Which item did the work ------------------------------------------------------------------

def used_item(content: Content, state: GameState, ctx: Ctx, cond: Optional[Mapping]) -> Optional[Tuple[str, str, int]]:
    """
    The item that satisfied a requirement: the first item of 'self' carrying a tag that
    a passing has_tag check asked for. Effects reach it with the item pick {"used": true}.
    """
    if cond is None:
        return None
    for leaf in _has_tag_leaves(cond):
        if leaf.get("subject", "self") != "self":
            continue
        ok, _ = conditions.evaluate(content, state, ctx, leaf)
        if not ok:
            continue
        cs = state.characters[ctx.self_id]
        for slot, inst in stats.held(cs):
            if not stats.is_broken(inst) and leaf["tag"] in stats.item_view(content, inst)["tags"]:
                return (ctx.self_id, slot[0], slot[1])
    return None


def _has_tag_leaves(cond: Mapping) -> List[Mapping]:
    if "all" in cond or "any" in cond:
        return [leaf for part in cond.get("all", cond.get("any")) for leaf in _has_tag_leaves(part)]
    if "not" in cond:
        return []
    return [cond] if cond.get("check") == "has_tag" else []
