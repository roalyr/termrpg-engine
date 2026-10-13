"""
What every tool shares: the Tool base class (asking with a form, a message line,
saving and leaving), running one on its own, and saving without losing anyone's work.
"""
import argparse
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from lib import forms, screen, term
from tools.lib.packfiles import PackFiles


class Tool:
    """
    The plumbing of an editor built from (PackFiles, Look): 'form' is the open list,
    field or question and 'after' what its answer leads to; 'message' is the line the
    tool says; 'closed' ends it. Saving runs the checker and says its verdict; leaving
    with changes asks to save.
    """

    name = ""
    about = ""
    pack: PackFiles
    look: screen.Look
    form = None
    after: Optional[Callable] = None
    message: Tuple[str, str] = ("", "quiet")
    closed = False

    def ask(self, form, after: Callable) -> None:
        self.form, self.after = form, after

    def say(self, text: str, role: str = "quiet") -> None:
        self.message = (text, role)

    def close(self) -> None:
        self.closed = True

    def right(self) -> str:
        """The title band's right side: the pack's name, '*' while there are unsaved changes."""
        return self.pack.manifest.get("name", self.pack.id) + (" *" if self.pack.dirty else "")

    def form_screen(self, columns: int, rows: int, heading: Callable[[], str]) -> str:
        """The screen while a form is open: titled by the form, or else by heading() (only worked out then)."""
        title = getattr(self.form, "title", "") or heading()
        return screen.form_screen(self.look, self.form, title, self.right(), columns, rows)

    def saved(self, report) -> None:
        """Called with the checker's report after each save; a tool that shows problems keeps it."""

    def save(self, then: Optional[Callable[[str], None]] = None) -> None:
        """Saves (asking first if a file changed on disk meanwhile), then says the checker's verdict, or hands it to 'then'."""
        def write():
            written = self.pack.save()
            report = self.pack.check()
            self.saved(report)
            words = (f"Saved {len(written)} file(s). Checker: {len(report.errors)} error(s), "
                     f"{len(report.warnings)} warning(s).") + (" " + report.errors[0] if report.errors else "")
            if then:
                then(words)
            else:
                self.say(words, "danger" if report.errors else "quiet")
        save_safely(self, write)

    def leave(self) -> bool:
        """Closes, asking first to save or discard changes; True while it's asking."""
        if not self.pack.dirty:
            self.close()
            return False

        def done(answer):
            if answer == "save":
                self.save(then=lambda words: self.close())
            else:
                self.pack.reload()
                self.close()
        self.ask(forms.Question(self.look, "Save your changes?", [("y", "save", "save"), ("n", "discard", "discard")]),
                 done)
        return True


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
