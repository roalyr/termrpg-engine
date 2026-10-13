"""
Colours as packs write them: names from the pack's palette (palette.json), the default
colours always among them. The picker every tool uses lists those names; a new colour
is picked from the terminal grid, named, and added to the palette.
"""
import re
from typing import Callable, Dict, List, Optional, Tuple

from lib.text import DEFAULT_COLOURS
from lib import forms, screen
from tools.lib.packfiles import PackFiles

DEFAULT = object()                            # "leave it to the UI pack": the field is removed
_NEW = object()
KIND = "palette"
FILE = "palette.json"
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def sample(look: screen.Look, colour) -> str:
    """A swatch of the colour (a name, or a terminal number); a plain block without colour."""
    return look.style.pixels("█", look.style.code(colour), None) if look.style.colour else "█"


def names(pack: PackFiles) -> List[Tuple[str, int]]:
    """(name, terminal number) of every colour: the defaults first (as the palette sets them), then the pack's own."""
    codes = dict(pack.palette)
    shown = [(name, codes.get(name, code)) for name, code in DEFAULT_COLOURS.items()]
    return shown + [(name, code) for name, code in codes.items() if name not in DEFAULT_COLOURS]


def ensure_file(pack: PackFiles) -> str:
    """The pack's palette file; without one, palette.json is made with the default colours and listed in pack.json."""
    if pack.kinds.get(KIND):
        return pack.kinds[KIND][0]
    entries = [{"id": name, "code": code} for name, code in DEFAULT_COLOURS.items()]
    pack.add_file(KIND, FILE, {"$schema": "../../schemas/palette.schema.json", "entries": entries})
    return FILE


def add(pack: PackFiles, name: str, code: int) -> None:
    """Adds a colour to the palette (making the file first if the pack has none)."""
    pack.add(KIND, {"id": name, "code": code}, ensure_file(pack))


def check_name(pack: PackFiles, name: str) -> str:
    """What's wrong with a new colour's name, or ''."""
    if not ID_PATTERN.match(name):
        return "Lower case letters, digits and _, starting with a letter."
    return "That name is taken." if name in dict(names(pack)) else ""


class ColourGrid:
    """The 256 terminal colours, 32 to a row: arrows move, Enter picks, Esc goes back."""

    title = "Pick a terminal colour"
    PER_ROW = 32

    def __init__(self, look: screen.Look, selected: int = 0, named: Optional[Dict[int, List[str]]] = None):
        self.look, self.selected = look, selected
        self.named = named or {}               # terminal number -> the palette's names for it

    def lines(self, width: int):
        style, per = self.look.style, min(self.PER_ROW, width)
        lines = [""]
        for start in range(0, 256, per):
            cells = []
            for n in range(start, min(start + per, 256)):
                cell = style.pixels("█", n, None) if style.colour else "·"
                cells.append(style.inverse("+") if n == self.selected else cell)
            lines.append("".join(cells))
        swatch = style.pixels("████", self.selected, None) if style.colour else ""
        lines += ["", f"{swatch} {self.selected}".strip()]
        return lines, 1 + self.selected // per

    def about(self) -> str:
        named = self.named.get(self.selected)
        return f"Colour {self.selected}" + (f": {', '.join(named)}." if named else ".")

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


def grid(tool, selected: int = 0) -> ColourGrid:
    """The terminal grid, telling which of the pack's colours each number already is."""
    named: Dict[int, List[str]] = {}
    for name, code in names(tool.pack):
        named.setdefault(code, []).append(name)
    return ColourGrid(tool.look, selected, named)


def new(tool, then: Callable[[str], None], code: int = 0) -> None:
    """Asks for a new colour (its terminal number, then its name), adds it to the palette and gives its name."""
    def named(number):
        def done(name):
            add(tool.pack, name, number)
            then(name)
        tool.ask(forms.Field(tool.look, f"Name for colour {number}", "", lambda text: check_name(tool.pack, text),
                             "Plain words, e.g. rust or hull. Every colour in the pack is used by this name."), done)
    tool.ask(grid(tool, code), named)


def choose(tool, title: str, then: Callable, selected=None, default: str = "") -> None:
    """
    Asks for a colour through the tool's ask(): a name from the pack's palette, or a new
    colour added to it. With 'default' (its label) the list starts with that choice,
    answered as DEFAULT.
    """
    choices = ([forms.Choice(default, DEFAULT)] if default else [])
    choices += [forms.Choice(f"{sample(tool.look, name)} {name}", name, str(code)) for name, code in names(tool.pack)]
    choices.append(forms.Choice("New colour…", _NEW, "", "Pick a terminal colour and name it: it joins the palette."))

    def picked(colour):
        if colour is _NEW:
            return new(tool, then, dict(names(tool.pack)).get(selected, 0))
        then(colour)
    tool.ask(forms.Picker(tool.look, title, choices, selected), picked)
