"""
Small interactive parts the tools share: a list to pick from (typing filters it), a
text field and a question. Each gives its band's lines with lines(width) and the hint
line's parts with hints(); handle(key) returns None while it's still open, or what
came of it.

In a list or a field, letters are typed, so only the arrows move and Esc goes back.
"""
from typing import Any, List, NamedTuple, Optional, Sequence

from lib import screen

CANCEL = object()     # handle() returns this when Esc closes a list or a field


class Choice(NamedTuple):
    label: str
    value: Any
    detail: str = ""      # quiet words after the label (an id, a region)
    about: str = ""       # the description band's text while this is picked


class Picker:
    """A list to pick from. Typing filters it (by label and detail); arrows move; Enter picks."""

    def __init__(self, look: screen.Look, title: str, choices: Sequence[Choice], selected: Any = None):
        self.look, self.title, self.choices = look, title, list(choices)
        self.filter = ""
        self.selected = next((i for i, c in enumerate(self.choices) if c.value == selected), 0) \
            if selected is not None else 0

    def shown(self) -> List[Choice]:
        """The choices the filter lets through; the pick is kept among them."""
        words = self.filter.lower().split()
        shown = [c for c in self.choices if all(w in screen.strip(f"{c.label} {c.detail}").lower() for w in words)]
        self.selected = max(0, min(self.selected, len(shown) - 1))
        return shown

    def current(self) -> Optional[Choice]:
        shown = self.shown()
        return shown[self.selected] if shown else None

    def lines(self, width: int):
        """The list's lines and the picked line's index (for scrolling)."""
        style, cursor = self.look.style, self.look.glyphs["cursor"]
        lines = [style.role(f"Filter: {self.filter}_", "quiet") if self.filter else ""]
        shown = self.shown()
        for index, choice in enumerate(shown):
            detail = "  " + style.role(choice.detail, "quiet") if choice.detail else ""
            if index == self.selected:
                lines.append(cursor + style.key(choice.label) + detail)
            else:
                lines.append(" " + choice.label + detail)
        if not shown:
            lines.append(style.role("Nothing matches.", "quiet"))
        return lines, self.selected + 1

    def about(self) -> str:
        current = self.current()
        return current.about if current else ""

    def hints(self) -> List[str]:
        return ["type to filter", "↑↓ pick", "Enter choose", "Esc back"]

    def handle(self, key: str):
        shown = self.shown()
        if key == "esc":
            return CANCEL
        if key == "up":
            self.selected = max(0, self.selected - 1)
        elif key == "down":
            self.selected = min(max(0, len(shown) - 1), self.selected + 1)
        elif key == "enter":
            return shown[self.selected].value if shown else None
        elif key == "backspace":
            self.filter, self.selected = self.filter[:-1], 0
        elif len(key) == 1 and key.isprintable():
            self.filter, self.selected = self.filter + key, 0
        return None


class Field:
    """One line of text. Enter gives the text (if 'check' finds no problem), Esc cancels."""

    def __init__(self, look: screen.Look, title: str, value: str = "", check=None, note: str = ""):
        self.look, self.title, self.value, self.check, self.note = look, title, value, check, note
        self.problem = ""

    def lines(self, width: int):
        style = self.look.style
        lines = ["", f"{self.title}:", style.inverse(self.value + " ") if style.colour else self.value + "_", ""]
        if self.problem:
            lines += [style.role(line, "danger") for line in screen.wrap(self.problem, width)]
        elif self.note:
            lines += screen.quiet(self.look, self.note, width)
        return lines, 2

    def about(self) -> str:
        return ""

    def hints(self) -> List[str]:
        return ["Enter done", "Esc back"]

    def handle(self, key: str):
        if key == "esc":
            return CANCEL
        if key == "enter":
            self.problem = self.check(self.value) if self.check else ""
            return None if self.problem else self.value
        if key == "backspace":
            self.value = self.value[:-1]
        elif len(key) == 1 and key.isprintable():
            self.value += key
        self.problem = ""
        return None


class Question:
    """A question answered with one key: 'answers' maps keys to outcomes; X or Esc answers None."""

    def __init__(self, look: screen.Look, text: str, answers: Sequence[tuple]):
        self.look, self.text, self.answers = look, text, list(answers)   # (key, label, outcome)
        self.title = ""

    def lines(self, width: int):
        return [""] + screen.wrap(self.text, width) + [""], 0

    def about(self) -> str:
        return ""

    def hints(self) -> List[str]:
        return [f"{key.upper()} {label}" for key, label, _ in self.answers] + [f"{self.look.key('back')} back"]

    def handle(self, key: str):
        for answer, _, outcome in self.answers:
            if key.lower() == answer:
                return outcome
        if self.look.action(key) == "back":
            return CANCEL
        return None

