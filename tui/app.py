"""
The terminal game: one key at a time, autosaving after every turn.

Keys come from the UI pack's bindings: moving, waiting, the fitting board, the
character sheet, closing, quitting and the board's next page. Number keys pick
numbered entries (a choice's options, board items, action tiles, targets); the letters
shown in menus act. Any key leaves the after-action screen.

When stdin isn't a terminal, keys are read from it one character at a time, so a
game can be scripted: python3 play.py < keys.txt
"""
import random
import sys
from pathlib import Path
from typing import NamedTuple, Optional

from engine import build, encounter, events, journal, save, turns, world
from engine.content import Content, PackError, load_pack
from engine.effects import choose_option
from engine.state import GameState, Message, new_game
from tui import render, shell, text, widgets
from tui.ui import ROOT_DIR, UI, UIPackError, default_ui, load_ui, ui_dir_for

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
    screen: Optional[str] = None     # a full screen of the world: 'fitting', 'character' or 'talk'; on the
                                     # fitting screen 'selected' is the pick and 'panel' its sub-window
    log: tuple = ()                  # a conversation's history: what you said and what followed
    back: Optional[object] = None    # on the quit question: the view to go back to


def _digit(key: str) -> Optional[int]:
    return int(key) if len(key) == 1 and key.isdigit() and key != "0" else None


def handle(content: Content, state: GameState, key: str, view: View = View(), ui: Optional[UI] = None):
    """One key: returns the new state (with what it said added to the journal), the view, and whether to quit."""
    ui = ui or default_ui()
    after, view, quit_now = _handle(content, state, key, view, ui)
    return journal.record(state, after), view, quit_now


def _handle(content: Content, state: GameState, key: str, view: View, ui: UI):
    action = FIXED_KEYS.get(key) or ui.action_of(key.lower())        # bindings are lower case
    if key in FIXED_KEYS:
        key = ui.bindings.get(action, "")
    key = key.lower()
    if view.screen == "quit":                     # Y quits to the start screen, N or close go back
        if key == "y":
            return state, view.back or View(), True
        if key == "n" or action == "close":
            return state, view.back or View(), False
        return state, view, False
    if action == "quit":
        return state, View(screen="quit", back=view), False
    if state.debrief is not None:                 # any key leaves the after-action screen
        return events.settle(content, state._replace(debrief=None)), View(), False
    if state.pending is not None:                 # a question, on its card: digits answer, up and down scroll
        if action in ("move_north", "move_south"):
            return state, _scroll(action, view), False
        if _digit(key):
            state = choose_option(content, state._replace(card=None), _digit(key) - 1)
            state = turns.advance(content, state, 0)
            view = view._replace(scroll=0)
        return events.settle(content, state), view, False
    if state.card is not None and state.encounter is None:
        if widgets.card_shown(ui, content, state):     # a card: up and down scroll, any other key continues
            if action in ("move_north", "move_south"):
                return state, _scroll(action, view), False
            return state._replace(card=None), view._replace(scroll=0), False
        state = state._replace(card=None)              # a short text was read in the log
    if state.encounter is not None:
        state, view = _fight(content, state, key, action, view)
        return events.settle(content, state), view, False
    if view.screen == "fitting":
        state, view = _fitting(content, state, key, action, view, ui)
    elif view.screen == "character":
        state, view = state, _character(action, view)
    elif view.screen == "talk":
        state, view = _talk(content, state, key, action, view, ui)
    else:
        state, view = _world(content, state, key, action, view, ui)
    return events.settle(content, state), view, False


def _fight(content: Content, state: GameState, key: str, action: Optional[str], view: View):
    """
    A digit picks a tile and shows its details; the same digit again uses it, another
    digit picks another, close lets go. An action with several possible targets then asks
    for one in the fighters column: a digit picks it, close goes back to the tile.
    """
    tiles = encounter.tiles(content, state)
    number = _digit(key)
    if view.panel == "target" and view.selected is not None:
        if action == "close":
            return state, view._replace(panel=None)
        options = encounter.targets(content, state, state.player, tiles[view.selected].action)
        if number and number <= len(options):
            return encounter.take_turn(content, state, tiles[view.selected].action, options[number - 1]), View()
        return state, view
    if action == "close":
        return state, View()
    if not number or number > len(tiles):
        return state, view
    if view.selected != number - 1:                           # pick it: its details show
        return state, View(selected=number - 1)
    tile = tiles[number - 1]                                  # the same number again: use it
    if not tile.available:
        return state, view
    if len(encounter.targets(content, state, state.player, tile.action)) > 1:
        return state, View(selected=number - 1, panel="target")
    return encounter.take_turn(content, state, tile.action), View()


