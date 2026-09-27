from typing import Optional, Tuple, List, Dict

from core.types import (
    GameState, Node, Fixture, Actor, Edge, Item, FixtureState, ItemCategory,
)
from core.tick import process_tick
from core.presets import DEFAULT_DATA_DIR, load_catalogs
from core import rules
from core.rules import Source
from core import routine
from core.menu import DONE_STATES, CLOSED_STATES, get_entity_at, entity_under_cursor
from core.text import danger, gain, quiet, speech, needs, tag_name, hazard_words, TAG_NAMES, STATE_WORDS

# Default catalogues, for callers that build items outside a game state (tests, tools).
ALL_ITEMS_BY_ID, ALL_COMPANIONS_BY_ID = load_catalogs(DEFAULT_DATA_DIR)

_TOOL_EFFECTS = ("unlock", "repair", "harvest", "override")
_STRESS_NOTE = " (Hard to focus. Details may be off.)"


# --- Lookup helpers --------------------------------------------------------

def _find_fixture(node: Node, ref: str) -> Optional[Fixture]:
    ref = ref.strip()
    if ref in node.fixtures:
        return node.fixtures[ref]
    for f in node.fixtures.values():
        if f.glyph == ref or f.name.lower() == ref.lower():
            return f
    return None


def _find_actor(node: Node, ref: str) -> Optional[Actor]:
    ref = ref.strip()
    if ref in node.actors:
        return node.actors[ref]
    for a in node.actors.values():
        if a.glyph == ref or a.name.lower() == ref.lower():
            return a
    return None


def _with_fixture(node: Node, fixture: Fixture) -> Node:
    fixtures = dict(node.fixtures)
    fixtures[fixture.id] = fixture
    return node._replace(fixtures=fixtures)


def _with_node(state: GameState, node: Node) -> GameState:
    nodes = dict(state.nodes)
    nodes[node.id] = node
    return state._replace(nodes=nodes)


def _refresh_menu(state: GameState) -> GameState:
    """The menu is drawn from state by the renderer; this only toggles whether it shows."""
    on_entity = state.active_view == "compartment" and any(entity_under_cursor(state))
    return state._replace(proximity_menu_active=on_entity)


def _say(state: GameState, *lines: str) -> GameState:
    """Replaces Zone 5 with lines without advancing time."""
    return _refresh_menu(state._replace(message_buffer=tuple(lines)))


def _gate_placement(node: Node, edge: Edge) -> Optional[Tuple[int, int]]:
    gate_ids = {edge.gated_by_fixture} | {f.id for f in node.fixtures.values() if f.grants_edge == edge.id}
    for p in node.placements:
        if p.entity_id in gate_ids:
            return p.row, p.col
    return None


def _spend(state: GameState, source: Optional[Source], effect: str) -> Tuple[Tuple[Item, ...], str]:
    """Applies wear for the item that satisfied a requirement. Returns (inventory, note)."""
    inventory = state.character.inventory
    if source is None:
        return inventory, ""
    if source.item_idx is None:
        return inventory, f" Done with {source.label}."
    item = inventory[source.item_idx]
    if effect == "harvest" or rules.tool_protected(state, item) or item.max_integrity <= 0:
        return inventory, f" Used your {item.name}."
    inventory, used_up = rules.wear_item(inventory, source.item_idx)
    if used_up:
        return inventory, f" Your {item.name} is used up."
    return inventory, f" {item.name}: {item.integrity - 1}/{item.max_integrity} left."


def _describe_arrival(state: GameState, dest: Node) -> List[str]:
    lines = [f"You enter {dest.name}."]
    if state.flavor_enabled and dest.id not in state.visited_nodes:
        lines.append(quiet(dest.description))
    hazards = hazard_words(dest.base_vitals)
    if hazards and not rules.is_safe_haven(dest):
        lines.append(danger(f"{hazards.capitalize()} here. Exposure rises every turn."))
    return lines


# --- Movement --------------------------------------------------------------

def reduce_move(state: GameState, direction: str) -> GameState:
    """
    Moves player cursor one tile on the Zone 2 grid via WASD raw keys.
    Advances simulation tick on success. Landing on an entity opens the proximity menu.
    """
    direction = direction.lower().strip()
    node = state.nodes[state.current_node_id]
    delta = {"w": (-1, 0), "s": (1, 0), "a": (0, -1), "d": (0, 1)}.get(direction)
    if not delta:
        return state._replace(message_buffer=(f"Use W, A, S or D to move.",))

    new_r = state.player_row + delta[0]
    new_c = state.player_col + delta[1]
    # Walls simply block: no message, no time, and the menu for the current tile stays usable.
    if not (0 <= new_r < node.size and 0 <= new_c < node.size):
        return state
    fixture, actor = get_entity_at(node, new_r, new_c)
    is_border = new_r in (0, node.size - 1) or new_c in (0, node.size - 1)
    if is_border and not fixture and not actor:
        return state

    moved = state._replace(player_row=new_r, player_col=new_c, message_buffer=())
    return _refresh_menu(process_tick(moved, ""))


