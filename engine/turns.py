"""
Time. advance() processes turns one by one; actions call it with the turns they take,
and it also pays the turns that effects owe (spend_time).

Each turn, for every character in a location: the location's on_turn runs; each
status's on_turn runs once per stack, then its duration counts down and, when it runs
out, the status ends and its on_expire runs; timed stat changes count down and end.
A pending choice pauses time until it is answered.
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
    """Processes count turns, then any turns effects owe, until done or a choice is pending."""
    owed = count + state.turns_owed
    state = state._replace(turns_owed=0)
    processed = 0
    while owed > 0 and state.pending is None and processed < MAX_TURNS_PER_ACTION:
        state = _one_turn(content, state)
        processed += 1
        owed = owed - 1 + state.turns_owed
        state = state._replace(turns_owed=0)
    return state._replace(turns_owed=owed if state.pending is not None else 0)


def _one_turn(content: Content, state: GameState) -> GameState:
    before_day, before_phase = day_of(content, state.turn), phase_of(content, state.turn)
    state = state._replace(turn=state.turn + 1)
    if day_of(content, state.turn) != before_day:
        state = _say(state, "plain", content.message("day_start", day=day_of(content, state.turn)))
    elif phase_of(content, state.turn) != before_phase:
        phase = content.get("phase", phase_of(content, state.turn))
        state = _say(state, "plain", content.message("phase_start", phase=phase["name"], day=before_day))
    for cid in list(state.characters):
        cs = state.characters[cid]
        if cs.location is None:
            continue
        location = content.get("location", cs.location)
        state = run(content, state, Ctx(self_id=cid), location.get("on_turn", ()))
        state = _statuses(content, state, cid)
        state = _timed_mods(content, state, cid)
    return state


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
