"""
The effect interpreter.

run() applies a list of effects in order and returns the new state. Effects run from
a queue: 'if' puts its chosen branch next; a character going down puts their
on_defeat next; arriving somewhere puts the location's on_enter next; 'choose' stops
the queue and leaves the rest in state.pending until choose_option() is called.

An effect on a group (subject 'party') applies to each member; an effect whose
subject names nobody does nothing. Messages are shown only for what the player can
see: their own character, and characters in the player's location.

Encounters and events come in later milestones: start_encounter and trigger_event
leave a request in the state, and end_encounter does nothing outside an encounter.
spend_time adds to the turns owed, which engine.turns processes after the action.
"""
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from engine import context, stats
from engine.conditions import evaluate, holds
from engine.content import Content
from engine.frozen import Record, freeze
from engine.state import (CharState, Ctx, GameState, ItemInst, Message, Pending, StatMod, StatusInst,
                          add_items, entry_point, is_plain)

Work = List[Tuple[Record, Ctx]]
Handler = Callable[[Content, GameState, Ctx, Record], Tuple[GameState, Work]]


def run(content: Content, state: GameState, ctx: Ctx, effects: Sequence[Record]) -> GameState:
    """Applies effects in order. Stops at a 'choose', leaving the rest pending."""
    return _drain(content, state, [(e, ctx) for e in effects])


def choose_option(content: Content, state: GameState, index: int) -> GameState:
    """Resumes a pending choice with the option at index. Unavailable options leave the choice pending."""
    pending = state.pending
    if pending is None or not 0 <= index < len(pending.options):
        return state
    option = pending.options[index]
    ok, state = holds(content, state, pending.ctx, option.get("condition"))
    if not ok:
        return _say(state, "plain", content.text(option["hint"])) if option.get("hint") else state
    queue = [(e, pending.ctx) for e in option["effects"]] + list(pending.rest)
    return _drain(content, state._replace(pending=None), queue)


def _drain(content: Content, state: GameState, queue: Work) -> GameState:
    while queue:
        effect, ctx = queue.pop(0)
        if effect["op"] == "choose":
            return state._replace(pending=Pending(
                prompt=content.text(effect["prompt"]) if effect.get("prompt") else None,
                options=tuple(effect["options"]), ctx=ctx, rest=tuple(queue)))
        state, follow = HANDLERS[effect["op"]](content, state, ctx, effect)
        queue[:0] = follow
    return state


# --- Helpers -----------------------------------------------------------------------

def _say(state: GameState, kind: str, text: str) -> GameState:
    return state._replace(messages=state.messages + (Message(kind, text),))


def _visible(state: GameState, char_id: str) -> bool:
    player = state.characters[state.player]
    cs = state.characters[char_id]
    return char_id == state.player or (cs.location is not None and cs.location == player.location)


def _set(state: GameState, cs: CharState) -> GameState:
    chars = dict(state.characters)
    chars[cs.id] = cs
    return state._replace(characters=freeze(chars))


def _who(state: GameState, ctx: Ctx, effect: Record, default: str = "self") -> List[str]:
    return context.subjects(state, ctx, effect.get("subject", default))


def _number(content: Content, state: GameState, ctx: Ctx, value) -> Tuple[float, GameState]:
    return context.amount(content, state, ctx, value)


def _name_list(content: Content, counts: Sequence[Tuple[str, int]]) -> str:
    parts = [f"{content.get('item', i)['name']}" + (f" x{n}" if n > 1 else "") for i, n in counts]
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + content.message("list_and") + parts[-1]


def _give(content: Content, state: GameState, char_id: str, item_id: str, count: int) -> Tuple[GameState, int]:
    """Gives as many as fit in cargo. Returns the state and how many were given."""
    cs = state.characters[char_id]
    capacity = int(stats.budget_provided(content, cs, "cargo"))
    given = 0
    inventory = cs.inventory
    for _ in range(count):
        trial = add_items(content, inventory, item_id, 1)
        if len(trial) > capacity:
            break
        inventory = trial
        given += 1
    return _set(state, cs._replace(inventory=inventory)), given


