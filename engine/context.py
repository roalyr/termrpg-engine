"""
Resolving the grammar's references at run time: subjects and agents to characters
and relation keys, object references to placements, item picks to held items, and
amounts to numbers.
"""
import math
from typing import Any, List, Mapping, Optional, Tuple

from engine import rng, stats
from engine.content import Content
from engine.state import Ctx, GameState, char_key, faction_key
from engine.stats import Slot


# --- Parties -------------------------------------------------------------------

def leader_of(state: GameState, char_id: str) -> str:
    """The top of a character's leader chain (themselves if they lead or travel alone)."""
    seen = set()
    current = char_id
    while current in state.characters and state.characters[current].leader and current not in seen:
        seen.add(current)
        current = state.characters[current].leader
    return current


def party_of(state: GameState, char_id: str) -> List[str]:
    """The character first, then everyone else in their party."""
    top = leader_of(state, char_id)
    others = [cid for cid in state.characters if cid != char_id and leader_of(state, cid) == top]
    return [char_id] + others


# --- Subjects and agents ---------------------------------------------------------

def subjects(state: GameState, ctx: Ctx, subject: Any) -> List[str]:
    """The characters a subject means. Empty when it names nobody present (no target, unknown role)."""
    if subject == "self":
        found = [ctx.self_id]
    elif subject == "target":
        found = [ctx.target] if ctx.target else []
    elif subject == "player":
        found = [state.player]
    elif subject == "party":
        found = party_of(state, ctx.self_id)
    elif isinstance(subject, Mapping) and "character" in subject:
        found = [subject["character"]]
    elif isinstance(subject, Mapping) and "role" in subject:
        found = [ctx.roles[subject["role"]]] if subject["role"] in ctx.roles else []
    else:
        found = []
    return [cid for cid in found if cid in state.characters]


def agent(state: GameState, ctx: Ctx, value: Any) -> Optional[str]:
    """The relation key ('character:x' or 'faction:y') an agent means, or None."""
    if isinstance(value, Mapping) and "faction" in value:
        return faction_key(value["faction"])
    found = subjects(state, ctx, value)
    return char_key(found[0]) if found else None


def faction_of(content: Content, state: GameState, key: str) -> Optional[str]:
    """The faction key of a character key, if the character belongs to one."""
    if not key.startswith("character:"):
        return None
    cs = state.characters.get(key.split(":", 1)[1])
    faction = content.get("character", cs.source).get("faction") if cs else None
    return faction_key(faction) if faction else None


def relation(content: Content, state: GameState, of: str, toward: str) -> int:
    """
    How 'of' regards 'toward'. Without a direct view, the factions stand in: of's
    faction toward 'toward', of toward toward's faction, faction toward faction.
    Then the pack's relation_default.
    """
    of_faction, toward_faction = faction_of(content, state, of), faction_of(content, state, toward)
    for a, b in ((of, toward), (of_faction, toward), (of, toward_faction), (of_faction, toward_faction)):
        if a and b and b in state.relations.get(a, {}):
            return state.relations[a][b]
    return content.settings["relation_default"]


# --- Objects and items -----------------------------------------------------------

def placement(ctx: Ctx, ref: str) -> Optional[str]:
    """The placement an object reference means: 'this' or a placement id."""
    return ctx.this if ref == "this" else ref


def pick(content: Content, state: GameState, ctx: Ctx, char_id: str, item_pick: Mapping) -> Optional[Slot]:
    """Where the item an item pick means is held, or None."""
    cs = state.characters[char_id]
    if item_pick.get("used"):
        if ctx.used and ctx.used[0] == char_id:
            return (ctx.used[1], ctx.used[2])
        return None
    for slot, inst in stats.held(cs):
        view = stats.item_view(content, inst)
        if "item" in item_pick and inst.item == item_pick["item"]:
            return slot
        if "tag" in item_pick and item_pick["tag"] in view["tags"]:
            return slot
        if "slot_type" in item_pick and slot[0] == "equipped" \
                and view["slot_type"] == item_pick["slot_type"]:
            return slot
    return None


# --- Amounts ---------------------------------------------------------------------

def amount(content: Content, state: GameState, ctx: Ctx, value: Any) -> Tuple[float, GameState]:
    """
    A number from an amount: fixed, a seeded roll between min and max, or a stat or
    skill level of the subject times 'times' plus 'plus', rounded down.
    """
    if isinstance(value, (int, float)):
        return value, state
    if "min" in value:
        rolled, nxt = rng.between(state.rng, value["min"], value["max"])
        return rolled, state._replace(rng=nxt)
    found = subjects(state, ctx, value.get("subject", "self"))
    base = 0.0
    if found:
        cs = state.characters[found[0]]
        if "stat" in value:
            base = stats.current(content, cs, value["stat"])
        else:
            base = cs.skills.get(value["skill"], 0)
    return math.floor(base * value.get("times", 1) + value.get("plus", 0)), state
