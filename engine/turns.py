"""
Time. advance() processes turns one by one; actions call it with the turns they take,
and it also pays the turns that effects owe (spend_time).

Each turn, for every character in the player's location, that location's on_turn runs
(its 'message' and 'choose' steps only for the player, so a line shows once and a
question is only ever the player's); for every character in a location, each
status's on_turn runs once per stack, then its duration counts down and, when it runs
out, the status ends and its on_expire runs; timed stat changes count down and end.
A pending choice pauses time until it is answered.

A turn that brings a trigger moment some event listens to (a new day, or 'turn') ends
the stretch early: the rest is owed, so events.settle() can handle that moment at its
own time before more turns pass. Only listened-to moments are queued, and at most one
'turn' moment waits at a time (turns passing in a fight count as one).
"""
from engine import stats
from engine.content import Content
from engine.effects import run
from engine.frozen import freeze
from engine.state import Ctx, GameState, Message, day_of, phase_of

MAX_TURNS_PER_ACTION = 1000  # a guard against effects that keep spending time


def today(content: Content, state: GameState) -> int:
    return day_of(content, state.turn)


def advance(content: Content, state: GameState, count: int) -> GameState:
    """
    Processes count turns, then any turns effects owe, until done, a choice is pending,
    or a turn queued a trigger moment for events; then the rest stays owed.
    """
    owed = count + state.turns_owed
    state = state._replace(turns_owed=0)
    processed = 0
    while owed > 0 and state.pending is None and processed < MAX_TURNS_PER_ACTION:
        queued = len(state.triggers)
        state = _one_turn(content, state)
        processed += 1
        owed = owed - 1 + state.turns_owed
        state = state._replace(turns_owed=0)
        if len(state.triggers) > queued and state.encounter is None:
            return state._replace(turns_owed=owed)          # events.settle() goes on from here
    return state._replace(turns_owed=owed if state.pending is not None else 0)


def _listened(content: Content, trigger: str) -> bool:
    return any(event["trigger"] == trigger for event in content.all("event").values())


def _one_turn(content: Content, state: GameState) -> GameState:
    before_day, before_phase = day_of(content, state.turn), phase_of(content, state.turn)
    state = state._replace(turn=state.turn + 1)
    if _listened(content, "turn") and "turn" not in state.triggers:
        state = state._replace(triggers=state.triggers + ("turn",))
    if day_of(content, state.turn) != before_day:
        state = _say(state, "plain", content.message("day_start", day=day_of(content, state.turn)))
        if _listened(content, "day_start"):
            state = state._replace(triggers=state.triggers + ("day_start",))
    elif phase_of(content, state.turn) != before_phase:
        phase = content.get("phase", phase_of(content, state.turn))
        state = _say(state, "plain", content.message("phase_start", phase=phase["name"], day=before_day))
    here = state.characters[state.player].location
    for cid in list(state.characters):
        cs = state.characters[cid]
        if cs.location is None:
            continue
        if cs.location == here:                    # places only act where the player is
            on_turn = content.get("location", here).get("on_turn", ())
            state = run(content, state, Ctx(self_id=cid), on_turn if cid == state.player else _silent(on_turn))
        state = _statuses(content, state, cid)
        state = _timed_mods(content, state, cid)
    return state


def _silent(effects):
    """The effects without their 'message' and 'choose' steps (nested 'if' branches too)."""
    kept = []
    for effect in effects:
        if effect["op"] in ("message", "choose"):
            continue
        if effect["op"] == "if":
            effect = freeze({**effect, "then": _silent(effect.get("then", ())), "else": _silent(effect.get("else", ()))})
        kept.append(effect)
    return tuple(kept)


def _statuses(content: Content, state: GameState, cid: str) -> GameState:
    for inst in state.characters[cid].statuses:
        record = content.get("status", inst.status)
        for _ in range(inst.stacks):
            state = run(content, state, Ctx(self_id=cid), record.get("on_turn", ()))
    cs = state.characters[cid]
    kept, ended = [], []
    for inst in cs.statuses:
        if inst.turns_left is None:
            kept.append(inst)
        elif inst.turns_left <= 1:
            ended.append(inst)
        else:
            kept.append(inst._replace(turns_left=inst.turns_left - 1))
    state = _set(state, cs._replace(statuses=tuple(kept)))
    for inst in ended:
        record = content.get("status", inst.status)
        if cid == state.player or state.characters[cid].location == state.characters[state.player].location:
            state = _say(state, "plain", content.message(
                "status_ended", character=content.get("character", cs.source)["name"], status=record["name"]))
        state = run(content, state, Ctx(self_id=cid), record.get("on_expire", ()))
    return state


def _timed_mods(content: Content, state: GameState, cid: str) -> GameState:
    cs = state.characters[cid]
    mods = tuple(m if m.turns_left is None else m._replace(turns_left=m.turns_left - 1)
                 for m in cs.mods if m.turns_left is None or m.turns_left > 1)
    if mods == cs.mods:
        return state
    return _set(state, stats.clamp_pools(content, cs._replace(mods=mods)))


def _set(state: GameState, cs) -> GameState:
    chars = dict(state.characters)
    chars[cs.id] = cs
    return state._replace(characters=freeze(chars))


def _say(state: GameState, kind: str, text: str) -> GameState:
    return state._replace(messages=state.messages + (Message(kind, text),))
