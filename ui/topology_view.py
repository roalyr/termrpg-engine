from typing import Dict, Set
from core.types import GameState

NODE_SHORT_CODES: Dict[str, str] = {
    "stn_a_hab": "hab",
    "stn_a_berth": "brt",
    "stn_a_sub": "sub",
    "stn_b_array": "arr",
    "stn_b_fuel": "fuel",
    "stn_b_dock": "dock",
    "shuttle_ab": "shut",
    "luna_pad": "pad",
    "luna_dome": "dome",
    "luna_smelter": "smlt",
    "luna_crater": "crtr",
    "luna_mine": "mine",
    "luna_tube": "tube",
}

NODE_DISPLAY_NAMES: Dict[str, str] = {
    "stn_a_hab": "Hab Ring",
    "stn_a_berth": "Berth 04",
    "stn_a_sub": "Sub-Deck (D:1)",
    "stn_b_array": "Array Hub",
    "stn_b_fuel": "Fuel Spur",
    "stn_b_dock": "Dock Ring",
    "shuttle_ab": "Shuttle Transit",
    "luna_pad": "Lunar Pad",
    "luna_dome": "Habitat Dome",
    "luna_smelter": "Smelter Flat",
    "luna_crater": "Crater Rim",
    "luna_mine": "Deep Mine (D:1)",
    "luna_tube": "Lava Tube (D:1)",
}


def _get_label(node_id: str, current_id: str, visited: Set[str], reachable: Set[str]) -> str:
    """Returns formatted short label for a node in the ASCII graph."""
    code = NODE_SHORT_CODES.get(node_id, "???")
    is_here = (node_id == current_id)
    is_known = (node_id in visited or node_id in reachable)

    if not is_known:
        return "[???]"

    if is_here:
        return f"[*{code[:3]}]"
    else:
        return f"[{code[:4]:^4}]"


def render_topology(state: GameState, terminal_width: int) -> str:
    """Renders dedicated sector topology ASCII graph."""
    w = max(40, terminal_width)
    divider = "─" * min(w, 40)
    current_node = state.nodes.get(state.current_node_id)
    visited = set(state.visited_nodes)

    reachable = set()
    if current_node:
        for edge in current_node.edges.values():
            reachable.add(edge.target_node_id)

    def lbl(nid: str) -> str:
        return _get_label(nid, state.current_node_id, visited, reachable)

    lines = [
        "TOPOLOGY [SECTOR GRAPH]",
        divider,
        " STATION ALPHA        STATION BETA",
        f" {lbl('stn_a_hab')} ── {lbl('stn_a_berth')}      {lbl('stn_b_array')} ── {lbl('stn_b_fuel')}",
        f"            │            \\    /",
        f"          (D:1)          {lbl('stn_b_dock')}",
        f"          {lbl('stn_a_sub')}            │",
        f"            : shuttle      : shuttle",
        f"            :··············:",
        f"                   :",
        f"          ════════{lbl('luna_pad')}════════ (Surface)",
        f"                   │",
        f"               {lbl('luna_dome')}",
        f"               /      \\",
        f"          {lbl('luna_smelter')}      {lbl('luna_crater')}",
        f"            ║            ║",
        f"          {lbl('luna_mine')}D:1   {lbl('luna_tube')}D:1",
        divider,
        "SECTOR DIRECTORY:",
    ]

    # Render 2-column directory for known nodes
    items = []
    for nid, name in NODE_DISPLAY_NAMES.items():
        if nid in visited or nid in reachable:
            prefix = "[*]" if nid == state.current_node_id else "   "
            short = NODE_SHORT_CODES.get(nid, nid)
            items.append(f"{prefix}{short:>4}: {name}")

    for i in range(0, len(items), 2):
        col1 = items[i]
        col2 = items[i + 1] if i + 1 < len(items) else ""
        lines.append(f" {col1:<18} {col2}")

    lines.append(divider)
    lines.append("CMD: back / leave <exit_id>")
    lines.append("> ")

    return "\n".join(lines)