def _after_loadout_change(content: Content, state: GameState, char_id: str) -> GameState:
    return _set(state, stats.clamp_pools(content, state.characters[char_id]))


# --- Items ---------------------------------------------------------------------------

def _give_item(content, state, ctx, effect):
    for cid in _who(state, ctx, effect):
        count, state = _number(content, state, ctx, effect["count"])
        state, given = _give(content, state, cid, effect["item"], int(count))
        if cid == state.player:
            if given:
                state = _say(state, "gain", content.message("items_gained", items=_name_list(content, [(effect["item"], given)])))
            if given < count:
                state = _say(state, "plain", content.message("cargo_full", item=content.get("item", effect["item"])["name"]))
    return state, []


def _take_item(content, state, ctx, effect):
    for cid in _who(state, ctx, effect):
        count, state = _number(content, state, ctx, effect["count"])
        cs = state.characters[cid]
        left, inventory, taken = int(count), [], {}
        for inst in cs.inventory:
            view = stats.item_view(content, inst)
            matches = inst.item == effect["item"] if "item" in effect else effect["tag"] in view["tags"]
            if matches and left > 0:
                take = min(left, inst.count)
                left -= take
                taken[inst.item] = taken.get(inst.item, 0) + take
                if inst.count > take:
                    inventory.append(inst._replace(count=inst.count - take))
            else:
                inventory.append(inst)
        state = _set(state, cs._replace(inventory=tuple(inventory)))
        if taken and cid == state.player:
            state = _say(state, "plain", content.message("items_lost", items=_name_list(content, list(taken.items()))))
    return state, []


def _wear(content, state, ctx, effect):
    for cid in _who(state, ctx, effect):
        slot = context.pick(content, state, ctx, cid, effect["pick"])
        if slot is None:
            continue
        cs = state.characters[cid]
        inst = stats.item_at(cs, slot)
        if inst.condition is None:
            continue
        amount, state = _number(content, state, ctx, effect["amount"])
        top = stats.item_view(content, inst)["max_condition"]
        new = int(max(0, min(top, inst.condition - amount)))
        state = _set(state, stats.with_item(state.characters[cid], slot, inst._replace(condition=new)))
        if new == 0 < inst.condition and cid == state.player:
            state = _say(state, "danger", content.message("item_broken", item=stats.item_view(content, inst)["name"]))
        state = _after_loadout_change(content, state, cid)
    return state, []


def _modify_item(content, state, ctx, effect):
    change = freeze({k: v for k, v in effect.items() if k not in ("op", "pick", "subject")})
    for cid in _who(state, ctx, effect):
        slot = context.pick(content, state, ctx, cid, effect["pick"])
        if slot is None:
            continue
        cs = state.characters[cid]
        inst = stats.item_at(cs, slot)
        changed = ItemInst(item=inst.item, count=1, condition=inst.condition, mods=inst.mods,
                           changes=inst.changes + (change,))
        if change.get("max_condition") and changed.condition is not None:
            changed = changed._replace(condition=changed.condition + change["max_condition"])
        if inst.count > 1:  # one comes off the stack as a unique item
            cs = stats.with_item(cs, slot, inst._replace(count=inst.count - 1))
            cs = cs._replace(inventory=cs.inventory + (changed,))
        else:
            cs = stats.with_item(cs, slot, changed)
        state = _after_loadout_change(content, _set(state, cs), cid)
    return state, []


def _learn_design(content, state, ctx, effect):
    for cid in _who(state, ctx, effect):
        cs = state.characters[cid]
        if effect["item"] not in cs.designs:
            state = _set(state, cs._replace(designs=cs.designs + (effect["item"],)))
    return state, []


