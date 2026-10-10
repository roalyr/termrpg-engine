"""
A pack at a glance: its files and entry counts by kind, and what the checker says.
The smallest tool, and the template for the others: a class with render() and handle().

  python3 -m tools.overview packs/test

Keys: up/down (or w/s) scroll, r checks again, q quits.
"""
import argparse
import sys
from pathlib import Path

from tools.lib import term
from tools.lib.packfiles import PackFiles
from tui.text import pad, wrap


class Overview:
    def __init__(self, pack: PackFiles):
        self.pack = pack
        self.scroll = 0
        self.report = pack.check()

    def lines(self) -> list:
        m = self.pack.manifest
        out = [f"{m.get('name', self.pack.id)}  ({self.pack.id} {m.get('version', '?')})", ""]
        for kind, files in self.pack.kinds.items():
            count = sum(1 for _ in self.pack.entries(kind)) if kind != "vocab" else "-"
            out.append(f"  {kind:14} {count:>4}  {', '.join(files)}")
        errors, warnings = self.report.errors, self.report.warnings
        out += ["", f"Checker: {len(errors)} error(s), {len(warnings)} warning(s)"]
        out += [f"  error: {e}" for e in errors] + [f"  warning: {w}" for w in warnings]
        return out

    def render(self, columns: int, rows: int) -> str:
        body = [part for line in self.lines() for part in wrap(line, columns)]
        height = max(1, rows - 2)
        self.scroll = max(0, min(self.scroll, len(body) - height))
        shown = [pad(line, columns) for line in body[self.scroll:self.scroll + height]]
        return "\n".join(shown + ["", "w/s scroll  r check  q quit"]) + "\n"

    def handle(self, key: str) -> bool:
        if key in ("q", "esc"):
            return False
        if key in ("up", "w"):
            self.scroll = max(0, self.scroll - 1)
        elif key in ("down", "s"):
            self.scroll += 1
        elif key == "r":
            self.report = self.pack.check()
        return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="A pack at a glance.")
    parser.add_argument("pack", nargs="?", default="packs/test", help="pack folder")
    args = parser.parse_args(argv)
    view = Overview(PackFiles(Path(args.pack)))
    return term.run(view.render, view.handle)


if __name__ == "__main__":
    sys.exit(main())
