from typing import Optional, Tuple, List, Dict

from core.types import (
    GameState, Node, Fixture, Actor, Edge, Item, FixtureState, ItemCategory,
)
from core.tick import process_tick
from core.presets import DEFAULT_DATA_DIR, load_catalogs
from core import rules
from core.rules import Source

# Default catalogues, for callers that build items outside a game state (tests, tools).
ALL_ITEMS_BY_ID, ALL_COMPANIONS_BY_ID = load_catalogs(DEFAULT_DATA_DIR)

_DONE_STATES = (FixtureState.OPEN.value, FixtureState.SPENT.value)
_CLOSED_STATES = (FixtureState.SEALED.value, FixtureState.LOCKED.value)
_TOOL_EFFECTS = ("unlock", "repair", "harvest", "override")


# --- Lookup helpers --------------------------------------------------------

def _get_entity_at(node: Node, row: int, col: int) -> Tuple[Optional[Fixture], Optional[Actor]]:
    """Returns any fixture or actor placed at (row, col) on the node grid."""
    for placement in node.placements:
        if placement.row == row and placement.col == col:
            return node.fixtures.get(placement.entity_id), node.actors.get(placement.entity_id)
    return None, None


def _entity_under_cursor(state: GameState) -> Tuple[Optional[Fixture], Optional[Actor]]:
    return _get_entity_at(state.nodes[state.current_node_id], state.player_row, state.player_col)


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


def _say(state: GameState, *lines: str) -> GameState:
    """Replaces Zone 5 with lines without advancing time; keeps the menu if the cursor is on an entity."""
    return _refresh_menu(state._replace(message_buffer=tuple(lines)))


def _gate_placement(node: Node, edge: Edge) -> Optional[Tuple[int, int]]:
    gate_ids = {edge.gated_by_fixture} | {f.id for f in node.fixtures.values() if f.grants_edge == edge.id}
    for p in node.placements:
        if p.entity_id in gate_ids:
            return p.row, p.col
    return None


# --- Proximity menu --------------------------------------------------------

def _use_label(state: GameState, fixture: Fixture) -> Optional[str]:
    """Label for the [U] option, or None when using the fixture is not possible right now."""
    effect = fixture.on_use_effect
    if effect in (None, "log", "scavenge") or fixture.state in _DONE_STATES:
        return None
    if effect == "repair" and fixture.state == FixtureState.ACTIVE.value:
        return None
    inventory = state.character.inventory
    if effect == "refill":
        idx = rules.first_item_with_tags(state, ("refillable",))
        return f"Refill {inventory[idx].name}" if idx is not None else None
    if effect == "smelt":
        idx = rules.first_item_with_tags(state, ("mineral", "salvage"))
        return f"Smelt {inventory[idx].name}" if idx is not None else None
    if not fixture.required_tags:
        return None
    source = rules.resolve_requirement(state, fixture.required_tags)
    return f"Use {source.label}" if source else None


def _build_proximity_menu(state: GameState, fixture: Optional[Fixture], actor: Optional[Actor]) -> Tuple[str, ...]:
    """Constructs proximity interaction menu options (§5.2)."""
    entity_name = fixture.name if fixture else (actor.name if actor else "Object")
    opts = ["[I] Inspect"]
    if fixture:
        if fixture.on_use_effect == "scavenge" and fixture.state != FixtureState.SPENT.value:
            opts.append("[F] Search")
        if fixture.on_use_effect == "log":
            opts.append("[R] Read")
        label = _use_label(state, fixture)
        if label:
            opts.append(f"[U] {label}")
        if fixture.grants_edge and fixture.state == FixtureState.OPEN.value:
            edge = state.nodes[state.current_node_id].edges.get(fixture.grants_edge)
            if edge:
                opts.append(f"[G] Go -> {edge.label}")
    if actor:
        opts.append("[T] Talk")
        if rules.trade_item_idx(state, actor) is not None:
            opts.append("[B] Barter")
    opts.append("[X] Cancel")
    return (f"Near: {entity_name}", "  ".join(opts))


def _refresh_menu(state: GameState) -> GameState:
    """Appends a fresh proximity menu when the cursor rests on an entity; hides it otherwise."""
    if state.active_view != "compartment":
        return state._replace(proximity_menu_active=False)
    fixture, actor = _entity_under_cursor(state)
    if not (fixture or actor):
        return state._replace(proximity_menu_active=False)
    return state._replace(
        message_buffer=state.message_buffer + _build_proximity_menu(state, fixture, actor),
        proximity_menu_active=True,
    )