def roll_table(content: Content, state: GameState, ctx: Ctx, table_id: str) -> Tuple[List[Tuple[str, int]], GameState]:
    """What one roll of a loot table gives, as (item, count) pairs."""
    from engine import rng
    table = content.get("loot_table", table_id)
    found: List[Tuple[str, int]] = []
    for entry in table.get("always", ()):
        count, state = _number(content, state, ctx, entry["count"])
        found.append((entry["item"], int(count)))
    rolls, state = _number(content, state, ctx, table["rolls"])
    for _ in range(int(rolls)):
        options = []
        for entry in table["entries"]:
            ok, state = holds(content, state, ctx, entry.get("when"))
            if ok:
                options.append(entry)
        weights = [e["weight"] for e in options] + [table.get("nothing", 0)]
        if sum(weights) <= 0:
            continue
        index, nxt = rng.weighted(state.rng, weights)
        state = state._replace(rng=nxt)
        if index == len(options):
            continue  # drew nothing
        entry = options[index]
        if "table" in entry:
            more, state = roll_table(content, state, ctx, entry["table"])
            found += more
        else:
            count, state = _number(content, state, ctx, entry["count"])
            found.append((entry["item"], int(count)))
    return found, state


def _roll_loot(content, state, ctx, effect):
    for cid in _who(state, ctx, effect):
        receiver = ctx._replace(self_id=cid)
        got: Dict[str, int] = {}
        for _ in range(effect["rolls"]):
            found, state = roll_table(content, state, receiver, effect["table"])
            for item_id, count in found:
                state, given = _give(content, state, cid, item_id, count)
                if given:
                    got[item_id] = got.get(item_id, 0) + given
                if given < count and cid == state.player:
                    state = _say(state, "plain", content.message("cargo_full", item=content.get("item", item_id)["name"]))
        if got and cid == state.player:
            state = _say(state, "gain", content.message("items_found", items=_name_list(content, list(got.items()))))
    return state, []


# --- Stats and statuses -------------------------------------------------------------

def _damage(content, state, ctx, effect):
    follow: Work = []
    health = content.stat_roles["health"]
    resisted_by = content.get("damage_type", effect["damage_type"]).get("resisted_by")
    for cid in _who(state, ctx, effect, "target"):
        cs = state.characters[cid]
        if cs.down:
            continue
        amount, state = _number(content, state, ctx, effect["amount"])
        if resisted_by:
            amount -= stats.stat(content, cs, resisted_by)
        amount = max(0, amount)
        now = max(0, stats.current(content, cs, health) - amount)
        cs = cs._replace(pools=freeze({**cs.pools, health: now}))
        if now <= 0:
            cs = cs._replace(down=True)
            state = _set(state, cs)
            if _visible(state, cid):
                state = _say(state, "danger", content.message("character_down", character=content.get("character", cs.source)["name"]))
            on_defeat = content.get("character", cs.source).get("on_defeat", ())
            follow += [(e, Ctx(self_id=cid, target=ctx.self_id)) for e in on_defeat]
        else:
            state = _set(state, cs)
    return state, follow


def _restore(content, state, ctx, effect):
    health = content.stat_roles["health"]
    for cid in _who(state, ctx, effect):
        cs = state.characters[cid]
        amount, state = _number(content, state, ctx, effect["amount"])
        top = stats.stat(content, cs, effect["stat"])
        now = min(top, stats.current(content, cs, effect["stat"]) + max(0, amount))
        cs = cs._replace(pools=freeze({**cs.pools, effect["stat"]: now}))
        if effect["stat"] == health and now > 0:
            cs = cs._replace(down=False)
        state = _set(state, cs)
    return state, []


def _modify_stat(content, state, ctx, effect):
    for cid in _who(state, ctx, effect):
        amount, state = _number(content, state, ctx, effect["amount"])
        cs = state.characters[cid]
        cs = cs._replace(mods=cs.mods + (StatMod(effect["stat"], amount, effect.get("duration")),))
        state = _set(state, stats.clamp_pools(content, cs))
    return state, []


