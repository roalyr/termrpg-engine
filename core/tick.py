from typing import Optional, Mapping, Any, List, Dict

from core.types import GameState, Exposure, ItemCategory, TreeNode
from core.rules import (
    exposure_deltas, exposure_thresholds, is_critical, is_safe_haven, max_exposure,
    parse_survive_parameter, REVIVE_NODE_ID, REVIVE_CYCLES,
)


def process_tick(
    state: GameState,
    action_summary: str,
    action_context: Optional[Mapping[str, Any]] = None,
    physical: bool = False,
) -> GameState:
    """
    Pure tick processor called after every tick-advancing action.
    Executes the 6-step pipeline from §5.6 of the GDD.

    physical=True marks hands-on work (use, search, barter). At Critical exposure
    such work costs a second cycle (forced physiological delay, §4.3).
    """
    was_critical = is_critical(state)
    new_state = _advance(state, action_summary, action_context or {})
    if physical and was_critical and new_state.current_node_id == state.current_node_id:
        delayed = new_state._replace(
            message_buffer=new_state.message_buffer + ("[!] Your hands shake. The work takes twice as long.",)
        )
        new_state = _advance(delayed, "", {})
    return new_state


def _advance(state: GameState, action_summary: str, action_context: Mapping[str, Any]) -> GameState:
    new_cycle = state.cycle + 1
    current_node = state.nodes[state.current_node_id]
    caps = set(state.character.unlocked_capabilities)

    # Steps 2-3: exposure accumulation and recovery
    deltas = exposure_deltas(state, current_node)
    cur = state.character.exposure
    p_acc = cur.pressure_debt + deltas.pressure_debt
    r_acc = cur.radiation_dose + deltas.radiation_dose
    t_acc = cur.thermal_stress + deltas.thermal_stress
    if is_safe_haven(current_node):
        p_acc = max(0.0, p_acc - 2.0)
        r_acc = max(0.0, r_acc - 2.0)
        t_acc = max(0.0, t_acc - 2.0)
    new_exposure = Exposure(round(p_acc, 2), round(r_acc, 2), round(t_acc, 2))

    # Step 4: consequences
    messages: List[str] = list(state.message_buffer)
    thresholds = exposure_thresholds(caps)
    level = max_exposure(new_exposure)
    incapacitated = level >= thresholds.incapacitated
    if incapacitated:
        messages.append("[CRITICAL FAILURE] Environmental exposure exceeded survivable limits. Incapacitated.")
    elif level >= thresholds.critical:
        messages.append("[!] CRITICAL EXPOSURE: Physical collapse imminent. Retreat to pressurized quarters immediately.")
    elif level >= thresholds.stressed:
        messages.append("[!] CAUTION: Environmental stress accumulating.")

    # Step 5: depth survival tracking and progression tree
    new_depth_ticks: Dict[int, int] = dict(state.depth_ticks)
    hostile = any(d > 0 for d in deltas)
    if current_node.depth > 0 and hostile and level < thresholds.critical:
        new_depth_ticks[current_node.depth] = new_depth_ticks.get(current_node.depth, 0) + 1

    tree_by_id = {node.id: node for node in state.tree}
    new_tree: List[TreeNode] = []
    for node in state.tree:
        if node.attuned:
            new_tree.append(node)
            continue
        prereq = tree_by_id.get(node.prerequisite) if node.prerequisite else None
        prereq_met = node.prerequisite is None or (prereq is not None and prereq.attuned)
        if prereq_met and _condition_met(state, node, new_depth_ticks, action_context):
            new_tree.append(node._replace(attuned=True))
            caps.add(node.id)
            messages.append(f"[ATTUNEMENT] Capability unlocked: {node.name}.")
        else:
            new_tree.append(node)

    # Step 6: sustenance decay and action log
    decay_interval = 20 if "wayfarer" in caps else 10
    new_inventory = []
    for item in state.character.inventory:
        if new_cycle % decay_interval == 0 and item.category == ItemCategory.SUSTENANCE.value:
            if item.integrity - 1 > 0:
                new_inventory.append(item._replace(integrity=item.integrity - 1))
            else:
                messages.append(f"{item.name} is used up.")
        else:
            new_inventory.append(item)

    new_log = list(state.action_log)
    if action_summary:
        new_log = (new_log + [action_summary])[-20:]

    next_state = state._replace(
        character=state.character._replace(
            exposure=new_exposure,
            unlocked_capabilities=frozenset(caps),
            inventory=tuple(new_inventory),
        ),
        tree=tuple(new_tree),
        visited_nodes=state.visited_nodes | {state.current_node_id},
        depth_ticks=new_depth_ticks,
        cycle=new_cycle,
        message_buffer=tuple(messages),
        action_log=tuple(new_log),
    )
    return _revive(next_state) if incapacitated else next_state


def _condition_met(
    state: GameState,
    node: TreeNode,
    depth_ticks: Mapping[int, int],
    action_context: Mapping[str, Any],
) -> bool:
    condition, param = node.unlock_condition, node.unlock_parameter
    if condition == "visit_node":
        return state.current_node_id == param or param in state.visited_nodes
    if condition == "survive_depth":
        depth, ticks = parse_survive_parameter(param)
        return depth_ticks.get(depth, 0) >= ticks
    if condition == "complete_trade":
        if action_context.get("traded_actor_id") == param:
            return True
        return any(param in n.actors and n.actors[param].trade_completed for n in state.nodes.values())
    if condition == "use_fixture":
        return action_context.get("used_fixture_id") == param
    return False


def _revive(state: GameState) -> GameState:
    """Emergency medical recovery: back to the bunkroom, clean exposure, lost time and one ration."""
    messages = list(state.message_buffer)
    inventory = list(state.character.inventory)
    for idx, item in enumerate(inventory):
        if item.category == ItemCategory.SUSTENANCE.value:
            inventory.pop(idx)
            messages.append(f"The medics used your {item.name} during recovery.")
            break
    messages.append(f"You wake in the bunkroom. Medical crew carried you back. {REVIVE_CYCLES} cycles lost.")

    node = state.nodes[REVIVE_NODE_ID]
    return state._replace(
        character=state.character._replace(exposure=Exposure(0.0, 0.0, 0.0), inventory=tuple(inventory)),
        current_node_id=REVIVE_NODE_ID,
        player_row=node.size // 2,
        player_col=node.size // 2,
        cycle=state.cycle + REVIVE_CYCLES,
        active_view="compartment",
        proximity_menu_active=False,
        message_buffer=tuple(messages),
        action_log=(state.action_log + ("Collapsed. Revived in bunkroom.",))[-20:],
        visited_nodes=state.visited_nodes | {REVIVE_NODE_ID},
    )
