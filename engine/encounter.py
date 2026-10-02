"""
Encounters.

An encounter begins when start_encounter has left a request: template enemies are
spawned, extra allies join the player's side (with the player's party), and on_start
runs. Each round:

  1. AI-controlled characters (everyone but the player) choose an action and target;
     enemies' choices show as intent.
  2. The player chooses an action tile (and a target when there is a choice).
  3. All chosen actions resolve in order: priority, then initiative, ties to the
     player's side. Costs are paid (heat, cooldown, charges, consumed items), effects
     run against the targets, and the action trains its skills.
  4. Cooldowns count down and one world turn passes (statuses, hazards).

Heat goes into the actor's heat pool; reaching the maximum overheats them: they lose
their next action and cool to their constant load. Characters with no heat capacity
don't track heat. AI never ends the encounter for its side: below its flee_below
health share it flees alone.

On a defeat during an encounter, on_defeat waits until the encounter ends. The end
runs on_win / on_lose / on_escape, then on_defeat for everyone who is down; a player
still down afterwards comes back with 1 health. Winning rolls the encounter's loot
and each defeated enemy's. Spawned characters leave, and heat cools to the constant
load.
"""
from typing import Dict, List, Mapping, NamedTuple, Optional, Tuple

from engine import conditions, context, rng, stats, turns
from engine.content import Content
from engine.effects import run
from engine.frozen import Record, freeze
from engine.state import CharState, Ctx, GameState, Message, character_from


class EncounterState(NamedTuple):
    id: str
    allies: Tuple[str, ...]                          # the player's side, the player first
    enemies: Tuple[str, ...]
    spawned: Tuple[str, ...] = ()                    # template copies, removed at the end
    round: int = 1
    intents: Mapping[str, Tuple[str, Optional[str]]] = freeze({})   # AI actor -> (action, target)
    cooldowns: Mapping[str, Mapping[str, int]] = freeze({})        # actor -> action -> rounds left
    charges: Mapping[str, Mapping[str, int]] = freeze({})          # actor -> action -> uses so far
    skip: Tuple[str, ...] = ()                        # overheated: lose their next action
    fled: Tuple[str, ...] = ()
    result: Optional[str] = None                      # 'won', 'lost', 'escaped' (for the player's side)


class Tile(NamedTuple):
    key: str
    action: str
    label: str
    available: bool
    hint: Optional[str]
    cost: str


# --- Helpers ----------------------------------------------------------------------------

def _set(state: GameState, cs: CharState) -> GameState:
    chars = dict(state.characters)
    chars[cs.id] = cs
    return state._replace(characters=freeze(chars))


def _say(state: GameState, kind: str, text: str) -> GameState:
    return state._replace(messages=state.messages + (Message(kind, text),))


def _name(content: Content, state: GameState, cid: str) -> str:
    return content.get("character", state.characters[cid].source)["name"]


def _enc(state: GameState) -> EncounterState:
    return state.encounter


def _with_enc(state: GameState, **changes) -> GameState:
    return state._replace(encounter=state.encounter._replace(**changes))


def side_of(state: GameState, cid: str) -> str:
    return "allies" if cid in _enc(state).allies else "enemies"


def active(state: GameState, cid: str) -> bool:
    """Still fighting: in play, not down, not fled."""
    enc = _enc(state)
    return cid in state.characters and not state.characters[cid].down and cid not in enc.fled


def living(state: GameState, side: str) -> List[str]:
    return [cid for cid in getattr(_enc(state), side) if active(state, cid)]


def opponents(state: GameState, cid: str) -> List[str]:
    return living(state, "enemies" if side_of(state, cid) == "allies" else "allies")


def friends(state: GameState, cid: str) -> List[str]:
    return living(state, side_of(state, cid))


def _health_share(content: Content, cs: CharState) -> float:
    health = content.stat_roles["health"]
    top = stats.stat(content, cs, health)
    return stats.current(content, cs, health) / top if top else 0


