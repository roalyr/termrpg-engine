"""
What every tool shares: running one on its own, and saving without losing anyone's work.
"""
import argparse
from pathlib import Path
from typing import Callable, List

from lib import forms, screen, term
from tools.lib.packfiles import PackFiles


def run_tool(tool_class, argv: List[str]) -> int:
    """Runs one tool on its own: python3 -m tools.<name> [pack] [--no-colour]."""
    parser = argparse.ArgumentParser(description=tool_class.about)
    parser.add_argument("pack", nargs="?", default="packs/test_scifi", help="pack folder")
    parser.add_argument("--no-colour", action="store_true", help="plain text")
    args = parser.parse_args(argv)
    pack = PackFiles(Path(args.pack))
    tool = tool_class(pack, screen.look(not args.no_colour, palette=pack.palette))
    return term.run(tool.render, tool.handle)


def save_safely(tool, write: Callable[[], None]) -> None:
    """
    Saves with 'write', unless a file about to be written was also changed on disk by
    something else since the tool read it: then it asks first, so nobody's work is lost
    without a word. Not saving keeps the tool's changes open.
    """
    clash = tool.pack.changed_elsewhere()
    if not clash:
        return write()

    def done(answer):
        if answer == "overwrite":
            write()
        else:
            tool.say("Not saved. To keep the other changes, leave without saving and open the pack again.", "danger")
    names = ", ".join(clash)
    tool.ask(forms.Question(tool.look, f"{names} changed on disk since you opened it. Saving overwrites those changes.",
                            [("o", "overwrite", "overwrite"), ("n", "don't save", "keep")]), done)
