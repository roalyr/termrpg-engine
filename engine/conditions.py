"""
The condition evaluator: every check in the grammar.

evaluate() returns the answer and the state, because a 'chance' check draws from the
state's randomness. A check on a group (subject 'party') passes when any member
passes; a check whose subject names nobody fails.
"""
from typing import Any, Callable, Dict, Mapping, Tuple

from engine import context, rng, stats
from engine.content import Content
from engine.state import Ctx, GameState, day_of, phase_of

Result = Tuple[bool, GameState]


def evaluate(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    """Whether a condition holds."""
    if "all" in cond:
        for part in cond["all"]:
            ok, state = evaluate(content, state, ctx, part)
            if not ok:
                return False, state
        return True, state
    if "any" in cond:
        for part in cond["any"]:
            ok, state = evaluate(content, state, ctx, part)
            if ok:
                return True, state
        return False, state
    if "not" in cond:
        ok, state = evaluate(content, state, ctx, cond["not"])
        return not ok, state
    return CHECKS[cond["check"]](content, state, ctx, cond)


def holds(content: Content, state: GameState, ctx: Ctx, cond: Any) -> Result:
    """Like evaluate(), but a missing condition (None) holds."""
    if cond is None:
        return True, state
    return evaluate(content, state, ctx, cond)


def _within(value: float, cond: Mapping) -> bool:
    return ("min" not in cond or value >= cond["min"]) and ("max" not in cond or value <= cond["max"])


def _any_subject(state: GameState, ctx: Ctx, cond: Mapping, test: Callable[[str], bool]) -> Result:
    return any(test(cid) for cid in context.subjects(state, ctx, cond.get("subject", "self"))), state


# --- Checks ------------------------------------------------------------------------

def _has_tag(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    source = cond.get("source", "any")

    def has(cid: str) -> bool:
        cs = state.characters[cid]
        tags = []
        if source in ("any", "equipped"):
            tags += stats.own_tags(content, cs, "equipped")
        if source in ("any", "carried"):
            tags += stats.own_tags(content, cs, "carried")
        if source in ("any", "body"):
            tags += stats.own_tags(content, cs, "body")
        if source in ("any", "party"):
            for other in context.party_of(state, cid)[1:]:
                ocs = state.characters[other]
                for own in ("equipped", "carried", "body"):
                    tags += stats.own_tags(content, ocs, own)
        return cond["tag"] in tags
    return _any_subject(state, ctx, cond, has)


def _has_item(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    source = cond.get("source", "carried")    # 'carried' matches what take_item can take

    def where(slot) -> bool:
        return source == "any" or (slot[0] == "inventory") == (source == "carried")

    def has(cid: str) -> bool:
        held = sum(inst.count for slot, inst in stats.held(state.characters[cid])
                   if inst.item == cond["item"] and where(slot))
        return held >= cond.get("count", 1)
    return _any_subject(state, ctx, cond, has)


def _skill(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    return _any_subject(state, ctx, cond,
                        lambda cid: state.characters[cid].skills.get(cond["skill"], 0) >= cond["min"])


def _stat(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    return _any_subject(state, ctx, cond,
                        lambda cid: _within(stats.current(content, state.characters[cid], cond["stat"]), cond))


def _item_condition(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    def ok(cid: str) -> bool:
        slot = context.pick(content, state, ctx, cid, cond["pick"])
        if slot is None:
            return False
        inst = stats.item_at(state.characters[cid], slot)
        return inst.condition is None or _within(inst.condition, cond)
    return _any_subject(state, ctx, cond, ok)


def _knows_design(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    return _any_subject(state, ctx, cond, lambda cid: cond["item"] in state.characters[cid].designs)


def _status(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    return _any_subject(state, ctx, cond,
                        lambda cid: any(s.status == cond["status"] for s in state.characters[cid].statuses))


def _flag(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    return _within(state.flags.get(cond["flag"], 0), cond), state


def _location(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    return _any_subject(state, ctx, cond, lambda cid: state.characters[cid].location == cond["location"])


def _region(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    def inside(cid: str) -> bool:
        loc = state.characters[cid].location
        region = content.get("location", loc)["region"] if loc else None
        while region:
            if region == cond["region"]:
                return True
            region = content.get("region", region).get("parent")
        return False
    return _any_subject(state, ctx, cond, inside)


def _visited(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    return _any_subject(state, ctx, cond, lambda cid: cond["location"] in state.characters[cid].visited)


def _object_state(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    pid = context.placement(ctx, cond["object"])
    return (pid is not None and state.object_states.get(pid) == cond["state"]), state


def _size(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    return _any_subject(state, ctx, cond, lambda cid: _within(stats.size(content, state.characters[cid]), cond))


def _fits(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    """Things without holds_size: locations and objects let anything through; items hold nothing."""
    if "into_object" in cond:
        pid = context.placement(ctx, cond["into_object"])
        limit = content.get("placement", pid).get("holds_size") if pid else -1
    elif "into_location" in cond:
        limit = content.get("location", cond["into_location"]).get("holds_size")
    else:
        limit = content.get("item", cond["into_item"]).get("holds_size")
        limit = -1 if limit is None else limit
    if limit is None:
        return True, state
    if "item" in cond:
        return content.get("item", cond["item"])["size"] <= limit, state
    return _any_subject(state, ctx, cond, lambda cid: stats.size(content, state.characters[cid]) <= limit)


def _in_party(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    leaders = context.subjects(state, ctx, cond.get("leader", "player"))
    if not leaders:
        return False, state
    top = context.leader_of(state, leaders[0])
    return _any_subject(state, ctx, cond, lambda cid: context.leader_of(state, cid) == top)


def _relation(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    of = context.agent(state, ctx, cond["of"])
    toward = context.agent(state, ctx, cond.get("toward", "player"))
    if of is None or toward is None:
        return False, state
    return _within(context.relation(content, state, of, toward), cond), state


def _rank(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    return _any_subject(state, ctx, cond, lambda cid: _within(state.characters[cid].rank, cond))


def _time(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    day = day_of(content, state.turn)
    ok = ("phase" not in cond or phase_of(content, state.turn) == cond["phase"]) \
        and ("day_min" not in cond or day >= cond["day_min"]) \
        and ("day_max" not in cond or day <= cond["day_max"])
    return ok, state


def _chance(content: Content, state: GameState, ctx: Ctx, cond: Mapping) -> Result:
    hit, nxt = rng.chance(state.rng, cond["p"])
    return hit, state._replace(rng=nxt)


CHECKS: Dict[str, Callable[[Content, GameState, Ctx, Mapping], Result]] = {
    "has_tag": _has_tag, "has_item": _has_item, "skill": _skill, "stat": _stat,
    "item_condition": _item_condition, "knows_design": _knows_design, "status": _status,
    "flag": _flag, "location": _location, "region": _region, "visited": _visited,
    "object_state": _object_state, "size": _size, "fits": _fits, "in_party": _in_party,
    "relation": _relation, "rank": _rank, "time": _time, "chance": _chance,
}