# --- Beginning --------------------------------------------------------------------------

def begin(content: Content, state: GameState) -> GameState:
    """Starts the requested encounter, if there is one and none is running."""
    request = state.encounter_request
    state = state._replace(encounter_request=None)
    if request is None or state.encounter is not None:
        return state
    record = content.get("encounter", request)
    player = state.characters[state.player]
    allies = list(context.party_of(state, state.player))
    enemies: List[str] = []
    spawned: List[str] = []
    for side, entries in (("allies", record.get("allies", ())), ("enemies", record["enemies"])):
        for entry in entries:
            source = content.get("character", entry["character"])
            if not source.get("template"):
                if entry["character"] in state.characters:
                    (allies if side == "allies" else enemies).append(entry["character"])
                continue
            count, state = context.amount(content, state, Ctx(self_id=state.player), entry["count"])
            for _ in range(int(count)):
                new_id = f"{entry['character']}#{state.spawned + 1}"
                cs = character_from(content, new_id, entry["character"])._replace(location=player.location)
                state = _set(state, stats.fill_pools(content, cs))._replace(spawned=state.spawned + 1)
                (allies if side == "allies" else enemies).append(new_id)
                spawned.append(new_id)
    state = state._replace(encounter=EncounterState(id=request, allies=tuple(dict.fromkeys(allies)),
                                                    enemies=tuple(enemies), spawned=tuple(spawned)),
                           focus=None)
    state = _say(state, "danger", content.message("encounter_start", encounter=record["name"]))
    if record.get("intro"):
        state = _say(state, "quiet", content.text(record["intro"]))
    state = run(content, state, Ctx(self_id=state.player), record.get("on_start", ()))
    return _plan_ai(content, state)


# --- Actions ----------------------------------------------------------------------------

def actions_of(content: Content, state: GameState, cid: str) -> List[str]:
    """Every action a character has: their own, their active items', their skill levels', and innate ones."""
    cs = state.characters[cid]
    found = list(content.get("character", cs.source).get("actions", ()))
    for _, inst in stats.active(cs):
        found += stats.item_view(content, inst)["actions"]
    for lv in stats.skill_levels(content, cs):
        found += list(lv.get("actions", ()))
    found += [aid for aid, a in content.all("action").items() if a.get("innate")]
    return list(dict.fromkeys(found))


def _ends_encounter(effects) -> bool:
    for effect in effects:
        if effect["op"] == "end_encounter":
            return True
        if effect["op"] == "if" and (_ends_encounter(effect["then"]) or _ends_encounter(effect.get("else", ()))):
            return True
        if effect["op"] == "choose" and any(_ends_encounter(o["effects"]) for o in effect["options"]):
            return True
    return False


def usable(content: Content, state: GameState, cid: str, action_id: str) -> Tuple[bool, Optional[str], GameState]:
    """Whether a character can use an action now, and if not, why."""
    action = content.get("action", action_id)
    enc = _enc(state)
    rounds = enc.cooldowns.get(cid, {}).get(action_id, 0)
    if rounds > 0:
        return False, content.message("on_cooldown", rounds=rounds), state
    cost = action.get("cost", {})
    if cost.get("charges") and enc.charges.get(cid, {}).get(action_id, 0) >= cost["charges"]:
        return False, content.message("no_charges"), state
    consumes = cost.get("consumes")
    if consumes:
        cs = state.characters[cid]
        have = sum(inst.count for inst in cs.inventory
                   if inst.item == consumes.get("item") or consumes.get("tag") in stats.item_view(content, inst)["tags"])
        if have < consumes["count"]:
            what = content.get("item", consumes["item"])["name"] if consumes.get("item") \
                else content.get("tag", consumes["tag"])["name"]
            return False, content.message("needs_item", item=what), state
    ok, state = conditions.holds(content, state, Ctx(self_id=cid), action.get("requires"))
    if not ok:
        return False, content.text(action["hint"]) if action.get("hint") else content.message("unavailable"), state
    if action["target"] in ("enemy",) and not opponents(state, cid):
        return False, content.message("unavailable"), state
    return True, None, state