def _apply_status(content, state, ctx, effect):
    follow: Work = []
    for cid in _who(state, ctx, effect, "target"):
        record = content.get("status", effect["status"])
        cs = state.characters[cid]
        existing = next((s for s in cs.statuses if s.status == effect["status"]), None)
        if existing is None:
            new = StatusInst(effect["status"], effect.get("stacks", 1), effect.get("duration"))
        elif record.get("stacking", "refresh") == "ignore":
            continue
        elif record.get("stacking") == "stack":
            stacks = existing.stacks + effect.get("stacks", 1)
            if record.get("max_stacks"):
                stacks = min(stacks, record["max_stacks"])
            new = existing._replace(stacks=stacks, turns_left=effect.get("duration"))
        else:
            new = existing._replace(turns_left=effect.get("duration"))
        statuses = tuple(s for s in cs.statuses if s.status != effect["status"]) + (new,)
        state = _set(state, cs._replace(statuses=statuses))
        if existing is None:
            if _visible(state, cid):
                state = _say(state, "danger" if record.get("harmful", True) else "plain",
                             content.message("status_applied", character=content.get("character", cs.source)["name"],
                                             status=record["name"]))
            follow += [(e, Ctx(self_id=cid, target=ctx.self_id)) for e in record.get("on_apply", ())]
    return state, follow


def _remove_status(content, state, ctx, effect):
    for cid in _who(state, ctx, effect):
        cs = state.characters[cid]
        state = _set(state, cs._replace(statuses=tuple(s for s in cs.statuses if s.status != effect["status"])))
    return state, []


# --- World ---------------------------------------------------------------------------

def _set_flag(content, state, ctx, effect):
    flags = dict(state.flags)
    flags[effect["flag"]] = effect["value"] if "value" in effect else flags.get(effect["flag"], 0) + effect["add"]
    return state._replace(flags=freeze(flags)), []


def _set_state(content, state, ctx, effect):
    pid = context.placement(ctx, effect["object"])
    if pid is None:
        return state, []
    return state._replace(object_states=freeze({**state.object_states, pid: effect["state"]})), []


def _move_to(content, state, ctx, effect):
    follow: Work = []
    moving: List[str] = []
    for cid in _who(state, ctx, effect):
        moving += [m for m in context.party_of(state, cid) if m not in moving]
    location = content.get("location", effect["location"])
    at = entry_point(content, effect["location"], effect.get("entry"))
    for cid in moving:
        cs = state.characters[cid]
        visited = cs.visited if effect["location"] in cs.visited else cs.visited + (effect["location"],)
        state = _set(state, cs._replace(location=effect["location"], at=at, visited=visited))
        follow += [(e, Ctx(self_id=cid)) for e in location.get("on_enter", ())]
    if state.player in moving:
        state = _say(state, "plain", content.message("enter_location", location=location["name"],
                                                     character=content.get("character", state.characters[state.player].source)["name"]))
    return state, follow


def _spend_time(content, state, ctx, effect):
    return state._replace(turns_owed=state.turns_owed + effect["turns"]), []   # paid by engine.turns


def _trigger_event(content, state, ctx, effect):
    return state._replace(event_requests=state.event_requests + (effect["event"],)), []


def _start_encounter(content, state, ctx, effect):
    return state._replace(encounter_request=effect["encounter"]), []


def _end_encounter(content, state, ctx, effect):
    return state, []  # only meaningful inside an encounter (milestone 4)


# --- People --------------------------------------------------------------------------

def _grant_xp(content, state, ctx, effect):
    top = content.settings["skill_max_level"]
    for cid in _who(state, ctx, effect):
        amount, state = _number(content, state, ctx, effect["amount"])
        cs = state.characters[cid]
        skill_id = effect["skill"]
        total = cs.xp.get(skill_id, 0) + int(amount)
        old_level = cs.skills.get(skill_id, 0)
        levels = content.get("skill", skill_id)["levels"]
        new_level = max([lv["level"] for lv in levels if lv["xp"] <= total and lv["level"] <= top] + [old_level])
        cs = cs._replace(xp=freeze({**cs.xp, skill_id: total}), skills=freeze({**cs.skills, skill_id: new_level}))
        state = _set(state, cs)
        if new_level > old_level and cid == state.player:
            for lv in levels:
                if old_level < lv["level"] <= new_level:
                    state = _say(state, "gain", content.message(
                        "skill_up", skill=content.get("skill", skill_id)["name"], level=lv["level"],
                        text=content.text(lv["text"])))
    return state, []