def _spend(state: GameState, source: Optional[Source], effect: str) -> Tuple[Tuple[Item, ...], str]:
    """Applies wear for the item that satisfied a requirement. Returns (inventory, note)."""
    inventory = state.character.inventory
    if source is None or source.item_idx is None:
        return inventory, f" ({source.label})" if source else ""
    item = inventory[source.item_idx]
    if effect == "harvest" or rules.tool_protected(state, item):
        return inventory, f" Used {item.name}."
    inventory, used_up = rules.wear_item(inventory, source.item_idx)
    if used_up:
        return inventory, f" {item.name} was used up."
    return inventory, f" Used {item.name}."


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
        return state._replace(message_buffer=(f"Invalid direction '{direction}'. Use W/A/S/D.",))

    new_r = state.player_row + delta[0]
    new_c = state.player_col + delta[1]
    blocked = state._replace(message_buffer=("Bulkhead blocks movement.",), proximity_menu_active=False)
    if not (0 <= new_r < node.size and 0 <= new_c < node.size):
        return blocked
    fixture, actor = _get_entity_at(node, new_r, new_c)
    is_border = new_r in (0, node.size - 1) or new_c in (0, node.size - 1)
    if is_border and not fixture and not actor:
        return blocked

    moved = state._replace(player_row=new_r, player_col=new_c, message_buffer=())
    return _refresh_menu(process_tick(moved, ""))


def _enter_node(state: GameState, edge: Edge, via_fixture: Optional[Fixture]) -> GameState:
    """Crosses edge into its destination node. Gate checks happen in the callers."""
    if edge.requires_capability and edge.requires_capability not in rules.party_tags(state):
        return _say(state, f"Requires capability '{edge.requires_capability}' to traverse here.")
    dest = state.nodes.get(edge.target_node_id)
    if not dest:
        return _say(state, f"Route error: destination {edge.target_node_id} unreachable.")

    messages = [f"Moved to {dest.name}."]
    if rules.is_critical(state):
        messages.append("[!] Moving under severe physical strain.")

    origin = state.nodes[state.current_node_id]
    gate_ids = {edge.gated_by_fixture, via_fixture.id if via_fixture else None}
    for fid in gate_ids:
        gate = origin.fixtures.get(fid) if fid else None
        if gate and gate.reseal_on_pass and gate.state == FixtureState.OPEN.value:
            origin = _with_fixture(origin, gate._replace(state=FixtureState.SEALED.value))
            messages.append(f"{gate.name} reseals behind you.")

    moved = _with_node(state, origin)._replace(
        current_node_id=dest.id,
        player_row=dest.size // 2,
        player_col=dest.size // 2,
        active_view="compartment",
        message_buffer=state.message_buffer + tuple(messages),
    )
    return _refresh_menu(process_tick(moved, f"Traversed to {dest.name}."))


def reduce_interact_go(state: GameState) -> GameState:
    """[G] Traverses the open edge granted by the fixture under the cursor."""
    node = state.nodes[state.current_node_id]
    fixture, _ = _entity_under_cursor(state)
    if not fixture or not fixture.grants_edge:
        return state._replace(message_buffer=("No hatch or exit under cursor to go through.",),
                              proximity_menu_active=False)
    edge = node.edges.get(fixture.grants_edge)
    if not edge:
        return _say(state, f"Route error: edge '{fixture.grants_edge}' not found.")
    if fixture.state != FixtureState.OPEN.value:
        return _say(state, f"Access blocked. {fixture.name} is {fixture.state.upper()}.")
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
        available = ", ".join(f"'{k}' ({v.label})" for k, v in node.edges.items())
        return state._replace(message_buffer=(f"No exit '{edge_id}'. Available: {available}",))

    gate = node.fixtures.get(edge.gated_by_fixture) if edge.gated_by_fixture else None
    if gate and gate.state != FixtureState.OPEN.value:
        return state._replace(message_buffer=(f"Access blocked. {gate.name} is {gate.state.upper()}.",))
    if edge.requires_capability and edge.requires_capability not in rules.party_tags(state):
        return state._replace(message_buffer=(f"Requires capability '{edge.requires_capability}' to traverse here.",))

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

