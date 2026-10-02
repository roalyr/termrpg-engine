"""
The terminal game: one key at a time, autosaving after every turn.

Keys: WASD move; the letters shown in the menu act; X closes the menu; '.' waits;
1-4 answer a choice; P and C toggle the pack and character panels; Q saves and
quits. In the pack panel, 1-9 pick an item and the letters shown act on it.

When stdin isn't a terminal, keys are read from it one character at a time, so a
game can be scripted: python3 play.py < keys.txt
"""
import sys
from pathlib import Path
from typing import NamedTuple, Optional

from engine import build, save, turns, world
from engine.content import Content, PackError, load_pack
from engine.effects import choose_option
from engine.state import GameState, new_game
from tui import render, text


class View(NamedTuple):
    """What the screen shows besides the world: an open panel and the picked pack item."""
    panel: Optional[str] = None      # 'pack' or 'character'
    selected: Optional[int] = None   # index into build.pack_slots()


def handle(content: Content, state: GameState, key: str, view: View = View()):
    """One key: returns the new state, the view, and whether to quit."""
    key = key.lower()
    if key == "q":
        return state, view, True
    if state.pending is not None:
        if key in "1234" and key:
            state = choose_option(content, state, int(key) - 1)
            state = turns.advance(content, state, 0)
        return state, view, False
    if key in ("p", "c"):
        wanted = "pack" if key == "p" else "character"
        return state, View() if view.panel == wanted else View(wanted), False
    if key in world.DIRECTIONS:
        return world.move(content, state, key), View(), False
    if key == "x":
        return state._replace(focus=None, messages=()), View(), False
    if view.panel == "pack":
        slots = build.pack_slots(content, state)
        if key.isdigit() and key != "0":
            index = int(key) - 1
            return state, view._replace(selected=index if index < len(slots) else None), False
        if view.selected is not None and view.selected < len(slots):
            state = build.item_act(content, state, slots[view.selected], key)
            return state, view._replace(selected=None), False
        return state, view, False
    if key == ".":
        return world.wait(content, state), View(), False
    return world.act(content, state, key), View(), False


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
    view = View()
    interactive = sys.stdin.isatty()
    while True:
        if interactive:
            text.clear()
        columns, rows = text.terminal_size()
        sys.stdout.write(render.render(content, state, columns, rows, view.panel, colour, view.selected))
        sys.stdout.flush()
        key = text.read_key()
        if key in ("", "\x03", "\x04"):
            break
        if key in ("\n", "\r", " "):
            continue
        before = state.turn
        state, view, quit_now = handle(content, state, key, view)
        if state.turn != before:
            save.save(content, state, save_path)
        if quit_now:
            break
    save.save(content, state, save_path)
    print(content.message("game_saved"))
    return 0
