#!/usr/bin/env python3
"""
Play a content pack in the terminal (the new engine).

  python3 play.py                       the start screen of the test pack (saves in saves/test_scifi/)
  python3 play.py --pack packs/game     another pack
  python3 play.py --slot two --new      straight into a fresh game in a save named 'two'
  python3 play.py --new                 straight into a fresh game in slot 1
  python3 play.py --ui packs/ui/mine    another UI pack (default: the one the game pack names)
"""
import argparse
import sys
from pathlib import Path

from tui.app import run

ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Play a content pack.")
    parser.add_argument("--pack", default=str(ROOT / "packs" / "test_scifi"), help="pack folder")
    parser.add_argument("--slot", help="go straight into this save (a name, or slot1, slot2...)")
    parser.add_argument("--seed", type=int, help="seed for new games (default: a random one)")
    parser.add_argument("--new", action="store_true", help="go straight into a new game (in --slot, or slot1)")
    parser.add_argument("--no-colour", action="store_true", help="plain text")
    parser.add_argument("--ui", help="UI pack folder (default: the UI pack the game pack names)")
    args = parser.parse_args()
    pack = Path(args.pack)
    saves = ROOT / "saves" / pack.name
    save_path = saves / f"{args.slot or 'slot1'}.json" if (args.slot or args.new) else None
    return run(pack, save_path, args.seed, args.new, colour=not args.no_colour,
               ui_dir=Path(args.ui) if args.ui else None, saves_dir=saves)


if __name__ == "__main__":
    sys.exit(main())