def reduce_interact_inspect(state: GameState) -> GameState:
    """[I] Inspects the entity under the cursor."""
    fixture, actor = _entity_under_cursor(state)
    if fixture or actor:
        return reduce_inspect(state, (fixture or actor).id)
    return state._replace(message_buffer=("Nothing here to inspect.",), proximity_menu_active=False)


def reduce_inspect(state: GameState, target_id: str) -> GameState:
    """Inspects a fixture, actor, inventory item, or exit. Does not advance the tick."""
    target_id = target_id.strip()
    if not target_id:
        return state._replace(message_buffer=("Inspect what? Specify target ID or item name.",))

    node = state.nodes[state.current_node_id]
    suffix = " [readings unclear due to environmental stress]" if rules.is_stressed(state) else ""

    fixture = _find_fixture(node, target_id)
    if fixture:
        lines = [f"{fixture.name} [{fixture.id}]: {fixture.description}{suffix} State: {fixture.state.upper()}."]
        pending = fixture.state not in _DONE_STATES
        if fixture.required_tags and pending:
            needed = " or ".join(f"'{t}'" for t in fixture.required_tags)
            if "seam_discipline" in state.character.unlocked_capabilities:
                source = rules.resolve_requirement(state, fixture.required_tags)
                have = f" You can do it with: {source.label}." if source else " You have nothing that fits."
                lines.append(f"  [Fixing Leaks] Needs {needed}.{have}")
            else:
                lines.append(f"  Requires one of: {needed}.")
        return _say(state, *lines)

    actor = _find_actor(node, target_id)
    if actor:
        return _say(state, f"{actor.name} ({actor.title}): {actor.status}.{suffix} \"{rules.dialogue_for(state, actor)}\"")

    idx = rules.find_item(state, target_id)
    if idx is not None:
        item = state.character.inventory[idx]
        cond = f"{item.integrity}/{item.max_integrity}" if item.max_integrity > 0 else "PERMANENT"
        return _say(state, f"{item.name} [{item.id}] ({item.category}): {item.description}{suffix} "
                           f"Integrity: {cond}. Tags: [{', '.join(item.tags)}].")

    edge = node.edges.get(target_id)
    if edge:
        lines = [f"Exit to {edge.label} [{edge.id}].{suffix}"]
        target_node = state.nodes.get(edge.target_node_id)
        if "bulkhead_ear" in state.character.unlocked_capabilities and target_node:
            v = target_node.base_vitals
            lines.append(f"  [Hear Pressure] Sensor feed: {v.pressure_kpa} kPa, {v.temperature_c}°C, "
                         f"{v.radiation_msv} mSv ({target_node.environment}).")
        gate = node.fixtures.get(edge.gated_by_fixture) if edge.gated_by_fixture else None
        if gate and gate.state != FixtureState.OPEN.value:
            lines.append(f"  Gated by {gate.name} (currently {gate.state}).")
        if edge.requires_capability:
            lines.append(f"  Requires clearance/capability: '{edge.requires_capability}'.")
        return _say(state, *lines)

    return state._replace(message_buffer=(f"Nothing found matching '{target_id}' to inspect.",))


def reduce_interact_talk(state: GameState) -> GameState:
    """[T] Talks with the actor under the cursor."""
    _, actor = _entity_under_cursor(state)
    if not actor:
        return state._replace(message_buffer=("No one here to speak with.",), proximity_menu_active=False)
    return reduce_talk(state, actor.id)


def reduce_talk(state: GameState, actor_id: str) -> GameState:
    """Talks to an actor. Describes any trade on offer but never trades by itself. Advances the tick."""
    actor = _find_actor(state.nodes[state.current_node_id], actor_id)
    if not actor:
        return state._replace(message_buffer=(f"No one named '{actor_id.strip()}' here.",))

    lines = [f"{actor.name}: \"{rules.dialogue_for(state, actor)}\""]
    offered = rules.catalog_item(state, actor.trade_offered_id)
    idx = rules.trade_item_idx(state, actor)
    if idx is not None and offered:
        mine = state.character.inventory[idx]
        lines.append(f"Trade offer: your {mine.name} for {offered.name}. [B] or /barter to accept.")
    elif offered and not actor.trade_completed and actor.trade_required_tags:
        wants = " or ".join(actor.trade_required_tags)
        lines.append(f"{actor.name} would trade {offered.name} for anything tagged {wants}.")
    talked = state._replace(message_buffer=tuple(lines))
    return _refresh_menu(process_tick(talked, f"Spoke with {actor.name}."))


