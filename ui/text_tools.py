import os
import re
import shutil
from typing import Tuple, List

ANSI_ESCAPE_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def visible_len(text: str) -> int:
    """Returns the visible character length of text, ignoring ANSI escape sequences."""
    return len(ANSI_ESCAPE_RE.sub('', text))


def pad_visible(text: str, width: int, align: str = '^') -> str:
    """Pads a string to target width based on visible character length."""
    vlen = visible_len(text)
    total_pad = max(0, width - vlen)
    if align == '^':
        left = total_pad // 2
        right = total_pad - left
        return " " * left + text + " " * right
    elif align == '<':
        return text + " " * total_pad
    elif align == '>':
        return " " * total_pad + text
    return text


def check_terminal() -> int:
    """Returns terminal column width, defaulting to 40 on error or non-interactive shells."""
    try:
        size = shutil.get_terminal_size(fallback=(40, 24))
        return size.columns
    except Exception:
        return 40


def wrap_text(text: str, width: int) -> Tuple[str, ...]:
    """Wraps text cleanly to fit within the given character width."""
    if width <= 1:
        return (text,)
    words = text.split()
    if not words:
        return ("",)

    lines: List[str] = []
    current_line = words[0]

    for word in words[1:]:
        if len(current_line) + 1 + len(word) <= width:
            current_line += " " + word
        else:
            lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return tuple(lines)


def read_raw_key() -> str:
    """Reads a single keypress from stdin in raw mode without waiting for Enter."""
    import sys
    if not sys.stdin.isatty():
        return sys.stdin.read(1)

    import termios
    import tty
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch


def clear_terminal() -> None:
    """Clears the terminal screen and resets cursor position."""
    import sys
    if os.name == "nt":
        os.system("cls")
    else:
        sys.stdout.write("\033[H\033[2J")
        sys.stdout.flush()