def _enter_node(state: GameState, edge: Edge, via_fixture: Optional[Fixture]) -> GameState:
    """Crosses edge into its destination node. Gate checks happen in the callers."""
    if edge.requires_capability and edge.requires_capability not in rules.party_tags(state):
        return _say(state, f"Needs {tag_name(edge.requires_capability)}.")
    dest = state.nodes.get(edge.target_node_id)
    if not dest:
        return _say(state, f"Route error: {edge.target_node_id} is missing from this world.")

    messages = _describe_arrival(state, dest)
    if rules.is_critical(state):
        messages.append(danger("You stagger through, barely standing."))

    origin = state.nodes[state.current_node_id]
    gate_ids = {edge.gated_by_fixture, via_fixture.id if via_fixture else None}
    for fid in gate_ids:
        gate = origin.fixtures.get(fid) if fid else None
        if gate and gate.reseal_on_pass and gate.state == FixtureState.OPEN.value:
            origin = _with_fixture(origin, gate._replace(state=FixtureState.SEALED.value))
            messages.append(f"The {gate.name} locks behind you.")

    moved = _with_node(state, origin)._replace(
        current_node_id=dest.id,
        player_row=dest.size // 2,
        player_col=dest.size // 2,
        active_view="compartment",
        message_buffer=state.message_buffer + tuple(messages),
    )
    return _refresh_menu(process_tick(moved, f"Went to {dest.name}."))


def reduce_interact_go(state: GameState) -> GameState:
    """[G] Traverses the open edge granted by the fixture under the cursor."""
    node = state.nodes[state.current_node_id]
    fixture, _ = entity_under_cursor(state)
    if not fixture or not fixture.grants_edge:
        return state._replace(message_buffer=("There is no way through here.",), proximity_menu_active=False)
    edge = node.edges.get(fixture.grants_edge)
    if not edge:
        return _say(state, f"Route error: exit '{fixture.grants_edge}' is missing.")
    if fixture.state != FixtureState.OPEN.value:
        return _say(state, f"The {fixture.name} is {STATE_WORDS.get(fixture.state, fixture.state)}.")
    return _enter_node(state._replace(message_buffer=()), edge, fixture)


def reduce_leave(state: GameState, edge_id: str) -> GameState:
    """
    Walks to an exit and crosses it. Costs one cycle per tile walked (minimum one),
    so exposure applies exactly as if the player had moved there with WASD.
    """
    edge_id = edge_id.strip()
    node = state.nodes[state.current_node_id]
    edge = node.edges.get(edge_id)
    if not edge:
        for e in node.edges.values():
            if e.label.lower() == edge_id.lower() or e.target_node_id == edge_id:
                edge = e
                break
    if not edge:
        available = ", ".join(f"{k} ({v.label})" for k, v in node.edges.items())
        return state._replace(message_buffer=(f"No exit '{edge_id}'. Exits: {available}",))

    gate = node.fixtures.get(edge.gated_by_fixture) if edge.gated_by_fixture else None
    if gate and gate.state != FixtureState.OPEN.value:
        return state._replace(message_buffer=(f"The {gate.name} is {STATE_WORDS.get(gate.state, gate.state)}.",))
    if edge.requires_capability and edge.requires_capability not in rules.party_tags(state):
        return state._replace(message_buffer=(f"Needs {tag_name(edge.requires_capability)}.",))

    walking = state._replace(message_buffer=())
    target = _gate_placement(node, edge)
    if target:
        steps = abs(target[0] - state.player_row) + abs(target[1] - state.player_col)
        for _ in range(max(0, steps - 1)):
            walking = process_tick(walking, "")
            if walking.current_node_id != node.id:  # collapsed on the way
                return walking
        walking = walking._replace(player_row=target[0], player_col=target[1])
    return _enter_node(walking, edge, None)


# --- Inspection and conversation ------------------------------------------

