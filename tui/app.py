"""
The terminal game: one key at a time, autosaving after every turn.

Keys come from the UI pack's bindings: moving, waiting, the fitting board, the
character sheet, closing, quitting and the board's next page. Number keys pick
numbered entries (a choice's options, board items, action tiles, targets); the letters
shown in menus act. Any key leaves the after-action screen.

When stdin isn't a terminal, keys are read from it one character at a time, so a
game can be scripted: python3 play.py < keys.txt
"""
import sys
from pathlib import Path
from typing import NamedTuple, Optional

from engine import build, encounter, events, save, turns, world
from engine.content import Content, PackError, load_pack
from engine.effects import choose_option
from engine.state import GameState, new_game
from tui import render, text
from tui.ui import UI, UIPackError, default_ui, load_ui, ui_dir_for

# The engine's step directions, by input action.
MOVES = {"move_north": "w", "move_west": "a", "move_south": "s", "move_east": "d"}


class View(NamedTuple):
    """What the screen shows besides the world: an open panel and a picked entry."""
    panel: Optional[str] = None      # 'pack' or 'character'
    selected: Optional[int] = None   # a board item (index into build.pack_slots()), or in an
                                     # encounter the action tile waiting for a target
    page: int = 0                    # the board's page


def _digit(key: str) -> Optional[int]:
    return int(key) if len(key) == 1 and key.isdigit() and key != "0" else None


def handle(content: Content, state: GameState, key: str, view: View = View(), ui: Optional[UI] = None):
    """One key: returns the new state, the view, and whether to quit."""
    ui = ui or default_ui()
    key = key.lower()
    action = ui.action_of(key)
    if action == "quit":
        return state, view, True
    if state.debrief is not None:                 # any key leaves the after-action screen
        return events.settle(content, state._replace(debrief=None)), View(), False
    if state.pending is not None:
        if _digit(key):
            state = choose_option(content, state, _digit(key) - 1)
            state = turns.advance(content, state, 0)
        return events.settle(content, state), view, False
    if state.encounter is not None:
        state, view = _fight(content, state, key, action, view)
        return events.settle(content, state), view, False
    state, view = _world(content, state, key, action, view, ui)
    return events.settle(content, state), view, False


def _fight(content: Content, state: GameState, key: str, action: Optional[str], view: View):
    """A digit picks a tile; when it needs a target, a second digit picks one."""
    tiles = encounter.tiles(content, state)
    if view.selected is not None:
        if action == "close":
            return state, View()
        options = encounter.targets(content, state, state.player, tiles[view.selected].action)
        if _digit(key) and _digit(key) <= len(options):
            return encounter.take_turn(content, state, tiles[view.selected].action, options[_digit(key) - 1]), View()
        return state, view
    if not _digit(key) or _digit(key) > len(tiles):
        return state, view
    tile = tiles[_digit(key) - 1]
    if tile.available and len(encounter.targets(content, state, state.player, tile.action)) > 1:
        return state, View(selected=_digit(key) - 1)
    return encounter.take_turn(content, state, tile.action), View()


def _world(content: Content, state: GameState, key: str, action: Optional[str], view: View, ui: UI):
    if action in ("pack", "character"):
        return state, View() if view.panel == action else View(action)
    if action in MOVES:
        return world.move(content, state, MOVES[action]), View()
    if action == "close":
        return state._replace(focus=None, messages=()), View()
    if view.panel == "pack":
        slots = build.pack_slots(content, state)
        page_size = ui.tokens["size"]["page_size"]
        pages = max(1, -(-len(slots) // page_size))
        if action == "next_page":
            return state, View("pack", None, (view.page + 1) % pages)
        if _digit(key) and _digit(key) <= page_size:
            index = (view.page % pages) * page_size + _digit(key) - 1
            return state, view._replace(selected=index if index < len(slots) else None)
        if view.selected is not None and view.selected < len(slots):
            state = build.item_act(content, state, slots[view.selected], key, ui.bound_keys)
            return state, view._replace(selected=None)
        return state, view
    if action == "wait":
        return world.wait(content, state), View()
    return world.act(content, state, key, ui.bound_keys), View()


def run(pack_dir: Path, save_path: Path, seed: int, fresh: bool, colour: bool = True,
        ui_dir: Optional[Path] = None) -> int:
    try:
        content = load_pack(pack_dir)
        ui = load_ui(ui_dir or ui_dir_for(content.pack["ui"]))
    except (PackError, UIPackError) as error:
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
        sys.stdout.write(render.render(content, state, columns, rows, view.panel, colour, view.selected,
                                       view.page, ui))
        sys.stdout.flush()
        key = text.read_key()
        if key in ("", "\x03", "\x04"):
            break
        if key in ("\n", "\r", " "):
            continue
        before = state.turn
        state, view, quit_now = handle(content, state, key, view, ui)
        if state.turn != before:
            save.save(content, state, save_path)
        if quit_now:
            break
    save.save(content, state, save_path)
    print(content.message("game_saved"))
    return 0
