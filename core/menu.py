"""Proximity menu (§5.2): what the player can do with the entity under the cursor."""
from typing import NamedTuple, Optional, Tuple

from core.types import GameState, Node, Fixture, Actor, FixtureState
from core import rules
from core.text import needs, hazard_words

DONE_STATES = (FixtureState.OPEN.value, FixtureState.SPENT.value)
CLOSED_STATES = (FixtureState.SEALED.value, FixtureState.LOCKED.value)
EFFECT_VERBS = {"unlock": "open", "repair": "repair", "harvest": "harvest", "override": "bypass"}


class MenuOption(NamedTuple):
    key: str
    label: str


class Menu(NamedTuple):
    title: str
    options: Tuple[MenuOption, ...]
    hint: str            # Why an expected action is missing, or ""


def get_entity_at(node: Node, row: int, col: int) -> Tuple[Optional[Fixture], Optional[Actor]]:
    """Returns any fixture or actor placed at (row, col) on the node grid."""
    for placement in node.placements:
        if placement.row == row and placement.col == col:
            return node.fixtures.get(placement.entity_id), node.actors.get(placement.entity_id)
    return None, None


def entity_under_cursor(state: GameState) -> Tuple[Optional[Fixture], Optional[Actor]]:
    return get_entity_at(state.nodes[state.current_node_id], state.player_row, state.player_col)


def _source_suffix(source: rules.Source) -> str:
    return f" ({source.label})"


def _use_option(state: GameState, fixture: Fixture) -> Tuple[Optional[MenuOption], str]:
    """[U] option for a fixture and, when it is unavailable, the reason."""
    effect = fixture.on_use_effect
    if effect in (None, "log", "scavenge") or fixture.state in DONE_STATES:
        return None, ""
    if effect == "repair" and fixture.state == FixtureState.ACTIVE.value:
        return None, ""
    inventory = state.character.inventory
    if effect == "refill":
        idx = rules.first_item_with_tags(state, ("refillable",))
        return (MenuOption("U", f"refill {inventory[idx].name}"), "") if idx is not None else (None, "")
    if effect == "smelt":
        idx = rules.first_item_with_tags(state, ("mineral", "salvage"))
        if idx is None:
            return None, "Bring ore or scrap metal to smelt."
        return MenuOption("U", f"smelt {inventory[idx].name}"), ""
    if not fixture.required_tags:
        return None, ""
    source = rules.resolve_requirement(state, fixture.required_tags)
    if not source:
        return None, f"Needs {needs(fixture.required_tags)}."
    return MenuOption("U", EFFECT_VERBS.get(effect, "use") + _source_suffix(source)), ""


def menu_for(state: GameState) -> Optional[Menu]:
    """The proximity menu for the tile under the cursor, or None when it is empty floor."""
    fixture, actor = entity_under_cursor(state)
    if not (fixture or actor):
        return None
    options = []
    hint = ""
    if fixture:
        if fixture.on_use_effect == "scavenge" and fixture.state != FixtureState.SPENT.value:
            if fixture.state in CLOSED_STATES and fixture.required_tags:
                source = rules.resolve_requirement(state, fixture.required_tags)
                if source:
                    options.append(MenuOption("F", "pry open" + _source_suffix(source)))
                else:
                    hint = f"Sealed. Needs {needs(fixture.required_tags)}."
            else:
                options.append(MenuOption("F", "search"))
        if fixture.on_use_effect == "scavenge" and fixture.state == FixtureState.SPENT.value:
            hint = "Already searched."
        if fixture.on_use_effect == "log":
            options.append(MenuOption("R", "read"))
        use, why = _use_option(state, fixture)
        if use:
            options.append(use)
        hint = hint or why
        if fixture.grants_edge and fixture.state == FixtureState.OPEN.value:
            edge = state.nodes[state.current_node_id].edges.get(fixture.grants_edge)
            dest = state.nodes.get(edge.target_node_id) if edge else None
            if edge:
                danger = hazard_words(dest.base_vitals) if dest else ""
                options.append(MenuOption("G", f"go to {edge.label}" + (f" ({danger})" if danger else "")))
    if actor:
        options.append(MenuOption("T", "talk"))
        if rules.trade_item_idx(state, actor) is not None:
            options.append(MenuOption("B", "trade"))
    title = fixture.name if fixture else actor.name
    return Menu(title, tuple(options), hint)


def menu_text(menu: Menu) -> str:
    """Plain one-line rendering, used by tests and non-styled output."""
    opts = " · ".join(f"{o.key} {o.label}" for o in menu.options)
    return f"{menu.title}: {opts}" if opts else menu.title
