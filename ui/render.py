import re
from typing import Callable, Dict, List, Optional, Tuple

from core.types import GameState, Node, Fixture, FixtureState
from core import rules
from core.menu import menu_for, entity_under_cursor
from core.text import STATUS_NAMES, STATE_WORDS, TRACK_NAMES, message_kind, strip_kind, hazard_words
from ui.text_tools import wrap_text, pad_visible
from ui.topology_view import render_topology
from ui import style

CLUSTER_NAMES = {
    "station_alpha": "Station A",
    "station_beta": "Station B",
    "transit": "In transit",
    "lunar_base": "Moon",
}
_KEY_RE = re.compile(r"(^ |[:·] )([A-Z])(?= )")
_KIND_ORDER = {"danger": 0, "gain": 1, "plain": 2, "quiet": 3}
_NOTABLE_STATES = (FixtureState.SEALED.value, FixtureState.LOCKED.value,
                   FixtureState.DISABLED.value, FixtureState.SPENT.value)


def build_grid(node: Node, player_row: int = -1, player_col: int = -1) -> Tuple[str, ...]:
    """
    Constructs N×N grid rows from node walls, floor, placements, and player cursor
    strictly according to §10 of the GDD. Inverts entity tile color on player overlap.
    """
    n = node.size
    grid = [[node.grid_floor] * n for _ in range(n)]

    for r in range(n):
        for c in range(n):
            if r == 0 or r == n - 1 or c == 0 or c == n - 1:
                grid[r][c] = node.grid_wall

    for placement in node.placements:
        entity = node.fixtures.get(placement.entity_id) or node.actors.get(placement.entity_id)
        if entity:
            grid[placement.row][placement.col] = entity.glyph

    if 0 <= player_row < n and 0 <= player_col < n:
        cell = grid[player_row][player_col]
        if cell == node.grid_floor:
            grid[player_row][player_col] = '@'
        else:
            # Overlap with item/entity tile: invert the item tile color
            grid[player_row][player_col] = f"\033[7m{cell}\033[0m"

    return tuple(' '.join(row) for row in grid)


def _boxed(text: str, width: int, paint: Callable[[str], str] = lambda t: t) -> str:
    """One bordered line: pads plain text to width, then applies styling."""
    return f"│{paint(pad_visible(text[:width], width, align='<'))}│"


def _status_rows(state: GameState, node: Node, z3_w: int, on: bool) -> List[str]:
    """Zone 3: turn, status, the three exposure tracks with per-turn trend, and the team."""
    exp = tuple(state.character.exposure)
    th = rules.exposure_thresholds(state.character.unlocked_capabilities)
    status = rules.exposure_status(state)
    label = STATUS_NAMES[status]

    def fit(text: str) -> str:
        return pad_visible(text[:z3_w], z3_w, align='<')

    def shortest(*options: str) -> str:
        """First option that fits the panel, else the last one."""
        return next((o for o in options if len(o) <= z3_w), options[-1])

    limit = f"{th.incapacitated:g}"
    if status == "NOMINAL":
        status_line = fit(f" {label}")
    else:
        text = fit(shortest(f" {label} · max {limit}", f" {label} /{limit}"))
        status_line = style.alarm(text, on) if status == "CRITICAL" else style.accent(text, on)
    rows = [fit(f" Turn {state.cycle}"), status_line]

    safe = rules.is_safe_haven(node)
    deltas = tuple(rules.exposure_deltas(state, node))
    for name, value, delta in zip(TRACK_NAMES, exp, deltas):
        if safe and value > 0:
            trend = " -2"
        elif delta > 0:
            trend = f" +{delta:.1f}"
        else:
            trend = ""
        text = fit(shortest(f" {name:<4} {value:4.1f}{trend}", f" {name} {value:.0f}{trend}"))
        rows.append(style.accent(text, on) if value >= th.stressed or delta > 0 else text)

    if state.companions:
        names = [c.name for c in state.companions]
        team = " Team: " + ", ".join(names)
        while len(team) > z3_w and len(names) > 1:
            names.pop()
            team = " Team: " + ", ".join(names) + f" +{len(state.companions) - len(names)}"
        rows.append(fit(team))
    return rows


def _border_side(node: Node, row: int, col: int) -> str:
    last = node.size - 1
    if row == 0:
        return "N"
    if row == last:
        return "S"
    if col == 0:
        return "W"
    if col == last:
        return "E"
    return ""


def _legend_lines(node: Node, width: int, on: bool) -> List[str]:
    """
    Zone 4: one line per glyph. Exits are named by destination with the wall they sit on,
    so several doors sharing a glyph stay distinguishable: '◆ Bunkroom N · Hab Ring W'.
    """
    groups: Dict[str, List[str]] = {}
    seen = set()
    for placement in node.placements:
        entity = node.fixtures.get(placement.entity_id) or node.actors.get(placement.entity_id)
        if not entity or entity.id in seen:
            continue
        seen.add(entity.id)
        label = entity.name
        if isinstance(entity, Fixture):
            edge = node.edges.get(entity.grants_edge) if entity.grants_edge else None
            if edge:
                side = _border_side(node, placement.row, placement.col)
                label = edge.label + (f" {side}" if side else "")
            if entity.state in _NOTABLE_STATES:
                label += f" ({STATE_WORDS[entity.state]})"
        groups.setdefault(entity.glyph, []).append(label)
    lines = []
    for glyph, labels in groups.items():
        wrapped = wrap_text(" · ".join(labels), width - 4)
        for idx, wline in enumerate(wrapped):
            prefix = f" {glyph} " if idx == 0 else "   "
            lines.append(_boxed(prefix + wline, width, lambda t: style.dim(t, on)))
    return lines