def _world(content: Content, state: GameState, key: str, action: Optional[str], view: View, ui: UI):
    """
    While a sub-window is open it has the keys: up and down scroll it (the pack panel
    turns pages), left and right do nothing, and only its close key closes it.
    """
    if view.panel in SCROLLING:
        return state, _scrolling(action, view)
    if view.panel == "history":
        return state, _history(action, view)
    if action == "history" and view.panel is None:
        return state, View("history")
    if action == "fitting" and view.panel is None:
        return state, View(screen="fitting", selected=0)
    if action == "character" and view.panel is None:
        return state, View(screen="character")
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
    if current is not None and any(o.key == key and o.kind == "talk" and o.available for o in current.options):
        return world.act(content, state, key, ui.bound_keys), View(screen="talk")   # Talk opens the conversation
    return world.act(content, state, key, ui.bound_keys), View()


def _fitting(content: Content, state: GameState, key: str, action: Optional[str], view: View, ui: UI):
    """
    The fitting screen. Up and down move the pick, digits jump to an entry, the picked
    entry's letters act on it (fit, remove, repair, take apart, make), M lists its
    modifications, I opens its details, and close goes back a level.
    """
    pickable = widgets.picks(content, state)
    rows = build.fitting_rows(content, state)
    selected = max(0, min(view.selected or 0, len(pickable) - 1)) if pickable else 0
    slot = rows[pickable[selected]].slot if pickable else None
    if view.panel == "item":                                  # the details: scroll, or back to the list
        if action == "close":
            return state, view._replace(panel=None, scroll=0)
        if action in ("move_north", "move_south"):
            return state, _scrolling(action, view)
        return state, view
    if view.panel == "modify":                                # the modifications: a digit applies one
        if action == "close":
            return state, view._replace(panel=None)
        mods = [o for o in build.item_options(content, state, slot, ui.bound_keys, "fitting") if o.kind == "modify"]
        if slot is not None and _digit(key) and _digit(key) <= len(mods):
            after = build.item_act(content, state, slot, mods[_digit(key) - 1].key, ui.bound_keys, "fitting")
            return after, view._replace(panel=None, selected=_follow_pick(content, state, after, slot, selected))
        return state, view
    if slot is not None:
        options = build.item_options(content, state, slot, ui.bound_keys, "fitting")
        option = next((o for o in options if o.key == key and o.kind != "modify"), None)
        if option is not None:
            after = build.item_act(content, state, slot, key, ui.bound_keys, "fitting")
            return after, view._replace(selected=_follow_pick(content, state, after, slot, selected))
        if key == world.MENU_KEYS["inspect"]:
            return state, view._replace(panel="item", scroll=0)
        if key == build.MODIFY_KEY and any(o.kind == "modify" for o in options):
            return state, view._replace(panel="modify")
    if action == "close":
        return state, View()
    if action == "move_north":
        return state, view._replace(selected=max(0, selected - 1))
    if action == "move_south":
        return state, view._replace(selected=min(len(pickable) - 1, selected + 1) if pickable else 0)
    if _digit(key) and _digit(key) <= len(pickable):
        return state, view._replace(selected=_digit(key) - 1)
    return state, view


def _follow_pick(content: Content, before: GameState, after: GameState, slot, selected: int) -> int:
    """The pick after an action: the same item wherever it went (fitted, removed, taken), else the same place."""
    old = build.entry_at(content, before, slot)
    rows = build.fitting_rows(content, after)
    pickable = [i for i, row in enumerate(rows) if row.slot is not None]
    for number, index in enumerate(pickable):
        if old is not None and build.entry_at(content, after, rows[index].slot) == old:
            return number
    return max(0, min(selected, len(pickable) - 1))


HISTORY = 40   # conversation lines kept


def _talk(content: Content, state: GameState, key: str, action: Optional[str], view: View, ui: UI):
    """
    A conversation: a digit answers with one of the speaker's interactions (the last one
    leaves), up and down look back through what was said, close leaves. Anything that
    takes over (a fight, a question, the speaker out of reach) ends it.
    """
    current = world.menu(content, state, ui.bound_keys)
    answers = [o for o in current.options if o.kind == "interaction"] if current else []
    if action == "close" or current is None:
        return state, View()
    if action == "move_north":
        return state, view._replace(scroll=view.scroll + 1)          # back through the history
    if action == "move_south":
        return state, view._replace(scroll=max(0, view.scroll - 1))
    number = _digit(key)
    if not number or number > len(answers) + 1:
        return state, view
    if number == len(answers) + 1:
        return state, View()
    option = answers[number - 1]
    after = world.act(content, state, option.key, ui.bound_keys)
    log = (view.log + (Message("response", option_label(option, ui)),) + after.messages)[-HISTORY:]
    if after.encounter_request or after.encounter is not None or after.pending is not None \
            or world.menu(content, after, ui.bound_keys) is None:
        return after, View()
    return after, view._replace(log=log, scroll=0)