def reduce_look(state: GameState) -> GameState:
    """Describes the current room and its exits. Does not advance the tick."""
    node = state.nodes[state.current_node_id]
    lines = [quiet(node.description)]
    for edge in node.edges.values():
        dest = state.nodes.get(edge.target_node_id)
        hazards = hazard_words(dest.base_vitals) if dest else ""
        lines.append(f"Exit: {edge.label}" + (f" ({hazards})" if hazards else ""))
    return _say(state, *lines)


def reduce_interact_inspect(state: GameState) -> GameState:
    """[I] Inspects the entity under the cursor."""
    fixture, actor = entity_under_cursor(state)
    if fixture or actor:
        return reduce_inspect(state, (fixture or actor).id)
    return state._replace(message_buffer=("There is nothing here to look at.",), proximity_menu_active=False)


def reduce_inspect(state: GameState, target_id: str) -> GameState:
    """Inspects a fixture, actor, inventory item, or exit. Does not advance the tick."""
    target_id = target_id.strip()
    if not target_id:
        return state._replace(message_buffer=("Inspect what? Give a name, e.g. /inspect canteen.",))

    node = state.nodes[state.current_node_id]
    note = _STRESS_NOTE if rules.is_stressed(state) else ""

    fixture = _find_fixture(node, target_id)
    if fixture:
        lines = [f"{fixture.name}: {fixture.description}{note}"]
        if fixture.state in (FixtureState.SEALED.value, FixtureState.LOCKED.value,
                             FixtureState.DISABLED.value, FixtureState.SPENT.value):
            lines.append(f"It is {STATE_WORDS[fixture.state]}.")
        if fixture.required_tags and fixture.state not in DONE_STATES:
            source = rules.resolve_requirement(state, fixture.required_tags)
            lines.append(f"Needs {needs(fixture.required_tags)}.")
            if "seam_discipline" in state.character.unlocked_capabilities:
                lines.append(f"Fixing Leaks: you can do it with {source.label}." if source
                             else "Fixing Leaks: nothing you carry fits.")
        return _say(state, *lines)

    actor = _find_actor(node, target_id)
    if actor:
        return _say(state, f"{actor.name}, {actor.title}. {actor.status}.{note}",
                    speech(actor.name, rules.dialogue_for(state, actor)))

    idx = rules.find_item(state, target_id)
    if idx is not None:
        item = state.character.inventory[idx]
        cond = f" Condition {item.integrity}/{item.max_integrity}." if item.max_integrity > 0 else ""
        uses = [tag_name(t) for t in item.tags if t in TAG_NAMES]
        use_line = f" Counts as {', '.join(uses)}." if uses else ""
        return _say(state, f"{item.name}: {item.description}{note}{cond}{use_line}")

    edge = node.edges.get(target_id)
    if edge:
        lines = [f"Exit to {edge.label}.{note}"]
        target_node = state.nodes.get(edge.target_node_id)
        if target_node:
            hazards = hazard_words(target_node.base_vitals)
            lines.append(f"Beyond: {hazards}." if hazards else "Beyond: safe air.")
            if "bulkhead_ear" in state.character.unlocked_capabilities:
                v = target_node.base_vitals
                lines.append(f"Hear Pressure: {v.pressure_kpa:g} kPa, {v.temperature_c}°C, rad {v.radiation_msv:g}.")
        gate = node.fixtures.get(edge.gated_by_fixture) if edge.gated_by_fixture else None
        if gate and gate.state != FixtureState.OPEN.value:
            lines.append(f"The {gate.name} is {STATE_WORDS.get(gate.state, gate.state)}.")
        return _say(state, *lines)

    return state._replace(message_buffer=(f"Nothing called '{target_id}' here.",))


def reduce_interact_talk(state: GameState) -> GameState:
    """[T] Talks with the actor under the cursor."""
    _, actor = entity_under_cursor(state)
    if not actor:
        return state._replace(message_buffer=("No one here to talk to.",), proximity_menu_active=False)
    return reduce_talk(state, actor.id)


def reduce_talk(state: GameState, actor_id: str) -> GameState:
    """Talks to an actor. Describes any trade on offer but never trades by itself. Advances the tick."""
    actor = _find_actor(state.nodes[state.current_node_id], actor_id)
    if not actor:
        return state._replace(message_buffer=(f"No one called '{actor_id.strip()}' here.",))

    lines = [speech(actor.name, rules.dialogue_for(state, actor))]
    offered = rules.catalog_item(state, actor.trade_offered_id)
    idx = rules.trade_item_idx(state, actor)
    if idx is not None and offered:
        mine = state.character.inventory[idx]
        lines.append(f"Offer: your {mine.name} for a {offered.name}. Press B to trade.")
    elif offered and not actor.trade_completed and actor.trade_required_tags:
        lines.append(f"{actor.name} trades a {offered.name} for {needs(actor.trade_required_tags)}.")
    talked = state._replace(message_buffer=tuple(lines))
    return _refresh_menu(process_tick(talked, f"Talked with {actor.name}."))


