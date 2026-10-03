"""
The widget catalogue. Each widget draws itself into a given width from the Frame
(content, state, the UI pack and what the screen shows) and its own options, and returns
lines. Widgets without anything to show return no lines.

Words come from two places: the game's voice from the content pack, the UI's labels and
headings from the UI pack. Sizes, glyphs and styles come from the UI pack's tokens.
"""
from typing import Any, Callable, Dict, List, Mapping, NamedTuple, Optional

from engine import build, conditions, context, encounter, stats, world
from engine.content import Content
from engine.state import GameState, day_of, phase_of
from tui.text import ANSI, Style, visible_len, wrap
from tui.ui import UI


class Frame(NamedTuple):
    """Everything a widget may draw from."""
    content: Content
    state: GameState
    ui: UI
    style: Style
    screen: str                   # 'world', 'encounter', 'debrief'
    panel: Optional[str] = None   # 'pack' or 'character'
    selected: Optional[int] = None
    page: int = 0
    compact: bool = False         # the screen is short: widgets with a compact form use it

    @property
    def tokens(self) -> Mapping[str, Any]:
        return self.ui.tokens

    @property
    def glyphs(self) -> Mapping[str, Any]:
        return self.ui.tokens["glyphs"]

    @property
    def size(self) -> Mapping[str, Any]:
        return self.ui.tokens["size"]


Draw = Callable[[Frame, int, Mapping[str, Any]], List[str]]


# --- Helpers ---------------------------------------------------------------------------

def bar(frame: Frame, value: float, top: float, length: int) -> str:
    filled = 0 if top <= 0 else round(length * max(0, min(value, top)) / top)
    return frame.glyphs["bar_full"] * filled + frame.glyphs["bar_empty"] * (length - filled)


def styled_lines(text: str, width: int, frame: Frame, role: Optional[str]) -> List[str]:
    lines = wrap(text, width)
    return [frame.style.role(line, role) for line in lines] if role else lines


def option_text(ui: UI, option: Any) -> str:
    """A menu or item option's words: the content's own label, or the UI's word for its kind."""
    if option.label is not None:
        return option.label
    word = "go_to" if option.kind == "go" else option.kind
    return ui.word(word, **dict(option.params))


def option_lines(frame: Frame, option: Any, width: int, hints: bool = True) -> List[str]:
    key, text = option.key.upper(), option_text(frame.ui, option)
    if option.available:
        entry = f"{frame.style.key(key)} {text}"
        return [entry] if visible_len(entry) <= width else wrap(f"{key} {text}", width)
    hint = f" - {option.hint}" if hints and option.hint else ""
    return styled_lines(f"{key} {text}{hint}", width, frame, "unavailable")


def message_lines(frame: Frame, messages, width: int) -> List[str]:
    """Messages in the order they happened; their kind sets only the mark and the style."""
    glyphs = frame.glyphs
    lines: List[str] = []
    for message in messages:
        if message.kind == "heading":                # a UI word, e.g. the end of a round
            lines += styled_lines(frame.ui.word(message.text), width, frame, "quiet")
            continue
        mark = {"danger": glyphs["mark_danger"], "gain": glyphs["mark_gain"]}.get(message.kind, "")
        role = {"danger": "danger", "gain": "gain", "quiet": "quiet"}.get(message.kind)
        lines += styled_lines(mark + message.text, width, frame, role)
    return lines


# --- title -----------------------------------------------------------------------------

def title(frame: Frame, width: int, options: Mapping) -> List[str]:
    content, state, style = frame.content, frame.state, frame.style
    if frame.screen == "debrief":
        debrief = state.debrief
        return [style.role(debrief.title, "danger" if debrief.result == "lost" else "title")]
    if frame.screen == "encounter":
        record = content.get("encounter", state.encounter.id)
        return [style.role(frame.ui.word("encounter_round", encounter=record["name"], round=state.encounter.round),
                           "title")]
    location = content.get("location", state.characters[state.player].location)
    name, region = location["name"], content.get("region", location["region"])["name"]
    gap = max(1, width - len(name) - len(region))
    lines = [style.role(name, "title") + " " * gap + region]
    hazards = [content.get("tag", t)["name"] for t in location.get("tags", ()) if content.get("tag", t).get("hazard")]
    if hazards:
        lines += styled_lines(", ".join(hazards), width, frame, "danger")
    return lines


