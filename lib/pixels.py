"""
Pictures in half-block pixels: two pixels to a text cell, one above the other ('▀'
with a foreground and a background colour). Used for characters' art in the game,
the art editor's canvas and the loadout editor.
"""
from typing import Collection, List, Mapping, Optional, Sequence, Tuple

from lib.text import Style, colour_code

Pixels = List[List[Optional[int]]]      # rows of terminal colour numbers; None is see-through


def centred(rows: Sequence[str], palette: Mapping[str, object], width: int, height: int) -> Pixels:
    """A picture (pixel letters and their palette; ' ' and '.' see-through) centred in width by height, cut to it."""
    grid: Pixels = [[None] * width for _ in range(height)]
    widest = max((len(r) for r in rows), default=0)
    top, left = (height - len(rows)) // 2, (width - widest) // 2
    for y, row in enumerate(rows):
        for x, letter in enumerate(row):
            if letter not in " ." and 0 <= top + y < height and 0 <= left + x < width:
                grid[top + y][left + x] = colour_code(palette.get(letter, "white"))
    return grid


def half_blocks(style: Style, grid: Pixels, empty: str = " ", marked: Collection[Tuple[int, int]] = ()) -> List[str]:
    """
    The grid as lines of text, two pixel rows to a line. Without colour only the shape
    shows ('█', '▀', '▄'); pixels in 'marked' (y, x) are then drawn inverse, so a cursor
    still shows. 'empty' fills cells with no pixel (already styled by the caller).
    """
    lines = []
    for y in range(0, len(grid), 2):
        upper_row = grid[y]
        lower_row = grid[y + 1] if y + 1 < len(grid) else [None] * len(upper_row)
        cells = []
        for x, (upper, lower) in enumerate(zip(upper_row, lower_row)):
            if not style.colour:
                shape = {(True, True): "█", (True, False): "▀", (False, True): "▄"}.get(
                    (upper is not None, lower is not None))
                if (y, x) in marked or (y + 1, x) in marked:
                    cells.append(style.inverse(shape or " "))
                else:
                    cells.append(shape or empty)
            elif upper is None and lower is None:
                cells.append(empty)
            elif upper is None:
                cells.append(style.pixels("▄", lower, None))
            elif lower is None or lower == upper:
                cells.append(style.pixels("█" if lower == upper else "▀", upper, None))
            else:
                cells.append(style.pixels("▀", upper, lower))
        lines.append("".join(cells))
    return lines
