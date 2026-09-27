"""Pure rule helpers shared by reducers, the tick processor, persistence and the UI."""
from typing import Dict, FrozenSet, Iterable, NamedTuple, Optional, Tuple

from core.types import (
    GameState, Node, Item, Actor, Companion, Exposure, ItemCategory,
)

# Tags whose items count as tools for Careful Hands (conduit_mastery).
TOOL_TAGS = frozenset({"force_lever", "wrench"})
# Tags that let the player read the locked part of a log fixture.
LOG_READER_TAGS = ("signal_analysis", "signal_boost", "lore")
ROUTINE_LABELS: Dict[str, str] = {
    "seal_fitting": "Seam Scraper training",
    "bio_filter": "Algae Tender training",
    "heavy_lift": "Cargo Handler training",
}
DEFAULT_SURVIVE_TICKS = 5
REVIVE_NODE_ID = "stn_a_bunkroom"
REVIVE_CYCLES = 12


class Thresholds(NamedTuple):
    stressed: float
    critical: float
    incapacitated: float


class Source(NamedTuple):
    """What satisfied a requirement: a carried item (item_idx set) or a free party source."""
    tag: str
    label: str
    item_idx: Optional[int]


# --- Exposure --------------------------------------------------------------

def exposure_thresholds(caps: Iterable[str]) -> Thresholds:
    bonus = 5.0 if "trench_hardened" in set(caps) else 0.0
    return Thresholds(5.0 + bonus, 10.0 + bonus, 15.0 + bonus)


def max_exposure(exposure: Exposure) -> float:
    return max(exposure.pressure_debt, exposure.radiation_dose, exposure.thermal_stress)


def exposure_level(value: float, th: Thresholds) -> str:
    if value >= th.critical:
        return "CRITICAL"
    if value >= th.stressed:
        return "STRESSED"
    return "NOMINAL"


def exposure_status(state: GameState) -> str:
    th = exposure_thresholds(state.character.unlocked_capabilities)
    return exposure_level(max_exposure(state.character.exposure), th)


def is_stressed(state: GameState) -> bool:
    return exposure_status(state) != "NOMINAL"


def is_critical(state: GameState) -> bool:
    return exposure_status(state) == "CRITICAL"


def exposure_deltas(state: GameState, node: Node) -> Exposure:
    """Per-tick exposure gain in node after progression and party mitigations (GDD §4.3)."""
    vitals = node.base_vitals
    delta_p = max(0.0, (90.0 - vitals.pressure_kpa) / 30.0)
    delta_r = max(0.0, (vitals.radiation_msv - 5.0) / 15.0)
    delta_t = max(0.0, (-10.0 - vitals.temperature_c) / 20.0)

    caps = state.character.unlocked_capabilities
    if "vacuum_walk" in caps:
        delta_p *= 0.5
    if "deep_well" in caps:
        delta_r *= 0.5
    if "cold_bypass" in caps:
        delta_t *= 0.5
    if "crew_coordination" in caps and state.companions:
        delta_p = max(0.0, delta_p - 0.2)
        delta_r = max(0.0, delta_r - 0.2)
        delta_t = max(0.0, delta_t - 0.2)
    return Exposure(delta_p, delta_r, delta_t)


def is_safe_haven(node: Node) -> bool:
    """Exposure recovers only in depth-0 pressurized compartments."""
    return node.depth == 0 and node.environment == "pressurized"


# --- Requirements ----------------------------------------------------------

def free_tag_sources(state: GameState) -> Dict[str, str]:
    """Tags the party provides without spending an item, mapped to a display label."""
    tree_names = {t.id: t.name for t in state.tree}
    sources: Dict[str, str] = {}
    for cap in state.character.unlocked_capabilities:
        sources[cap] = ROUTINE_LABELS.get(cap) or tree_names.get(cap) or "clearance on file"
    if "wayfarer" in state.character.unlocked_capabilities:
        sources.setdefault("transit_clearance", tree_names.get("wayfarer", "Deep Traveler"))
    for comp in state.companions:
        if comp.capability_tag:
            sources.setdefault(comp.capability_tag, comp.name)
    return sources


def party_tags(state: GameState) -> FrozenSet[str]:
    return frozenset(free_tag_sources(state))


def find_item(state: GameState, item_ref: str) -> Optional[int]:
    """Index of the carried item matching an ID or display name."""
    ref = item_ref.strip().lower()
    if not ref:
        return None
    for idx, it in enumerate(state.character.inventory):
        if it.id == ref or it.name.lower() == ref:
            return idx
    return None