def reduce_interact_barter(state: GameState) -> GameState:
    """[B] Barters with the actor under the cursor."""
    _, actor = _entity_under_cursor(state)
    if not actor:
        return state._replace(message_buffer=("No one here to barter with.",), proximity_menu_active=False)
    return reduce_barter(state, actor.id)


def reduce_barter(state: GameState, actor_id: str = "", item_id: str = "") -> GameState:
    """
    Executes an actor's trade (§5.4). Any item carrying one of the actor's tags is accepted.
    Credentials are shown and kept; items that wear lose one integrity; others change hands.
    """
    node = state.nodes[state.current_node_id]
    if actor_id:
        actor = _find_actor(node, actor_id)
    else:
        actor = _entity_under_cursor(state)[1]
    if not actor:
        return state._replace(message_buffer=("No one here to barter with.",))
    if actor.trade_completed:
        return _say(state, f"{actor.name} has nothing more to trade.")
    offered = rules.catalog_item(state, actor.trade_offered_id)
    if not offered or not actor.trade_required_tags:
        return _say(state, f"{actor.name} isn't trading.")

    preferred = None
    if item_id:
        preferred = rules.find_item(state, item_id)
        if preferred is None:
            return _say(state, f"You don't carry '{item_id}'.")
    idx = rules.trade_item_idx(state, actor, preferred)
    if idx is None:
        return _say(state, f"{actor.name} wants something tagged {' or '.join(actor.trade_required_tags)}.")
    if preferred is not None and idx != preferred:
        return _say(state, f"{actor.name} won't take that. Wants: {' or '.join(actor.trade_required_tags)}.")

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

    messages = [f"Exchanged {given.name} for {offered.name}.",
                f"{actor.name}: \"{updated_actor.dialogue_post_trade or 'Transaction confirmed.'}\""]
    companions = state.companions
    recruit = rules.catalog_companion(state, actor.companion_unlock)
    if recruit and not any(c.id == recruit.id for c in companions):
        companions = companions + (recruit,)
        new_node = new_node._replace(placements=tuple(p for p in new_node.placements if p.entity_id != actor.id))
        messages.append(f"[PARTY] Companion joined: {recruit.name} ({recruit.title}).")

    traded = _with_node(state, new_node)._replace(
        character=state.character._replace(inventory=inventory),
        companions=companions,
        message_buffer=tuple(messages),
    )
    return _refresh_menu(process_tick(
        traded, f"Traded with {actor.name}.", {"traded_actor_id": actor.id}, physical=True))


# --- Fixtures --------------------------------------------------------------

def reduce_interact_use(state: GameState) -> GameState:
    """[U] Uses the fixture under the cursor with whatever best satisfies it."""
    fixture, _ = _entity_under_cursor(state)
    if not fixture:
        return state._replace(message_buffer=("No fixture here to use items on.",), proximity_menu_active=False)
    return reduce_use(state, "", fixture.id)


def reduce_interact_read(state: GameState) -> GameState:
    """[R] Reads the log fixture under the cursor."""
    fixture, _ = _entity_under_cursor(state)
    if not fixture:
        return state._replace(message_buffer=("Nothing here to read.",), proximity_menu_active=False)
    return reduce_read(state, fixture.id)


def reduce_interact_scavenge(state: GameState) -> GameState:
    """[F] Searches the fixture under the cursor."""
    fixture, _ = _entity_under_cursor(state)
    if not fixture:
        return state._replace(message_buffer=("Nothing here to search.",), proximity_menu_active=False)
    return reduce_scavenge(state, fixture.id)


def reduce_interact_cancel(state: GameState) -> GameState:
    """[X] Dismisses the proximity menu."""
    return state._replace(proximity_menu_active=False, message_buffer=())


