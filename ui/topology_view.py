from typing import Dict, List, Set
from core.types import GameState

NODE_SHORT_CODES: Dict[str, str] = {
    "stn_a_bunkroom": "bunk",
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

# (row, col, node_id or literal text) on a fixed 40-column canvas.
_CANVAS_ROWS = 10
_LAYOUT = (
    (0, 1, "@stn_a_bunkroom"), (0, 7, "─"), (0, 8, "@stn_a_berth"), (0, 14, "─"), (0, 15, "@stn_a_hab"),
    (0, 26, "@stn_b_array"),
    (1, 5, "\\"), (1, 9, "/"), (1, 12, "│"), (1, 28, "│"),
    (2, 4, "@stn_a_sub"), (2, 12, "│"), (2, 26, "@stn_b_dock"), (2, 32, "─"), (2, 33, "@stn_b_fuel"),
    (3, 5, "D:1"), (3, 12, "└────"), (3, 17, "@shuttle_ab"), (3, 23, "─────┘"),
    (4, 19, "│"),
    (5, 3, "@luna_smelter"), (5, 9, "─"), (5, 10, "@luna_dome"), (5, 16, "─"), (5, 17, "@luna_pad"),
    (5, 25, "LUNA SURFACE"),
    (6, 5, "║"), (6, 12, "│"),
    (7, 3, "@luna_mine"), (7, 10, "@luna_crater"),
    (8, 4, "D:1"), (8, 12, "║"),
    (9, 10, "@luna_tube"), (9, 17, "D:1"),
)


def _get_label(node_id: str, current_id: str, visited: Set[str], reachable: Set[str]) -> str:
    """Returns a 6-character label for a node in the ASCII graph."""
    code = NODE_SHORT_CODES.get(node_id, "???")
    if node_id not in visited and node_id not in reachable:
        return "[ ?? ]"
    if node_id == current_id:
        return f"[*{code[:4]:<4}]"[:5] + "]"
    return f"[{code[:4]:^4}]"


def render_topology(state: GameState, terminal_width: int) -> str:
    """Renders dedicated sector topology ASCII graph."""
    w = max(40, terminal_width)
    divider = "─" * min(w, 40)
    current_node = state.nodes.get(state.current_node_id)
    visited = set(state.visited_nodes)
    reachable = {e.target_node_id for e in current_node.edges.values()} if current_node else set()

    canvas: List[List[str]] = [[" "] * 40 for _ in range(_CANVAS_ROWS)]
    for row, col, text in _LAYOUT:
        if text.startswith("@"):
            text = _get_label(text[1:], state.current_node_id, visited, reachable)
        for offset, ch in enumerate(text):
            canvas[row][col + offset] = ch

    lines = ["TOPOLOGY [SECTOR GRAPH]", divider, " STATION ALPHA            STATION BETA"]
    lines += ["".join(row).rstrip() for row in canvas]
    lines += [divider, "SECTOR DIRECTORY:"]
    for nid, node in state.nodes.items():
        if nid in visited or nid in reachable:
            prefix = "[*]" if nid == state.current_node_id else "   "
            lines.append(f"{prefix} {NODE_SHORT_CODES.get(nid, nid):>4}: {node.name}"[:w])
    lines += [divider, "CMD: /back  /leave <exit_id>"]
    return "\n".join(lines)
