"""Terminal helpers: styles, the colour palette, visible width, wrapping and raw keys."""
import os
import re
import shutil
import sys
from typing import List, Mapping, Optional

ANSI = re.compile(r"\x1b\[[0-9;]*m")
RESET = "\x1b[0m"

# The engine's palette (grade colours and the warning colour), as 256-colour codes.
PALETTE = {"grey": 245, "white": 255, "green": 114, "cyan": 80, "blue": 75,
           "violet": 141, "yellow": 221, "orange": 208, "red": 203}


class Style:
    """
    Text styles by role, from the UI pack's tokens. With colour off everything is plain
    except the player's inverse cursor.
    """

    def __init__(self, colour: bool = True, styles: Optional[Mapping[str, Mapping]] = None):
        self.colour = colour
        self.styles = styles or {}

    def _wrap(self, text: str, code: str) -> str:
        return f"\x1b[{code}m{text}{RESET}" if self.colour and text else text

    def role(self, text: str, role: str, *extra: str) -> str:
        """Text in a role's style: its colour, bold and dim (plus any extra codes)."""
        spec = self.styles.get(role, {})
        codes = list(extra)
        if spec.get("bold"):
            codes.append("1")
        if spec.get("dim"):
            codes.append("2")
        if spec.get("colour"):
            codes.append(f"38;5;{PALETTE.get(spec['colour'], PALETTE['white'])}")
        return self._wrap(text, ";".join(codes)) if codes else text

    def inverse(self, text: str) -> str:
        return f"\x1b[7m{text}{RESET}" if text else text

    def pixels(self, text: str, fg: Optional[int], bg: Optional[int]) -> str:
        """Half-block pixels: 'fg' and 'bg' are 256-colour codes (None for none). Plain without colour."""
        codes = ([f"38;5;{fg}"] if fg is not None else []) + ([f"48;5;{bg}"] if bg is not None else [])
        return self._wrap(text, ";".join(codes)) if codes else text

    def key(self, text: str) -> str:
        """A key letter in a menu: inverse, in the 'key' role's style. Plain without colour."""
        return self.role(text, "key", "7")


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
    """
    One keypress without Enter (raw mode): a whole character, or a whole escape sequence
    such as an arrow key ('\x1b[A'). '' only at the end of input. When stdin isn't a
    terminal, keys are read from it one character at a time.
    """
    if not sys.stdin.isatty():
        return sys.stdin.read(1)
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        data = os.read(fd, 1)
        if data == b"\x1b":                               # an escape sequence, or Esc alone
            data += _pending_bytes(fd)
        elif data and data[0] >= 0xC0:                    # the rest of a UTF-8 character
            data += os.read(fd, 1 if data[0] < 0xE0 else 2 if data[0] < 0xF0 else 3)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return data.decode(errors="replace")


def _pending_bytes(fd: int, limit: int = 8) -> bytes:
    """Bytes that arrive right after Esc: the rest of an escape sequence."""
    import select
    data = b""
    while len(data) < limit and select.select([fd], [], [], 0.03)[0]:
        data += os.read(fd, 1)
    return data