def tiles(content: Content, state: GameState) -> List[Tile]:
    """The player's action tiles, numbered 1-9."""
    result = []
    for number, action_id in enumerate(actions_of(content, state, state.player)[:9], 1):
        action = content.get("action", action_id)
        ok, hint, state = usable(content, state, state.player, action_id)
        heat = action.get("cost", {}).get("heat")
        cost = "" if not heat else (f"{heat}" if isinstance(heat, (int, float)) else f"{heat['min']}-{heat['max']}"
                                     if "min" in heat else "")
        label = action.get("short") or action["name"][:8]
        result.append(Tile(str(number), action_id, label, ok, hint, cost))
    return result


def targets(content: Content, state: GameState, cid: str, action_id: str) -> List[str]:
    """Who a single-target action can be aimed at."""
    kind = content.get("action", action_id)["target"]
    if kind == "enemy":
        return opponents(state, cid)
    if kind == "ally":
        return friends(state, cid)
    return []


# --- AI ---------------------------------------------------------------------------------

def _plan_ai(content: Content, state: GameState) -> GameState:
    """Every AI-controlled fighter picks an action and target for this round."""
    intents: Dict[str, Tuple[str, Optional[str]]] = {}
    fled = list(_enc(state).fled)
    for cid in living(state, "allies") + living(state, "enemies"):
        if cid == state.player:
            continue
        record = content.get("character", state.characters[cid].source)
        flee_below = record.get("ai", {}).get("flee_below")
        escape = content.get("encounter", _enc(state).id).get("escape", True)
        if flee_below is not None and escape and _health_share(content, state.characters[cid]) < flee_below:
            fled.append(cid)
            state = _say(state, "plain", content.message("fled", character=_name(content, state, cid)))
            continue
        choice, state = _ai_choice(content, state, cid)
        if choice:
            intents[cid] = choice
    return _with_enc(state, intents=freeze(intents), fled=tuple(fled))


def _ai_choice(content: Content, state: GameState, cid: str) -> Tuple[Optional[Tuple[str, Optional[str]]], GameState]:
    options, weights = [], []
    for action_id in actions_of(content, state, cid):
        action = content.get("action", action_id)
        if _ends_encounter(action["effects"]):
            continue                                   # AI flees alone instead
        ok, _, state = usable(content, state, cid, action_id)
        if not ok:
            continue
        ai = action.get("ai", {})
        wanted, state = conditions.holds(content, state, Ctx(self_id=cid), ai.get("when"))
        if not wanted or ai.get("weight", 1) <= 0:
            continue
        options.append(action_id)
        weights.append(ai.get("weight", 1))
    if not options:
        return None, state
    index, nxt = rng.weighted(state.rng, weights)
    state = state._replace(rng=nxt)
    action_id = options[index]
    kind = content.get("action", action_id)["target"]
    target = None
    if kind == "enemy":
        target, nxt = rng.pick(state.rng, opponents(state, cid))
        state = state._replace(rng=nxt)
    elif kind == "ally":
        target = min(friends(state, cid), key=lambda f: _health_share(content, state.characters[f]))
    return (action_id, target), state


def intent_line(content: Content, state: GameState, cid: str) -> Optional[str]:
    """What an AI fighter is about to do, in the pack's words."""
    choice = _enc(state).intents.get(cid)
    if not choice:
        return None
    action = content.get("action", choice[0])
    word = content.text(action["intent"]) if action.get("intent") else action["name"]
    target = _name(content, state, choice[1]) if choice[1] else ""
    return content.message("intent", action=word, target=target).strip()


# --- A round ----------------------------------------------------------------------------