def reduce_interact_barter(state: GameState) -> GameState:
    """[B] Barters with the actor under the cursor."""
    _, actor = entity_under_cursor(state)
    if not actor:
        return state._replace(message_buffer=("No one here to trade with.",), proximity_menu_active=False)
    return reduce_barter(state, actor.id)


def reduce_barter(state: GameState, actor_id: str = "", item_id: str = "") -> GameState:
    """
    Executes an actor's trade (§5.4). Any item carrying one of the actor's tags is accepted.
    Credentials are shown and kept; items that wear lose one integrity; others change hands.
    """
    node = state.nodes[state.current_node_id]
    actor = _find_actor(node, actor_id) if actor_id else entity_under_cursor(state)[1]
    if not actor:
        return state._replace(message_buffer=("No one here to trade with.",))
    if actor.trade_completed:
        return _say(state, f"{actor.name} has nothing more to trade.")
    offered = rules.catalog_item(state, actor.trade_offered_id)
    if not offered or not actor.trade_required_tags:
        return _say(state, f"{actor.name} isn't trading.")

    preferred = None
    if item_id:
        preferred = rules.find_item(state, item_id)
        if preferred is None:
            return _say(state, f"You don't have '{item_id}'.")
    idx = rules.trade_item_idx(state, actor, preferred)
    if idx is None:
        return _say(state, f"{actor.name} wants {needs(actor.trade_required_tags)}.")
    if preferred is not None and idx != preferred:
        return _say(state, f"{actor.name} won't take that. Wants {needs(actor.trade_required_tags)}.")

    given = state.character.inventory[idx]
    inventory = state.character.inventory
    if rules.is_handed_over(given):
        if given.max_integrity > 0:
            inventory, _ = rules.wear_item(inventory, idx)
        else:
            inventory = rules.remove_item(inventory, idx)
    inventory = inventory + (offered,)

    updated_actor = actor._replace(trade_completed=True)
    actors = dict(node.actors)
    actors[actor.id] = updated_actor
    new_node = node._replace(actors=actors)

    kept = "" if rules.is_handed_over(given) else " (you keep it)"
    messages = [gain(f"Got: {offered.name}, for your {given.name}{kept}."),
                speech(actor.name, updated_actor.dialogue_post_trade or "Deal.")]
    companions = state.companions
    recruit = rules.catalog_companion(state, actor.companion_unlock)
    if recruit and not any(c.id == recruit.id for c in companions):
        companions = companions + (recruit,)
        new_node = new_node._replace(placements=tuple(p for p in new_node.placements if p.entity_id != actor.id))
        messages.insert(1, gain(f"Team: {recruit.name} ({recruit.title}) joins you."))

    traded = _with_node(state, new_node)._replace(
        character=state.character._replace(inventory=inventory),
        companions=companions,
        message_buffer=tuple(messages),
    )
    return _refresh_menu(process_tick(
        traded, f"Traded with {actor.name}.",
        {"traded_actor_id": actor.id, "xp": {"logistics": routine.XP_TRADE}}, physical=True))


# --- Fixtures --------------------------------------------------------------

def reduce_interact_use(state: GameState) -> GameState:
    """[U] Uses the fixture under the cursor with whatever best satisfies it."""
    fixture, _ = entity_under_cursor(state)
    if not fixture:
        return state._replace(message_buffer=("There is nothing here to use.",), proximity_menu_active=False)
    return reduce_use(state, "", fixture.id)


def reduce_interact_read(state: GameState) -> GameState:
    """[R] Reads the log fixture under the cursor."""
    fixture, _ = entity_under_cursor(state)
    if not fixture:
        return state._replace(message_buffer=("There is nothing here to read.",), proximity_menu_active=False)
    return reduce_read(state, fixture.id)


def reduce_interact_scavenge(state: GameState) -> GameState:
    """[F] Searches the fixture under the cursor."""
    fixture, _ = entity_under_cursor(state)
    if not fixture:
        return state._replace(message_buffer=("There is nothing here to search.",), proximity_menu_active=False)
    return reduce_scavenge(state, fixture.id)


