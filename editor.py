#!/usr/bin/env python3
"""
The pack editor: one menu for every tool, laid out like the game's start screen.

  python3 editor.py                       pick a pack (or open the only one)
  python3 editor.py --pack packs/test_scifi     open this pack
  python3 editor.py --no-colour           plain text

Tools live in tools/ (see tools/README.md); each also runs on its own.
"""
import argparse
import sys
from pathlib import Path
from typing import List, Optional

from tools import tools
from lib import term
from lib import screen
from tools.lib.packfiles import PackFiles

ROOT = Path(__file__).resolve().parent


def find_packs(packs_dir: Path = ROOT / "packs") -> List[Path]:
    """Game packs: folders in packs/ with a pack.json."""
    return sorted(p.parent for p in packs_dir.glob("*/pack.json"))


class Editor:
    """The menu ('menu'), the pack list ('packs'), or a tool running in its place."""

    def __init__(self, look: screen.Look, packs: List[Path], pack: Optional[Path] = None):
        self.look, self.packs = look, packs
        self.pack: Optional[PackFiles] = None
        self.tool = None
        self.selected = 0
        self.screen = "packs"
        if pack is not None or len(packs) == 1:
            self.open(pack or packs[0])

    def open(self, folder: Path) -> None:
        self.pack, self.screen, self.selected = PackFiles(folder), "menu", 0
        self.look.style.palette = self.pack.palette          # the tools draw in this pack's colours

    def entries(self) -> list:
        """(label, about, what it does) for each menu entry."""
        found = [(t.name, t.about, t) for t in tools()]
        if len(self.packs) > 1:
            found.append(("Open another pack", "Choose another game pack from packs/.", "packs"))
        return found + [("Quit", "", "quit")]

    def pack_entries(self) -> list:
        found = []
        for folder in self.packs:
            manifest = PackFiles(folder).manifest
            found.append((manifest.get("name", folder.name), manifest.get("description", ""), folder))
        return found

    def render(self, columns: int, rows: int) -> str:
        if self.tool is not None:
            return self.tool.render(columns, rows)
        look, width = self.look, screen.inner_width(self.look, columns)
        if self.screen == "menu":
            m = self.pack.manifest
            top = screen.title(look, "Editor", f"{m.get('name', self.pack.id)} {m.get('version', '')}", width)
            listed = self.entries()
        else:
            top = screen.title(look, "Open a pack", "", width)
            listed = self.pack_entries()
        lines, focus = screen.menu(look, [label for label, _, _ in listed], self.selected)
        keys = ["↑↓ pick", f"1-{len(listed)} choose"]
        if self.screen == "packs" and self.pack is not None:
            keys.append(f"{look.key('back')} back")
        bands = [top, lines, screen.quiet(look, listed[self.selected][1], width), screen.hints(look, keys, width)]
        return screen.draw(look, [b for b in bands if b], columns, rows, flex=1, focus=focus).text

    def handle(self, key: str) -> bool:
        if self.tool is not None:
            if not self.tool.handle(key):
                self.tool = None
            return True
        action = self.look.action(key)
        listed = self.entries() if self.screen == "menu" else self.pack_entries()
        if action == "up":
            self.selected = max(0, self.selected - 1)
        elif action == "down":
            self.selected = min(len(listed) - 1, self.selected + 1)
        elif action in ("back", "quit"):
            if self.screen == "packs" and self.pack is not None:
                self.screen, self.selected = "menu", 0
                return True
            return False
        elif action == "enter" or (key.isdigit() and 0 < int(key) <= len(listed)):
            pick = self.selected if action == "enter" else int(key) - 1
            self.selected = pick
            return self.choose(listed[pick][2])
        return True

    def choose(self, what) -> bool:
        if what == "quit":
            return False
        if what == "packs":
            self.screen, self.selected = "packs", 0
        elif isinstance(what, Path):
            self.open(what)
        else:
            self.tool = what(self.pack, self.look)
        return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="The pack editor.")
    parser.add_argument("--pack", help="pack folder (default: pick one)")
    parser.add_argument("--no-colour", action="store_true", help="plain text")
    args = parser.parse_args(argv)
    packs = find_packs()
    if not packs and not args.pack:
        print("No game packs in packs/.")
        return 1
    editor = Editor(screen.look(not args.no_colour), packs, Path(args.pack) if args.pack else None)
    return term.run(editor.render, editor.handle)


if __name__ == "__main__":
    sys.exit(main())
