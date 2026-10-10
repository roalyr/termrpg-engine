"""
Colours as packs write them (a palette name or a 256-colour terminal number) and the
picker every tool uses to choose one: the named colours in a list, then the full
terminal grid.
"""
from typing import Callable, List

from tools.lib import forms, screen
from tui.text import PALETTE

NAMED = ("grey", "white", "green", "cyan", "blue", "violet", "yellow", "orange", "red")
DEFAULT = object()                            # "leave it to the UI pack": the field is removed
_GRID = object()


def code(colour) -> int:
    """A palette colour (a name or a 256-colour number) as a terminal colour number."""
    return colour if isinstance(colour, int) else PALETTE.get(colour, PALETTE["white"])


def sample(look: screen.Look, colour) -> str:
    """A swatch of the colour; a plain block without colour."""
    return look.style.pixels("█", code(colour), None) if look.style.colour else "█"


class ColourGrid:
    """The 256 terminal colours, 32 to a row: arrows move, Enter picks, Esc goes back."""

    title = "Pick a terminal colour"
    PER_ROW = 32

    def __init__(self, look: screen.Look, selected: int = 0):
        self.look, self.selected = look, selected

    def lines(self, width: int):
        style, per = self.look.style, min(self.PER_ROW, width)
        lines = [""]
        for start in range(0, 256, per):
            cells = []
            for n in range(start, min(start + per, 256)):
                cell = style.pixels("█", n, None) if style.colour else "·"
                cells.append(style.inverse("+") if n == self.selected else cell)
            lines.append("".join(cells))
        return lines, 1 + self.selected // per

    def about(self) -> str:
        return f"Colour {self.selected}."

    def hints(self) -> List[str]:
        return ["←↑↓→ move", "Enter choose", "Esc back"]

    def handle(self, key: str):
        action = self.look.action(key)
        if key == "esc" or action == "back":
            return forms.CANCEL
        if key == "enter":
            return self.selected
        step = {"up": -self.PER_ROW, "down": self.PER_ROW, "left": -1, "right": 1}.get(action)
        if step is not None and 0 <= self.selected + step < 256:
            self.selected += step
        return None


def choose(tool, title: str, then: Callable, selected=None, default: str = "") -> None:
    """
    Asks for a colour through the tool's ask(): a named colour, or one from the terminal
    grid. With 'default' (its label) the list starts with that choice, answered as DEFAULT.
    """
    choices = ([forms.Choice(default, DEFAULT)] if default else [])
    choices += [forms.Choice(f"{sample(tool.look, name)} {name}", name) for name in NAMED]
    choices.append(forms.Choice("Terminal colour (0-255)…", _GRID))

    def picked(colour):
        if colour is _GRID:
            return tool.ask(ColourGrid(tool.look, selected if isinstance(selected, int) else 0), then)
        then(colour)
    tool.ask(forms.Picker(tool.look, title, choices, selected if selected in NAMED else None), picked)