def _message_lines(state: GameState, width: int, on: bool) -> List[str]:
    """Zone 5: events sorted by importance (danger, gains, results, speech), then the menu."""
    ordered = sorted(state.message_buffer, key=lambda m: _KIND_ORDER[message_kind(m)])
    lines: List[str] = []
    for msg in ordered:
        kind = message_kind(msg)
        text = strip_kind(msg)
        if kind == "danger":
            text = "! " + text[3:]
        paint = {
            "danger": lambda t: style.accent(t, on),
            "gain": lambda t: style.bold(t, on),
            "quiet": lambda t: style.dim(t, on),
        }.get(kind, lambda t: t)
        for wline in wrap_text(text, width - 2):
            lines.append(_boxed(" " + wline, width, paint))

    menu = menu_for(state) if state.proximity_menu_active else None
    if menu:
        head = f"{menu.title}:" if menu.options else menu.title
        plain = head + " " + " · ".join(f"{o.key} {o.label}" for o in menu.options)
        for idx, wline in enumerate(wrap_text(plain.strip(), width - 2)):
            styled = " " + wline
            if on:
                styled = _KEY_RE.sub(lambda m: m.group(1) + style.inverse(m.group(2)), styled)
                if idx == 0:
                    styled = styled.replace(f" {head}", " " + style.bold(head), 1)
            lines.append(f"│{pad_visible(styled, width, align='<')}│")
        if menu.hint:
            for wline in wrap_text(menu.hint, width - 2):
                lines.append(_boxed(" " + wline, width, lambda t: style.dim(t, on)))
    if not lines:
        lines.append(_boxed("", width))
    return lines


def render_frame(state: GameState, terminal_width: int, prompt_mode: bool = False,
                 terminal_height: Optional[int] = None) -> str:
    """
    Pure view renderer returning the 6-zone viewport string (>= 40 columns).
    When terminal_height is given and the frame is too tall, the legend is dropped first.
    """
    if terminal_width < 40:
        return (
            "[!] TERMINAL VIEWPORT CONFLICT: Terminal columns < 40.\n"
            "    Please expand terminal window to at least 40 columns."
        )
    if state.active_view == "map_topology":
        return render_topology(state, terminal_width)

    on = state.color_enabled
    w = max(40, terminal_width)
    inner = w - 2
    node = state.nodes[state.current_node_id]
    top = "┌" + "─" * inner + "┐"
    mid = "├" + "─" * inner + "┤"
    bot = "└" + "─" * inner + "┘"

    # Zone 1: where you are and what the air is like
    cluster = CLUSTER_NAMES.get(node.cluster, node.cluster.replace("_", " ").title())
    name = f" {node.name}"[:inner - len(cluster) - 2]
    title = name + " " * (inner - len(name) - len(cluster) - 1) + cluster + " "
    v = node.base_vitals
    readings = f" {v.pressure_kpa:g} kPa · {v.temperature_c}°C · {v.radiation_msv:g} mSv"
    hazards = hazard_words(v) if not rules.is_safe_haven(node) else ""
    if hazards and len(readings) + len(hazards) + 2 <= inner:
        vitals_line = (f"│{readings}  " + style.accent(hazards, on)
                       + " " * (inner - len(readings) - len(hazards) - 2) + "│")
    elif hazards:  # the warning matters more than the numbers
        vitals_line = _boxed(" " + hazards.capitalize(), inner, lambda t: style.accent(t, on))
    else:
        vitals_line = _boxed(readings + ("  safe air" if not hazards else ""), inner)
    zone1 = [top, _boxed(title, inner, lambda t: style.bold(t, on)), vitals_line, mid]

    # Zones 2 and 3: grid beside status
    grid_rows = build_grid(node, state.player_row, state.player_col)
    z2_w = (node.size * 2 - 1) + 4
    z3_w = w - z2_w - 3
    z2 = ["┌" + "─" * (z2_w - 2) + "┐"]
    z2 += ["│" + pad_visible(row, z2_w - 2, align='^') + "│" for row in grid_rows]
    z2.append("└" + "─" * (z2_w - 2) + "┘")
    z3 = _status_rows(state, node, z3_w, on)
    rows = max(len(z2), len(z3))
    z2 += [" " * z2_w] * (rows - len(z2))
    z3 += [" " * z3_w] * (rows - len(z3))
    split = [f"│{a}│{b}│" for a, b in zip(z2, z3)]

    legend = _legend_lines(node, inner, on)
    zone4 = [mid] + legend if legend else []
    zone5 = [mid] + _message_lines(state, inner, on)

    if prompt_mode:
        zone6 = [mid, "> "]
    else:
        if state.proximity_menu_active:
            talking = entity_under_cursor(state)[1] is not None
            hints = [" I inspect  X close  WASD move",
                     " M map  P pack  C char" + ("" if talking else "  T team")]
        else:
            hints = [" WASD move  / command  Q quit", " M map  P pack  C char  T team"]
        zone6 = [mid] + [_boxed(h, inner, lambda t: style.dim(t, on)) for h in hints] + [bot]

    lines = zone1 + split + zone4 + zone5 + zone6
    if terminal_height and len(lines) > terminal_height and zone4:
        lines = zone1 + split + zone5 + zone6
    return "\n".join(lines)