def reduce_read(state: GameState, fixture_id: str) -> GameState:
    """Reads a log fixture. Locked sections need signal_analysis, signal_boost or lore. Advances the tick."""
    fixture = _find_fixture(state.nodes[state.current_node_id], fixture_id)
    if not fixture:
        return state._replace(message_buffer=(f"No fixture '{fixture_id.strip()}' here.",))
    if fixture.on_use_effect != "log":
        return _say(state, f"There is nothing to read on {fixture.name}.")

    lines = [f"{fixture.name}: {fixture.log_text or fixture.description}"]
    if fixture.log_text_locked:
        if rules.can_read_locked_logs(state):
            lines.append(f"[Decoded] {fixture.log_text_locked}")
        else:
            lines.append("Part of the feed is encrypted. Radio Ears, a signal specialist, "
                         "or an old tally slate could make sense of it.")
    read = state._replace(message_buffer=tuple(lines))
    return _refresh_menu(process_tick(read, f"Read {fixture.name}.", {"used_fixture_id": fixture.id}))


def reduce_scavenge(state: GameState, fixture_id: Optional[str] = None,
                    preferred_item_idx: Optional[int] = None) -> GameState:
    """Searches a container fixture, prying it open first if it is sealed. Advances the tick."""
    node = state.nodes[state.current_node_id]
    fixture = _find_fixture(node, fixture_id) if fixture_id else _entity_under_cursor(state)[0]
    if not fixture:
        return state._replace(message_buffer=("Specify a container or scrap cache to search.",),
                              proximity_menu_active=False)
    if fixture.on_use_effect != "scavenge":
        return _say(state, f"Nothing to search in {fixture.name}.")
    if fixture.state == FixtureState.SPENT.value:
        return _say(state, f"{fixture.name} is picked clean. Nothing left to salvage.")

    inventory = state.character.inventory
    tool_note = ""
    if fixture.state in _CLOSED_STATES and fixture.required_tags:
        source = rules.resolve_requirement(state, fixture.required_tags, preferred_item_idx)
        if not source:
            needed = " or ".join(f"'{t}'" for t in fixture.required_tags)
            return _say(state, f"{fixture.name} is sealed tight. Requires {needed} to open.")
        inventory, tool_note = _spend(state, source, "unlock")

    found: List[Item] = [it for it in (rules.catalog_item(state, i) for i in fixture.yields or ("scrap_metal",)) if it]
    bonus_note = ""
    if "scavenger_instinct" in state.character.unlocked_capabilities:
        scrap = rules.catalog_item(state, "scrap_metal")
        if scrap:
            found.append(scrap)
            bonus_note = " [Sharp Eye: Found bonus scrap metal!]"
    found_names = ", ".join(it.name for it in found) or "nothing useful"

    new_node = _with_fixture(node, fixture._replace(state=FixtureState.SPENT.value))
    searched = _with_node(state, new_node)._replace(
        character=state.character._replace(inventory=inventory + tuple(found)),
        message_buffer=(f"Searched {fixture.name}: found {found_names}.{tool_note}{bonus_note}",),
    )
    return _refresh_menu(process_tick(
        searched, f"Scavenged {fixture.name}.", {"used_fixture_id": fixture.id}, physical=True))


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
            return state._replace(message_buffer=(f"You don't carry '{item_id.strip()}'.",))

    node = state.nodes[state.current_node_id]
    fixture = _find_fixture(node, fixture_id)
    if not fixture:
        return state._replace(message_buffer=(f"No fixture '{fixture_id.strip()}' here.",))

    effect = fixture.on_use_effect
    if effect == "log":
        return reduce_read(state, fixture.id)
    if fixture.state in _DONE_STATES:
        return _say(state, "Already done.")
    if effect == "repair" and fixture.state == FixtureState.ACTIVE.value:
        return _say(state, f"{fixture.name} is already running.")
    if effect == "scavenge":
        if fixture.state in _CLOSED_STATES:
            return reduce_scavenge(state, fixture.id, item_idx)
        return _say(state, "That doesn't work here. Search it with [F] instead.")

    inventory = state.character.inventory
    new_node = node
    context = {"used_fixture_id": fixture.id}

    if effect == "refill":
        idx = rules.first_item_with_tags(state, ("refillable",), item_idx)
        if idx is None:
            return _say(state, "Nothing to refill. You need a refillable container.")
        item = inventory[idx]
        inventory = inventory[:idx] + (item._replace(integrity=item.max_integrity),) + inventory[idx + 1:]
        msg = f"Refilled {item.name} at {fixture.name}."

    elif effect == "smelt":
        idx = rules.first_item_with_tags(state, ("mineral", "salvage"), item_idx)
        if idx is None:
            return _say(state, f"{fixture.name} needs ore or scrap metal.")
        item = inventory[idx]
        inventory = rules.remove_item(inventory, idx)
        if "mineral" in item.tags and "scrap_fabrication" in state.character.unlocked_capabilities:
            product = rules.catalog_item(state, "tool_prybar")
            msg = f"Refined {item.name} in {fixture.name} into a heavy Thermal Pry-Bar."
        elif "mineral" in item.tags:
            product = rules.catalog_item(state, "scrap_metal")
            msg = f"Melted {item.name} down to scrap. Forging tools takes Making Parts."
        else:
            product = rules.catalog_item(state, "fitting_copper")
            msg = f"Melted {item.name} in {fixture.name} and cast a clean Copper Pipe Fitting."
        if product:
            inventory = inventory + (product,)

    elif effect in _TOOL_EFFECTS and fixture.required_tags:
        source = rules.resolve_requirement(state, fixture.required_tags, item_idx)
        if not source:
            if item_idx is not None:
                return _say(state, "That doesn't work here.")
            return _say(state, f"Requires one of: {', '.join(fixture.required_tags)}.")
        inventory, note = _spend(state, source, effect)

        if effect == "unlock":
            new_node = _with_fixture(node, fixture._replace(state=FixtureState.OPEN.value))
            msg = f"Unlocked {fixture.name}.{note}"
        elif effect == "repair":
            new_node = _with_fixture(node, fixture._replace(state=FixtureState.ACTIVE.value))
            msg = f"Repaired and engaged {fixture.name}.{note}"
            if fixture.on_repair_vitals:
                v = fixture.on_repair_vitals
                new_node = new_node._replace(base_vitals=v)
                msg += f" Compartment now reads {v.pressure_kpa} kPa, {v.temperature_c}°C."
        elif effect == "harvest":
            yields = [rules.catalog_item(state, i) for i in fixture.yields or ("algae_paste",)]
            inventory = inventory + tuple(it for it in yields if it)
            msg = f"Harvested {', '.join(it.name.lower() for it in yields if it)} from {fixture.name}.{note}"
        else:  # override
            new_node = _with_fixture(node, fixture._replace(state=FixtureState.SPENT.value))
            msg = f"Bypassed {fixture.name}.{note}"
            target = new_node.fixtures.get(fixture.opens_fixture) if fixture.opens_fixture else None
            if target:
                new_node = _with_fixture(new_node, target._replace(state=FixtureState.OPEN.value))
                msg += f" {target.name} cycles open."
            if fixture.grants_capability:
                caps = state.character.unlocked_capabilities | {fixture.grants_capability}
                state = state._replace(character=state.character._replace(unlocked_capabilities=caps))
                msg += f" New clearance on file: {fixture.grants_capability}."
    else:
        return _say(state, "That doesn't work here.")

    used = _with_node(state, new_node)._replace(
        character=state.character._replace(inventory=inventory),
        message_buffer=(msg,),
    )
    return _refresh_menu(process_tick(used, f"Used {fixture.name}.", context, physical=True))


