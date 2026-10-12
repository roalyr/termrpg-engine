"""
Drawing the game: picks the screen (world, encounter or the after-action screen) and
lays it out from the UI pack. A pure function: the same state and UI pack always draw
the same frame. The look, layout and the UI's words come from the UI pack; the game's
own words come from the content pack.
"""
from typing import Optional

from engine.content import Content
from engine.state import GameState
from tui.layout import draw_screen, scroll_limit
from lib.text import Style
from lib.ui import UI, default_ui
from tui.widgets import Frame, card_shown


def render(content: Content, state: GameState, columns: int, rows: int = 60,
           panel: Optional[str] = None, colour: bool = True, selected: Optional[int] = None,
           page: int = 0, ui: Optional[UI] = None, scroll: int = 0, screen: Optional[str] = None,
           log: tuple = (), cursor: Optional[tuple] = None) -> str:
    """Draws the screen; 'screen' picks a full screen of the world (such as 'gear'), 'log' is a conversation's
    history, 'cursor' the map's cursor."""
    frame = _frame(content, state, panel, colour, selected, page, ui, scroll, screen, log, cursor)
    if not _fits(frame, columns, rows):
        size = frame.size
        return frame.ui.word("terminal_too_small", columns=size["min_columns"], rows=size["min_rows"]) + "\n"
    return draw_screen(frame, frame.ui.screens[frame.screen], columns, rows)


def max_scroll(content: Content, state: GameState, columns: int, rows: int, panel: Optional[str] = None,
               selected: Optional[int] = None, page: int = 0, ui: Optional[UI] = None,
               screen: Optional[str] = None, log: tuple = (), cursor: Optional[tuple] = None) -> int:
    """How far the open sub-window can scroll at this terminal size (0 when it all fits)."""
    frame = _frame(content, state, panel, False, selected, page, ui, 0, screen, log, cursor)
    if not _fits(frame, columns, rows):
        return 0
    return scroll_limit(frame, frame.ui.screens[frame.screen], columns, rows)


def render_shell(content: Content, ui: UI, shell, data, columns: int, rows: int, colour: bool = True) -> str:
    """The start, slots or help screen (tui.shell), before a game is loaded: there's no game state."""
    frame = Frame(content=content, state=None, ui=ui, style=Style(colour, ui.tokens["styles"], content.palette), screen=shell.screen,
                  selected=shell.selected, scroll=shell.scroll, shell=data)
    if not _fits(frame, columns, rows):
        return ui.word("terminal_too_small", columns=frame.size["min_columns"], rows=frame.size["min_rows"]) + "\n"
    return draw_screen(frame, ui.screens[shell.screen], columns, rows)


def shell_scroll_limit(content: Content, ui: UI, shell, data, columns: int, rows: int) -> int:
    frame = Frame(content=content, state=None, ui=ui, style=Style(False, ui.tokens["styles"], content.palette), screen=shell.screen,
                  selected=shell.selected, scroll=0, shell=data)
    return scroll_limit(frame, ui.screens[shell.screen], columns, rows) if _fits(frame, columns, rows) else 0


def _fits(frame: Frame, columns: int, rows: int) -> bool:
    return columns >= frame.size["min_columns"] and rows >= frame.size["min_rows"]


def _frame(content: Content, state: GameState, panel: Optional[str], colour: bool, selected: Optional[int],
           page: int, ui: Optional[UI], scroll: int, wanted: Optional[str] = None, log: tuple = (),
           cursor: Optional[tuple] = None) -> Frame:
    ui = ui or default_ui()
    if wanted == "quit":
        screen = "quit"                                       # asked from anywhere, a fight too
    elif state.debrief is not None:
        screen = "debrief"
    elif state.encounter is not None:
        screen = "encounter"
    else:
        screen = wanted or "world"
    in_world = screen != "debrief"                            # fights have a target choice
    if screen == "world" and panel is None and card_shown(ui, content, state):
        panel = "card"                                        # an event's card, or a question
    return Frame(content=content, state=state, ui=ui, style=Style(colour, ui.tokens["styles"], content.palette), screen=screen,
                 panel=panel if in_world else None, selected=selected, page=page, scroll=scroll,
                 log=tuple(log) if screen == "talk" else (), cursor=cursor if screen == "map" else None)