# --- grid ------------------------------------------------------------------------------

def grid_width(frame: Frame, options: Mapping) -> int:
    location = frame.content.get("location", frame.state.characters[frame.state.player].location)
    tiles, cell = location["grid"]["width"], frame.size["cell_width"]
    return tiles + (tiles - 1) * (cell - 1) + 4


def grid(frame: Frame, width: int, options: Mapping) -> List[str]:
    content, state, glyphs = frame.content, frame.state, frame.glyphs
    border = glyphs["border"]
    player = state.characters[state.player]
    location = content.get("location", player.location)
    spec = location["grid"]
    people = {tuple(state.characters[cid].at): cid for cid in world.others_here(state)}
    gap = " " * (frame.size["cell_width"] - 1)
    inner = grid_width(frame, options) - 2
    lines = [border["top_left"] + border["horizontal"] * inner + border["top_right"]]
    for row in range(spec["height"]):
        cells = []
        for col in range(spec["width"]):
            pos = (row, col)
            glyph = _cell(content, state, location, pos, people)
            if pos == tuple(player.at):
                glyph = frame.style.inverse(glyph if glyph.strip() not in ("", spec["floor"]) else glyphs["player"])
            cells.append(glyph)
        lines.append(border["vertical"] + " " + gap.join(cells) + " " + border["vertical"])
    lines.append(border["bottom_left"] + border["horizontal"] * inner + border["bottom_right"])
    return lines


def _cell(content: Content, state: GameState, location, pos, people) -> str:
    if pos in people:
        record = content.get("character", state.characters[people[pos]].source)
        return record.get("glyph") or record["name"][0]
    placed = world.placement_at(content, location["id"], pos)
    if placed is not None:
        current = state.object_states.get(placed["id"])
        return placed.get("state_glyphs", {}).get(current, placed["glyph"])
    kind = world.tile(content, location["id"], pos)
    return {"#": location["grid"]["wall"], ".": location["grid"]["floor"]}.get(kind, " ")


# --- status ----------------------------------------------------------------------------

def status(frame: Frame, width: int, options: Mapping) -> List[str]:
    content, state, style = frame.content, frame.state, frame.style
    player = state.characters[state.player]
    lines: List[str] = []
    if options.get("day", True):
        phase = content.get("phase", phase_of(content, state.turn))["name"]
        lines += wrap(frame.ui.word("day_phase", day=day_of(content, state.turn), phase=phase), width)
    pools = options.get("pools", "all")
    if pools == "all":
        shown = [sid for sid, rec in content.all("stat").items() if rec.get("kind") == "pool"]
    else:
        shown = [content.stat_roles[r] for r in pools if r in content.stat_roles
                 and content.get("stat", content.stat_roles[r]).get("kind") == "pool"]
    length = frame.size["bar_length"]
    for stat_id in shown:
        record = content.get("stat", stat_id)
        top, now = stats.stat(content, player, stat_id), stats.current(content, player, stat_id)
        label = record.get("short") or record["name"][:3]
        line = f"{label:<4}{bar(frame, now, top, length)} {int(now)}/{int(top)}"
        low = (record.get("role") == "health" and now <= top / 3) or (record.get("role") == "heat" and now >= top * 0.8)
        lines.append(style.role(line, "danger") if low else line)
    if options.get("statuses", True):
        for inst in player.statuses:
            record = content.get("status", inst.status)
            text = f"{record.get('glyph', '*')} {record['name']}" + (f" x{inst.stacks}" if inst.stacks > 1 else "")
            lines.append(style.role(text, "danger") if record.get("harmful", True) else text)
    party = context.party_of(state, state.player)[1:]
    if party and options.get("party", True):
        names = ", ".join(content.get("character", state.characters[c].source)["name"] for c in party)
        lines += wrap(frame.ui.word("party", names=names), width)
    return lines


# --- legend ----------------------------------------------------------------------------

