"""
The tools' look, borrowed from the game: bordered bands drawn with the UI pack's
glyphs, padding and styles, a numbered menu with the game's cursor, and a line of key
hints. Keys follow the game's bindings too, so a tool's keys are the game's keys.

A screen is a list of bands, each a list of lines. One band may be flexible: it gets
the rows the others leave and scrolls (a long list, a report). When the rest is still
too tall, the tallest band loses its last lines; a tool keeps its bands short instead.
"""
from typing import List, NamedTuple, Optional, Sequence, Tuple

from tui.text import ANSI, Style, pad, visible_len, wrap  # noqa: F401  (wrap is for the tools)
from tui.ui import UI, default_ui

# Input actions every tool understands, besides plain letters.
ARROWS = {"up": "move_north", "down": "move_south", "left": "move_west", "right": "move_east"}
DIRECTIONS = {"move_north": "up", "move_south": "down", "move_west": "left", "move_east": "right"}


class Look(NamedTuple):
    ui: UI
    style: Style

    @property
    def glyphs(self):
        return self.ui.tokens["glyphs"]

    @property
    def min_size(self) -> Tuple[int, int]:
        size = self.ui.tokens["size"]
        return size["min_columns"], size["min_rows"]

    def action(self, key: str) -> str:
        """
        What a key means, the same in every tool: 'up', 'down', 'left', 'right' (arrows or
        the movement keys), 'enter', 'back' (Esc or the close key), 'quit' (the quit key),
        or the key itself.
        """
        if key in ARROWS:
            return key
        if key == "esc":
            return "back"
        bound = self.ui.action_of(key.lower()) if len(key) == 1 else None
        if bound in DIRECTIONS:
            return DIRECTIONS[bound]
        if bound == "close":
            return "back"
        if bound == "quit":
            return "quit"
        return key

    def key(self, action: str) -> str:
        """The key to show in hints for 'back' or 'quit'."""
        return {"back": self.ui.bindings["close"], "quit": self.ui.bindings["quit"]}[action].upper()


def look(colour: bool = True, ui: Optional[UI] = None) -> Look:
    ui = ui or default_ui()
    return Look(ui, Style(colour, ui.tokens["styles"]))


def title(look: Look, left: str, right: str, width: int) -> List[str]:
    """A title band's line: the name on the left, quiet words on the right."""
    gap = max(1, width - visible_len(left) - visible_len(right))
    return [look.style.role(left, "title") + " " * gap + look.style.role(right, "quiet")]


def menu(look: Look, labels: Sequence[str], selected: int) -> Tuple[List[str], int]:
    """Numbered choices with the pick marked, as on the game's start screen; and the pick's line."""
    lines = [""]
    for index, label in enumerate(labels):
        text = f"{index + 1} {label}"
        if index == selected:
            lines.append("  " + look.glyphs["cursor"] + look.style.key(text))
        else:
            lines.append("   " + text)
    return lines + [""], selected + 1


def strip(text: str) -> str:
    """Text without its styles."""
    return ANSI.sub("", text)


def quiet(look: Look, text: str, width: int) -> List[str]:
    return [look.style.role(line, "quiet") for line in wrap(text, width)] if text else []


def hints(look: Look, parts: Sequence[str], width: int, styled: bool = True) -> List[str]:
    """
    Key hints, wrapped between hints, never inside one: only the keys that work now.
    With styled=False the parts keep their own styles (a legend of colours).
    """
    lines: List[str] = []
    for part in parts:
        if lines and visible_len(lines[-1]) + 2 + visible_len(part) <= width:
            lines[-1] += "  " + part
        else:
            lines += wrap(part, width) if styled else [part]
    return [look.style.role(line, "hint") for line in lines] if styled else lines


def inner_width(look: Look, columns: int) -> int:
    """The text width inside the border and padding."""
    return max(1, columns - 2 - 2 * look.ui.tokens["padding"])


class Drawn(NamedTuple):
    text: str
    scroll: int     # the flexible band's offset, within its limits
    limit: int      # the largest offset; 0 when it all fits


def draw(look: Look, bands: Sequence[List[str]], columns: int, rows: int,
         flex: Optional[int] = None, scroll: int = 0, focus: Optional[int] = None) -> Drawn:
    """
    Bands in a border at the terminal's size. 'flex' is the band that scrolls: from
    'scroll', or kept around its 'focus' line when one is given.
    """
    min_columns, min_rows = look.min_size
    if columns < min_columns or rows < min_rows:
        return Drawn(look.ui.word("terminal_too_small", columns=min_columns, rows=min_rows) + "\n", 0, 0)
    bands = [list(b) for b in bands]
    limit = 0
    while sum(len(b) for i, b in enumerate(bands) if i != flex) + len(bands) + 1 + (flex is not None) > rows:
        tallest = max((i for i in range(len(bands)) if i != flex), key=lambda i: len(bands[i]))
        if len(bands[tallest]) <= 1:
            break
        bands[tallest] = bands[tallest][:-1]               # too tall: the tallest band loses its last lines
    if flex is not None:
        others = sum(len(b) for i, b in enumerate(bands) if i != flex) + len(bands) + 1
        window = max(1, rows - others)
        lines = bands[flex]
        limit = max(0, len(lines) - window)
        if focus is not None:
            scroll = focus - window // 2
        scroll = max(0, min(scroll, limit))
        bands[flex] = lines[scroll:scroll + window]
    padding = " " * look.ui.tokens["padding"]
    text_width = inner_width(look, columns)
    border = look.glyphs["border"]
    horizontal = border["horizontal"] * (columns - 2)
    out = [border["top_left"] + horizontal + border["top_right"]]
    for index, band in enumerate(bands):
        if index:
            out.append(border["join_left"] + horizontal + border["join_right"])
        out += [border["vertical"] + padding + pad(line, text_width) + padding + border["vertical"]
                for line in band]
    out.append(border["bottom_left"] + horizontal + border["bottom_right"])
    return Drawn("\n".join(out) + "\n", scroll if flex is not None else 0, limit)