def _join_party(content, state, ctx, effect):
    leaders = context.subjects(state, ctx, effect.get("leader", "player"))
    if not leaders:
        return state, []
    top = context.leader_of(state, leaders[0])
    for cid in _who(state, ctx, effect):
        if cid == top or context.leader_of(state, cid) == top:
            continue
        state = _set(state, state.characters[cid]._replace(leader=top))
        if _visible(state, cid):
            state = _say(state, "gain", content.message(
                "party_join", character=content.get("character", state.characters[cid].source)["name"],
                leader=content.get("character", state.characters[top].source)["name"]))
    return state, []


def _leave_party(content, state, ctx, effect):
    for cid in _who(state, ctx, effect):
        cs = state.characters[cid]
        if cs.leader is None:
            continue
        state = _set(state, cs._replace(leader=None))
        if _visible(state, cid):
            state = _say(state, "plain", content.message("party_leave", character=content.get("character", cs.source)["name"]))
    return state, []


def _change_relation(content, state, ctx, effect):
    of = context.agent(state, ctx, effect["of"])
    toward = context.agent(state, ctx, effect.get("toward", "player"))
    if of is None or toward is None:
        return state, []
    amount, state = _number(content, state, ctx, effect["amount"])
    low, high = content.settings["relation_min"], content.settings["relation_max"]
    relations = {k: dict(v) for k, v in state.relations.items()}
    pairs = [(of, toward)] + ([(toward, of)] if effect.get("mutual") else [])
    for a, b in pairs:
        value = context.relation(content, state, a, b) + int(amount)
        relations.setdefault(a, {})[b] = max(low, min(high, value))
    return state._replace(relations=freeze(relations)), []


def _change_rank(content, state, ctx, effect):
    ranks = [r["rank"] for r in content.ranks]
    for cid in _who(state, ctx, effect):
        cs = state.characters[cid]
        rank = cs.rank + effect["amount"]
        if ranks:
            rank = max(min(ranks), min(max(ranks), rank))
        state = _set(state, cs._replace(rank=rank))
    return state, []


def _unlock_slot(content, state, ctx, effect):
    for cid in _who(state, ctx, effect):
        cs = state.characters[cid]
        slots = {**cs.body_slots, effect["slot_type"]: cs.body_slots.get(effect["slot_type"], 0) + effect["count"]}
        state = _set(state, cs._replace(body_slots=freeze(slots)))
    return state, []


# --- Flow ----------------------------------------------------------------------------

def _message(content, state, ctx, effect):
    return _say(state, effect.get("kind", "plain"), content.text(effect["text"])), []


def _if(content, state, ctx, effect):
    ok, state = evaluate(content, state, ctx, effect["if"])
    branch = effect["then"] if ok else effect.get("else", ())
    return state, [(e, ctx) for e in branch]


HANDLERS: Dict[str, Handler] = {
    "message": _message, "give_item": _give_item, "take_item": _take_item, "wear": _wear,
    "modify_item": _modify_item, "learn_design": _learn_design, "roll_loot": _roll_loot,
    "damage": _damage, "restore": _restore, "modify_stat": _modify_stat,
    "apply_status": _apply_status, "remove_status": _remove_status,
    "set_flag": _set_flag, "set_state": _set_state, "move_to": _move_to, "spend_time": _spend_time,
    "trigger_event": _trigger_event, "start_encounter": _start_encounter, "end_encounter": _end_encounter,
    "grant_xp": _grant_xp, "join_party": _join_party, "leave_party": _leave_party,
    "change_relation": _change_relation, "change_rank": _change_rank, "unlock_slot": _unlock_slot,
    "if": _if,
}
