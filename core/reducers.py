from typing import Optional, Mapping, Tuple, Dict, Any, List

from core.types import (
    GameState, Node, Fixture, Actor, Edge, Item, Companion,
    FixtureState, ItemCategory, TreeNode
)
from core.tick import process_tick
from core.presets import DEFAULT_ITEMS, DEFAULT_COMPANIONS

# Index default items and companions for lookups
ALL_ITEMS_BY_ID: Dict[str, Item] = {
    raw["id"]: Item(
        id=raw["id"],
        name=raw["name"],
        category=raw["category"],
        tags=tuple(raw["tags"]),
        integrity=raw["integrity"],
        max_integrity=raw["max_integrity"],
        description=raw["description"]
    )
    for raw in DEFAULT_ITEMS
}

ALL_COMPANIONS_BY_ID: Dict[str, Companion] = {
    raw["id"]: Companion(
        id=raw["id"],
        name=raw["name"],
        title=raw["title"],
        status=raw["status"],
        capability_tag=raw.get("capability_tag")
    )
    for raw in DEFAULT_COMPANIONS
}


def _is_stressed_or_critical(state: GameState) -> bool:
    """Returns True if any exposure track is in Stressed or Critical range."""
    caps = state.character.unlocked_capabilities
    thresh = 10.0 if "trench_hardened" in caps else 5.0
    exp = state.character.exposure
    return max(exp.pressure_debt, exp.radiation_dose, exp.thermal_stress) >= thresh


def _is_critical(state: GameState) -> bool:
    """Returns True if any exposure track is at or above Critical threshold."""
    caps = state.character.unlocked_capabilities
    thresh = 15.0 if "trench_hardened" in caps else 10.0
    exp = state.character.exposure
    return max(exp.pressure_debt, exp.radiation_dose, exp.thermal_stress) >= thresh


def reduce_inspect(state: GameState, target_id: str) -> GameState:
    """
    Inspects a fixture, actor, inventory item, or edge in the current compartment.
    Does not advance the tick.
    """
    target_id = target_id.strip()
    if not target_id:
        return state._replace(message_buffer=("Inspect what? Specify target ID or item name.",))

    current_node = state.nodes[state.current_node_id]
    stressed = _is_stressed_or_critical(state)
    suffix = " [readings unclear due to environmental stress]" if stressed else ""

    # 1. Check fixtures
    fixture: Optional[Fixture] = current_node.fixtures.get(target_id)
    if not fixture:
        # Check by glyph
        for f in current_node.fixtures.values():
            if f.glyph == target_id:
                fixture = f
                break

    if fixture:
        lines = [f"{fixture.name} [{fixture.id}]: {fixture.description}{suffix} State: {fixture.state.upper()}."]
        if "seam_discipline" in state.character.unlocked_capabilities and fixture.state == FixtureState.SEALED.value:
            lines.append(f"  [Seam Discipline] Seal integrity nominal. Required key tag: '{fixture.required_tag}'.")
        elif fixture.required_tag and fixture.state != FixtureState.OPEN.value:
            lines.append(f"  Requires tag: '{fixture.required_tag}'.")
        return state._replace(message_buffer=tuple(lines))

    # 2. Check actors
    actor: Optional[Actor] = current_node.actors.get(target_id)
    if not actor:
        for a in current_node.actors.values():
            if a.glyph == target_id:
                actor = a
                break

    if actor:
        dialogue = actor.dialogue_post_trade if actor.trade_completed and actor.dialogue_post_trade else actor.dialogue_idle
        msg = f"{actor.name} ({actor.title}): {actor.status}.{suffix} \"{dialogue}\""
        return state._replace(message_buffer=(msg,))

    # 3. Check inventory items
    for item in state.character.inventory:
        if item.id == target_id or item.name.lower() == target_id.lower():
            cond = f"{item.integrity}/{item.max_integrity}" if item.max_integrity > 0 else "PERMANENT"
            msg = (
                f"{item.name} [{item.id}] ({item.category}): {item.description}{suffix} "
                f"Integrity: {cond}. Tags: [{', '.join(item.tags)}]."
            )
            return state._replace(message_buffer=(msg,))

    # 4. Check edges
    edge: Optional[Edge] = current_node.edges.get(target_id)
    if edge:
        lines = [f"Exit to {edge.label} [{edge.id}].{suffix}"]
        if "bulkhead_ear" in state.character.unlocked_capabilities:
            target_node = state.nodes.get(edge.target_node_id)
            if target_node:
                lines.append(
                    f"  [Bulkhead Ear] Sensor feed: {target_node.base_vitals.pressure_kpa} kPa, "
                    f"{target_node.base_vitals.temperature_c}°C ({target_node.environment})."
                )
        if edge.gated_by_fixture:
            gf = current_node.fixtures.get(edge.gated_by_fixture)
            if gf and gf.state != FixtureState.OPEN.value:
                lines.append(f"  Gated by {gf.name} (currently {gf.state}).")
        if edge.requires_capability:
            lines.append(f"  Requires clearance/capability: '{edge.requires_capability}'.")
        return state._replace(message_buffer=tuple(lines))

    return state._replace(message_buffer=(f"Nothing found matching '{target_id}' to inspect.",))