def reduce_interact_cancel(state: GameState) -> GameState:
    """[X] Dismisses the proximity menu."""
    return state._replace(proximity_menu_active=False, message_buffer=())


def reduce_read(state: GameState, fixture_id: str) -> GameState:
    """Reads a log fixture. Locked sections need signal_analysis, signal_boost or lore. Advances the tick."""
    fixture = _find_fixture(state.nodes[state.current_node_id], fixture_id)
    if not fixture:
        return state._replace(message_buffer=(f"Nothing called '{fixture_id.strip()}' here.",))
    if fixture.on_use_effect != "log":
        return _say(state, f"There is nothing to read on the {fixture.name}.")

    lines = [f"{fixture.name}: {fixture.log_text or fixture.description}"]
    if fixture.log_text_locked:
        if rules.can_read_locked_logs(state):
            lines.append(f"Decoded: {fixture.log_text_locked}")
        else:
            lines.append(quiet("Part of it is scrambled. Radio Ears, a signal specialist "
                               "or an old tally slate could make sense of it."))
    read = state._replace(message_buffer=tuple(lines))
    return _refresh_menu(process_tick(read, f"Read the {fixture.name}.", {"used_fixture_id": fixture.id}))


def reduce_scavenge(state: GameState, fixture_id: Optional[str] = None,
                    preferred_item_idx: Optional[int] = None) -> GameState:
    """Searches a container fixture, prying it open first if it is sealed. Advances the tick."""
    node = state.nodes[state.current_node_id]
    fixture = _find_fixture(node, fixture_id) if fixture_id else entity_under_cursor(state)[0]
    if not fixture:
        return state._replace(message_buffer=("Search what? Give a name, e.g. /search locker.",),
                              proximity_menu_active=False)
    if fixture.on_use_effect != "scavenge":
        return _say(state, f"Nothing to search in the {fixture.name}.")
    if fixture.state == FixtureState.SPENT.value:
        return _say(state, f"The {fixture.name} is empty.")

    inventory = state.character.inventory
    tool_note = ""
    xp = {"logistics": routine.XP_SEARCH}
    if fixture.state in CLOSED_STATES and fixture.required_tags:
        source = rules.resolve_requirement(state, fixture.required_tags, preferred_item_idx)
        if not source:
            return _say(state, f"The {fixture.name} is sealed. Needs {needs(fixture.required_tags)}.")
        inventory, tool_note = _spend(state, source, "unlock")
        xp["engineering"] = routine.XP_PRY

    found: List[Item] = [it for it in (rules.catalog_item(state, i) for i in fixture.yields or ("scrap_metal",)) if it]
    bonus = ""
    if "scavenger_instinct" in state.character.unlocked_capabilities:
        scrap = rules.catalog_item(state, "scrap_metal")
        if scrap:
            found.append(scrap)
            bonus = " (Sharp Eye: extra scrap)"
    names = ", ".join(it.name for it in found) or "nothing useful"

    messages = [gain(f"Found: {names}{bonus}.")]
    if tool_note:
        messages.append(f"Pried open the {fixture.name}.{tool_note}")
    new_node = _with_fixture(node, fixture._replace(state=FixtureState.SPENT.value))
    searched = _with_node(state, new_node)._replace(
        character=state.character._replace(inventory=inventory + tuple(found)),
        message_buffer=tuple(messages),
    )
    return _refresh_menu(process_tick(
        searched, f"Searched the {fixture.name}.", {"used_fixture_id": fixture.id, "xp": xp}, physical=True))


