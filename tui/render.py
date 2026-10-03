"""
Drawing the game: picks the screen (world, encounter or the after-action screen) and
lays it out from the UI pack. A pure function: the same state and UI pack always draw
the same frame. The look, layout and the UI's words come from the UI pack; the game's
own words come from the content pack.
"""
from typing import Optional

from engine.content import Content
from engine.state import GameState
from tui.layout import draw_screen
from tui.text import Style
from tui.ui import UI, default_ui
from tui.widgets import Frame


def render(content: Content, state: GameState, columns: int, rows: int = 60,
           panel: Optional[str] = None, colour: bool = True, selected: Optional[int] = None,
           page: int = 0, ui: Optional[UI] = None) -> str:
    ui = ui or default_ui()
    size = ui.tokens["size"]
    if columns < size["min_columns"] or rows < size["min_rows"]:
        return ui.word("terminal_too_small", columns=size["min_columns"], rows=size["min_rows"]) + "\n"
    if state.debrief is not None:
        screen = "debrief"
    elif state.encounter is not None:
        screen = "encounter"
    else:
        screen = "world"
    frame = Frame(content=content, state=state, ui=ui, style=Style(colour, ui.tokens["styles"]), screen=screen,
                  panel=panel if screen == "world" else None, selected=selected, page=page)
    return draw_screen(frame, ui.screens[screen], columns, rows)