def take_turn(content: Content, state: GameState, action_id: str, target: Optional[str] = None) -> GameState:
    """The player acts; then the whole round resolves."""
    state = state._replace(messages=())
    ok, hint, state = usable(content, state, state.player, action_id)
    if not ok:
        return _say(state, "plain", hint)
    if content.get("action", action_id)["target"] in ("enemy", "ally"):
        candidates = targets(content, state, state.player, action_id)
        if target not in candidates:
            target = candidates[0] if candidates else None
    chosen = {**_enc(state).intents, state.player: (action_id, target)}
    return _resolve(content, _with_enc(state, intents=freeze(chosen)))


def _order(content: Content, state: GameState) -> List[str]:
    enc = _enc(state)
    initiative = content.stat_roles["initiative"]
    actors = [cid for cid in enc.intents if active(state, cid)]

    def key(cid: str):
        action = content.get("action", enc.intents[cid][0])
        return (-action.get("priority", 0), -stats.stat(content, state.characters[cid], initiative),
                0 if side_of(state, cid) == "allies" else 1, (enc.allies + enc.enemies).index(cid))
    return sorted(actors, key=key)


def _resolve(content: Content, state: GameState) -> GameState:
    for cid in _order(content, state):
        if _enc(state).result or not active(state, cid):
            continue
        if cid in _enc(state).skip:
            state = _with_enc(state, skip=tuple(s for s in _enc(state).skip if s != cid))
            state = _say(state, "plain", content.message("skips_turn", character=_name(content, state, cid)))
            continue
        if any(content.get("status", s.status).get("blocks_actions") for s in state.characters[cid].statuses):
            state = _say(state, "plain", content.message("skips_turn", character=_name(content, state, cid)))
            continue
        action_id, target = _enc(state).intents[cid]
        state = _perform(content, state, cid, action_id, target)
        state = _check_end(content, state)
    if _enc(state).result:
        return _finish(content, state)
    # End of round: cooldowns count down, one world turn passes.
    cooldowns = {cid: {a: n - 1 for a, n in acts.items() if n > 1} for cid, acts in _enc(state).cooldowns.items()}
    state = _with_enc(state, cooldowns=freeze(cooldowns), round=_enc(state).round + 1)
    state = turns.advance(content, state, 1)
    state = _check_end(content, state)
    if _enc(state).result:
        return _finish(content, state)
    return _plan_ai(content, state)


def _perform(content: Content, state: GameState, cid: str, action_id: str, target: Optional[str]) -> GameState:
    ok, _, state = usable(content, state, cid, action_id)
    if not ok:
        return state
    action = content.get("action", action_id)
    kind = action["target"]
    if kind in ("enemy", "ally"):
        pool = opponents(state, cid) if kind == "enemy" else friends(state, cid)
        if target not in pool:
            target = pool[0] if pool else None
        if target is None:
            return state
        aimed = [target]
    elif kind == "all_enemies":
        aimed = opponents(state, cid)
    elif kind == "all_allies":
        aimed = friends(state, cid)
    else:
        aimed = [cid]
    state = _say(state, "plain", content.message("uses_action", character=_name(content, state, cid),
                                                 action=action["name"]))
    state = _pay(content, state, cid, action_id)
    for aimed_at in aimed:
        if _enc(state).result:
            break
        state = run(content, state, Ctx(self_id=cid, target=aimed_at), action["effects"])
    for skill_id, amount in action.get("trains", {}).items():
        state = run(content, state, Ctx(self_id=cid),
                    [freeze({"op": "grant_xp", "skill": skill_id, "amount": amount, "subject": "self"})])
    return state


