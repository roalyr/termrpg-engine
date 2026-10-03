"""
The layout engine: turns a screen's zones into bordered lines.

A zone is one bordered band; its content is a widget, a row of two layouts side by side
(the 'fixed' side keeps its natural width, the other gets the rest), or a stack of
layouts one after another. Zones with nothing to show are skipped when
hide_when_empty is on. When the screen is taller than the terminal, zones are dropped
highest priority first (priority 0 is never dropped); if it still doesn't fit, scroll
zones keep only their last lines (at least one). If even that is too tall, the screen
is drawn again with the widgets' compact forms (tiles as a list, no gaps, no art frame),
and as a last resort the tallest zones lose their last lines, so a frame never
overflows the terminal.
"""
from typing import Any, List, Mapping, Optional, Tuple

from tui.text import pad
from tui.widgets import NATURAL_WIDTH, WIDGETS, Frame


def draw_layout(frame: Frame, layout: Mapping[str, Any], width: int) -> List[str]:
    """A layout's lines, each at most 'width' wide (rows are padded to exactly 'width')."""
    if "widget" in layout:
        return WIDGETS[layout["widget"]](frame, width, layout)
    if "stack" in layout:
        return [line for part in layout["stack"] for line in draw_layout(frame, part, width)]
    return _row(frame, layout, width)


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


def _zone_lines(frame: Frame, zone: Mapping[str, Any], inner: int) -> List[str]:
    """A zone's lines between the side borders, without the borders themselves."""
    content = zone["content"]
    padding = frame.tokens["padding"]
    if "row" in content:
        return draw_layout(frame, content, inner)
    text_width = max(1, inner - 2 * padding)
    return [" " * padding + pad(line, text_width) + " " * padding
            for line in draw_layout(frame, content, text_width)]


def draw_screen(frame: Frame, zones: List[Mapping[str, Any]], columns: int, rows: int) -> str:
    """A whole screen at the terminal's size: zones in bordered bands, fitted to the terminal's height."""
    border = frame.glyphs["border"]
    inner = columns - 2
    bands = _fit(frame, zones, inner, rows)
    if _height(bands) > rows and not frame.compact:
        bands = _fit(frame._replace(compact=True), zones, inner, rows)
    while _height(bands) > rows:                             # last resort: clip the tallest zone
        i = max(range(len(bands)), key=lambda j: len(bands[j][1]))
        if len(bands[i][1]) <= 1:
            break
        bands[i] = (bands[i][0], bands[i][1][:-1])
    horizontal = border["horizontal"] * inner
    out = [border["top_left"] + horizontal + border["top_right"]]
    for index, (_, lines) in enumerate(bands):
        if index:
            out.append(border["join_left"] + horizontal + border["join_right"])
        out += [border["vertical"] + pad(line, inner) + border["vertical"] for line in lines]
    out.append(border["bottom_left"] + horizontal + border["bottom_right"])
    return "\n".join(out) + "\n"


def _fit(frame: Frame, zones: List[Mapping[str, Any]], inner: int, rows: int) -> List[Tuple[Mapping[str, Any], List[str]]]:
    """The zones' bands, with low-priority zones dropped and scroll zones scrolled to fit."""
    bands: List[Tuple[Mapping[str, Any], List[str]]] = []
    for zone in zones:
        lines = _zone_lines(frame, zone, inner)
        if not lines:
            if zone.get("hide_when_empty", True):
                continue
            lines = [""]                                   # kept in place, empty
        bands.append((zone, lines))
    while _height(bands) > rows:
        droppable = [i for i, (zone, _) in enumerate(bands) if zone.get("priority", 0) > 0]
        if not droppable:
            break
        bands.pop(max(droppable, key=lambda i: (bands[i][0]["priority"], i)))
    for i, (zone, lines) in enumerate(bands):
        excess = _height(bands) - rows
        if excess > 0 and zone.get("scroll") and len(lines) > 1:
            bands[i] = (zone, lines[min(excess, len(lines) - 1):])
    return bands


def _height(bands: List[Tuple[Mapping[str, Any], List[str]]]) -> int:
    return sum(len(lines) for _, lines in bands) + len(bands) + 1
