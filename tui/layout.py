"""
The layout engine: turns a screen's zones into bordered lines.

A zone is one bordered band; its content is a widget, a row of two layouts side by side
(the 'fixed' side keeps its natural width, the other gets the rest), or a stack of
layouts one after another. Zones with nothing to show are skipped when
hide_when_empty is on.

Fitting the terminal's height, in order:
1. zones are dropped highest priority first (priority 0 is never dropped);
2. the screen is drawn again with the widgets' compact forms (tiles as a list, no gaps,
   no art frame), so text doesn't have to be cut;
3. scroll zones keep only their last lines (at least one);
4. as a last resort the tallest zones lose their last lines.
A frame never overflows the terminal.

An open sub-window (Inspect, the character sheet) changes this: its zone is flexible.
Low-priority zones still make room for it first; then it takes every row the other
zones leave, shows the part at the scroll offset, and draws a slider at its right edge
when its content is longer than that. On a list screen (fitting) with no sub-window
open, the list's zone is the flexible one, and it scrolls to keep the pick in view.
"""
from typing import Any, List, Mapping, NamedTuple, Optional, Tuple

from tui.text import pad
from tui.widgets import FOCUS, LISTS, NATURAL_WIDTH, SUBWINDOWS, WIDGETS, Frame


class Band(NamedTuple):
    zone: Mapping[str, Any]
    lines: List[str]
    flexible: bool = False     # the open sub-window or the list: windowed and scrolled
    focus: Optional[int] = None  # the list's picked line, kept in view


class Arranged(NamedTuple):
    bands: List[Band]
    scroll: int                # the sub-window's offset, within its limits
    limit: int                 # the largest offset; 0 when it all fits


def draw_layout(frame: Frame, layout: Mapping[str, Any], width: int) -> List[str]:
    """A layout's lines, each at most 'width' wide (rows are padded to exactly 'width')."""
    if "widget" in layout:
        return WIDGETS[layout["widget"]](frame, width, layout)
    if "stack" in layout:
        return [line for part in layout["stack"] for line in draw_layout(frame, part, width)]
    return _row(frame, layout, width)


def _widgets(layout: Mapping[str, Any]) -> List[str]:
    if "widget" in layout:
        return [layout["widget"]]
    return [w for part in layout.get("row", layout.get("stack", [])) for w in _widgets(part)]


def _natural(frame: Frame, layout: Mapping[str, Any]) -> Optional[int]:
    if "widget" in layout and layout["widget"] in NATURAL_WIDTH:
        return NATURAL_WIDTH[layout["widget"]](frame, layout)
    return None