# --- Self and time ---------------------------------------------------------

CONSUME_EFFECTS: Dict[str, Tuple[float, float, float]] = {
    # tag: (pressure, radiation, thermal) reduction
    "hydration": (0.0, 0.0, 1.5),
    "nutrition": (1.0, 1.0, 1.0),
}


def reduce_consume(state: GameState, item_id: str = "") -> GameState:
    """Eats or drinks a sustenance item to shed exposure, then advances the tick."""
    inventory = state.character.inventory
    if item_id.strip():
        idx = rules.find_item(state, item_id)
        if idx is None:
            return state._replace(message_buffer=(f"You don't carry '{item_id.strip()}'.",))
    else:
        idx = next((i for i, it in enumerate(inventory) if it.category == ItemCategory.SUSTENANCE.value), None)
        if idx is None:
            return state._replace(message_buffer=("You carry nothing to eat or drink.",))
    item = inventory[idx]
    if item.category != ItemCategory.SUSTENANCE.value:
        return state._replace(message_buffer=(f"{item.name} is not something you can eat or drink.",))

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
    relief = ", ".join(f"{name} -{v:g}" for name, v in (("P", p), ("R", r), ("T", t)) if v)
    consumed = state._replace(
        character=state.character._replace(inventory=inventory, exposure=new_exp),
        message_buffer=(f"Consumed {item.name}. Exposure relief: {relief or 'none'}.",),
    )
    return _refresh_menu(process_tick(consumed, f"Consumed {item.name}."))


