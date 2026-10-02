"""Terminal helpers: styles, the colour palette, visible width, wrapping and raw keys."""
import os
import re
import shutil
import sys
from typing import List

ANSI = re.compile(r"\x1b\[[0-9;]*m")
RESET = "\x1b[0m"

# The engine's palette (grade colours and the warning colour), as 256-colour codes.
PALETTE = {"grey": 245, "white": 255, "green": 114, "cyan": 80, "blue": 75,
           "violet": 141, "yellow": 221, "orange": 208, "red": 203}
DANGER = "orange"


class Style:
    """Text styles. With colour off everything is plain except the player's inverse cursor."""

    def __init__(self, colour: bool = True):
        self.colour = colour

    def _wrap(self, text: str, code: str) -> str:
        return f"\x1b[{code}m{text}{RESET}" if self.colour and text else text

    def bold(self, text: str) -> str:
        return self._wrap(text, "1")

    def dim(self, text: str) -> str:
        return self._wrap(text, "2")

    def inverse(self, text: str) -> str:
        return f"\x1b[7m{text}{RESET}" if text else text

    def key(self, text: str) -> str:
        """A key letter in a menu: inverse in colour, plain otherwise."""
        return f"\x1b[7m{text}{RESET}" if self.colour and text else text

    def tint(self, text: str, colour: str) -> str:
        return self._wrap(text, f"38;5;{PALETTE.get(colour, PALETTE['white'])}")

    def danger(self, text: str) -> str:
        return self.tint(text, DANGER)


def visible_len(text: str) -> int:
    return len(ANSI.sub("", text))


def pad(text: str, width: int) -> str:
    """Left-aligned to a visible width, cut if longer."""
    if visible_len(text) > width:
        plain = ANSI.sub("", text)
        return plain[:width]
    return text + " " * (width - visible_len(text))


def wrap(text: str, width: int) -> List[str]:
    """Plain text wrapped to a width."""
    lines: List[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            while len(word) > width:
                if line:
                    lines.append(line)
                    line = ""
                lines.append(word[:width])
                word = word[width:]
            candidate = f"{line} {word}" if line else word
            if len(candidate) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return lines


def terminal_size() -> tuple:
    size = shutil.get_terminal_size((44, 40))
    return size.columns, size.lines


def clear() -> None:
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()


def read_key() -> str:
    """One keypress without Enter (raw mode). Falls back to a line when stdin isn't a terminal."""
    if not sys.stdin.isatty():
        return sys.stdin.read(1)
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        key = os.read(fd, 1).decode(errors="ignore")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return key