def resolve_requirement(
    state: GameState,
    tags: Tuple[str, ...],
    preferred_item_idx: Optional[int] = None,
) -> Optional[Source]:
    """
    Finds what satisfies any of tags. Free party sources (skills, clearances,
    companions) win over carried items so nothing wears when it does not have to.
    A preferred item is tried before the rest of the pack.
    """
    free = free_tag_sources(state)
    for tag in tags:
        if tag in free:
            return Source(tag, free[tag], None)

    inventory = state.character.inventory
    order = list(range(len(inventory)))
    if preferred_item_idx is not None and 0 <= preferred_item_idx < len(inventory):
        order.remove(preferred_item_idx)
        order.insert(0, preferred_item_idx)
    for idx in order:
        for tag in tags:
            if tag in inventory[idx].tags:
                return Source(tag, inventory[idx].name, idx)
    return None


def first_item_with_tags(
    state: GameState, tags: Iterable[str], preferred_item_idx: Optional[int] = None
) -> Optional[int]:
    """Index of the first carried item carrying any of tags (preferred item first)."""
    wanted = set(tags)
    inventory = state.character.inventory
    if preferred_item_idx is not None and 0 <= preferred_item_idx < len(inventory):
        if wanted & set(inventory[preferred_item_idx].tags):
            return preferred_item_idx
    for idx, it in enumerate(inventory):
        if wanted & set(it.tags):
            return idx
    return None


def wear_item(inventory: Tuple[Item, ...], idx: int) -> Tuple[Tuple[Item, ...], bool]:
    """Removes one point of integrity. Returns (new_inventory, item_was_used_up)."""
    item = inventory[idx]
    if item.max_integrity <= 0:
        return inventory, False
    remaining = item.integrity - 1
    items = list(inventory)
    if remaining <= 0:
        items.pop(idx)
        return tuple(items), True
    items[idx] = item._replace(integrity=remaining)
    return tuple(items), False


def remove_item(inventory: Tuple[Item, ...], idx: int) -> Tuple[Item, ...]:
    return inventory[:idx] + inventory[idx + 1:]


def tool_protected(state: GameState, item: Item) -> bool:
    """Careful Hands keeps tools from wearing on pipe and valve work."""
    return "conduit_mastery" in state.character.unlocked_capabilities and bool(TOOL_TAGS & set(item.tags))


def can_read_locked_logs(state: GameState) -> bool:
    available = set(party_tags(state))
    for it in state.character.inventory:
        available |= set(it.tags)
    return any(tag in available for tag in LOG_READER_TAGS)


# --- Catalogues, trade and dialogue ----------------------------------------

def catalog_item(state: GameState, item_id: Optional[str]) -> Optional[Item]:
    return state.item_catalog.get(item_id) if item_id else None


def catalog_companion(state: GameState, companion_id: Optional[str]) -> Optional[Companion]:
    return state.companion_catalog.get(companion_id) if companion_id else None


def is_handed_over(item: Item) -> bool:
    """Credentials are shown in trade and kept; everything else changes hands."""
    return item.category != ItemCategory.CREDENTIAL.value


def trade_item_idx(state: GameState, actor: Actor, preferred_item_idx: Optional[int] = None) -> Optional[int]:
    """Carried item the actor would accept, or None when no trade is possible."""
    if actor.trade_completed or not actor.trade_offered_id or not actor.trade_required_tags:
        return None
    return first_item_with_tags(state, actor.trade_required_tags, preferred_item_idx)


def condition_met(state: GameState, condition: str) -> bool:
    """Evaluates 'past_work:x', 'visited:node', 'party:companion' or 'has_cap:cap'."""
    kind, _, value = condition.partition(":")
    if kind == "past_work":
        return state.character.past_work == value
    if kind == "visited":
        return value in state.visited_nodes
    if kind == "party":
        return any(c.id == value for c in state.companions)
    if kind == "has_cap":
        return value in state.character.unlocked_capabilities
    return False


def dialogue_for(state: GameState, actor: Actor) -> str:
    if actor.trade_completed and actor.dialogue_post_trade:
        return actor.dialogue_post_trade
    for condition, text in actor.dialogue_variants:
        if condition_met(state, condition):
            return text
    return actor.dialogue_idle


def parse_survive_parameter(parameter: str) -> Tuple[int, int]:
    """'depth:ticks' -> (depth, ticks); a bare depth means the default tick count."""
    depth, _, ticks = parameter.partition(":")
    return int(depth), int(ticks) if ticks else DEFAULT_SURVIVE_TICKS


def stack_items(inventory: Tuple[Item, ...]) -> Tuple[Tuple[Item, int], ...]:
    """Groups identical items (same ID and condition) for display, keeping first-seen order."""
    counts: Dict[Tuple[str, int], int] = {}
    firsts: Dict[Tuple[str, int], Item] = {}
    for it in inventory:
        key = (it.id, it.integrity)
        counts[key] = counts.get(key, 0) + 1
        firsts.setdefault(key, it)
    return tuple((firsts[k], counts[k]) for k in firsts)