def reduce_talk(state: GameState, actor_id: str) -> GameState:
    """
    Talks to an actor in the current compartment.
    Executes trade protocol if requirements are met.
    Advances simulation tick.
    """
    actor_id = actor_id.strip()
    current_node = state.nodes[state.current_node_id]

    actor: Optional[Actor] = current_node.actors.get(actor_id)
    if not actor:
        for a in current_node.actors.values():
            if a.glyph == actor_id or a.name.lower() == actor_id.lower():
                actor = a
                break

    if not actor:
        return state._replace(message_buffer=(f"No one named '{actor_id}' here.",))

    # Check trade eligibility
    can_trade = (
        not actor.trade_completed
        and actor.trade_required_tag is not None
        and actor.trade_offered_id is not None
    )

    matching_item_idx: Optional[int] = None
    if can_trade:
        for idx, item in enumerate(state.character.inventory):
            if actor.trade_required_tag in item.tags:
                matching_item_idx = idx
                break

    if can_trade and matching_item_idx is not None:
        # Execute Trade Protocol (§5.4)
        item_to_trade = state.character.inventory[matching_item_idx]
        new_inv: List[Item] = list(state.character.inventory)

        # 2a. Consume 1 integrity of player's item
        if item_to_trade.max_integrity > 0:
            new_integrity = item_to_trade.integrity - 1
            if new_integrity <= 0:
                new_inv.pop(matching_item_idx)
            else:
                new_inv[matching_item_idx] = item_to_trade._replace(integrity=new_integrity)
        # (Permanent items with max_integrity=0 are not consumed or can be consumed if integrity=0)

        # 2b. Add offered item
        offered_item = ALL_ITEMS_BY_ID.get(actor.trade_offered_id)
        if offered_item:
            new_inv.append(offered_item)

        # 2c. Update actor state
        updated_actor = actor._replace(trade_completed=True)
        updated_actors = dict(current_node.actors)
        updated_actors[actor.id] = updated_actor
        updated_node = current_node._replace(actors=updated_actors)
        updated_nodes = dict(state.nodes)
        updated_nodes[current_node.id] = updated_node

        # 2d. Unlock companion if applicable
        new_companions = list(state.companions)
        if actor.companion_unlock and actor.companion_unlock in ALL_COMPANIONS_BY_ID:
            comp = ALL_COMPANIONS_BY_ID[actor.companion_unlock]
            if not any(c.id == comp.id for c in new_companions):
                new_companions.append(comp)

        trade_dialogue = actor.dialogue_post_trade or "Transaction confirmed."
        messages = [
            f"Exchanged {item_to_trade.name} for {offered_item.name if offered_item else actor.trade_offered_id}.",
            f"{actor.name}: \"{trade_dialogue}\""
        ]
        if actor.companion_unlock:
            messages.append(f"[PARTY] Companion joined: {actor.companion_unlock}!")

        temp_char = state.character._replace(inventory=tuple(new_inv))
        state_after_trade = state._replace(
            character=temp_char,
            nodes=updated_nodes,
            companions=tuple(new_companions),
            message_buffer=tuple(messages)
        )
        return process_tick(
            state_after_trade,
            f"Traded with {actor.name}.",
            action_context={"traded_actor_id": actor.id}
        )

    # Standard conversation without trade
    dialogue = actor.dialogue_post_trade if actor.trade_completed and actor.dialogue_post_trade else actor.dialogue_idle
    msg = f"{actor.name}: \"{dialogue}\""
    state_with_msg = state._replace(message_buffer=(msg,))
    return process_tick(state_with_msg, f"Spoke with {actor.name}.")