def reduce_use(state: GameState, item_id: str, fixture_id: str) -> GameState:
    """
    Uses a fixture in the compartment. item_id is optional: when given, that item is
    preferred, but a skill, clearance or companion that fits always goes first so
    nothing wears needlessly. Advances the tick on success.
    """
    item_idx = None
    if item_id.strip():
        item_idx = rules.find_item(state, item_id)
        if item_idx is None:
            return state._replace(message_buffer=(f"You don't have '{item_id.strip()}'.",))

    node = state.nodes[state.current_node_id]
    fixture = _find_fixture(node, fixture_id)
    if not fixture:
        return state._replace(message_buffer=(f"Nothing called '{fixture_id.strip()}' here.",))

    effect = fixture.on_use_effect
    if effect == "log":
        return reduce_read(state, fixture.id)
    if effect == "sleep":
        return reduce_sleep(state)
    if fixture.state in DONE_STATES:
        return _say(state, f"The {fixture.name} is already {STATE_WORDS.get(fixture.state, fixture.state)}.")
    if effect == "repair" and fixture.state == FixtureState.ACTIVE.value:
        return _say(state, f"The {fixture.name} is already working.")
    if effect == "scavenge":
        if fixture.state in CLOSED_STATES:
            return reduce_scavenge(state, fixture.id, item_idx)
        return _say(state, "That doesn't work here. Press F to search it.")

    inventory = state.character.inventory
    new_node = node
    context: Dict[str, object] = {"used_fixture_id": fixture.id}
    messages: List[str] = []

    if effect == "refill":
        idx = rules.first_item_with_tags(state, ("refillable",), item_idx)
        if idx is None:
            return _say(state, "You have nothing to fill. Bring a canteen.")
        item = inventory[idx]
        inventory = inventory[:idx] + (item._replace(integrity=item.max_integrity),) + inventory[idx + 1:]
        messages.append(f"{item.name} refilled.")

    elif effect == "smelt":
        idx = rules.first_item_with_tags(state, ("mineral", "salvage"), item_idx)
        if idx is None:
            return _say(state, f"The {fixture.name} needs ore or scrap metal.")
        item = inventory[idx]
        inventory = rules.remove_item(inventory, idx)
        if "mineral" in item.tags and "scrap_fabrication" in state.character.unlocked_capabilities:
            product = rules.catalog_item(state, "tool_prybar")
        elif "mineral" in item.tags:
            product = rules.catalog_item(state, "scrap_metal")
            messages.append("Forging tools from ore takes the Making Parts skill.")
        else:
            product = rules.catalog_item(state, "fitting_copper")
        if product:
            inventory = inventory + (product,)
            messages.insert(0, gain(f"Got: {product.name}, smelted from your {item.name}."))
        context["xp"] = {"engineering": routine.XP_SMELT}

    elif effect in _TOOL_EFFECTS and fixture.required_tags:
        source = rules.resolve_requirement(state, fixture.required_tags, item_idx)
        if not source:
            if item_idx is not None:
                return _say(state, f"That doesn't work. Needs {needs(fixture.required_tags)}.")
            return _say(state, f"Needs {needs(fixture.required_tags)}.")
        inventory, note = _spend(state, source, effect)

        context["xp"] = {"engineering": {"unlock": routine.XP_UNLOCK, "repair": routine.XP_REPAIR,
                                         "override": routine.XP_OVERRIDE}.get(effect, 0)}
        if effect == "unlock":
            new_node = _with_fixture(node, fixture._replace(state=FixtureState.OPEN.value))
            messages.append(f"The {fixture.name} opens.{note}")
        elif effect == "repair":
            new_node = _with_fixture(node, fixture._replace(state=FixtureState.ACTIVE.value))
            messages.append(f"The {fixture.name} is fixed.{note}")
            if fixture.on_repair_vitals:
                v = fixture.on_repair_vitals
                new_node = new_node._replace(base_vitals=v)
                hazards = hazard_words(v)
                messages.append(gain(f"Air here is now {v.pressure_kpa:g} kPa, {v.temperature_c}°C"
                                     + (f" ({hazards})." if hazards else ". Safe to breathe.")))
        elif effect == "harvest":
            yields = [it for it in (rules.catalog_item(state, i) for i in fixture.yields or ("algae_paste",)) if it]
            inventory = inventory + tuple(yields)
            messages.append(gain(f"Got: {', '.join(it.name for it in yields)}.") + note)
            context["xp"] = {"logistics": routine.XP_HARVEST}
            if fixture.restock:
                new_node = _with_fixture(node, fixture._replace(state=FixtureState.SPENT.value))
                messages.append(f"The {fixture.name} regrows overnight.")
        else:  # override
            new_node = _with_fixture(node, fixture._replace(state=FixtureState.SPENT.value))
            messages.append(f"You bypass the {fixture.name}.{note}")
            target = new_node.fixtures.get(fixture.opens_fixture) if fixture.opens_fixture else None
            if target:
                new_node = _with_fixture(new_node, target._replace(state=FixtureState.OPEN.value))
                messages.append(f"The {target.name} opens.")
            if fixture.grants_capability:
                caps = state.character.unlocked_capabilities | {fixture.grants_capability}
                state = state._replace(character=state.character._replace(unlocked_capabilities=caps))
                messages.append(gain(f"Got: {tag_name(fixture.grants_capability)} (on file, counts forever)."))
    else:
        return _say(state, "That doesn't work here.")

    used = _with_node(state, new_node)._replace(
        character=state.character._replace(inventory=inventory),
        message_buffer=tuple(messages),
    )
    return _refresh_menu(process_tick(used, f"Used the {fixture.name}.", context, physical=True))


