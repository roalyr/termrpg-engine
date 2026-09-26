from typing import Tuple, List, Optional
from core.types import GameState, Node, Fixture, Actor
from ui.text_tools import wrap_text, pad_visible
from ui.topology_view import render_topology


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
        entity = node.fixtures.get(placement.entity_id) or \
                 node.actors.get(placement.entity_id)
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



def render_frame(state: GameState, terminal_width: int, prompt_mode: bool = False) -> str:
    """
    Pure view renderer returning a 6-zone mobile viewport string (<= 40 cols minimum).
    Every line is strictly formatted to terminal_width.
    """
    if terminal_width < 40:
        return (
            "[!] TERMINAL VIEWPORT CONFLICT: Terminal columns < 40.\n"
            "    Please expand terminal window to at least 40 columns."
        )

    if state.active_view == "map_topology":
        return render_topology(state, terminal_width)

    w = max(40, terminal_width)
    node = state.nodes[state.current_node_id]

    # --- ZONE 1: LOCATION HEADER ---
    border_horiz = "+" + "─" * (w - 2) + "+"
    title_line = f" {node.name.upper()} [{node.cluster.upper()}]"
    title_line = title_line[:w - 2]
    vitals = node.base_vitals
    vitals_line = f" ATM:{int(vitals.pressure_kpa)}kPa | TMP:{vitals.temperature_c}C | RAD:{vitals.radiation_msv}mSv"
    vitals_line = vitals_line[:w - 2]

    zone1_lines = [
        border_horiz,
        f"│{title_line:<{w - 2}}│",
        f"│{vitals_line:<{w - 2}}│",
        border_horiz
    ]

    # --- ZONE 2 & 3: SPLIT UPPER VIEWPORT ---
    grid_rows = build_grid(node, state.player_row, state.player_col)
    grid_char_width = (node.size * 2) - 1
    # Zone 2 width including its internal box borders
    z2_w = grid_char_width + 4
    # Zone 3 width fills remainder: w = 1 (outer) + z2_w + 1 (divider) + z3_w + 1 (outer)
    z3_w = w - z2_w - 3

    # Format Zone 2 (Spatial Grid)
    z2_rows: List[str] = []
    z2_top = "┌" + "─" * (z2_w - 2) + "┐"
    z2_bot = "└" + "─" * (z2_w - 2) + "┘"
    z2_rows.append(z2_top)
    for row in grid_rows:
        z2_rows.append("│" + pad_visible(row, z2_w - 2, align='^') + "│")
    z2_rows.append(z2_bot)

    # Format Zone 3 (Status)
    exp = state.character.exposure
    max_exp = max(exp.pressure_debt, exp.radiation_dose, exp.thermal_stress)
    if max_exp >= 10.0:
        exp_status = "CRITICAL"
    elif max_exp >= 5.0:
        exp_status = "STRESSED"
    else:
        exp_status = "NOMINAL"

    z3_rows: List[str] = [
        f" CYCLE: {state.cycle:03d}"[:z3_w],
        f" AIR: {exp_status}"[:z3_w],
        " PACK:"[:z3_w]
    ]
    if not state.character.inventory:
        z3_rows.append("  (empty)"[:z3_w])
    else:
        for it in state.character.inventory:
            cond = f"({it.integrity})" if it.max_integrity > 0 else ""
            line = f"  - {it.name[:z3_w - 8]}{cond}"
            z3_rows.append(line[:z3_w])

    if state.companions:
        names = ", ".join(c.name for c in state.companions)
        z3_rows.append(f" CREW: {names[:z3_w - 8]}"[:z3_w])

    # Equalize row counts between Zone 2 and Zone 3
    max_rows = max(len(z2_rows), len(z3_rows))
    while len(z2_rows) < max_rows:
        z2_rows.append(" " * z2_w)
    while len(z3_rows) < max_rows:
        z3_rows.append("")

    split_lines: List[str] = []
    for z2, z3 in zip(z2_rows, z3_rows):
        split_lines.append(f"│{z2}│{z3:<{z3_w}}│")

    # --- ZONE 4: LEGEND ---
    z4_entries: List[str] = []
    seen_ids = set()
    for placement in node.placements:
        if placement.entity_id in seen_ids:
            continue
        seen_ids.add(placement.entity_id)
        entity = node.fixtures.get(placement.entity_id) or \
                 node.actors.get(placement.entity_id)
        if entity:
            status_hint = ""
            if isinstance(entity, Fixture):
                status_hint = f" ({entity.state})"
            elif isinstance(entity, Actor):
                status_hint = f" [{entity.title}]"
            line = f" {entity.glyph} : {entity.name}{status_hint} [{entity.id}]"
            z4_entries.append(line[:w - 2])

    zone4_lines = [
        border_horiz,
        f"│{' MAP LEGEND':<{w - 2}}│"
    ]
    for ent in z4_entries:
        zone4_lines.append(f"│{ent:<{w - 2}}│")

    # Exits summary
    edge_items = [f"{eid}->{e.label}" for eid, e in node.edges.items()]
    exits_line = f" EXITS: {', '.join(edge_items)}"
    zone4_lines.append(f"│{exits_line[:w - 2]:<{w - 2}}│")

    # --- ZONE 5: MESSAGES / PROXIMITY MENU ---
    zone5_lines = [border_horiz]
    if state.proximity_menu_active:
        for msg in state.message_buffer:
            wrapped = wrap_text(msg, w - 4)
            for wline in wrapped:
                zone5_lines.append(f"│ {wline:<{w - 3}}│")
    else:
        msg_list = list(state.message_buffer)
        if state.flavor_enabled and node.description and len(msg_list) < 3:
            msg_list.insert(0, f"[{node.description}]")

        if not msg_list:
            zone5_lines.append(f"│{' (All systems nominal)':<{w - 2}}│")
        else:
            for msg in msg_list[-6:]:
                wrapped = wrap_text(msg, w - 4)
                for wline in wrapped:
                    zone5_lines.append(f"│ {wline:<{w - 3}}│")

    # --- ZONE 6: PROMPT / KEY HINTS ---
    if prompt_mode:
        zone6_lines = [
            border_horiz,
            "> "
        ]
    else:
        if state.proximity_menu_active:
            hint = " I: inspect  U: use  S: scavenge  T: talk  G: go  X: exit"
        else:
            hint = " WASD: move  /: cmd  M: map  Q: quit"
        zone6_lines = [
            border_horiz,
            f"│{hint[:w - 2]:<{w - 2}}│",
            border_horiz
        ]

    all_lines = (
        zone1_lines +
        split_lines +
        zone4_lines +
        zone5_lines +
        zone6_lines
    )
    return "\n".join(all_lines)