def reduce_use(state: GameState, item_id: str, fixture_id: str) -> GameState:
    """
    Uses an item from inventory on a fixture in the compartment.
    Advances simulation tick on success.
    """
    item_id = item_id.strip()
    fixture_id = fixture_id.strip()

    # 1. Validate item in inventory
    item: Optional[Item] = None
    item_idx: Optional[int] = None
    for idx, it in enumerate(state.character.inventory):
        if it.id == item_id or it.name.lower() == item_id.lower():
            item = it
            item_idx = idx
            break

    if item is None or item_idx is None:
        return state._replace(message_buffer=(f"You don't carry '{item_id}'.",))

    # 2. Validate fixture in current compartment
    current_node = state.nodes[state.current_node_id]
    fixture: Optional[Fixture] = current_node.fixtures.get(fixture_id)
    if not fixture:
        for f in current_node.fixtures.values():
            if f.glyph == fixture_id or f.name.lower() == fixture_id.lower():
                fixture = f
                break

    if not fixture:
        return state._replace(message_buffer=(f"No fixture '{fixture_id}' here.",))

    # 3. Check fixture already open or spent
    if fixture.state in (FixtureState.OPEN.value, FixtureState.SPENT.value):
        return state._replace(message_buffer=("Already done.",))

    # 4. Check tag match (item tags + companion tags)
    all_available_tags = set(item.tags)
    for companion in state.companions:
        if companion.capability_tag:
            all_available_tags.add(companion.capability_tag)

    if not fixture.required_tag or fixture.required_tag not in all_available_tags:
        return state._replace(message_buffer=("That doesn't work here.",))

    # 5. Execute On-Use Effect (§5.5)
    effect = fixture.on_use_effect
    new_inv: List[Item] = list(state.character.inventory)
    new_fixtures = dict(current_node.fixtures)
    msg = ""

    if effect == "unlock":
        new_fixture = fixture._replace(state=FixtureState.OPEN.value)
        new_fixtures[fixture.id] = new_fixture
        # Consume item integrity if destructible
        if item.max_integrity > 0:
            rem = item.integrity - 1
            if rem <= 0:
                new_inv.pop(item_idx)
                msg = f"Unlocked {fixture.name}. {item.name} broke from strain."
            else:
                new_inv[item_idx] = item._replace(integrity=rem)
                msg = f"Unlocked {fixture.name}."
        else:
            msg = f"Unlocked {fixture.name}."

    elif effect == "refill":
        new_inv[item_idx] = item._replace(integrity=item.max_integrity)
        msg = f"Refilled {item.name} at {fixture.name}."

    elif effect == "repair":
        new_fixture = fixture._replace(state=FixtureState.ACTIVE.value)
        new_fixtures[fixture.id] = new_fixture
        if item.max_integrity > 0:
            rem = item.integrity - 1
            if rem <= 0:
                new_inv.pop(item_idx)
                msg = f"Repaired {fixture.name}. {item.name} was spent."
            else:
                new_inv[item_idx] = item._replace(integrity=rem)
                msg = f"Repaired and engaged {fixture.name}."
        else:
            msg = f"Repaired and engaged {fixture.name}."

    else:
        # Generic effect: consume item integrity
        if item.max_integrity > 0:
            rem = item.integrity - 1
            if rem <= 0:
                new_inv.pop(item_idx)
                msg = f"Used {item.name} on {fixture.name}. {item.name} was consumed."
            else:
                new_inv[item_idx] = item._replace(integrity=rem)
                msg = f"Used {item.name} on {fixture.name}."
        else:
            msg = f"Used {item.name} on {fixture.name}."

    updated_node = current_node._replace(fixtures=new_fixtures)
    updated_nodes = dict(state.nodes)
    updated_nodes[current_node.id] = updated_node
    updated_char = state.character._replace(inventory=tuple(new_inv))

    state_before_tick = state._replace(
        character=updated_char,
        nodes=updated_nodes,
        message_buffer=(msg,)
    )

    return process_tick(
        state_before_tick,
        f"Used {item.name} on {fixture.name}.",
        action_context={"used_fixture_id": fixture.id}
    )


def reduce_wait(state: GameState) -> GameState:
    """Advances simulation clock by 1 cycle."""
    state_msg = state._replace(message_buffer=("Waiting. Time passes...",))
    return process_tick(state_msg, "Waited one cycle.")


