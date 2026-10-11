"""
The terminal loop the tools share. A tool is two functions, like the game:
render(columns, rows) -> the screen as text, and handle(key) -> False to quit.
Keys arrive as names: a character, or 'up', 'down', 'left', 'right', 'enter', 'esc',
'backspace', 'tab'. Raw keys and styles come from lib.text.
"""
import argparse
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, List, Optional

from lib import text

KEY_NAMES = {"\x1b[A": "up", "\x1b[B": "down", "\x1b[C": "right", "\x1b[D": "left",
             "\x1bOA": "up", "\x1bOB": "down", "\x1bOC": "right", "\x1bOD": "left",
             "\r": "enter", "\n": "enter", "\x1b": "esc", "\x7f": "backspace", "\x08": "backspace",
             "\t": "tab"}
QUIT_KEYS = ("", "\x03", "\x04")                  # end of input, Ctrl-C, Ctrl-D


def key_name(raw: str) -> str:
    return KEY_NAMES.get(raw, raw)


def run(render: Callable[[int, int], str], handle: Callable[[str], bool]) -> int:
    """Draws, reads a key, handles it, until handle() returns False or input ends."""
    interactive = sys.stdin.isatty()
    if interactive:
        sys.stdout.write("\x1b[?1049h\x1b[?25l")        # the alternate screen, cursor hidden
    try:
        while True:
            columns, rows = text.terminal_size()
            if interactive:
                text.clear()
            sys.stdout.write(render(columns, rows))
            sys.stdout.flush()
            raw = text.read_key()
            if raw in QUIT_KEYS or not handle(key_name(raw)):
                return 0
    finally:
        if interactive:
            sys.stdout.write("\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()


def edit_text(text: str, suffix: str = ".txt") -> Optional[str]:
    """
    Opens the text in the user's editor ($VISUAL, $EDITOR, or nano) on the whole terminal and
    returns what was saved; None if the editor couldn't run or failed. The tool's screen
    comes back afterwards.
    """
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano"
    handle, path = tempfile.mkstemp(suffix=suffix, text=True)
    interactive = sys.stdout.isatty()
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            f.write(text)
        if interactive:
            sys.stdout.write("\x1b[?25h\x1b[?1049l")             # leave the tool's screen
            sys.stdout.flush()
        try:
            code = subprocess.call(shlex.split(editor) + [path])
        except OSError:
            return None
        return Path(path).read_text(encoding="utf-8") if code == 0 else None
    finally:
        os.unlink(path)
        if interactive:
            sys.stdout.write("\x1b[?1049h\x1b[?25l")
            sys.stdout.flush()


def run_tool(tool_class, argv: List[str]) -> int:
    """Runs one tool on its own: python3 -m tools.<name> [pack] [--no-colour]."""
    from tools.lib import screen
    from tools.lib.packfiles import PackFiles
    parser = argparse.ArgumentParser(description=tool_class.about)
    parser.add_argument("pack", nargs="?", default="packs/test", help="pack folder")
    parser.add_argument("--no-colour", action="store_true", help="plain text")
    args = parser.parse_args(argv)
    tool = tool_class(PackFiles(Path(args.pack)), screen.look(not args.no_colour))
    return run(tool.render, tool.handle)