def _row(frame: Frame, layout: Mapping[str, Any], width: int) -> List[str]:
    padding = frame.tokens["padding"]
    vertical = frame.glyphs["border"]["vertical"]
    left, right = layout["row"]
    fixed = layout.get("fixed", "left")
    side_min = frame.size["side_min_width"]
    available = width - 1                               # one column for the divider
    natural = _natural(frame, left if fixed == "left" else right)
    fixed_width = min(natural if natural is not None else available // 2, available - side_min)
    if fixed == "left":
        left_width, right_width = fixed_width, available - fixed_width
    else:
        left_width, right_width = available - fixed_width, fixed_width
    left_lines = _side(frame, left, left_width, padding, natural is not None and fixed == "left")
    right_lines = _side(frame, right, right_width, padding, natural is not None and fixed == "right")
    lines = []
    for i in range(max(len(left_lines), len(right_lines))):
        a = left_lines[i] if i < len(left_lines) else " " * left_width
        b = right_lines[i] if i < len(right_lines) else " " * right_width
        lines.append(a + vertical + b)
    return lines


def _side(frame: Frame, layout: Mapping[str, Any], width: int, padding: int, boxed: bool) -> List[str]:
    """One side of a row at exactly 'width': boxed widgets (grid, art) sit flush, others get padding."""
    if boxed:
        return [pad(line, width) for line in draw_layout(frame, layout, width)]
    inner = max(1, width - padding)
    return [" " * padding + pad(line, inner) for line in draw_layout(frame, layout, inner)]


def _holds_subwindow(frame: Frame, zone: Mapping[str, Any]) -> bool:
    widget = SUBWINDOWS.get(frame.panel) if frame.panel is not None else LISTS.get(frame.screen)
    return widget is not None and widget in _widgets(zone["content"])


def _zone_lines(frame: Frame, zone: Mapping[str, Any], inner: int, flexible: bool) -> List[str]:
    """
    A zone's lines between the side borders, without the borders themselves. A flexible
    zone's lines leave the last 2 + padding columns free for the slider.
    """
    content = zone["content"]
    padding = frame.tokens["padding"]
    if "row" in content:
        return draw_layout(frame, content, inner)
    if flexible:
        text_width = max(1, inner - 2 * padding - 2)
        return [(FOCUS if line.startswith(FOCUS) else "") + " " * padding + pad(line.lstrip(FOCUS), text_width)
                for line in draw_layout(frame, content, text_width)]
    text_width = max(1, inner - 2 * padding)
    return [" " * padding + pad(line, text_width) + " " * padding
            for line in draw_layout(frame, content, text_width)]


def _height(bands: List[Band], flexible_as: Optional[int] = None) -> int:
    """Lines the bands take with their borders; a flexible band counts as 'flexible_as' lines if given."""
    total = sum(min(len(b.lines), flexible_as) if b.flexible and flexible_as is not None else len(b.lines)
                for b in bands)
    return total + len(bands) + 1


def _fit(frame: Frame, zones: List[Mapping[str, Any]], inner: int, rows: int) -> List[Band]:
    """The zones' bands, with low-priority zones dropped to fit."""
    bands: List[Band] = []
    for zone in zones:
        flexible = _holds_subwindow(frame, zone)
        lines = _zone_lines(frame, zone, inner, flexible)
        if not lines:
            if zone.get("hide_when_empty", True):
                continue
            lines = [""]                                   # kept in place, empty
        focus = next((i for i, line in enumerate(lines) if line.startswith(FOCUS)), None)
        lines = [line.lstrip(FOCUS) for line in lines]
        bands.append(Band(zone, lines, flexible, focus))
    while _height(bands) > rows:                           # make room, for a sub-window too
        droppable = [i for i, b in enumerate(bands) if b.zone.get("priority", 0) > 0]
        if not droppable:
            break
        bands.pop(max(droppable, key=lambda i: (bands[i].zone["priority"], i)))
    return bands


def _scroll_zones(bands: List[Band], rows: int) -> List[Band]:
    """Scroll zones keep only their last lines (at least one) while the screen is too tall."""
    for i, band in enumerate(bands):
        excess = _height(bands, flexible_as=1) - rows
        if excess > 0 and band.zone.get("scroll") and not band.flexible and len(band.lines) > 1:
            bands[i] = band._replace(lines=band.lines[min(excess, len(band.lines) - 1):])
    return bands


def arrange(frame: Frame, zones: List[Mapping[str, Any]], columns: int, rows: int) -> Arranged:
    """The bands that fit the terminal, and where the open sub-window is scrolled to."""
    inner = columns - 2
    bands = _fit(frame, zones, inner, rows)
    if _height(bands, flexible_as=1) > rows and not frame.compact:    # compact widgets before cutting text
        frame = frame._replace(compact=True)
        bands = _fit(frame, zones, inner, rows)
    bands = _scroll_zones(bands, rows)
    while _height(bands, flexible_as=1) > rows:              # last resort: clip the tallest zone
        i = max((j for j in range(len(bands)) if not bands[j].flexible),
                key=lambda j: len(bands[j].lines), default=None)
        if i is None or len(bands[i].lines) <= 1:
            break
        bands[i] = bands[i]._replace(lines=bands[i].lines[:-1])
    flexible = next((i for i, b in enumerate(bands) if b.flexible), None)
    if flexible is None:
        return Arranged(bands, 0, 0)
    band = bands[flexible]
    window = max(1, rows - (_height(bands) - len(band.lines)))
    limit = max(0, len(band.lines) - window)
    # a list follows its pick (scrolling counts back from there); anything else scrolls from the top
    wanted = band.focus - window // 2 - frame.scroll if band.focus is not None else frame.scroll
    scroll = max(0, min(wanted, limit))
    visible = band.lines[scroll:scroll + window]
    bands[flexible] = band._replace(lines=[line + _slider(frame, band.zone, i, window, scroll, limit, len(band.lines))
                                           for i, line in enumerate(visible)])
    return Arranged(bands, scroll, limit)


def _slider(frame: Frame, zone: Mapping[str, Any], row: int, window: int, scroll: int, limit: int, total: int) -> str:
    """The slider's column on one visible row of a sub-window: a gap, the track or thumb, the padding."""
    padding = " " * frame.tokens["padding"]
    shows = limit > 0 and _slider_wanted(frame, zone)
    if not shows:
        return "  " + padding
    thumb = max(1, round(window * window / total))
    start = round(scroll * (window - thumb) / limit)
    glyph = frame.glyphs["slider_thumb"] if start <= row < start + thumb else frame.glyphs["slider_track"]
    return " " + glyph + padding


def _slider_wanted(frame: Frame, layout: Mapping[str, Any]) -> bool:
    """The sub-window widget's 'slider' option (on by default)."""
    if "widget" in layout:
        return layout.get("slider", True) if layout["widget"] == SUBWINDOWS.get(frame.panel) else True
    if "content" in layout:
        return _slider_wanted(frame, layout["content"])
    return all(_slider_wanted(frame, part) for part in layout.get("row", layout.get("stack", [])))


def draw_screen(frame: Frame, zones: List[Mapping[str, Any]], columns: int, rows: int) -> str:
    """A whole screen at the terminal's size: zones in bordered bands, fitted to the terminal's height."""
    arranged = arrange(frame, zones, columns, rows)
    if arranged.limit and not frame.scrollable:           # the hints can now offer scrolling
        arranged = arrange(frame._replace(scrollable=True), zones, columns, rows)
    border = frame.glyphs["border"]
    horizontal = border["horizontal"] * (columns - 2)
    out = [border["top_left"] + horizontal + border["top_right"]]
    for index, band in enumerate(arranged.bands):
        if index:
            out.append(border["join_left"] + horizontal + border["join_right"])
        out += [border["vertical"] + pad(line, columns - 2) + border["vertical"] for line in band.lines]
    out.append(border["bottom_left"] + horizontal + border["bottom_right"])
    return "\n".join(out) + "\n"


def scroll_limit(frame: Frame, zones: List[Mapping[str, Any]], columns: int, rows: int) -> int:
    """How far the open sub-window can scroll at this terminal size (0 when it all fits)."""
    return arrange(frame, zones, columns, rows).limit
