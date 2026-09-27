"""Work skills, daily jobs, fatigue and the day cycle. All pure functions over GameState."""
from typing import Dict, List, Mapping, Optional, Tuple

from core.types import GameState, Job, Skill, Exposure, FixtureState, ItemCategory
from core.text import gain, danger

# A day: about 90 turns awake, then sleep. Night passes in one jump.
SHIFT_TURNS = 30
SHIFTS = ("Morning", "Evening", "Night")
TIRED_AFTER = 60          # hands-on work takes twice as long
COLLAPSE_AFTER = 90       # you fall asleep where you stand
MIN_AWAKE_TO_SLEEP = 20
NIGHT_TURNS = 30
JOBS_PER_DAY = 3
BUNKROOM_ID = "stn_a_bunkroom"

# Experience per action. Survival is earned per turn spent where exposure builds up.
XP_UNLOCK = 15
XP_REPAIR = 20
XP_OVERRIDE = 15
XP_SMELT = 10
XP_PRY = 10
XP_SEARCH = 8
XP_TRADE = 20
XP_HARVEST = 5
XP_HOSTILE_TURN = 2
XP_HOSTILE_STRAINED = 3


# --- Skills ---------------------------------------------------------------

def skill_level(skill: Skill, xp: int) -> int:
    return 1 + sum(1 for p in skill.perks if xp >= p.xp)


def next_perk(skill: Skill, xp: int):
    return next((p for p in skill.perks if xp < p.xp), None)


def award_xp(state: GameState, gains: Mapping[str, int]) -> Tuple[GameState, List[str]]:
    """Adds experience; each level reached grants its perk's capability and a message."""
    if not gains:
        return state, []
    skills = dict(state.skills)
    caps = set(state.character.unlocked_capabilities)
    messages: List[str] = []
    for skill in state.skill_catalog:
        amount = gains.get(skill.id, 0)
        if amount <= 0:
            continue
        before = skills.get(skill.id, 0)
        after = before + amount
        skills[skill.id] = after
        for perk in skill.perks:
            if before < perk.xp <= after:
                caps.add(perk.grants)
                messages.append(gain(f"{skill.name} {perk.level}! {perk.text}"))
    return state._replace(
        skills=skills,
        character=state.character._replace(unlocked_capabilities=frozenset(caps)),
    ), messages


def skill_name(state: GameState, skill_id: str) -> str:
    return next((s.name for s in state.skill_catalog if s.id == skill_id), skill_id.title())


# --- Fatigue --------------------------------------------------------------

def awake_turns(state: GameState) -> int:
    return max(0, state.cycle - state.woke_at)


def is_tired(state: GameState) -> bool:
    return awake_turns(state) >= TIRED_AFTER


def shift_name(state: GameState) -> str:
    return SHIFTS[min(len(SHIFTS) - 1, awake_turns(state) // SHIFT_TURNS)]


def fatigue_messages(before: int, after: int) -> List[str]:
    if before < TIRED_AFTER <= after:
        return [danger("You're tired. Work takes twice as long. Find a bunk.")]
    if before < COLLAPSE_AFTER - 6 <= after:
        return [danger("You can barely keep your eyes open. Sleep soon.")]
    return []


# --- Jobs -----------------------------------------------------------------

def jobs_for_day(catalog: Tuple[Job, ...], day: int) -> Tuple[Job, ...]:
    """Deterministic daily rotation through the job templates."""
    if not catalog:
        return ()
    count = min(JOBS_PER_DAY, len(catalog))
    start = ((day - 1) * count) % len(catalog)
    return tuple(catalog[(start + i) % len(catalog)] for i in range(count))


def advance_jobs(state: GameState, used_fixture_id: Optional[str]) -> Tuple[GameState, List[str]]:
    """Moves today's jobs forward after a tick and pays for the ones completed."""
    jobs: List[Job] = []
    finished: List[Job] = []
    inventory = list(state.character.inventory)
    for job in state.jobs:
        if job.done:
            jobs.append(job)
            continue
        if job.kind == "use" and used_fixture_id == job.target:
            job = job._replace(done=True)
        elif job.kind == "stay" and state.current_node_id == job.target:
            job = job._replace(progress=job.progress + 1)
            job = job._replace(done=job.progress >= job.count)
        elif job.kind == "deliver" and state.current_node_id == job.target:
            held = [i for i, it in enumerate(inventory) if it.id == job.item]
            if len(held) >= job.count:
                for idx in reversed(held[:job.count]):
                    inventory.pop(idx)
                job = job._replace(done=True)
        if job.done:
            finished.append(job)
        jobs.append(job)
    if not finished:
        return state._replace(jobs=tuple(jobs)), []

    messages: List[str] = []
    gains: Dict[str, int] = {}
    for job in finished:
        rewards = [state.item_catalog[i] for i in job.reward_items if i in state.item_catalog]
        inventory += rewards
        gains[job.skill] = gains.get(job.skill, 0) + job.xp
        paid = ", ".join(it.name for it in rewards)
        messages.append(gain(f"Job done: {job.title}. +{job.xp} {skill_name(state, job.skill)}"
                             + (f", got {paid}." if paid else ".")))
    state = state._replace(jobs=tuple(jobs), character=state.character._replace(inventory=tuple(inventory)))
    state, level_messages = award_xp(state, gains)
    return state, messages + level_messages


# --- The day cycle --------------------------------------------------------

def start_day(state: GameState, node_id: str, messages: Tuple[str, ...] = ()) -> GameState:
    """Night passes: exposure clears, containers restock, harvests regrow, new jobs are posted."""
    nodes = {}
    for nid, node in state.nodes.items():
        fixtures = dict(node.fixtures)
        for fid, f in node.fixtures.items():
            if f.restock and f.state == FixtureState.SPENT.value:
                fixtures[fid] = f._replace(state=FixtureState.ACTIVE.value)
        nodes[nid] = node._replace(fixtures=fixtures)

    day = state.day + 1
    cycle = state.cycle + NIGHT_TURNS
    room = nodes[node_id]
    return state._replace(
        nodes=nodes,
        current_node_id=node_id,
        player_row=room.size // 2,
        player_col=room.size // 2,
        cycle=cycle,
        woke_at=cycle,
        day=day,
        jobs=jobs_for_day(state.job_catalog, day),
        character=state.character._replace(exposure=Exposure(0.0, 0.0, 0.0)),
        active_view="compartment",
        proximity_menu_active=False,
        visited_nodes=state.visited_nodes | {node_id},
        message_buffer=tuple(messages) + (f"Day {day} begins.", gain("New jobs posted. Press J to see them.")),
    )


def lose_one_ration(state: GameState) -> Tuple[GameState, List[str]]:
    inventory = list(state.character.inventory)
    for idx, item in enumerate(inventory):
        if item.category == ItemCategory.SUSTENANCE.value:
            inventory.pop(idx)
            return (state._replace(character=state.character._replace(inventory=tuple(inventory))),
                    [f"The medics used your {item.name}."])
    return state, []