# --- Self and time ---------------------------------------------------------

CONSUME_EFFECTS: Dict[str, Tuple[float, float, float]] = {
    # tag: (air, radiation, cold) reduction
    "hydration": (0.0, 0.0, 1.5),
    "nutrition": (1.0, 1.0, 1.0),
}


def reduce_consume(state: GameState, item_id: str = "") -> GameState:
    """Eats or drinks a sustenance item to shed exposure, then advances the tick."""
    inventory = state.character.inventory
    if item_id.strip():
        idx = rules.find_item(state, item_id)
        if idx is None:
            return state._replace(message_buffer=(f"You don't have '{item_id.strip()}'.",))
    else:
        idx = next((i for i, it in enumerate(inventory) if it.category == ItemCategory.SUSTENANCE.value), None)
        if idx is None:
            return state._replace(message_buffer=("You have nothing to eat or drink.",))
    item = inventory[idx]
    if item.category != ItemCategory.SUSTENANCE.value:
        return state._replace(message_buffer=(f"You can't eat or drink the {item.name}.",))

    p, r, t = 0.0, 0.0, 0.0
    for tag in item.tags:
        dp, dr, dt = CONSUME_EFFECTS.get(tag, (0.0, 0.0, 0.0))
        p, r, t = p + dp, r + dr, t + dt
    if "biomass" in item.tags and "bio_filter" in rules.party_tags(state):
        r += 2.0
    exp = state.character.exposure
    new_exp = exp._replace(
        pressure_debt=round(max(0.0, exp.pressure_debt - p), 2),
        radiation_dose=round(max(0.0, exp.radiation_dose - r), 2),
        thermal_stress=round(max(0.0, exp.thermal_stress - t), 2),
    )
    inventory, _ = rules.wear_item(inventory, idx)
    relief = ", ".join(f"{name} -{v:g}" for name, v in (("Air", p), ("Rad", r), ("Cold", t)) if v)
    consumed = state._replace(
        character=state.character._replace(inventory=inventory, exposure=new_exp),
        message_buffer=(f"You have some {item.name}. {relief or 'No effect'}.",),
    )
    return _refresh_menu(process_tick(consumed, f"Ate or drank {item.name}."))


def reduce_wait(state: GameState) -> GameState:
    """Advances simulation clock by 1 cycle."""
    return _refresh_menu(process_tick(state._replace(message_buffer=("You wait.",)), "Waited."))


def reduce_map(state: GameState) -> GameState:
    """Switches active screen to topology map."""
    return state._replace(active_view="map_topology", message_buffer=())


def reduce_back(state: GameState) -> GameState:
    """Returns to compartment view from map."""
    return _refresh_menu(state._replace(active_view="compartment", message_buffer=()))


def reduce_pack(state: GameState) -> GameState:
    """Displays carried items and status."""
    lines = ["PACK:"]
    if not state.character.inventory:
        lines.append("  (empty)")
    for it, count in rules.stack_items(state.character.inventory):
        cond = f" {it.integrity}/{it.max_integrity}" if it.max_integrity > 1 else ""
        qty = f" x{count}" if count > 1 else ""
        lines.append(f"  {it.name}{qty}{cond}")
    return state._replace(message_buffer=tuple(lines))


def reduce_character(state: GameState) -> GameState:
    """Background plus each work skill's level, experience and next perk."""
    lines = [f"{state.character.name}, former {state.character.past_work.replace('_', ' ')}. "
             f"Keepsake: {state.character.personal_anchor.name}."]
    for skill in state.skill_catalog:
        xp = state.skills.get(skill.id, 0)
        level = routine.skill_level(skill, xp)
        upcoming = routine.next_perk(skill, xp)
        progress = f"{xp}/{upcoming.xp} XP" if upcoming else f"{xp} XP, max"
        lines.append(f"{skill.name.upper()} {level} ({progress}). {skill.earned_by}")
        for perk in skill.perks:
            if xp >= perk.xp:
                lines.append(f"  + {perk.text}")
        if upcoming:
            lines.append(f"  Next at {upcoming.level}: {upcoming.text}")
    return state._replace(message_buffer=tuple(lines))


