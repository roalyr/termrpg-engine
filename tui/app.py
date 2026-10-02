"""
The terminal game: one key at a time, autosaving after every turn.

Keys: WASD move; the letters shown in the menu act; X closes the menu; '.' waits;
1-4 answer a choice; P and C toggle the pack and character panels; Q saves and
quits. When stdin isn't a terminal, keys are read from it one character at a time,
so a game can be scripted: python3 play.py < keys.txt
"""
import sys
from pathlib import Path
from typing import Optional

from engine import save, turns, world
from engine.content import Content, PackError, load_pack
from engine.effects import choose_option
from engine.state import GameState, Message, new_game
from tui import render, text


def handle(content: Content, state: GameState, key: str, panel: Optional[str]):
    """One key: returns the new state, the panel to show, and whether to quit."""
    key = key.lower()
    if key == "q":
        return state, panel, True
    if state.pending is not None:
        if key in "1234" and key:
            state = choose_option(content, state, int(key) - 1)
            state = turns.advance(content, state, 0)
        return state, panel, False
    if key in ("p", "c"):
        wanted = "pack" if key == "p" else "character"
        return state, None if panel == wanted else wanted, False
    if key in world.DIRECTIONS:
        return world.move(content, state, key), None, False
    if key == "x":
        return state._replace(focus=None, messages=()), None, False
    if key == ".":
        return world.wait(content, state), None, False
    return world.act(content, state, key), None, False


def run(pack_dir: Path, save_path: Path, seed: int, fresh: bool, colour: bool = True) -> int:
    try:
        content = load_pack(pack_dir)
    except PackError as error:
        print(error)
        return 1
    if save_path.exists() and not fresh:
        try:
            state = save.load(content, save_path)
        except save.SaveError as error:
            print(f"{save_path}: {error}")
            return 1
    else:
        state = new_game(content, seed)
    panel = None
    interactive = sys.stdin.isatty()
    while True:
        if interactive:
            text.clear()
        columns, rows = text.terminal_size()
        sys.stdout.write(render.render(content, state, columns, rows, panel, colour))
        sys.stdout.flush()
        key = text.read_key()
        if key in ("", "\x03", "\x04"):
            break
        if key in ("\n", "\r", " "):
            continue
        before = state.turn
        state, panel, quit_now = handle(content, state, key, panel)
        if state.turn != before:
            save.save(content, state, save_path)
        if quit_now:
            break
    save.save(content, state, save_path)
    print(content.message("game_saved"))
    return 0