def option_label(option, ui: UI) -> str:
    return widgets.option_text(ui, option)


def _scroll(action: Optional[str], view: View) -> View:
    """Up and down on a sub-window that scrolls from the top."""
    if action == "move_north":
        return view._replace(scroll=max(0, view.scroll - 1))
    return view._replace(scroll=view.scroll + 1)                  # kept within the content when drawn


def _history(action: Optional[str], view: View) -> View:
    """The message history: up and down look back from the newest; close or its key leave it."""
    if action in ("close", "history"):
        return View()
    if action == "move_north":
        return view._replace(scroll=view.scroll + 1)
    if action == "move_south":
        return view._replace(scroll=max(0, view.scroll - 1))
    return view


def _character(action: Optional[str], view: View) -> View:
    """The character screen: up and down scroll it; close or its own key leave it."""
    if action in ("close", "character"):
        return View()
    if action == "move_north":
        return view._replace(scroll=max(0, view.scroll - 1))
    if action == "move_south":
        return view._replace(scroll=view.scroll + 1)              # kept within the content when drawn
    return view


# Sub-windows that scroll line by line, and the key that closes each besides 'close'.
SCROLLING = {"inspect": None, "item": "pack"}


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


def run(pack_dir: Path, save_path: Optional[Path] = None, seed: Optional[int] = None, fresh: bool = False,
        colour: bool = True, ui_dir: Optional[Path] = None, saves_dir: Optional[Path] = None) -> int:
    """
    The program: the start screen, then a game, then back to the start screen, until Quit.
    With 'save_path' it goes straight into that game first. The end of input (a script, or
    Ctrl-D) leaves at once.
    """
    try:
        content = load_pack(pack_dir)
        ui = load_ui(ui_dir or ui_dir_for(content.pack["ui"]))
    except (PackError, UIPackError) as error:
        print(error)
        return 1
    saves_dir = saves_dir or (save_path.parent if save_path else ROOT_DIR / "saves" / Path(pack_dir).name)
    if save_path is not None:
        outcome = _play(content, ui, save_path, seed, fresh, colour)
        if outcome != "menu":
            return 1 if outcome == "error" else 0
    while True:
        choice = _start(content, ui, saves_dir, colour)
        if choice in ("exit", "eof"):
            return 0
        _, path, new = choice
        if _play(content, ui, path, seed, new, colour) in ("eof", "error"):
            return 0


def _start(content: Content, ui: UI, saves_dir: Path, colour: bool):
    """The start, slots and help screens: returns ('play', path, fresh), 'exit' or 'eof'."""
    view = shell.Shell()
    interactive = sys.stdin.isatty()
    while True:
        slots = shell.read_slots(content, saves_dir, ui.tokens["size"]["save_slots"])
        data = shell.ShellData(shell.entries(slots), slots, view.mode)
        columns, rows = text.terminal_size()
        view = view._replace(scroll=min(view.scroll, render.shell_scroll_limit(content, ui, view, data, columns, rows)))
        if interactive:
            text.clear()
        sys.stdout.write(render.render_shell(content, ui, view, data, columns, rows, colour))
        sys.stdout.flush()
        key = text.read_key()
        if key in ("", "\x03", "\x04"):
            return "eof"
        action = FIXED_KEYS.get(key) or ui.action_of(key.lower())
        view, outcome = shell.handle(view, action, key, slots)
        if outcome is not None:
            return outcome


def _play(content: Content, ui: UI, save_path: Path, seed: Optional[int], fresh: bool, colour: bool) -> str:
    """One game in one slot, saved after every turn: returns 'menu' (quit to the start screen), 'eof' or 'error'."""
    if save_path.exists() and not fresh:
        try:
            state = save.load(content, save_path)
        except save.SaveError as error:
            print(f"{save_path}: {error}")
            return "error"
    else:
        state = new_game(content, seed if seed is not None else random.randrange(1, 2 ** 31))
        save.save(content, state, save_path)
    view = View()
    interactive = sys.stdin.isatty()
    outcome = "eof"
    while True:
        if interactive:
            text.clear()
        columns, rows = text.terminal_size()
        limit = render.max_scroll(content, state, columns, rows, view.panel, view.selected, view.page, ui,
                                  view.screen, view.log)
        view = view._replace(scroll=min(view.scroll, limit))
        sys.stdout.write(render.render(content, state, columns, rows, view.panel, colour, view.selected,
                                       view.page, ui, view.scroll, view.screen, view.log))
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
            outcome = "menu"
            break
    save.save(content, state, save_path)
    print(content.message("game_saved"))
    return outcome