def _pay(content: Content, state: GameState, cid: str, action_id: str) -> GameState:
    action = content.get("action", action_id)
    cost = action.get("cost", {})
    enc = _enc(state)
    if cost.get("cooldown"):
        cooldowns = {k: dict(v) for k, v in enc.cooldowns.items()}
        cooldowns.setdefault(cid, {})[action_id] = cost["cooldown"]
        state = _with_enc(state, cooldowns=freeze(cooldowns))
    if cost.get("charges"):
        charges = {k: dict(v) for k, v in _enc(state).charges.items()}
        charges.setdefault(cid, {})[action_id] = charges.get(cid, {}).get(action_id, 0) + 1
        state = _with_enc(state, charges=freeze(charges))
    if cost.get("consumes"):
        c = cost["consumes"]
        effect = {"op": "take_item", "count": c["count"], "subject": "self", **({"item": c["item"]} if c.get("item") else {"tag": c["tag"]})}
        state = run(content, state, Ctx(self_id=cid), [freeze(effect)])
    if cost.get("heat") is not None:
        heat = content.stat_roles["heat"]
        cs = state.characters[cid]
        top = stats.stat(content, cs, heat)
        if top > 0:
            amount, state = context.amount(content, state, Ctx(self_id=cid), cost["heat"])
            cs = state.characters[cid]
            now = stats.current(content, cs, heat) + amount
            if now >= top:
                load = stats.budget_used(content, cs, "heat")
                state = _set(state, cs._replace(pools=freeze({**cs.pools, heat: load})))
                state = _with_enc(state, skip=_enc(state).skip + (cid,))
                state = _say(state, "danger", content.message("overheated", character=_name(content, state, cid)))
            else:
                state = _set(state, cs._replace(pools=freeze({**cs.pools, heat: now})))
    return state


def _check_end(content: Content, state: GameState) -> GameState:
    enc = _enc(state)
    if enc.result:
        return state
    if state.characters[state.player].down:
        return _with_enc(state, result="lost")
    if not living(state, "enemies"):
        return _with_enc(state, result="won")
    return state


def end_for(state: GameState, actor: str, result: str) -> GameState:
    """end_encounter used by someone: the result is for the actor's side, turned to the player's side."""
    if state.encounter is None or state.encounter.result:
        return state
    if side_of(state, actor) == "enemies":
        result = {"won": "lost", "lost": "won"}.get(result, result)
    return _with_enc(state, result=result)


# --- The end ----------------------------------------------------------------------------

def _finish(content: Content, state: GameState) -> GameState:
    enc = _enc(state)
    record = content.get("encounter", enc.id)
    ctx = Ctx(self_id=state.player)
    result = enc.result
    state = _say(state, "danger" if result == "lost" else "gain",
                 content.message(f"encounter_{result}", encounter=record["name"]))
    if result == "won":
        if record.get("loot"):
            state = run(content, state, ctx, [freeze({"op": "roll_loot", "table": record["loot"], "rolls": 1, "subject": "self"})])
        for cid in enc.enemies:
            loot = content.get("character", state.characters[cid].source).get("loot")
            if loot and state.characters[cid].down:
                state = run(content, state, ctx, [freeze({"op": "roll_loot", "table": loot, "rolls": 1, "subject": "self"})])
    hook = {"won": "on_win", "lost": "on_lose", "escaped": "on_escape"}[result]
    participants = list(enc.enemies) + [c for c in enc.allies if c != state.player] + [state.player]
    down = [cid for cid in participants if state.characters[cid].down]
    state = state._replace(encounter=None)
    state = run(content, state, ctx, record.get(hook, ()))
    for cid in down:
        on_defeat = content.get("character", state.characters[cid].source).get("on_defeat", ())
        state = run(content, state, Ctx(self_id=cid, target=state.player), on_defeat)
    player = state.characters[state.player]
    health = content.stat_roles["health"]
    if player.down:                                    # never a game over
        state = _set(state, player._replace(down=False, pools=freeze({**player.pools, health: 1})))
    heat = content.stat_roles["heat"]
    chars = {}
    for cid, cs in state.characters.items():
        if cid in enc.spawned:
            continue
        if cid in participants and heat in cs.pools:
            cs = cs._replace(pools=freeze({**cs.pools, heat: stats.budget_used(content, cs, "heat")}))
        chars[cid] = cs
    return state._replace(characters=freeze(chars))
