from typing import Optional, Mapping, Any, List, Dict

from core.types import GameState, Exposure, ItemCategory
from core.rules import (
    exposure_deltas, exposure_level, exposure_thresholds, is_critical, is_safe_haven, max_exposure,
)
from core.text import danger, worst_track
from core import routine


def process_tick(
    state: GameState,
    action_summary: str,
    action_context: Optional[Mapping[str, Any]] = None,
    physical: bool = False,
) -> GameState:
    """
    Pure tick processor called after every tick-advancing action (§5.6).

    physical=True marks hands-on work (use, search, barter). At Critical exposure,
    or when tired, such work costs a second cycle.
    """
    slowed = is_critical(state) or routine.is_tired(state)
    day = state.day
    new_state = _advance(state, action_summary, action_context or {})
    if physical and slowed and new_state.day == day and new_state.current_node_id == state.current_node_id:
        why = "Your hands shake." if is_critical(state) else "You're worn out."
        delayed = new_state._replace(
            message_buffer=new_state.message_buffer + (danger(f"{why} That took twice as long."),)
        )
        new_state = _advance(delayed, "", {})
    return new_state


def _advance(state: GameState, action_summary: str, action_context: Mapping[str, Any]) -> GameState:
    new_cycle = state.cycle + 1
    current_node = state.nodes[state.current_node_id]
    caps = set(state.character.unlocked_capabilities)

    # 1-3: exposure accumulation and recovery
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

    # 4: consequences. Warnings fire when the level changes; Zone 3 shows the ongoing state.
    messages: List[str] = list(state.message_buffer)
    thresholds = exposure_thresholds(caps)
    level = max_exposure(new_exposure)
    incapacitated = level >= thresholds.incapacitated
    before = exposure_level(max_exposure(cur), thresholds)
    after = exposure_level(level, thresholds)
    track, value = worst_track(tuple(new_exposure))
    limit = f"{thresholds.incapacitated:g}"
    if incapacitated:
        messages.append(danger("You black out."))
    elif after != before and after == "CRITICAL":
        messages.append(danger(f"DANGER: {track} {value:.1f} of {limit}. Get to normal air now."))
    elif after != before and after == "STRESSED" and before == "NOMINAL":
        messages.append(danger(f"{track} {value:.1f} of {limit}. Head back soon."))
    elif after == "NOMINAL" and before != "NOMINAL":
        messages.append("You're breathing easier.")

    # 5: sustenance decay and action log
    decay_interval = 20 if "wayfarer" in caps else 10
    new_inventory = []
    for item in state.character.inventory:
        if new_cycle % decay_interval == 0 and item.category == ItemCategory.SUSTENANCE.value:
            if item.integrity - 1 > 0:
                new_inventory.append(item._replace(integrity=item.integrity - 1))
            else:
                messages.append(f"Your {item.name} has gone off.")
        else:
            new_inventory.append(item)

    new_log = list(state.action_log)
    if action_summary:
        new_log = (new_log + [action_summary])[-20:]

    next_state = state._replace(
        character=state.character._replace(exposure=new_exposure, inventory=tuple(new_inventory)),
        visited_nodes=state.visited_nodes | {state.current_node_id},
        cycle=new_cycle,
        message_buffer=tuple(messages),
        action_log=tuple(new_log),
    )

    # 6: experience (action work plus Survival for hostile turns) and jobs
    gains: Dict[str, int] = dict(action_context.get("xp", {}))
    if any(d > 0 for d in deltas) and not incapacitated:
        gains["survival"] = gains.get("survival", 0) + (
            routine.XP_HOSTILE_STRAINED if after != "NOMINAL" else routine.XP_HOSTILE_TURN)
    next_state, xp_messages = routine.award_xp(next_state, gains)
    next_state, job_messages = routine.advance_jobs(next_state, action_context.get("used_fixture_id"))
    next_state = next_state._replace(message_buffer=next_state.message_buffer + tuple(xp_messages + job_messages))

    # 7: fatigue and the end of the day
    if incapacitated:
        return _revive(next_state, "You wake in the Bunkroom. The medics carried you back.")
    awake_before, awake_after = routine.awake_turns(state), routine.awake_turns(next_state)
    if awake_after >= routine.COLLAPSE_AFTER:
        if is_safe_haven(current_node):
            return routine.start_day(next_state, current_node.id,
                                     next_state.message_buffer + ("You fall asleep where you stand.",))
        return _revive(next_state._replace(message_buffer=next_state.message_buffer + (
            danger("You fall asleep on your feet."),)), "You wake in the Bunkroom. The medics found you.")
    tired = routine.fatigue_messages(awake_before, awake_after)
    if tired:
        next_state = next_state._replace(message_buffer=next_state.message_buffer + tuple(tired))
    return next_state


def _revive(state: GameState, wake_line: str) -> GameState:
    """Medics carry the player to the Bunkroom; the night passes and one ration is used."""
    state, lost = routine.lose_one_ration(state)
    revived = routine.start_day(state, routine.BUNKROOM_ID, state.message_buffer + tuple(lost) + (wake_line,))
    return revived._replace(action_log=(state.action_log + ("Carried back to the Bunkroom.",))[-20:])
