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
from tui.text import Style
from tui.ui import UI, default_ui
from tui.widgets import Frame, card_shown


def render(content: Content, state: GameState, columns: int, rows: int = 60,
           panel: Optional[str] = None, colour: bool = True, selected: Optional[int] = None,
           page: int = 0, ui: Optional[UI] = None, scroll: int = 0, screen: Optional[str] = None,
           log: tuple = ()) -> str:
    """Draws the screen; 'screen' picks a full screen of the world (such as 'fitting'), 'log' is a conversation's history."""
    frame = _frame(content, state, panel, colour, selected, page, ui, scroll, screen, log)
    if not _fits(frame, columns, rows):
        size = frame.size
        return frame.ui.word("terminal_too_small", columns=size["min_columns"], rows=size["min_rows"]) + "\n"
    return draw_screen(frame, frame.ui.screens[frame.screen], columns, rows)


def max_scroll(content: Content, state: GameState, columns: int, rows: int, panel: Optional[str] = None,
               selected: Optional[int] = None, page: int = 0, ui: Optional[UI] = None,
               screen: Optional[str] = None, log: tuple = ()) -> int:
    """How far the open sub-window can scroll at this terminal size (0 when it all fits)."""
    frame = _frame(content, state, panel, False, selected, page, ui, 0, screen, log)
    if not _fits(frame, columns, rows):
        return 0
    return scroll_limit(frame, frame.ui.screens[frame.screen], columns, rows)


def _fits(frame: Frame, columns: int, rows: int) -> bool:
    return columns >= frame.size["min_columns"] and rows >= frame.size["min_rows"]


def _frame(content: Content, state: GameState, panel: Optional[str], colour: bool, selected: Optional[int],
           page: int, ui: Optional[UI], scroll: int, wanted: Optional[str] = None, log: tuple = ()) -> Frame:
    ui = ui or default_ui()
    if state.debrief is not None:
        screen = "debrief"
    elif state.encounter is not None:
        screen = "encounter"
    else:
        screen = wanted or "world"
    in_world = screen != "debrief"                            # fights have a target choice
    if screen == "world" and panel is None and card_shown(ui, content, state):
        panel = "card"                                        # an event's card, or a question
    return Frame(content=content, state=state, ui=ui, style=Style(colour, ui.tokens["styles"]), screen=screen,
                 panel=panel if in_world else None, selected=selected, page=page, scroll=scroll,
                 log=tuple(log) if screen == "talk" else ())
