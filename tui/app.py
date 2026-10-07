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
# Keys every terminal sends the same way, whatever the UI pack binds: arrows move, Esc closes.
FIXED_KEYS = {"\x1b[A": "move_north", "\x1b[B": "move_south", "\x1b[C": "move_east", "\x1b[D": "move_west",
              "\x1bOA": "move_north", "\x1bOB": "move_south", "\x1bOC": "move_east", "\x1bOD": "move_west",
              "\x1b": "close"}


class View(NamedTuple):
    """What the screen shows besides the world: an open sub-window and a picked entry."""
    panel: Optional[str] = None      # 'pack', 'character' or 'inspect'
    selected: Optional[int] = None   # a board item (index into build.pack_slots()), or in an
                                     # encounter the action tile waiting for a target
    page: int = 0                    # the board's page
    scroll: int = 0                  # how far a scrolling sub-window (inspect, character) is scrolled


def _digit(key: str) -> Optional[int]:
    return int(key) if len(key) == 1 and key.isdigit() and key != "0" else None


def handle(content: Content, state: GameState, key: str, view: View = View(), ui: Optional[UI] = None):
    """One key: returns the new state, the view, and whether to quit."""
    ui = ui or default_ui()
    action = FIXED_KEYS.get(key) or ui.action_of(key.lower())        # bindings are lower case
    if key in FIXED_KEYS:
        key = ui.bindings.get(action, "")
    key = key.lower()
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
    """
    While a sub-window is open it has the keys: up and down scroll it (the pack panel
    turns pages), left and right do nothing, and only its close key closes it.
    """
    if view.panel in SCROLLING:
        return state, _scrolling(action, view)
    if action in ("pack", "character"):
        return state, View() if view.panel == action else View(action)
    if action == "close":
        return state._replace(focus=None, messages=()), View()
    if view.panel == "pack":
        slots = build.pack_slots(content, state)
        page_size = ui.tokens["size"]["page_size"]
        pages = max(1, -(-len(slots) // page_size))
        if action in ("next_page", "move_south", "move_north"):
            step = -1 if action == "move_north" else 1
            return state, View("pack", None, (view.page + step) % pages)
        if action in MOVES:
            return state, view
        if view.selected is not None and view.selected < len(slots) and key == world.MENU_KEYS["inspect"]:
            return state, View("item", view.selected, view.page)       # the picked item's details
        if _digit(key) and _digit(key) <= page_size:
            index = (view.page % pages) * page_size + _digit(key) - 1
            return state, view._replace(selected=index if index < len(slots) else None)
        if view.selected is not None and view.selected < len(slots):
            slot = slots[view.selected]
            option = next((o for o in build.item_options(content, state, slot, ui.bound_keys) if o.key == key), None)
            after = build.item_act(content, state, slot, key, ui.bound_keys)
            if option is None or after is state:
                return state, view
            selected = build.follow(content, state, after, slot, option.kind)   # numbers shift; the pick doesn't
            page = selected // page_size if selected is not None else view.page
            return after, View("pack", selected, page)
        return state, view
    if action in MOVES:
        return world.move(content, state, MOVES[action]), View()
    if action == "wait":
        return world.wait(content, state), View()
    current = world.menu(content, state, ui.bound_keys)
    if current is not None and any(o.key == key and o.kind == "inspect" for o in current.options):
        return state, View("inspect")                      # Inspect opens the panel; it takes no time
    return world.act(content, state, key, ui.bound_keys), View()


# Sub-windows that scroll line by line, and the key that closes each besides 'close'.
SCROLLING = {"inspect": None, "character": "character", "item": "pack"}


def _scrolling(action: Optional[str], view: View) -> View:
    if action == "move_north":
        return view._replace(scroll=max(0, view.scroll - 1))
    if action == "move_south":
        return view._replace(scroll=view.scroll + 1)          # kept within the content when drawn
    if action == "close" and view.panel == "item":             # back to the pack, the item still picked
        return View("pack", view.selected, view.page)
    if action == "close" or (action is not None and action == SCROLLING[view.panel]):
        return View()
    return view


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
        limit = render.max_scroll(content, state, columns, rows, view.panel, view.selected, view.page, ui)
        view = view._replace(scroll=min(view.scroll, limit))
        sys.stdout.write(render.render(content, state, columns, rows, view.panel, colour, view.selected,
                                       view.page, ui, view.scroll))
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