def reduce_wait(state: GameState) -> GameState:
    """Advances simulation clock by 1 cycle."""
    return _refresh_menu(process_tick(state._replace(message_buffer=("Waiting. Time passes...",)), "Waited one cycle."))


def reduce_map(state: GameState) -> GameState:
    """Switches active screen to topology map."""
    return state._replace(active_view="map_topology", message_buffer=())


def reduce_back(state: GameState) -> GameState:
    """Returns to compartment view from map."""
    return state._replace(active_view="compartment", message_buffer=())


def reduce_pack(state: GameState) -> GameState:
    """Displays carried items and status."""
    lines = ["CARRIED GEAR (PACK):"]
    if not state.character.inventory:
        lines.append("  (empty)")
    for it, count in rules.stack_items(state.character.inventory):
        cond = f"{it.integrity}/{it.max_integrity}" if it.max_integrity > 0 else "PERM"
        qty = f" x{count}" if count > 1 else ""
        lines.append(f"  - {it.name}{qty} [{it.id}]: condition {cond} | tags: {', '.join(it.tags)}")
    return state._replace(message_buffer=tuple(lines))


def reduce_character(state: GameState) -> GameState:
    """Displays qualitative progression tree and attunements."""
    lines = [
        f"CHARACTER PROFILE: {state.character.name}",
        f"Routine: {state.character.past_work} | Personal Anchor: {state.character.personal_anchor.name}",
        "PROGRESSION TREE ATTUNEMENTS:",
    ]
    for node in state.tree:
        status = "[ATTUNED]" if node.attuned else "[LOCKED]"
        req = f" (Req: {node.prerequisite})" if node.prerequisite else ""
        lines.append(f"  {status} {node.name}{req} - {node.description}")
        if not node.attuned:
            lines.append(f"         Unlock: {node.unlock_condition} -> {node.unlock_parameter}")
    return state._replace(message_buffer=tuple(lines))


def reduce_party(state: GameState) -> GameState:
    """Displays active party companions."""
    lines = ["ACTIVE COMPANIONS (PARTY):"]
    if not state.companions:
        lines.append("  No companions travelling with you. Operating solo.")
    for c in state.companions:
        cap = f" | Contributes: '{c.capability_tag}'" if c.capability_tag else ""
        lines.append(f"  - {c.name} ({c.title}): {c.status}{cap}")
    return state._replace(message_buffer=tuple(lines))


def reduce_log(state: GameState) -> GameState:
    """Displays recent action log."""
    lines = ["RECENT LOG HISTORY:"]
    for idx, entry in enumerate(state.action_log[-10:], 1):
        lines.append(f"  {idx}. {entry}")
    return state._replace(message_buffer=tuple(lines))


def reduce_flavor(state: GameState, toggle: str) -> GameState:
    """Toggles atmospheric flavor text."""
    arg = toggle.strip().lower()
    if arg in ("on", "off"):
        new_val = arg == "on"
        msg = f"Flavor text {'enabled' if new_val else 'disabled'}."
    else:
        new_val = not state.flavor_enabled
        msg = f"Flavor text toggled {'ON' if new_val else 'OFF'}."
    return state._replace(flavor_enabled=new_val, message_buffer=(msg,))


def reduce_help(state: GameState) -> GameState:
    """Displays command syntax and verb descriptions."""
    lines = [
        "COMMAND REFERENCE:",
        "  w / a / s / d           - Move on the compartment grid",
        "  I U F R T B G X         - Menu keys: inspect, use, search, read, talk, barter, go, close",
        "  /inspect <target>       - Inspect fixture, actor, item, or exit",
        "  /talk <actor>           - Speak with an actor",
        "  /barter [actor] [item]  - Accept an actor's trade",
        "  /use [item] <fixture>   - Operate a fixture, optionally with a chosen item",
        "  /search <fixture>       - Search a container, bin, or rack",
        "  /read <fixture>         - Read a terminal or notice board",
        "  /consume [item]         - Eat or drink to shed exposure",
        "  /leave <exit>           - Walk to an exit and cross it",
        "  /wait                   - Advance clock by 1 cycle",
        "  /map  /back             - Toggle sector map",
        "  /pack /character /party /log",
        "  /flavor [on|off]        - Toggle descriptive text",
        "  /quit                   - Save and exit",
    ]
    return state._replace(message_buffer=tuple(lines))
