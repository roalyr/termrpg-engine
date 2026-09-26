import os
import shutil
from typing import Tuple, List

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

