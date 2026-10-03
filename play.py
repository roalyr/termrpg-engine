#!/usr/bin/env python3
"""
Play a content pack in the terminal (the new engine).

  python3 play.py                       the test pack, saved in saves/test/default.json
  python3 play.py --pack packs/game     another pack
  python3 play.py --slot two --new      a fresh game in another save slot
  python3 play.py --ui packs/ui/mine    another UI pack (default: the one the game pack names)
"""
import argparse
import sys
from pathlib import Path

from tui.app import run

ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Play a content pack.")
    parser.add_argument("--pack", default=str(ROOT / "packs" / "test"), help="pack folder")
    parser.add_argument("--slot", default="default", help="save slot name")
    parser.add_argument("--seed", type=int, default=1, help="seed for a new game")
    parser.add_argument("--new", action="store_true", help="start a new game even if a save exists")
    parser.add_argument("--no-colour", action="store_true", help="plain text")
    parser.add_argument("--ui", help="UI pack folder (default: the UI pack the game pack names)")
    args = parser.parse_args()
    pack = Path(args.pack)
    save_path = ROOT / "saves" / pack.name / f"{args.slot}.json"
    return run(pack, save_path, args.seed, args.new, colour=not args.no_colour,
               ui_dir=Path(args.ui) if args.ui else None)


if __name__ == "__main__":
    sys.exit(main())