def legend(frame: Frame, width: int, options: Mapping) -> List[str]:
    content, state = frame.content, frame.state
    location_id = state.characters[state.player].location
    entries: Dict[str, List[str]] = {}
    for placed in content.all("placement").values():
        if placed["location"] != location_id:
            continue
        current = state.object_states.get(placed["id"])
        glyph = placed.get("state_glyphs", {}).get(current, placed["glyph"])
        name = placed["name"]
        if placed.get("exit") and placed["exit"].get("location"):
            name = content.get("location", placed["exit"]["location"])["name"]
        if current:
            name += f" ({content.get('object_state', current)['name']})"
        entries.setdefault(glyph, []).append(name)
    for cid in world.others_here(state):
        record = content.get("character", state.characters[cid].source)
        entries.setdefault(record.get("glyph") or record["name"][0], []).append(record["name"])
    lines = []
    for glyph, names in entries.items():
        for i, line in enumerate(wrap(frame.glyphs["separator"].join(names), width - 2)):
            lines.append(f"{glyph if i == 0 else ' '} {frame.style.role(line, 'hint')}")
    return lines


# --- log -------------------------------------------------------------------------------

def log(frame: Frame, width: int, options: Mapping) -> List[str]:
    state = frame.state
    if frame.screen == "debrief":
        heading, messages = state.debrief.round, state.debrief.messages
    else:
        heading = state.encounter.log_round if state.encounter is not None else 0
        messages = state.messages
    lines: List[str] = []
    if heading and messages and options.get("round_heading", True) and frame.screen != "world":
        lines.append(frame.style.role(frame.ui.word("round_log", round=heading), "heading"))
    return lines + message_lines(frame, messages, width)


# --- menu and choice -------------------------------------------------------------------

def menu(frame: Frame, width: int, options: Mapping) -> List[str]:
    state = frame.state
    if state.pending is not None or frame.panel is not None:
        return []
    current = world.menu(frame.content, state, frame.ui.bound_keys)
    if current is None:
        return []
    lines = [frame.style.role(current.title, "heading")]
    for option in current.options:
        lines += option_lines(frame, option, width, options.get("hints", True))
    return lines


def choice(frame: Frame, width: int, options: Mapping) -> List[str]:
    content, state = frame.content, frame.state
    if state.pending is None:
        return []
    lines: List[str] = wrap(state.pending.prompt, width) if state.pending.prompt else []
    for i, option in enumerate(state.pending.options, 1):
        # Drawing must not change the game: the state a check returns is thrown away.
        ok, _ = conditions.holds(content, state, state.pending.ctx, option.get("condition"))
        text = f"{i} {content.text(option['label'])}"
        if ok:
            lines += wrap(text, width)
        else:
            hint = f" - {content.text(option['hint'])}" if options.get("hints", True) and option.get("hint") else ""
            lines += styled_lines(text + hint, width, frame, "unavailable")
    return lines


# --- board and sheet -------------------------------------------------------------------

