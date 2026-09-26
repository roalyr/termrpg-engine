from typing import Optional, Mapping, Any, List, Dict
from core.types import (
    GameState, Exposure, ItemCategory, TreeNode, PlayerCharacter
)

def process_tick(
    state: GameState,
    action_summary: str,
    action_context: Optional[Mapping[str, Any]] = None
) -> GameState:
    """
    Pure tick processor called after every tick-advancing action.
    Executes the 6-step pipeline from §5.6 of the GDD:
    1. Cycle increment
    2. Exposure accumulation
    3. Exposure recovery
    4. Exposure consequences
    5. Progression tree attunement checks
    6. Sustenance decay & Action log update
    """
    action_context = action_context or {}
    new_cycle = state.cycle + 1
    current_node = state.nodes[state.current_node_id]
    vitals = current_node.base_vitals

    # Step 2: Exposure accumulation
    delta_p = max(0.0, (90.0 - vitals.pressure_kpa) / 30.0)
    delta_r = max(0.0, (vitals.radiation_msv - 5.0) / 15.0)
    delta_t = max(0.0, (-10.0 - vitals.temperature_c) / 20.0)

    # Progression tree mitigations
    caps = set(state.character.unlocked_capabilities)
    if "vacuum_walk" in caps:
        delta_p *= 0.5
    if "deep_well" in caps:
        delta_r *= 0.5
    if "cold_bypass" in caps:
        delta_t *= 0.5

    cur_exp = state.character.exposure
    p_acc = cur_exp.pressure_debt + delta_p
    r_acc = cur_exp.radiation_dose + delta_r
    t_acc = cur_exp.thermal_stress + delta_t

    # Step 3: Exposure recovery
    if current_node.depth == 0 and current_node.environment == "pressurized":
        p_acc = max(0.0, p_acc - 2.0)
        r_acc = max(0.0, r_acc - 2.0)
        t_acc = max(0.0, t_acc - 2.0)

    new_exposure = Exposure(
        pressure_debt=round(p_acc, 2),
        radiation_dose=round(r_acc, 2),
        thermal_stress=round(t_acc, 2),
    )

    # Step 4: Exposure consequences
    messages: List[str] = list(state.message_buffer)
    is_running = state.is_running

    if "trench_hardened" in caps:
        stressed_threshold = 10.0
        critical_threshold = 15.0
        incapacitated_threshold = 20.0
    else:
        stressed_threshold = 5.0
        critical_threshold = 10.0
        incapacitated_threshold = 15.0

    max_exp = max(new_exposure.pressure_debt, new_exposure.radiation_dose, new_exposure.thermal_stress)

    if max_exp >= incapacitated_threshold:
        is_running = False
        messages.append("[CRITICAL FAILURE] Environmental exposure exceeded survivable limits. Incapacitated.")
    elif max_exp >= critical_threshold:
        messages.append("[!] CRITICAL EXPOSURE: Physical collapse imminent. Retreat to pressurized quarters immediately.")
    elif max_exp >= stressed_threshold:
        messages.append("[!] CAUTION: Environmental stress accumulating.")

    # Step 5: Progression tree & depth tracking
    new_depth_ticks: Dict[int, int] = dict(state.depth_ticks)
    if current_node.depth > 0 and max_exp < critical_threshold:
        d = current_node.depth
        new_depth_ticks[d] = new_depth_ticks.get(d, 0) + 1

    new_tree: List[TreeNode] = []
    tree_by_id = {node.id: node for node in state.tree}
    attuned_this_tick = set()

    for node in state.tree:
        if node.attuned:
            new_tree.append(node)
            continue

        # Check prerequisite
        prereq_met = True
        if node.prerequisite:
            prereq_node = tree_by_id.get(node.prerequisite)
            if not prereq_node or not prereq_node.attuned:
                prereq_met = False

        condition_met = False
        if prereq_met:
            if node.unlock_condition == "visit_node":
                if state.current_node_id == node.unlock_parameter or node.unlock_parameter in state.visited_nodes:
                    condition_met = True
            elif node.unlock_condition == "survive_depth":
                req_depth = int(node.unlock_parameter)
                if new_depth_ticks.get(req_depth, 0) >= 5:
                    condition_met = True
            elif node.unlock_condition == "complete_trade":
                if action_context.get("traded_actor_id") == node.unlock_parameter:
                    condition_met = True
                else:
                    # Also check if actor in nodes is already marked traded
                    for n in state.nodes.values():
                        if node.unlock_parameter in n.actors and n.actors[node.unlock_parameter].trade_completed:
                            condition_met = True
                            break
            elif node.unlock_condition == "use_fixture":
                if action_context.get("used_fixture_id") == node.unlock_parameter:
                    condition_met = True

        if condition_met:
            updated_node = node._replace(attuned=True)
            new_tree.append(updated_node)
            caps.add(node.id)
            attuned_this_tick.add(node.id)
            messages.append(f"[ATTUNEMENT] Capability unlocked: {node.name}.")
        else:
            new_tree.append(node)

    # Step 6: Sustenance decay & Action log
    new_inventory = []
    if new_cycle % 10 == 0:
        for item in state.character.inventory:
            if item.category == ItemCategory.SUSTENANCE.value:
                new_integrity = item.integrity - 1
                if new_integrity > 0:
                    new_inventory.append(item._replace(integrity=new_integrity))
                else:
                    messages.append(f"{item.name} is used up.")
            else:
                new_inventory.append(item)
    else:
        new_inventory = list(state.character.inventory)

    new_character = state.character._replace(
        exposure=new_exposure,
        unlocked_capabilities=frozenset(caps),
        inventory=tuple(new_inventory),
    )

    new_log = list(state.action_log)
    if action_summary:
        new_log.append(action_summary)
        if len(new_log) > 20:
            new_log = new_log[-20:]

    new_visited = state.visited_nodes | {state.current_node_id}

    return state._replace(
        character=new_character,
        companions=state.companions,
        tree=tuple(new_tree),
        visited_nodes=new_visited,
        depth_ticks=new_depth_ticks,
        cycle=new_cycle,
        message_buffer=tuple(messages),
        action_log=tuple(new_log),
        is_running=is_running,
    )
