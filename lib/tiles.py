"""
A room's tiles, and drawing them: '#' wall, '.' floor, ' ' nothing. A grid without
'rows' is a box: walls round the edge, floor inside. Rows are drawn one glyph per
tile, with walls joined across the gaps between tiles.
"""
from typing import Dict, List, Mapping, Optional, Tuple

from lib.text import Style, colour_code

Pos = Tuple[int, int]                   # (row, column)


def tiles(grid: Mapping) -> Optional[Dict[Pos, str]]:
    """Every tile of a grid, or None when its size or rows don't add up (the checker says why)."""
    width, height = grid.get("width"), grid.get("height")
    if not (isinstance(width, int) and isinstance(height, int)):
        return None
    rows = grid.get("rows")
    if rows is None:
        return {(r, c): "#" if r in (0, height - 1) or c in (0, width - 1) else "."
                for r in range(height) for c in range(width)}
    if len(rows) != height or any(len(row) != width for row in rows if isinstance(row, str)):
        return None
    return {(r, c): ch for r, row in enumerate(rows) for c, ch in enumerate(row)}


def tile(grid: Mapping, pos: Pos) -> str:
    """One tile; ' ' outside the grid."""
    row, col = pos
    if not (0 <= row < grid["height"] and 0 <= col < grid["width"]):
        return " "
    if grid.get("rows"):
        return grid["rows"][row][col]
    return "#" if row in (0, grid["height"] - 1) or col in (0, grid["width"] - 1) else "."


def room_line(cells: List[str], walls: List[bool], wall: str, cell_width: int) -> str:
    """
    One row of a room: one tile per cell, cell_width columns apart. Walls are joined: the gap
    between two tiles showing wall, and the edge beside one, is the wall glyph too, so walls
    are solid; a door or anything else in a wall leaves a gap around it.
    """
    gap = cell_width - 1
    line = [wall if walls and walls[0] else " "]
    for i, cell in enumerate(cells):
        if i:
            line.append((wall if walls[i - 1] and walls[i] else " ") * gap)
        line.append(cell)
    line.append(wall if walls and walls[-1] else " ")
    return "".join(line)


def map_glyph(style: Style, glyph: str, colour, role: str) -> str:
    """A map glyph in the pack's colour (a palette colour or a 256-colour number), else in its role's style."""
    if colour is not None:
        return style.pixels(glyph, colour_code(colour), None)
    return style.role(glyph, role)
