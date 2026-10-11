"""
A region's map as text: places on a grid of cells, and the links between neighbouring
cells. Each cell is one glyph followed by room for a link to the right ('───'), and a
line under it for a link down ('│'). Links between cells that aren't neighbours aren't
drawn. The callers decide what each place looks like (the editor by what's wrong with
it, the game by what the player has seen); this only lays them out.
"""
from typing import Iterable, List, Mapping, Tuple

Cell = Tuple[int, int]                      # (x, y)
PITCH = 4                                   # columns per cell: the glyph and a link
ACROSS, DOWN = "───", "│"


def fit(width: int, height: int) -> Cell:
    """How many cells fit across and down in a space of text."""
    return max(1, (width + PITCH - 1) // PITCH), max(1, (height + 1) // 2)


def origin(cursor: Cell, previous: Cell, across: int, down: int) -> Cell:
    """The top-left cell to show: the previous one, moved only as far as needed to keep the cursor in view."""
    x = min(max(previous[0], cursor[0] - across + 1), cursor[0])
    y = min(max(previous[1], cursor[1] - down + 1), cursor[1])
    return max(0, x), max(0, y)


def extent(cells: Iterable[Cell]) -> Cell:
    """The last cell holding a place."""
    cells = list(cells) or [(0, 0)]
    return max(c[0] for c in cells), max(c[1] for c in cells)


def draw(glyphs: Mapping[Cell, str], links: Iterable[Tuple[Cell, Cell]], start: Cell, across: int, down: int,
         last: Cell, blank: str = " ") -> List[str]:
    """
    Lines of the map from 'start', up to 'across' by 'down' cells and no further than
    'last'. 'glyphs' are already styled; empty cells show 'blank'. Each link is a pair
    of cells in either order.
    """
    joined = {tuple(sorted(pair)) for pair in links}
    lines = []
    for y in range(start[1], min(start[1] + down, last[1] + 1)):
        top, under = "", ""
        for x in range(start[0], min(start[0] + across, last[0] + 1)):
            top += glyphs.get((x, y), blank) + (ACROSS if ((x, y), (x + 1, y)) in joined else " " * (PITCH - 1))
            under += (DOWN if ((x, y), (x, y + 1)) in joined else " ") + " " * (PITCH - 1)
        lines += [top.rstrip(), under.rstrip()]
    return lines
