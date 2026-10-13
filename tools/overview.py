"""
A pack at a glance: its files and entry counts by kind, and what the checker says.
The smallest tool, and the template for the others.

  python3 -m tools.overview packs/test_scifi     on its own
  python3 editor.py                        from the editor's menu
"""
import sys

from lib import screen
from tools.lib.tool import run_tool
from tools.lib.packfiles import PackFiles


class Overview:
    name = "Overview"
    about = "The pack's files, how many entries of each kind, and what the checker says."

    def __init__(self, pack: PackFiles, look: screen.Look):
        self.pack, self.look = pack, look
        self.scroll = 0
        self.report = pack.check()

    def body(self, width: int) -> list:
        style = self.look.style
        lines = [""]
        for kind, files in self.pack.kinds.items():
            count = "" if kind == "vocab" else sum(1 for _ in self.pack.entries(kind))
            lines.append(f"{kind:14}{count:>4}  " + style.role(", ".join(files), "quiet"))
        lines.append("")
        for role, found in (("danger", self.report.errors), ("quiet", self.report.warnings)):
            for message in found:
                lines += [style.role(line, role) for line in screen.wrap(message, width)]
        return lines

    def verdict(self) -> list:
        """The checker's verdict, always in view; the messages themselves are in the body."""
        errors, warnings = self.report.errors, self.report.warnings
        words = f"{len(errors)} error(s), {len(warnings)} warning(s)"
        return [self.look.style.role("Checker: ", "heading") + self.look.style.role(words, "danger" if errors else "quiet")]

    def render(self, columns: int, rows: int) -> str:
        look, width = self.look, screen.inner_width(self.look, columns)
        manifest = self.pack.manifest
        bands = [screen.title(look, self.name, f"{manifest.get('name', self.pack.id)} {manifest.get('version', '')}", width),
                 self.verdict(),
                 self.body(width),
                 screen.hints(look, ["↑↓ scroll", "R check again", f"{look.key('back')} back"], width)]
        drawn = screen.draw(look, bands, columns, rows, flex=2, scroll=self.scroll)
        self.scroll = drawn.scroll
        return drawn.text

    def handle(self, key: str) -> bool:
        action = self.look.action(key)
        if action in ("back", "quit"):
            return False
        if action == "up":
            self.scroll = max(0, self.scroll - 1)
        elif action == "down":
            self.scroll += 1
        elif key.lower() == "r":
            self.report = self.pack.check()
        return True


if __name__ == "__main__":
    sys.exit(run_tool(Overview, sys.argv[1:]))