def reduce_leave(state: GameState, edge_id: str) -> GameState:
    """
    Traverses an open edge from the active compartment to a destination node.
    Advances simulation tick.
    """
    edge_id = edge_id.strip()
    current_node = state.nodes[state.current_node_id]

    edge: Optional[Edge] = current_node.edges.get(edge_id)
    if not edge:
        # Check by label matching
        for e in current_node.edges.values():
            if e.label.lower() == edge_id.lower() or e.target_node_id == edge_id:
                edge = e
                break

    if not edge:
        available = ", ".join(f"'{k}' ({v.label})" for k, v in current_node.edges.items())
        return state._replace(message_buffer=(f"No exit '{edge_id}'. Available: {available}",))

    # Check fixture gate
    if edge.gated_by_fixture:
        gate = current_node.fixtures.get(edge.gated_by_fixture)
        if gate and gate.state != FixtureState.OPEN.value:
            return state._replace(message_buffer=(f"Access blocked. {gate.name} is {gate.state.upper()}.",))

    # Check required capability
    if edge.requires_capability:
        if edge.requires_capability not in state.character.unlocked_capabilities:
            return state._replace(
                message_buffer=(f"Requires capability '{edge.requires_capability}' to traverse here.",)
            )

    dest_node = state.nodes.get(edge.target_node_id)
    if not dest_node:
        return state._replace(message_buffer=(f"Route error: destination {edge.target_node_id} unreachable.",))

    # If critical exposure, player struggles
    messages = [f"Moved to {dest_node.name}."]
    if _is_critical(state):
        messages.append("[!] Moving under severe physical strain.")

    state_moved = state._replace(
        current_node_id=dest_node.id,
        active_view="compartment",
        message_buffer=tuple(messages)
    )

    return process_tick(state_moved, f"Traversed to {dest_node.name}.")


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
    else:
        for it in state.character.inventory:
            cond = f"{it.integrity}/{it.max_integrity}" if it.max_integrity > 0 else "PERM"
            lines.append(f"  - {it.name} [{it.id}]: condition {cond} | tags: {', '.join(it.tags)}")
    return state._replace(message_buffer=tuple(lines))


def reduce_character(state: GameState) -> GameState:
    """Displays qualitative progression tree and attunements."""
    lines = [
        f"CHARACTER PROFILE: {state.character.name}",
        f"Routine: {state.character.past_work} | Personal Anchor: {state.character.personal_anchor.name}",
        "PROGRESSION TREE ATTUNEMENTS:"
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
    else:
        for c in state.companions:
            cap = f" | Contributes: '{c.capability_tag}'" if c.capability_tag else ""
            lines.append(f"  - {c.name} ({c.title}): {c.status}{cap}")
    return state._replace(message_buffer=tuple(lines))


def reduce_log(state: GameState) -> GameState:
    """Displays recent action log."""
    lines = ["RECENT LOG HISTORY:"]
    recent = state.action_log[-10:] if len(state.action_log) > 10 else state.action_log
    for idx, entry in enumerate(recent, 1):
        lines.append(f"  {idx}. {entry}")
    return state._replace(message_buffer=tuple(lines))


def reduce_flavor(state: GameState, toggle: str) -> GameState:
    """Toggles atmospheric flavor text."""
    arg = toggle.strip().lower()
    if arg == "off":
        new_val = False
        msg = "Flavor text disabled."
    elif arg == "on":
        new_val = True
        msg = "Flavor text enabled."
    else:
        new_val = not state.flavor_enabled
        msg = f"Flavor text toggled {'ON' if new_val else 'OFF'}."
    return state._replace(flavor_enabled=new_val, message_buffer=(msg,))


def reduce_help(state: GameState) -> GameState:
    """Displays command syntax and verb descriptions."""
    lines = [
        "COMMAND REFERENCE:",
        "  inspect <target>        - Inspect fixture, actor, item, or exit",
        "  talk <actor_id>         - Speak or trade with an actor",
        "  use <item_id> <target>  - Use carried tool/item on fixture",
        "  wait                    - Advance clock by 1 cycle",
        "  leave <exit_id>         - Move through exit to next node",
        "  map / back              - Toggle between compartment and sector map",
        "  pack                    - View inventory and item charges",
        "  character               - View qualitative progression tree",
        "  party                   - View companions and assigned assistance",
        "  log                     - Show recent activity log",
        "  flavor [on|off]         - Toggle descriptive environment text",
        "  quit                    - Save game and exit"
    ]
    return state._replace(message_buffer=tuple(lines))
