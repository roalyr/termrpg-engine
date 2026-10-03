"""
The living world: events, and settling everything an action left waiting.

settle() runs after every player action. While no encounter is running, no choice
is waiting and no after-action screen is up, it starts a requested encounter, fires requested events (trigger_event),
considers the trigger moments the action queued (day_start, turn, enter_location)
and pays any turns effects still owe; until nothing is left.

At a trigger moment, every event with that trigger is considered, heaviest weight
first (then by id). An event can fire when it isn't used up ('repeat': false, fired
before) or cooling down ('cooldown' days), its cast can be filled, its 'when' holds,
and its 'chance' passes. All that can fire, fire, unless the pack limits
events_per_trigger; then that many are picked by weight from those that can.

Casting: for each role in order, candidates come from 'from' (anyone in play, the
player's location, or the player's party), shuffled by the seed; the first one not
already cast whose 'when' holds (self is the candidate; earlier roles are known)
gets the role. A fixed 'character' must be in play and meet 'when'. An optional role
may stay empty; a required one that stays empty stops the event.

Firing: the event's text and effects run with self as the player and the cast as
roles. With notify off, the messages it produces are dropped. Requested (manual)
events skip chance and cooldown but still need their cast and 'when'. When an event
leaves a choice waiting, the rest of its trigger moment waits as requests until the
choice is answered.
"""
from typing import Dict, List, Optional, Tuple

from engine import conditions, context, encounter, rng, turns
from engine.content import Content
from engine.effects import run
from engine.frozen import Record, freeze
from engine.state import Ctx, GameState, Message, day_of

MAX_STEPS = 200  # a guard against events that keep triggering each other


def settle(content: Content, state: GameState) -> GameState:
    """Handles everything an action left waiting: encounters, requested events, triggers, owed time."""
    for _ in range(MAX_STEPS):
        if state.pending is not None or state.encounter is not None or state.debrief is not None:
            break
        if state.encounter_request:
            state = encounter.begin(content, state)
        elif state.event_requests:
            event_id, rest = state.event_requests[0], state.event_requests[1:]
            state = fire(content, state._replace(event_requests=rest), event_id, manual=True)
        elif state.triggers:
            trigger, rest = state.triggers[0], state.triggers[1:]
            state = consider(content, state._replace(triggers=rest), trigger)
        elif state.turns_owed:
            state = turns.advance(content, state, 0)
        else:
            break
    return state


def consider(content: Content, state: GameState, trigger: str) -> GameState:
    """Fires the events of one trigger moment."""
    candidates = sorted((e for e in content.all("event").values() if e["trigger"] == trigger),
                        key=lambda e: (-e["weight"], e["id"]))
    ready: List[Tuple[Record, Dict[str, str]]] = []
    for event in candidates:
        if not _available(content, state, event):
            continue
        roles, state = cast(content, state, event)
        if roles is None:
            continue
        ok, state = conditions.holds(content, state, Ctx(self_id=state.player, roles=freeze(roles)), event.get("when"))
        if not ok:
            continue
        hit, nxt = rng.chance(state.rng, event["chance"])
        state = state._replace(rng=nxt)
        if hit:
            ready.append((event, roles))
    limit = content.settings.get("events_per_trigger", 0)
    if limit and len(ready) > limit:
        chosen = []
        for _ in range(limit):
            index, nxt = rng.weighted(state.rng, [e["weight"] for e, _ in ready])
            state = state._replace(rng=nxt)
            chosen.append(ready.pop(index))
        ready = sorted(chosen, key=lambda pair: (-pair[0]["weight"], pair[0]["id"]))
    for index, (event, roles) in enumerate(ready):
        state = _run(content, state, event, roles)
        if state.pending is not None:
            # The rest wait until the choice is answered; their chance was already rolled.
            later = tuple(e["id"] for e, _ in ready[index + 1:])
            return state._replace(event_requests=later + state.event_requests)
    return state


def fire(content: Content, state: GameState, event_id: str, manual: bool = False) -> GameState:
    """Fires one event if it can. Manual requests skip chance and cooldown."""
    event = content.get("event", event_id)
    if not _available(content, state, event, ignore_cooldown=manual):
        return state
    roles, state = cast(content, state, event)
    if roles is None:
        return state
    ok, state = conditions.holds(content, state, Ctx(self_id=state.player, roles=freeze(roles)), event.get("when"))
    if not ok:
        return state
    if not manual:
        hit, nxt = rng.chance(state.rng, event["chance"])
        state = state._replace(rng=nxt)
        if not hit:
            return state
    return _run(content, state, event, roles)


def _available(content: Content, state: GameState, event: Record, ignore_cooldown: bool = False) -> bool:
    last = state.event_log.get(event["id"])
    if last is None:
        return True
    if not event.get("repeat", True):
        return False
    if ignore_cooldown or not event.get("cooldown"):
        return True
    return day_of(content, state.turn) - last >= event["cooldown"]


def cast(content: Content, state: GameState, event: Record) -> Tuple[Optional[Dict[str, str]], GameState]:
    """The event's roles filled by characters, or None when a required role can't be filled."""
    roles: Dict[str, str] = {}
    for role in event.get("cast", ()):
        if role.get("character"):
            pool = [role["character"]] if role["character"] in state.characters else []
        else:
            pool, state = _shuffled(state, _pool(state, role.get("from", "anyone")))
        chosen = None
        for candidate in pool:
            if candidate in roles.values():
                continue
            ok, state = conditions.holds(content, state, Ctx(self_id=candidate, roles=freeze(dict(roles))), role.get("when"))
            if ok:
                chosen = candidate
                break
        if chosen is not None:
            roles[role["role"]] = chosen
        elif not role.get("optional"):
            return None, state
    return roles, state


def _pool(state: GameState, source: str) -> List[str]:
    if source == "party":
        return context.party_of(state, state.player)
    if source == "here":
        here = state.characters[state.player].location
        return sorted(cid for cid, cs in state.characters.items() if cs.location == here)
    return sorted(state.characters)


def _shuffled(state: GameState, items: List[str]) -> Tuple[List[str], GameState]:
    items = list(items)
    generator = state.rng
    for i in range(len(items) - 1, 0, -1):
        j, generator = rng.between(generator, 0, i)
        items[i], items[j] = items[j], items[i]
    return items, state._replace(rng=generator)


def _run(content: Content, state: GameState, event: Record, roles: Dict[str, str]) -> GameState:
    state = state._replace(event_log=freeze({**state.event_log, event["id"]: day_of(content, state.turn)}))
    before = len(state.messages)
    if event.get("text"):
        state = state._replace(messages=state.messages + (Message("plain", content.text(event["text"])),))
    state = run(content, state, Ctx(self_id=state.player, roles=freeze(roles)), event["effects"])
    if not event.get("notify", True):
        state = state._replace(messages=state.messages[:before])
    return state