def reduce_jobs(state: GameState) -> GameState:
    """Today's jobs and their progress."""
    lines = [f"JOBS, DAY {state.day} ({routine.shift_name(state).lower()} shift):"]
    if not state.jobs:
        lines.append("  No jobs posted.")
    for job in state.jobs:
        mark = "x" if job.done else " "
        step = f" ({job.progress}/{job.count})" if job.kind == "stay" and not job.done else ""
        rewards = [state.item_catalog[i].name for i in job.reward_items if i in state.item_catalog]
        pay = f"{job.xp} {routine.skill_name(state, job.skill)}" + (f", {', '.join(rewards)}" if rewards else "")
        lines.append(f"  [{mark}] {job.title}{step}. Pays {pay}.")
    lines.append("New jobs are posted each morning.")
    return state._replace(message_buffer=tuple(lines))


def reduce_sleep(state: GameState) -> GameState:
    """Sleeps in a bunk: night passes, exposure clears, stock refills and new jobs are posted."""
    node = state.nodes[state.current_node_id]
    if not any(f.on_use_effect == "sleep" for f in node.fixtures.values()):
        return _say(state, "There is no bunk here. Bunks are in the Bunkroom and the Habitat Dome.")
    if routine.awake_turns(state) < routine.MIN_AWAKE_TO_SLEEP:
        return _say(state, "You're not tired enough to sleep yet.")
    slept = routine.start_day(state, node.id, ("You sleep through the night.",))
    return slept._replace(action_log=(state.action_log + (f"Slept. Day {slept.day}.",))[-20:])


def reduce_team(state: GameState) -> GameState:
    """Displays the companions travelling with the player."""
    lines = ["TEAM:"]
    if not state.companions:
        lines.append("  Nobody yet. Some people you trade with may join you.")
    for c in state.companions:
        helps = f" Counts as {tag_name(c.capability_tag)}." if c.capability_tag else ""
        lines.append(f"  {c.name}, {c.title}. {c.status}.{helps}")
    return state._replace(message_buffer=tuple(lines))


def reduce_log(state: GameState) -> GameState:
    """Displays recent action log."""
    lines = ["RECENT:"]
    for entry in state.action_log[-10:]:
        lines.append(f"  {entry}")
    return state._replace(message_buffer=tuple(lines))


def reduce_flavor(state: GameState, toggle: str) -> GameState:
    """Toggles room descriptions on arrival."""
    arg = toggle.strip().lower()
    new_val = arg == "on" if arg in ("on", "off") else not state.flavor_enabled
    return state._replace(flavor_enabled=new_val,
                          message_buffer=(f"Room descriptions {'on' if new_val else 'off'}.",))


def reduce_color(state: GameState, toggle: str) -> GameState:
    """Toggles colour and text styles."""
    arg = toggle.strip().lower()
    new_val = arg == "on" if arg in ("on", "off") else not state.color_enabled
    return state._replace(color_enabled=new_val, message_buffer=(f"Colour {'on' if new_val else 'off'}.",))


HELP_TOPICS: Dict[str, Tuple[str, ...]] = {
    "": (
        "HELP. Walk onto things to use them.",
        "  WASD move  M map  P pack  C character  T team  J jobs",
        "  Q quit  / type a command",
        "  On a tile:  I inspect  U use  F search  R read",
        "              T talk  B trade  G go  X close",
        "More: /help survival  /help trade  /help commands",
    ),
    "survival": (
        "SURVIVAL. Air, Rad and Cold build up in bad rooms.",
        "  At 15 you black out and wake in the Bunkroom.",
        "  Safe rooms (normal air, top level) lower all three.",
        "  /consume eats or drinks to lower them.",
        "  After 60 turns awake you're tired; at 90 you drop.",
        "  Sleep in a bunk (Bunkroom, Habitat Dome) to start a new day.",
        "  Fixing broken valves and walls makes rooms safer.",
    ),
    "trade": (
        "TRADE. T shows what someone wants; B makes the trade.",
        "  /barter <person> <item> offers a specific item.",
        "  Some traders join your team and lend their skills.",
    ),
    "commands": (
        "COMMANDS:",
        "  /look  /inspect <thing>  /use [item] <thing>",
        "  /search <thing>  /read <thing>  /talk <person>",
        "  /barter [person] [item]  /consume [item]",
        "  /leave <exit>  /wait  /map  /pack  /character",
        "  /team  /jobs  /sleep  /log  /flavor on|off",
        "  /color on|off  /quit",
    ),
}


def reduce_help(state: GameState, topic: str = "") -> GameState:
    """Displays help by topic."""
    lines = HELP_TOPICS.get(topic.strip().lower(), HELP_TOPICS[""])
    return state._replace(message_buffer=lines)