def board(frame: Frame, width: int, options: Mapping) -> List[str]:
    content, state, style, ui = frame.content, frame.state, frame.style, frame.ui
    if frame.panel != "pack" or state.pending is not None:
        return []
    player = state.characters[state.player]
    lines: List[str] = []
    if options.get("budgets", True):
        budgets = []
        for role, used in (("power", stats.budget_used(content, player, "power")),
                           ("mass", stats.budget_used(content, player, "mass")),
                           ("cargo", len(player.inventory))):
            stat_id = content.stat_roles.get(role)
            if stat_id:
                short = content.get("stat", stat_id).get("short") or content.get("stat", stat_id)["name"]
                budgets.append(f"{short} {used:g}/{stats.budget_provided(content, player, role):g}")
        lines += styled_lines("  ".join(budgets), width, frame, "hint")
    slots = build.pack_slots(content, state)
    page_size = frame.size["page_size"]
    pages = max(1, -(-len(slots) // page_size))
    page = frame.page % pages
    first = page * page_size
    where_store = build.storage_here(content, state)
    shown = set()
    for number, slot in enumerate(slots[first:first + page_size], 1):
        group = slot[0] if slot[0] in ("inventory", "storage", "design") else "fitted"
        if group not in shown:
            shown.add(group)
            heading = {"fitted": ui.word("pack_fitted"), "inventory": ui.word("pack_carried"),
                       "design": ui.word("pack_designs")}.get(group) or \
                ui.word("pack_stored", container=content.get("placement", where_store)["name"])
            lines.append(style.role(heading, "heading"))
        entry = build.entry_at(content, state, slot)
        text = content.get("item", entry)["name"] if slot[0] == "design" else _item_line(content, entry)
        entry = f"{number} {text}"[:width]
        lines.append(style.key(entry) if frame.selected == first + number - 1 else entry)
    if pages > 1:
        lines += styled_lines(ui.word("pack_more", page=page + 1, pages=pages), width, frame, "hint")
    if frame.selected is not None and frame.selected < len(slots):
        for option in build.item_options(content, state, slots[frame.selected], ui.bound_keys):
            lines += option_lines(frame, option, width)
    return lines


def _item_line(content: Content, inst) -> str:
    view = stats.item_view(content, inst)
    text = view["name"] + (f" x{inst.count}" if inst.count > 1 else "")
    if inst.condition is not None:
        text += f" {inst.condition}/{view['max_condition']}"
    return text


def sheet(frame: Frame, width: int, options: Mapping) -> List[str]:
    content, state = frame.content, frame.state
    if frame.panel != "character" or state.pending is not None:
        return []
    player = state.characters[state.player]
    lines = [frame.style.role(frame.ui.word("character_title", name=content.get("character", player.source)["name"]),
                              "heading")]
    top = content.settings["skill_max_level"]
    for skill_id, level in player.skills.items():
        skill = content.get("skill", skill_id)
        following = [lv["xp"] for lv in skill["levels"] if level < lv["level"] <= top]
        progress = f" ({player.xp.get(skill_id, 0)}/{min(following)})" if following else ""
        lines += wrap(f"  {skill['name']} {level}{progress}", width)
    for stat_id, stat in content.all("stat").items():
        if stat.get("kind") != "pool":
            lines += wrap(f"  {stat.get('short') or stat['name']} {stats.stat(content, player, stat_id):g}", width)
    return lines


# --- encounter widgets -----------------------------------------------------------------

def art_width(frame: Frame, options: Mapping) -> int:
    return max(visible_len(line) for line in _art_lines(frame, options))


def _art_lines(frame: Frame, options: Mapping) -> List[str]:
    state, content = frame.state, frame.content
    enemies = encounter.living(state, "enemies") if state.encounter is not None else []
    record = content.get("character", state.characters[enemies[0]].source) if enemies else {}
    lines = list(record.get("art", ())) or [record.get("glyph") or record.get("name", " ")[0]]
    widest = max(len(line) for line in lines)
    if not options.get("frame", True) or frame.compact:
        return [line.ljust(widest) for line in lines]
    border = frame.glyphs["border"]
    edge = border["horizontal"] * (widest + 2)
    return ([border["top_left"] + edge + border["top_right"]]
            + [f"{border['vertical']} {line.ljust(widest)} {border['vertical']}" for line in lines]
            + [border["bottom_left"] + edge + border["bottom_right"]])


def art(frame: Frame, width: int, options: Mapping) -> List[str]:
    return [line if visible_len(line) <= width else ANSI.sub("", line)[:width] for line in _art_lines(frame, options)]


def fighters(frame: Frame, width: int, options: Mapping) -> List[str]:
    content, state, style = frame.content, frame.state, frame.style
    health = content.stat_roles["health"]
    length = frame.size["fighter_bar_length"]
    lines = []
    for cid in encounter.living(state, "allies"):
        cs = state.characters[cid]
        name = content.get("character", cs.source)["name"][:10]
        lines.append(f"{name:<10} {bar(frame, stats.current(content, cs, health), stats.stat(content, cs, health), length)}")
    heat = content.stat_roles["heat"]
    me = state.characters[state.player]
    if stats.stat(content, me, heat) > 0:
        short = content.get("stat", heat).get("short") or heat
        lines.append(f"{short:<10} {bar(frame, stats.current(content, me, heat), stats.stat(content, me, heat), length)}")
    if not frame.compact:
        lines.append("")                              # a gap between the sides
    for number, cid in enumerate(encounter.living(state, "enemies"), 1):
        cs = state.characters[cid]
        name = content.get("character", cs.source)["name"][:8]
        now, top = stats.current(content, cs, health), stats.stat(content, cs, health)
        lines.append(f"{number} {name:<8} {bar(frame, now, top, length)} {int(now)}")
        intent = encounter.intent_line(content, state, cid) if options.get("intent", True) else None
        if intent:
            lines.append(style.role(f"  {frame.glyphs['intent']} {intent}"[:width], "danger"))
    return [line[:width] if visible_len(line) == len(line) else line for line in lines]


def tiles(frame: Frame, width: int, options: Mapping) -> List[str]:
    """Action tiles as boxes; compact, as a wrapped list ('1 Strike ▲1  2 Guard ▲1')."""
    tile_list = encounter.tiles(frame.content, frame.state)
    if frame.compact:
        lines: List[str] = []
        for tile in tile_list:
            cost = f" {frame.glyphs['cost']}{tile.cost}" if tile.cost else ""
            entry = f"{tile.key} {tile.label}{cost}"[:width]
            entry = entry if tile.available else frame.style.role(entry, "unavailable")
            if lines and visible_len(lines[-1]) + 2 + visible_len(entry) <= width:
                lines[-1] += "  " + entry
            else:
                lines.append(entry)
        return lines
    tile_width = frame.size["tile_width"]
    per_row = options.get("per_row", 0) or max(1, width // tile_width)
    per_row = min(per_row, max(1, width // tile_width))
    border = frame.glyphs["border"]
    inner = tile_width - 2
    lines: List[str] = []
    for start in range(0, len(tile_list), per_row):
        parts: List[List[str]] = [[], [], [], []]
        for tile in tile_list[start:start + per_row]:
            paint = (lambda t: t) if tile.available else (lambda t: frame.style.role(t, "unavailable"))
            cost = f"{frame.glyphs['cost']}{tile.cost}" if tile.cost else ""
            parts[0].append(border["top_left"] + border["horizontal"] * inner + border["top_right"])
            parts[1].append(paint(border["vertical"] + f"{tile.key} {tile.label}"[:inner].ljust(inner) + border["vertical"]))
            parts[2].append(paint(border["vertical"] + cost[:inner].ljust(inner) + border["vertical"]))
            parts[3].append(border["bottom_left"] + border["horizontal"] * inner + border["bottom_right"])
        lines += ["".join(p) for p in parts]
    return lines


# --- keys ------------------------------------------------------------------------------

def hint_context(frame: Frame) -> str:
    state = frame.state
    if frame.screen == "debrief":
        return "debrief"
    if state.pending is not None:
        return "choice"
    if frame.screen == "encounter":
        return "target" if frame.selected is not None else "encounter"
    if frame.panel == "pack":
        return "pack"
    if frame.panel == "character":
        return "sheet"
    if world.menu(frame.content, state, frame.ui.bound_keys) is not None:
        return "menu"
    return "walk"


def _numbered(frame: Frame, context: str) -> int:
    """How many numbered entries the context offers: what the digit keys can pick."""
    content, state = frame.content, frame.state
    if context == "choice":
        return len(state.pending.options)
    if context == "encounter":
        return len(encounter.tiles(content, state))
    if context == "target":
        tile = encounter.tiles(content, state)[frame.selected]
        return len(encounter.targets(content, state, state.player, tile.action))
    if context == "pack":
        slots, size = len(build.pack_slots(content, state)), frame.size["page_size"]
        pages = max(1, -(-slots // size))
        return max(0, min(size, slots - (frame.page % pages) * size))
    return 9


def keys(frame: Frame, width: int, options: Mapping) -> List[str]:
    """Key hints for the current context, built from the bindings: 'WASD move  P pack …'."""
    ui = frame.ui
    context = hint_context(frame)
    parts = []
    for hint in ui.hints.get(context, []):
        label = ui.labels.get(hint["label"], hint["label"])
        if hint.get("digits"):
            count = _numbered(frame, context)
            if count:
                parts.append(f"{'1' if count == 1 else f'1-{count}'} {label}")
        elif hint.get("actions"):
            parts.append("".join(ui.bindings[a].upper() for a in hint["actions"]) + f" {label}")
        else:
            parts.append(label)
    lines: List[str] = []
    for part in parts:                                # wrap between hints, never inside one
        if lines and visible_len(lines[-1]) + 2 + visible_len(part) <= width:
            lines[-1] += "  " + part
        else:
            lines += wrap(part, width)
    return [frame.style.role(line, "hint") for line in lines]


WIDGETS: Dict[str, Draw] = {
    "title": title, "grid": grid, "status": status, "legend": legend, "log": log, "menu": menu,
    "choice": choice, "board": board, "sheet": sheet, "tiles": tiles, "fighters": fighters,
    "art": art, "keys": keys,
}

# Widgets with a natural width of their own (the rest take the width they're given).
NATURAL_WIDTH: Dict[str, Callable[[Frame, Mapping], int]] = {"grid": grid_width, "art": art_width}
