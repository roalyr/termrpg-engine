#!/usr/bin/env python3
import sys
from pathlib import Path
from typing import Optional, List

from core.presets import init_game_state, ensure_presets
from core.persistence import save_state, load_state
from core.actions import dispatch_action
from ui.render import render_frame
from ui.text_tools import check_terminal

DEFAULT_PRESET_DIR = Path("presets/default-1.0")
DEFAULT_SAVES_DIR = Path("saves")


def run_character_creation(preset_dir: Path) -> Path:
    """Runs the sequential 4-step character creation CLI flow per §7."""
    print("========================================")
    print(" HARD SCI-FI CLI RPG: CHARACTER GEN")
    print("========================================\n")

    # Step 1: Identifier
    print("[STEP 1: IDENTIFIER]")
    while True:
        try:
            name_input = input("Enter callsign or name:\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)
        if name_input:
            break
        print("Name cannot be empty. Please enter a callsign.")

    # Step 2: Personal Anchor
    print("\n[STEP 2: THE PERSONAL ANCHOR]")
    print("What did you keep in your pocket?")
    print("  1. A copper pipe fitting (clean threads).")
    print("  2. A stamped paper work-pass (expired).")
    print("  3. A pair of steel dice (pips worn flat).")
    anchor_choice = 1
    while True:
        try:
            choice = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)
        if choice in ("1", "2", "3"):
            anchor_choice = int(choice)
            break
        print("Select option 1, 2, or 3.")

    # Step 3: The Routine
    print("\n[STEP 3: THE ROUTINE]")
    print("What did you do for work?")
    print("  1. Pipe cleaning and seam scraping.")
    print("  2. Algae-bed tending and filter rinsing.")
    print("  3. Cargo handling and skid lashing.")
    routine_choice = 1
    while True:
        try:
            choice = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)
        if choice in ("1", "2", "3"):
            routine_choice = int(choice)
            break
        print("Select option 1, 2, or 3.")

    # Step 4: Confirmation
    anchor_names = {1: "copper fitting", 2: "stamped work-pass", 3: "steel dice"}
    routine_names = {1: "former scraper", 2: "former algae tender", 3: "former cargo handler"}
    print(f"\n[STEP 4: CONFIRMATION]")
    print(f"{name_input}. {routine_names[routine_choice]}, {anchor_names[anchor_choice]} in pocket.")
    print("Starting in: Deck 4 - Shared Bunkroom.")
    while True:
        try:
            confirm = input("Begin? [y/n]:\n> ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)
        if confirm in ("y", "yes", ""):
            break
        elif confirm in ("n", "no"):
            print("Restarting character creation...\n")
            return run_character_creation(preset_dir)

    initial_state = init_game_state(
        preset_dir,
        name_input,
        anchor_choice,
        routine_choice
    )
    save_dir = DEFAULT_SAVES_DIR / name_input
    save_state(initial_state, save_dir)
    return save_dir


def select_or_create_save(preset_dir: Path) -> Path:
    """Discovers existing saves or starts character creation."""
    DEFAULT_SAVES_DIR.mkdir(parents=True, exist_ok=True)
    existing_saves: List[Path] = [
        d for d in DEFAULT_SAVES_DIR.iterdir()
        if d.is_dir() and (d / "state.json").exists()
    ]

    if not existing_saves:
        return run_character_creation(preset_dir)

    print("========================================")
    print(" ACTIVE PROFILES FOUND")
    print("========================================")
    for idx, sdir in enumerate(existing_saves, 1):
        print(f"  {idx}. Resume profile: {sdir.name}")
    print(f"  {len(existing_saves) + 1}. Create new character profile")

    while True:
        try:
            choice = input("\nSelect profile number:\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            sys.exit(0)
        if choice.isdigit():
            val = int(choice)
            if 1 <= val <= len(existing_saves):
                return existing_saves[val - 1]
            elif val == len(existing_saves) + 1:
                return run_character_creation(preset_dir)
        print("Invalid selection.")


def main() -> None:
    """Main execution loop for Hard Sci-Fi Functional CLI RPG."""
    ensure_presets(DEFAULT_PRESET_DIR)

    # Check for CLI flags
    save_dir: Optional[Path] = None
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        candidate = DEFAULT_SAVES_DIR / sys.argv[1]
        if (candidate / "state.json").exists():
            save_dir = candidate

    if not save_dir:
        save_dir = select_or_create_save(DEFAULT_PRESET_DIR)

    state = load_state(save_dir)
    if not state:
        print("Failed to load session snapshot. Starting fresh.")
        save_dir = run_character_creation(DEFAULT_PRESET_DIR)
        state = load_state(save_dir)
        if not state:
            print("Fatal: Could not initialize game state.")
            sys.exit(1)

    # Main stream I/O game loop
    try:
        while state.is_running:
            term_w = check_terminal()
            output = render_frame(state, term_w)
            print(output, end="", flush=True)

            try:
                raw_input = input()
            except (KeyboardInterrupt, EOFError):
                print("\n[SIGNAL RECEIVED] Interrupt. Persisting state snapshot...")
                save_state(state, save_dir)
                print("Snapshot committed. Terminal closed.")
                sys.exit(0)

            prev_cycle = state.cycle
            next_state = dispatch_action(state, raw_input)

            # Deterministic auto-save after every tick-advancing action
            if next_state.cycle > prev_cycle or not next_state.is_running:
                save_state(next_state, save_dir)

            state = next_state

        # Loop exited cleanly
        save_state(state, save_dir)
        print("\nSession persisted to saves/" + save_dir.name + "/state.json. Terminal offline.")

    except Exception as e:
        # Fallback persistence on unexpected error
        print(f"\n[UNEXPECTED EXCEPTION] {e}. Attempting emergency save...")
        try:
            save_state(state, save_dir)
            print("Emergency snapshot saved.")
        except Exception as save_err:
            print(f"Could not persist emergency state: {save_err}")
        raise e


if __name__ == "__main__":
    main()
