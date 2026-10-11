"""
The widget catalogue. Each widget draws itself into a given width from the Frame
(content, state, the UI pack and what the screen shows) and its own options, and returns
lines. Widgets without anything to show return no lines.

Words come from two places: the game's voice from the content pack, the UI's labels and
headings from the UI pack. Sizes, glyphs and styles come from the UI pack's tokens.
"""
from typing import Any, Callable, Dict, List, Mapping, NamedTuple, Optional, Tuple

from engine import atlas, build, conditions, context, encounter, stats, world
from engine.content import Content
from engine.state import GameState, ItemInst, Message, char_key, day_of, new_item, phase_of
from lib import graph, pixels
from lib.text import ANSI, Style, pad, visible_len, wrap
from lib.text import bar as text_bar
from lib.tiles import map_glyph, room_line
from lib.ui import UI


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
    scroll: int = 0               # how far the open sub-window is scrolled
    scrollable: bool = False      # the open sub-window is longer than its space
    log: Tuple = ()               # a conversation's history: Messages ('response' for what you said)
    shell: Any = None             # the start, slots and help screens' data (tui.shell.ShellData); no state there
    cursor: Optional[Tuple[int, int]] = None   # the map's cursor cell; 'page' is the region shown

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

# Sub-windows: what's open (Frame.panel) and the widget that shows it. While one is open
# it is the focus: its zone scrolls, and the log and menu step back.
SUBWINDOWS = {"inspect": "panel", "item": "panel", "modify": "pick", "card": "panel", "history": "panel",
              "pack": "board"}
SHOWS_LOG = ("pack",)    # sub-windows that keep the message log above them (what an action just did)
# List screens: with no sub-window open, this widget's zone scrolls to keep the pick in view.
LISTS = {"fitting": "loadout", "character": "skills", "talk": "conversation",
         "start": "start_menu", "slots": "slots", "help": "help"}
SHELL = ("start", "slots", "help")   # screens before a game is loaded: no state
FOCUS = "\x00"   # marks the picked line of a list for the layout; never drawn


# --- Helpers ---------------------------------------------------------------------------

def bar(frame: Frame, value: float, top: float, length: int) -> str:
    return text_bar(value, top, length, frame.glyphs["bar_full"], frame.glyphs["bar_empty"])


def styled_lines(text: str, width: int, frame: Frame, role: Optional[str]) -> List[str]:
    lines = wrap(text, width)
    return [frame.style.role(line, role) for line in lines] if role else lines


def option_text(ui: UI, option: Any) -> str:
    """A menu or item option's words: the content's own label, or the UI's word for its kind."""
    if option.label is not None:
        return option.label
    word = "go_to" if option.kind == "go" else option.kind
    return ui.word(word, **dict(option.params))


def hang(text: str, width: int, indent: int) -> List[str]:
    """Wrapped text whose following lines are indented under the first one's text ('2 Recruit - Doesn't…')."""
    first, *rest = wrap(text, width) or [""]
    if not rest:
        return [first]
    more = wrap(" ".join(rest), max(1, width - indent))
    return [first] + [" " * indent + line for line in more]


UI_KEYS = {"workshop": "fitting"}      # menu options opened by one of the UI's own keys


def option_lines(frame: Frame, option: Any, width: int, hints: bool = True) -> List[str]:
    key = (option.key or frame.ui.bindings.get(UI_KEYS.get(option.kind, ""), "")).upper()
    text = option_text(frame.ui, option)
    indent = len(key) + 1
    if option.available:
        entry = f"{frame.style.key(key)} {text}"
        return [entry] if visible_len(entry) <= width else hang(f"{key} {text}", width, indent)
    hint = f" - {option.hint}" if hints and option.hint else ""
    return [frame.style.role(line, "unavailable") for line in hang(f"{key} {text}{hint}", width, indent)]


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
    if frame.screen == "start":
        return [_right(style.role(content.pack["name"], "title"), style.role(content.pack["version"], "quiet"), width)]
    if frame.screen == "slots":
        word = "slots_new_title" if frame.shell.mode == "new" else "slots_load_title"
        return [style.role(frame.ui.word(word), "title")]
    if frame.screen == "help":
        return [style.role(frame.ui.word("help_title"), "title")]
    if frame.screen == "debrief":
        debrief = state.debrief
        return [style.role(debrief.title, "danger" if debrief.result == "lost" else "title")]
    if frame.screen == "character":
        me = state.characters[state.player]
        return [style.role(frame.ui.word("character_title", name=content.get("character", me.source)["name"]), "title")]
    if frame.screen == "map":
        regions = atlas.regions(content, state)
        shown = regions[frame.page % len(regions)]
        name = style.role(frame.ui.word("map_title", region=content.get("region", shown)["name"]), "title")
        count = frame.ui.word("map_regions", number=frame.page % len(regions) + 1, count=len(regions))
        return [_right(name, style.role(count, "quiet"), width) if len(regions) > 1 else name]
    if frame.screen == "talk":
        name = frame.ui.word("talk_title", name=content.get("character", state.characters[speaker_of(frame)].source)["name"])
        place = content.get("location", state.characters[state.player].location)["name"]
        return [_right(style.role(name, "title"), style.role(place, "quiet"), width)]
    if frame.screen == "fitting":
        me = state.characters[state.player]
        name = frame.ui.word("fitting_title", frame=stats.item_view(content, me.frame)["name"]) if me.frame \
            else frame.ui.word("fitting_no_frame")
        shop = build.workshop_here(content, state)
        place = frame.ui.word("fitting_at", place=content.get("placement", shop)["name"]) if shop \
            else frame.ui.word("fitting_planning")
        if visible_len(name) + 1 + visible_len(place) > width:
            return [style.role(name, "title")] + styled_lines(place, width, frame, "quiet")
        return [style.role(name, "title") + " " * (width - visible_len(name) - visible_len(place)) + place]
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
    content, state, glyphs, style = frame.content, frame.state, frame.glyphs, frame.style
    border = glyphs["border"]
    player = state.characters[state.player]
    location = content.get("location", player.location)
    spec = location["grid"]
    people = {tuple(state.characters[cid].at): cid for cid in world.others_here(state)}
    wall = map_glyph(style, spec["wall"], spec.get("wall_colour"), "map_wall")
    inner = grid_width(frame, options) - 2
    lines = [border["top_left"] + border["horizontal"] * inner + border["top_right"]]
    for row in range(spec["height"]):
        cells, walls = [], []
        for col in range(spec["width"]):
            pos = (row, col)
            glyph, colour, role = _cell(content, state, location, pos, people)
            if pos == tuple(player.at):
                shown = glyph if glyph.strip() not in ("", spec["floor"]) else glyphs["player"]
                cells.append(style.role(shown, "map_player", "7") if style.colour else style.inverse(shown))
            else:
                cells.append(map_glyph(style, glyph, colour, role))
            walls.append(role == "map_wall")              # a door or an open edge breaks the wall
        lines.append(border["vertical"] + room_line(cells, walls, wall, frame.size["cell_width"]) + border["vertical"])
    lines.append(border["bottom_left"] + border["horizontal"] * inner + border["bottom_right"])
    return lines


def _person_role(content: Content, state: GameState, cid: str) -> str:
    """Party members travel with the player and aren't drawn, so people are hostile or not."""
    return "map_hostile" if context.relation(content, state, char_key(cid), char_key(state.player)) < 0 else "map_person"


def _cell(content: Content, state: GameState, location, pos, people) -> Tuple[str, Any, str]:
    """The glyph on a tile, the pack's colour for it (or None) and its style role."""
    if pos in people:
        cid = people[pos]
        record = content.get("character", state.characters[cid].source)
        return record.get("glyph") or record["name"][0], record.get("colour"), _person_role(content, state, cid)
    placed = world.placement_at(content, location["id"], pos)
    if placed is not None:
        current = state.object_states.get(placed["id"])
        glyph = placed.get("state_glyphs", {}).get(current, placed["glyph"])
        return glyph, placed.get("colour"), "map_exit" if placed.get("exit") else "map_object"
    kind, spec = world.tile(content, location["id"], pos), location["grid"]
    if kind == "#":
        return spec["wall"], spec.get("wall_colour"), "map_wall"
    if kind == ".":
        return spec["floor"], spec.get("floor_colour"), "map_floor"
    return " ", None, "map_floor"


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
    lines += _pool_lines(frame, player, shown, width)
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


def _pool_lines(frame: Frame, cs, shown: List[str], width: Optional[int] = None) -> List[str]:
    """
    One bar per pool stat: 'HP  ████████ 30/30', low health or high heat in the warning colour.
    In a narrow panel the bar gets shorter so the numbers stay whole.
    """
    content, lines = frame.content, []
    for stat_id in shown:
        record = content.get("stat", stat_id)
        top, now = stats.stat(content, cs, stat_id), stats.current(content, cs, stat_id)
        if top <= 0:
            continue
        label = record.get("short") or record["name"][:3]
        numbers = f"{int(now)}/{int(top)}"
        length = frame.size["bar_length"] if width is None else max(1, min(frame.size["bar_length"],
                                                                           width - 5 - len(numbers)))
        line = f"{label:<4}{bar(frame, now, top, length)} {numbers}"
        low = (record.get("role") == "health" and now <= top / 3) or (record.get("role") == "heat" and now >= top * 0.8)
        lines.append(frame.style.role(line, "danger") if low else line)
    return lines


# --- legend ----------------------------------------------------------------------------

def legend(frame: Frame, width: int, options: Mapping) -> List[str]:
    """What each glyph in the room is, the glyph in its map colour."""
    content, state, style = frame.content, frame.state, frame.style
    location_id = state.characters[state.player].location
    entries: Dict[str, List[str]] = {}
    painted: Dict[str, str] = {}
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
        painted.setdefault(glyph, map_glyph(style, glyph, placed.get("colour"),
                                            "map_exit" if placed.get("exit") else "map_object"))
    for cid in world.others_here(state):
        record = content.get("character", state.characters[cid].source)
        glyph = record.get("glyph") or record["name"][0]
        entries.setdefault(glyph, []).append(record["name"])
        painted.setdefault(glyph, map_glyph(style, glyph, record.get("colour"), _person_role(content, state, cid)))
    lines = []
    for glyph, names in entries.items():
        names = list(dict.fromkeys(names))             # an open edge's tiles all lead to the same place
        for i, line in enumerate(wrap(frame.glyphs["separator"].join(names), width - 2)):
            lines.append(f"{painted[glyph] if i == 0 else ' '} {style.role(line, 'hint')}")
    return lines


# --- log -------------------------------------------------------------------------------

def log(frame: Frame, width: int, options: Mapping) -> List[str]:
    state = frame.state
    if state is None:
        return []
    if frame.screen == "debrief":
        heading, messages = state.debrief.round, state.debrief.messages
    else:
        heading = state.encounter.log_round if state.encounter is not None else 0
        messages = state.messages
    if frame.panel in SUBWINDOWS and frame.panel not in SHOWS_LOG:     # one focus at a time
        return []
    if frame.screen == "encounter" and frame.selected is not None and frame.panel != "target":
        return []                                    # the picked action's details take its place
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
    if frame.state.pending is None or frame.panel == "card":      # a card shows it instead
        return []
    return _choice_lines(frame, width, options.get("hints", True))


def _choice_lines(frame: Frame, width: int, hints: bool) -> List[str]:
    """A waiting question: its prompt, then numbered options, unavailable ones greyed out with their hint."""
    content, state = frame.content, frame.state
    lines: List[str] = wrap(state.pending.prompt, width) if state.pending.prompt else []
    for i, option in enumerate(state.pending.options, 1):
        # Drawing must not change the game: the state a check returns is thrown away.
        ok, _ = conditions.holds(content, state, state.pending.ctx, option.get("condition"))
        text = f"{i} {content.text(option['label'])}"
        if ok:
            lines += hang(text, width, len(str(i)) + 1)
        else:
            hint = f" - {content.text(option['hint'])}" if hints and option.get("hint") else ""
            lines += [frame.style.role(line, "unavailable") for line in hang(text + hint, width, len(str(i)) + 1)]
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
        for role, used in (("cargo", len(player.inventory)),):
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
        item = build.entry_at(content, state, slot)
        text = _item_entry(frame, item)
        entry = f"{number} {text}" if visible_len(f"{number} {text}") <= width else f"{number} {_item_line(content, item)}"[:width]
        if frame.selected == first + number - 1:                   # the pick, with what it can do under it
            lines.append(FOCUS + style.key(_plain(entry)))
            for option in build.item_options(content, state, slot, ui.bound_keys, "pack"):
                lines += ["  " + line for line in option_lines(frame, option, width - 2)]
            lines.append(f"  {style.key(world.MENU_KEYS['inspect'].upper())} {ui.word('details')}")
        else:
            lines.append(entry)
    if pages > 1:
        lines += styled_lines(ui.word("pack_more", page=page + 1, pages=pages), width, frame, "hint")
    return lines


def graded(frame: Frame, item_id: str, text: str) -> str:
    """An item's name in its grade's colour (ungraded items as they are)."""
    grade = frame.content.get("item", item_id).get("grade")
    return frame.style.colour_of(text, frame.content.get("grade", grade)["colour"]) if grade else text


def _item_entry(frame: Frame, inst) -> str:
    """'Cutter 4/4', 'Scrap x10': the name in its grade's colour, the count and condition plain."""
    plain = _item_line(frame.content, inst)
    name = stats.item_view(frame.content, inst)["name"]
    return graded(frame, inst.item, name) + plain[len(name):]


def _item_line(content: Content, inst) -> str:
    view = stats.item_view(content, inst)
    text = view["name"] + (f" x{inst.count}" if inst.count > 1 else "")
    if inst.condition is not None:
        text += f" {inst.condition}/{view['max_condition']}"
    return text


# --- panel -----------------------------------------------------------------------------

def card_shown(ui: UI, content: Content, state: GameState) -> bool:
    """
    Whether the world shows a card: a question always does; an event's text does when it's
    longer than the UI pack's card_min_lines on the narrowest screen (so it's the same on
    every terminal, and the app can tell without knowing the terminal's size).
    """
    if state.pending is not None:
        return True
    if state.card is None:
        return False
    width = ui.tokens["size"]["min_columns"] - 2 - 2 * ui.tokens["padding"] - 2
    return len(wrap(state.card.text, width)) > ui.tokens["size"]["card_min_lines"]


def _card(frame: Frame, width: int) -> List[str]:
    """An event's card: its name, its text, then the question and its choices if it asks one."""
    content, state, style = frame.content, frame.state, frame.style
    card = state.card
    title = card.title if card is not None else (world.focus_name(content, state) or "")
    lines = [style.role(line, "heading") for line in wrap(title, width)] if title else []
    if card is not None and card.text:
        if lines:
            lines.append("")
        for paragraph in card.text.split("\n"):
            lines += wrap(paragraph, width) if paragraph else [""]
    if state.pending is not None:
        if lines:
            lines.append("")
        question = _choice_lines(frame, width, True)
        lines += [FOCUS + question[0]] + question[1:] if question else []   # opens on the question
    return lines


def _history(frame: Frame, width: int) -> List[str]:
    """The journal, grouped under day and shift headings, newest last (kept in view)."""
    content, ui, style = frame.content, frame.ui, frame.style
    lines = [style.role(ui.word("history_title"), "heading")]
    journal = frame.state.journal
    if not journal:
        return lines + styled_lines(ui.word("history_empty"), width, frame, "quiet")
    shown = None
    for entry in journal:
        moment = (day_of(content, entry.turn), phase_of(content, entry.turn))
        if moment != shown:
            shown = moment
            phase = content.get("phase", moment[1])["name"]
            lines += styled_lines(ui.word("day_phase", day=moment[0], phase=phase), width, frame, "quiet")
        lines += ["  " + line for line in message_lines(frame, [Message(entry.kind, entry.text)], width - 2)]
    lines[-1] = FOCUS + lines[-1]                                 # the newest stays in view
    return lines


def panel(frame: Frame, width: int, options: Mapping) -> List[str]:
    """The shared panel: what Inspect shows, an item's details, an event's card, or the message history."""
    if frame.panel == "card":
        return _card(frame, width)
    if frame.panel == "history":
        return _history(frame, width)
    if frame.panel == "item":
        if frame.screen == "fitting":
            row = picked_row(frame)
            slot = row.slot if row is not None else None
        else:
            slots = build.pack_slots(frame.content, frame.state)
            slot = slots[frame.selected] if frame.selected is not None and frame.selected < len(slots) else None
        entry = build.entry_at(frame.content, frame.state, slot) if slot is not None else None
        return item_details(frame, entry, width) if entry is not None else []
    if frame.panel != "inspect":
        return []
    seen = world.inspect(frame.content, frame.state)
    if seen is None:
        return []
    lines = [frame.style.role(line, "heading") for line in wrap(seen.title, width)]
    if seen.subtitle:
        lines += styled_lines(seen.subtitle, width, frame, "quiet")
    if seen.text:
        lines.append("")
        for paragraph in seen.text.split("\n"):
            lines += wrap(paragraph, width) if paragraph else [""]
    return lines


def item_details(frame: Frame, entry, width: int) -> List[str]:
    """
    Everything about one item, for the panel: a held or stored item (ItemInst), or a
    design (an item id). Name, kind, slot and grade, condition, description, then
    labelled rows: what it uses and gives, mounts, tags, actions, mod slots, size,
    stack, needs, and what taking it apart, making and repairing involve.
    """
    content, state, ui, style = frame.content, frame.state, frame.ui, frame.style
    design = not isinstance(entry, ItemInst)
    inst = new_item(content, entry) if design else entry
    record = content.get("item", inst.item)
    view = stats.item_view(content, inst)

    title = view["name"] + (f" x{inst.count}" if inst.count > 1 else "")
    lines = [graded(frame, inst.item, line) if record.get("grade") else style.role(line, "heading")
             for line in wrap(title, width)]
    facts = [ui.word(f"kind_{view['kind']}")]
    if view["slot_type"]:
        facts.append(ui.word("slot_named", slot=content.get("slot_type", view["slot_type"])["name"]))
    if record.get("grade"):
        facts.append(content.get("grade", record["grade"])["name"])
    lines += styled_lines(" · ".join(facts), width, frame, "quiet")
    if inst.condition is not None and not design:
        if stats.is_broken(inst):
            lines += styled_lines(ui.word("item_broken"), width, frame, "danger")
        else:
            lines += wrap(ui.word("item_condition", now=inst.condition, top=view["max_condition"]), width)
    if record.get("description"):
        lines.append("")
        lines += wrap(content.text(record["description"]), width)

    rows = []
    uses = [f"{_role_short(content, role)} {amount:g}" for role, amount in view["uses"].items() if amount]
    if uses:
        rows.append((ui.word("item_uses"), uses))
    gives = [f"{_stat_short(content, sid)} {amount:+g}" for sid, amount in view["stats"].items() if amount]
    if gives:
        rows.append((ui.word("item_gives"), gives))
    mounts = [content.get("slot_type", m["slot_type"])["name"] + (f" x{m['count']}" if m.get("count", 1) > 1 else "")
              for m in record.get("slots", ())]
    if mounts:
        rows.append((ui.word("item_mounts"), ", ".join(mounts)))
    if view["tags"]:
        rows.append((ui.word("item_tags"), ", ".join(content.get("tag", t)["name"] for t in view["tags"])))
    if view["actions"]:
        rows.append((ui.word("item_actions"), ", ".join(content.get("action", a)["name"] for a in view["actions"])))
    if record.get("mod_slots"):
        names = [content.get("modification", m)["name"] for m in inst.mods]
        free = ui.word("item_mods_free", free=record["mod_slots"] - len(names), total=record["mod_slots"])
        rows.append((ui.word("item_mods"), ", ".join(names + [free])))
    rows.append((ui.word("item_size"), content.sizes[view["size"]]["name"] if view["size"] in content.sizes
                 else str(view["size"])))
    if view["stack"] > 1:
        rows.append((ui.word("item_stack"), ui.word("item_stack_count", count=view["stack"])))
    needs = _needs(content, record.get("fit_requires"))
    if needs:
        rows.append((ui.word("item_needs"), needs))
    if record.get("salvage"):
        rows.append((ui.word("item_salvage"), _counts(content, record["salvage"]["yields"])))
    if record.get("fabricate"):
        known = record["id"] in state.characters[state.player].designs
        rows.append((ui.word("item_fabricate"), [_counts(content, record["fabricate"]["inputs"]),
                                                 ui.word("design_known" if known else "design_unknown")]))
    if record.get("repair") and record.get("condition"):
        rows.append((ui.word("item_repair"), ui.word("item_repair_amount", items=_counts(content, record["repair"]["inputs"]),
                                                     amount=record["repair"].get("amount", 1))))
    if rows:
        lines.append("")
        lines += _label_rows(frame, rows, width)
    return lines


def _label_rows(frame: Frame, rows, width: int, widest: Optional[int] = None) -> List[str]:
    """
    Rows of 'label  value' with the values in one column. A value is text, or a list of
    entries ('PWR 1', 'MAS 2') that wrap only between entries, never inside one.
    """
    column = min(max(len(label) for label, _ in rows), widest or max(4, width // 3))
    lines = []
    for label, value in rows:
        wrapped = _pack(value, max(1, width - column - 2)) if isinstance(value, list) \
            else wrap(value, max(1, width - column - 2)) or [""]
        lines.append(frame.style.role(label[:column].ljust(column), "quiet") + "  " + wrapped[0])
        lines += [" " * (column + 2) + more for more in wrapped[1:]]
    return lines


def _pack(entries: List[str], width: int, gap: str = "  ") -> List[str]:
    """Entries on as few lines as fit, separated by 'gap'; an entry wider than a line wraps alone."""
    lines: List[str] = []
    for entry in entries:
        if lines and visible_len(lines[-1]) + len(gap) + visible_len(entry) <= width:
            lines[-1] += gap + entry
        else:
            lines += wrap(entry, width)
    return lines or [""]


def _stat_short(content: Content, stat_id: str) -> str:
    record = content.get("stat", stat_id)
    return record.get("short") or record["name"]


def _role_short(content: Content, role: str) -> str:
    stat_id = content.stat_roles.get(role)
    return _stat_short(content, stat_id) if stat_id else role


def _counts(content: Content, entries) -> str:
    return ", ".join(content.get("item", e["item"])["name"] + (f" x{e['count']}" if e.get("count", 1) > 1 else "")
                     for e in entries)


def _needs(content: Content, condition) -> Optional[str]:
    """A fit requirement in words, for the simple cases (skill levels, all of them); otherwise None."""
    if not condition:
        return None
    if condition.get("check") == "skill":
        return f"{content.get('skill', condition['skill'])['name']} {condition['min']}"
    if "all" in condition:
        parts = [_needs(content, part) for part in condition["all"]]
        return ", ".join(parts) if all(parts) else None
    return None


# --- the fitting screen ----------------------------------------------------------------

def picks(content: Content, state: GameState) -> List[int]:
    """The fitting list's rows that can be picked (not empty slots), as indexes into fitting_rows()."""
    return [i for i, row in enumerate(build.fitting_rows(content, state)) if row.slot is not None]


def picked_row(frame: Frame):
    rows = build.fitting_rows(frame.content, frame.state)
    pickable = [i for i, row in enumerate(rows) if row.slot is not None]
    if not pickable:
        return None
    return rows[pickable[max(0, min(frame.selected or 0, len(pickable) - 1))]]


def budgets(frame: Frame, width: int, options: Mapping) -> List[str]:
    """Power, mass, heat and cargo as bars: what the loadout uses of what it provides."""
    content, me = frame.content, frame.state.characters[frame.state.player]
    parts = []
    for role in ("power", "mass", "heat", "cargo"):
        if role not in content.stat_roles:
            continue
        used = len(me.inventory) if role == "cargo" else stats.budget_used(content, me, role)
        top = stats.budget_provided(content, me, role)
        text = f"{_role_short(content, role):<4}{bar(frame, used, top, frame.size['bar_length'])} {used:g}/{top:g}"
        over = used > top or (role == "heat" and used and used >= top)
        parts.append(frame.style.role(text, "danger") if over else text)
    return _pack(parts, width, "   ")


def loadout(frame: Frame, width: int, options: Mapping) -> List[str]:
    """The fitting list: worn by slot (empty slots too), spare gear, designs; the pick highlighted."""
    content, state, style, ui = frame.content, frame.state, frame.style, frame.ui
    if frame.screen != "fitting" or frame.panel is not None:
        return []
    rows = build.fitting_rows(content, state)
    pickable = [i for i, row in enumerate(rows) if row.slot is not None]
    chosen = pickable[max(0, min(frame.selected or 0, len(pickable) - 1))] if pickable else None
    slot_names = [content.get("slot_type", r.slot_type)["name"] for r in rows
                  if r.group == "worn" and r.slot_type not in (None, "frame")]
    name_width = max((len(n) for n in slot_names), default=0)
    lines: List[str] = []
    group = None
    cursor = frame.glyphs["cursor"]
    width -= 1                                         # a gutter for the cursor
    for index, row in enumerate(rows):
        if row.group != group:
            group = row.group
            lines.append(" " + style.role(ui.word(f"fitting_{group}"), "heading"))
        number = f"{pickable.index(index) + 1} " if row.slot is not None else ""
        entry = build.entry_at(content, state, row.slot) if row.slot is not None else None
        right = ""
        if row.group == "worn" and row.slot_type == "frame":
            left = number + (_item_entry(frame, entry) if entry is not None else ui.word("fitting_empty"))
            right = ui.word("fitting_frame_slot")
        elif row.group == "worn":
            label = content.get("slot_type", row.slot_type)["name"].ljust(name_width)
            left = "   " + label + "  " + (number + _item_entry(frame, entry) if entry is not None
                                           else style.role(ui.word("fitting_empty"), "quiet"))
        elif row.group == "spare":
            left = number + _item_entry(frame, entry)
            right = ui.word("fitting_in", container=content.get("placement", row.where)["name"]) if row.where \
                else ui.word("fitting_carried")
        else:
            left = number + graded(frame, entry, content.get("item", entry)["name"])
            right = _counts(content, content.get("item", entry).get("fabricate", {}).get("inputs", ()))
        line = _right(left, style.role(right, "quiet") if right else "", width)
        if index == chosen:
            line = FOCUS + cursor + style.key(pad(_plain(line), width))
        else:
            line = " " + line
        lines.append(line)
    return lines


def _plain(text: str) -> str:
    return ANSI.sub("", text)


def _right(left: str, right: str, width: int) -> str:
    """'left' with 'right' at the end of the line, when both fit; otherwise just 'left'."""
    room = width - visible_len(left) - visible_len(right)
    if right and room >= 2:
        return left + " " * room + right
    return left if visible_len(left) <= width else _plain(left)[:width]


def pick(frame: Frame, width: int, options: Mapping) -> List[str]:
    """The picked entry: what it is, what its action would change, and its keys; or its modifications."""
    content, state, style, ui = frame.content, frame.state, frame.style, frame.ui
    if frame.screen != "fitting" or frame.panel not in (None, "modify"):
        return []
    row = picked_row(frame)
    if row is None:
        return []
    entry = build.entry_at(content, state, row.slot)
    item_id = entry if isinstance(entry, str) else entry.item
    record = content.get("item", item_id)
    opts = build.item_options(content, state, row.slot, ui.bound_keys, "fitting")
    if frame.panel == "modify":
        return _modify_list(frame, row, entry, [o for o in opts if o.kind == "modify"], width)
    view = stats.item_view(content, new_item(content, entry) if isinstance(entry, str) else entry)
    facts = [ui.word(f"kind_{view['kind']}")]
    if view["slot_type"]:
        facts.append(ui.word("slot_named", slot=content.get("slot_type", view["slot_type"])["name"]))
    if record.get("grade"):
        facts.append(content.get("grade", record["grade"])["name"])
    lines = [_item_entry(frame, entry) if not isinstance(entry, str) else graded(frame, entry, record["name"])]
    if not frame.compact:                       # on a short terminal, the list matters more
        lines += styled_lines(" · ".join(facts), width, frame, "quiet")
        status = {"worn": ui.word("fitting_fitted"), "designs": ui.word("fitting_design")}.get(row.group) or (
            ui.word("fitting_in", container=content.get("placement", row.where)["name"]) if row.where
            else ui.word("fitting_carried"))
        lines += styled_lines(status, width, frame, "quiet")
    main = next((o for o in opts if o.kind in ("fit", "remove")), None)
    if main is not None:
        after = build.preview(content, state, row.slot, main.kind)
        # what it would change, when it can happen, or when the budgets are why it can't
        if after is not None and (main.available or main.hint == build.budget_problem(content, after)):
            lines += _change_line(frame, option_text(ui, main), state.characters[state.player], after, width)
    for option in opts:
        if option.kind != "modify":
            lines += option_lines(frame, option, width)
    mods = [o for o in opts if o.kind == "modify"]
    if mods:
        menu = SimpleOption(build.MODIFY_KEY, ui.word("modify_menu"), any(o.available for o in mods),
                            next((o.hint for o in mods if o.hint), None))
        lines += option_lines(frame, menu, width)
    lines.append(f"{style.key(world.MENU_KEYS['inspect'].upper())} {ui.word('details')}")
    return lines


class SimpleOption(NamedTuple):
    """An option the UI adds itself (Modify, Details), drawn like the engine's."""
    key: str
    label: str
    available: bool
    hint: Optional[str]
    kind: str = "ui"
    params: Mapping[str, str] = {}


def _change_line(frame: Frame, action: str, before, after, width: int) -> List[str]:
    """'Fit: PWR 4→5/6  MAS 5→7/10', over-budget numbers in the warning colour; nothing if nothing changes."""
    content = frame.content
    parts = []
    for role in ("health", "power", "mass", "heat", "cargo"):
        if role not in content.stat_roles:
            continue
        if role == "health":
            hb, ha = stats.stat(content, before, content.stat_roles[role]), stats.stat(content, after, content.stat_roles[role])
            if hb != ha:
                parts.append(f"{_role_short(content, role)} {hb:g}→{ha:g}")
            continue
        ub, ua = (len(before.inventory), len(after.inventory)) if role == "cargo" else \
            (stats.budget_used(content, before, role), stats.budget_used(content, after, role))
        pb, pa = stats.budget_provided(content, before, role), stats.budget_provided(content, after, role)
        if (ub, pb) == (ua, pa):
            continue
        text = f"{_role_short(content, role)} {ub:g}→{ua:g}/{pa:g}" if pb == pa else \
            f"{_role_short(content, role)} {ub:g}/{pb:g}→{ua:g}/{pa:g}"
        over = ua > pa or (role == "heat" and ua and ua >= pa)
        parts.append(frame.style.role(text, "danger") if over else text)
    if not parts:
        return []
    head = frame.ui.word("fitting_change", action=action, changes="").rstrip()
    return _pack([head + " " + parts[0]] + parts[1:], width, "  ")


def _modify_list(frame: Frame, row, entry, mods, width: int) -> List[str]:
    """The modifications that apply to the picked item, numbered, each with its cost, what it adds and why not."""
    content, state, style, ui = frame.content, frame.state, frame.style, frame.ui
    lines = [style.role(ui.word("modify_title", item=_item_line(content, entry)), "heading")]
    if not mods:
        return lines + styled_lines(ui.word("modify_none"), width, frame, "quiet")
    me = state.characters[state.player]
    for number, option in enumerate(mods, 1):
        mod = content.get("modification", option.modification)
        cost = content.get("item", mod["material"])["name"] + (f" x{mod['count']}" if mod.get("count", 1) > 1 else "")
        head = _right(f"{number} {mod['name']}", cost, width)
        adds = _adds(frame, mod["adds"])
        after = build.preview(content, state, row.slot, "modify", option.modification)
        change = _change_line(frame, mod["name"], me, after, width - 3) if after is not None else []
        body = _pack(adds, width - 3) + change
        if option.available:
            lines.append(head)
            lines += ["   " + line for line in body]
        else:
            lines.append(style.role(_plain(head), "unavailable"))
            lines += ["   " + style.role(_plain(line), "unavailable") for line in body]
            if option.hint:
                lines += ["   " + line for line in styled_lines(option.hint, width - 3, frame, "unavailable")]
    return lines


def _adds(frame: Frame, adds: Mapping) -> List[str]:
    """What a modification adds, as short entries: 'ARM +1', '+ Burn', '+ an air filter', 'HT use +1'."""
    content, ui = frame.content, frame.ui
    parts = [f"{_stat_short(content, sid)} {v:+g}" for sid, v in adds.get("stats", {}).items()]
    if adds.get("max_condition"):
        parts.append(ui.word("mod_condition", amount=f"{adds['max_condition']:+g}"))
    parts += [f"+ {content.get('action', a)['name']}" for a in adds.get("actions", ())]
    parts += [f"+ {content.get('tag', t)['name']}" for t in adds.get("tags", ())]
    parts += [ui.word("mod_uses", stat=_role_short(content, role), amount=f"{v:+g}") for role, v in adds.get("uses", {}).items()]
    return parts


# --- the character screen --------------------------------------------------------------

def portrait_size(frame: Frame) -> Tuple[int, int]:
    """The art zone in pixels: width (one column each) and height (two per line, rounded to even)."""
    return frame.size["art_width"], frame.size["art_height"] + frame.size["art_height"] % 2


def portrait_width(frame: Frame, options: Mapping) -> int:
    return portrait_size(frame)[0] + (2 if options.get("frame", True) else 0)


def picture_lines(frame: Frame, art_id: Optional[str], stand_in: str, framed: bool) -> List[str]:
    """
    A picture from the pack's art in half-block pixels, centred in the art zone and cut to
    it; without one, 'stand_in' (an initial, a glyph) in the middle.
    """
    pw, ph = portrait_size(frame)
    picture = frame.content.get("art", art_id) if art_id else None
    grid = pixels.centred(picture["rows"], picture["palette"], pw, ph) if picture else [[None] * pw for _ in range(ph)]
    lines = pixels.half_blocks(frame.style, grid)
    if not picture:                                             # the place kept: the stand-in in the middle
        middle = len(lines) // 2
        lines[middle] = pad(" " * ((pw - 1) // 2) + stand_in, pw)
    if not framed:
        return lines
    border = frame.glyphs["border"]
    edge = border["horizontal"] * pw
    return ([border["top_left"] + edge + border["top_right"]]
            + [border["vertical"] + line + border["vertical"] for line in lines]
            + [border["bottom_left"] + edge + border["bottom_right"]])


def portrait(frame: Frame, width: int, options: Mapping) -> List[str]:
    """The player's picture (the speaker's in a conversation), in the art zone; their initial without one."""
    whose = speaker_of(frame) if frame.screen == "talk" else frame.state.player
    record = frame.content.get("character", frame.state.characters[whose].source)
    return picture_lines(frame, record.get("art"), record["name"][0], options.get("frame", True))


def identity(frame: Frame, width: int, options: Mapping) -> List[str]:
    """Name, title, faction and rank, then the pool bars; in a conversation, the speaker and their trust."""
    content, state, ui = frame.content, frame.state, frame.ui
    if frame.screen == "talk":
        return _speaker(frame, width)
    me = state.characters[state.player]
    record = content.get("character", me.source)
    lines = [frame.style.role(line, "heading") for line in wrap(record["name"], width)]
    if record.get("title"):
        lines += styled_lines(content.text(record["title"]), width, frame, "quiet")
    facts = []
    if record.get("faction"):
        facts.append(content.get("faction", record["faction"])["name"])
    facts.append(_rank_name(content, me.rank))
    lines += styled_lines(" · ".join(facts), width, frame, "quiet")
    lines.append("")
    pools = [sid for sid, rec in content.all("stat").items() if rec.get("kind") == "pool"]
    return lines + _pool_lines(frame, me, pools, width)


def speaker_of(frame: Frame) -> str:
    """Who the player is talking to: the character in focus."""
    focus = frame.state.focus
    return focus[1] if focus and focus[0] == "character" else frame.state.player


def _speaker(frame: Frame, width: int) -> List[str]:
    """The speaker's name, title and faction, then how they regard you: the level, the number and a bar."""
    content, state, ui, style = frame.content, frame.state, frame.ui, frame.style
    who = speaker_of(frame)
    record = content.get("character", state.characters[who].source)
    lines = [style.role(line, "heading") for line in wrap(record["name"], width)]
    if record.get("title"):
        lines += styled_lines(content.text(record["title"]), width, frame, "quiet")
    if record.get("faction"):
        lines += styled_lines(content.get("faction", record["faction"])["name"], width, frame, "quiet")
    from engine.state import char_key
    value = context.relation(content, state, char_key(who), char_key(state.player))
    low, high = content.settings.get("relation_min", -100), content.settings.get("relation_max", 100)
    lines.append("")
    lines += wrap(ui.word("talk_trust", level=_relation_name(content, value), value=value), width)
    lines.append(bar(frame, value - low, high - low, frame.size["bar_length"]))
    return lines


def conversation(frame: Frame, width: int, options: Mapping) -> List[str]:
    """The last exchanges, the speaker's current line, your numbered responses with what trades give and take, Leave."""
    content, state, ui, style = frame.content, frame.state, frame.ui, frame.style
    if frame.screen != "talk":
        return []
    who = speaker_of(frame)
    lines: List[str] = []
    for message in frame.log:
        if message.kind == "response":
            lines += styled_lines(ui.word("talk_you", response=message.text), width, frame, "heading")
        else:
            lines += message_lines(frame, [message], width)
    if lines:
        lines.append("")
    line = world.talk_line(content, state, who)
    if line is not None:
        name = content.get("character", state.characters[who].source)["name"]
        lines += styled_lines(ui.word("talk_says", name=name, text=content.text(line["text"])), width, frame, "quiet")
        lines.append("")
    for number, option in enumerate(responses(frame), 1):
        text = f"{number} {option_text(ui, option)}"
        if option.available:
            lines += hang(text, width, len(str(number)) + 1)
        else:
            lines += [style.role(line, "unavailable")
                      for line in hang(text + (f" - {option.hint}" if option.hint else ""), width, len(str(number)) + 1)]
        if options.get("trades", True) and option.interaction is not None:
            gives, gets = exchange(content, option.interaction)
            rows = ([(ui.word("talk_give"), gives)] if gives else []) + ([(ui.word("talk_get"), gets)] if gets else [])
            if rows:
                lines += ["    " + row for row in _label_rows(frame, rows, width - 4)]
    leave = f"{len(responses(frame)) + 1} {ui.word('talk_leave')}"
    lines.append(FOCUS + leave)                      # the newest lines stay in view
    return lines


def responses(frame: Frame) -> List:
    """What the player can answer: the speaker's interactions, as the menu offers them."""
    current = world.menu(frame.content, frame.state, frame.ui.bound_keys)
    return [o for o in current.options if o.kind == "interaction"] if current else []


def exchange(content: Content, interaction: Mapping) -> Tuple[List[str], List[str]]:
    """
    What an interaction takes from you and gives you, read from its own take_item and
    give_item effects (in a character's interactions 'self' is you, 'target' them).
    """
    gives, gets = [], []
    for effect in interaction.get("effects", ()):
        if effect["op"] not in ("take_item", "give_item") or "item" not in effect:
            continue
        mine = effect.get("subject", "self") == "self"
        count = effect.get("count", 1)
        amount = f"{count['min']}-{count['max']}" if isinstance(count, Mapping) and "min" in count else count
        text = content.get("item", effect["item"])["name"] + (f" x{amount}" if amount != 1 else "")
        (gives if (effect["op"] == "take_item") == mine else gets).append(text)
    return gives, gets


def _rank_name(content: Content, rank: int) -> str:
    return next((r["name"] for r in content.ranks if r["rank"] == rank), str(rank))


def skills(frame: Frame, width: int, options: Mapping) -> List[str]:
    """Each skill: level, progress to the next level as a bar, and what the next level brings."""
    content, state, style, ui = frame.content, frame.state, frame.style, frame.ui
    me = state.characters[state.player]
    lines = [style.role(ui.word("skills_heading"), "heading")]
    if not me.skills:
        return lines + styled_lines(ui.word("skills_none"), width, frame, "quiet")
    top = content.settings["skill_max_level"]
    for skill_id, level in me.skills.items():
        skill = content.get("skill", skill_id)
        xp = me.xp.get(skill_id, 0)
        ahead = sorted((lv for lv in skill["levels"] if level < lv["level"] <= top), key=lambda lv: lv["level"])
        reached = max((lv["xp"] for lv in skill["levels"] if lv["level"] <= level), default=0)
        name = f"{skill['name']} {level}"
        if ahead:
            goal = ahead[0]["xp"]
            progress = f"{bar(frame, xp - reached, goal - reached, frame.size['bar_length'])} {xp}/{goal}"
            lines.append(_right(name, progress, width))
            nxt = ui.word("skill_next", level=ahead[0]["level"], text=content.text(ahead[0]["text"]))
            lines += ["  " + line for line in styled_lines(nxt, width - 2, frame, "quiet")]
        else:
            lines.append(_right(name, style.role(ui.word("skill_top"), "quiet"), width))
    return lines


def stats_widget(frame: Frame, width: int, options: Mapping) -> List[str]:
    """The derived stats in columns, then conditions with the turns they have left."""
    content, state, style, ui = frame.content, frame.state, frame.style, frame.ui
    me = state.characters[state.player]
    lines = ["", style.role(ui.word("stats_heading"), "heading")]
    entries = [f"{_stat_short(content, sid)} {stats.stat(content, me, sid):g}"
               for sid, rec in content.all("stat").items() if rec.get("kind") != "pool"]
    cell = max((len(e) for e in entries), default=0) + 2      # aligned columns
    lines += [line.rstrip() for line in _pack([e.ljust(cell) for e in entries], width, "")] if entries else []
    lines.append("")
    lines.append(style.role(ui.word("conditions_heading"), "heading"))
    if not me.statuses:
        return lines + styled_lines(ui.word("conditions_none"), width, frame, "quiet")
    for inst in me.statuses:
        record = content.get("status", inst.status)
        name = record["name"] + (f" x{inst.stacks}" if inst.stacks > 1 else "")
        left = ui.word("condition_turns", turns=_turns(ui, inst.turns_left)) if inst.turns_left is not None else ""
        line = _right(name, style.role(left, "quiet") if left else "", width)
        lines.append(style.role(_plain(line), "danger") if record.get("harmful", True) else line)
    return lines


def people(frame: Frame, width: int, options: Mapping) -> List[str]:
    """Who travels with you, with their health; then your rank and how the factions regard you."""
    content, state, style, ui = frame.content, frame.state, frame.style, frame.ui
    lines = ["", style.role(ui.word("party_heading"), "heading")]
    party = context.party_of(state, state.player)[1:]
    if not party:
        lines += styled_lines(ui.word("party_alone"), width, frame, "quiet")
    health = content.stat_roles.get("health")
    for cid in party:
        cs = state.characters[cid]
        name = content.get("character", cs.source)["name"]
        if cs.down:
            lines.append(_right(name, style.role(ui.word("party_down"), "danger"), width))
        elif health:
            now, top = stats.current(content, cs, health), stats.stat(content, cs, health)
            lines.append(_right(name, f"{bar(frame, now, top, frame.size['bar_length'])} {int(now)}/{int(top)}", width))
    lines.append("")
    lines.append(style.role(ui.word("standing_heading"), "heading"))
    me = state.characters[state.player]
    lines += wrap(ui.word("standing_rank", rank=_rank_name(content, me.rank)), width)
    from engine.state import char_key, faction_key
    for faction_id, faction in content.all("faction").items():
        value = context.relation(content, state, faction_key(faction_id), char_key(state.player))
        lines += wrap(ui.word("standing_view", faction=faction["name"], level=_relation_name(content, value),
                              value=value), width)
    return lines


def _relation_name(content: Content, value: int) -> str:
    levels = content.relation_levels
    name = levels[0]["name"] if levels else ""
    for level in levels:
        if value >= level["min"]:
            name = level["name"]
    return name


# --- around the game -------------------------------------------------------------------

def start_menu(frame: Frame, width: int, options: Mapping) -> List[str]:
    """The start screen's choices, numbered, the pick marked; Continue shows what it resumes."""
    from tui import shell as shell_mod
    ui, style = frame.ui, frame.style
    lines = [""]
    last = shell_mod.last_played(frame.shell.slots)
    for index, entry in enumerate(frame.shell.entries):
        text = f"{index + 1} {ui.word('start_' + entry)}"
        if index == frame.selected:
            lines.append(FOCUS + "  " + frame.glyphs["cursor"] + style.key(text))
        else:
            lines.append("   " + text)
        if entry == "continue" and last is not None:
            lines += ["     " + line for line in styled_lines(_slot_words(frame, last), width - 5, frame, "quiet")]
    return lines + [""]


def _slot_words(frame: Frame, slot) -> str:
    ui = frame.ui
    name = ui.word("slot_name", number=slot.number)
    if not slot.used:
        return f"{name} · {ui.word('slot_empty')}"
    if not slot.readable:
        return f"{name} · {ui.word('slot_unreadable')}"
    return f"{name} · " + ui.word("slot_where", place=slot.place, day=slot.day, phase=slot.phase)


def description(frame: Frame, width: int, options: Mapping) -> List[str]:
    """The game pack's description."""
    text = frame.content.pack.get("description")
    return styled_lines(frame.content.text(text), width, frame, "quiet") if text else []


def slots(frame: Frame, width: int, options: Mapping) -> List[str]:
    """The save slots: where and when each was saved, or empty; the pick marked."""
    ui, style = frame.ui, frame.style
    lines = styled_lines(ui.word("slots_new_note"), width, frame, "quiet") + [""] if frame.shell.mode == "new" else []
    for index, slot in enumerate(frame.shell.slots):
        name = ui.word("slot_name", number=slot.number)
        if not slot.used:
            where = style.role(ui.word("slot_empty"), "quiet")
        elif not slot.readable:
            where = style.role(ui.word("slot_unreadable"), "danger")
        else:
            where = ui.word("slot_where", place=slot.place, day=slot.day, phase=slot.phase)
        head = f"{index + 1} {name}"
        line = head + "   " + where
        if index == frame.selected:
            lines.append(FOCUS + frame.glyphs["cursor"] + style.key(_plain(line)[:width - 1]))
        else:
            lines.append(" " + line if visible_len(line) < width else " " + _plain(line)[:width - 1])
        if slot.saved:
            lines.append("    " + style.role(ui.word("slot_saved", when=slot.saved), "quiet"))
    return lines


def help_widget(frame: Frame, width: int, options: Mapping) -> List[str]:
    """The keys, generated from the bindings; then how the interface works, then the game's own help."""
    ui, style, content = frame.ui, frame.style, frame.content
    keys = ui.bindings
    arrows, escape = ui.word("key_arrows"), ui.word("key_escape")
    move = "".join(keys[a].upper() for a in ("move_north", "move_west", "move_south", "move_east"))
    rows = [(f"{move}, {arrows}", ui.word("key_move"))]
    for action in ("wait", "pack", "fitting", "character", "map", "history", "next_page", "quit"):
        if action in keys:
            rows.append((keys[action].upper(), ui.word(f"key_{action}")))
    rows.append((f"{keys['close'].upper()}, {escape}", ui.word("key_close")))
    rows.append(("1-9", ui.word("key_digits")))
    lines = [style.role(ui.word("help_keys"), "heading")]
    lines += ["  " + line for line in _label_rows(frame, rows, width - 2, (width - 2) // 2)]
    lines += ["", style.role(ui.word("help_how"), "heading")]
    lines += ["  " + line for line in wrap(ui.word("help_interface"), width - 2)]
    if content.pack.get("help"):
        lines += ["", style.role(content.pack["name"], "heading")]
        lines += ["  " + line for line in wrap(content.text(content.pack["help"]), width - 2)]
    return lines


def question(frame: Frame, width: int, options: Mapping) -> List[str]:
    """The quit question."""
    return ([frame.style.role(line, "heading") for line in wrap(frame.ui.word("quit_question"), width)]
            + styled_lines(frame.ui.word("quit_saved"), width, frame, "quiet"))


# --- encounter widgets -----------------------------------------------------------------

def art_width(frame: Frame, options: Mapping) -> int:
    return portrait_size(frame)[0] + (2 if options.get("frame", True) and not frame.compact else 0)


def art(frame: Frame, width: int, options: Mapping) -> List[str]:
    """The enemy in front, in the art zone; its glyph without a picture."""
    state, content = frame.state, frame.content
    enemies = encounter.living(state, "enemies") if state.encounter is not None else []
    record = content.get("character", state.characters[enemies[0]].source) if enemies else {}
    stand_in = record.get("glyph") or record.get("name", " ")[0]
    lines = picture_lines(frame, record.get("art"), stand_in, options.get("frame", True) and not frame.compact)
    return [line if visible_len(line) <= width else ANSI.sub("", line)[:width] for line in lines]


def fighters(frame: Frame, width: int, options: Mapping) -> List[str]:
    """
    Both sides with health bars and statuses (rounds left), and the enemies' intents.
    While picking a target, the possible targets carry the cursor glyph and their number.
    """
    content, state, style = frame.content, frame.state, frame.style
    health = content.stat_roles["health"]
    length = frame.size["fighter_bar_length"]
    aims = _targets(frame)
    cursor = frame.glyphs["cursor"]

    def mark(cid: str, number: str) -> str:
        """The number column: a space for the cursor, so picking a target doesn't move the layout."""
        if aims is None or cid not in aims:
            return " " + number if aims is None else " " * (len(number) + 1)
        return f"{cursor}{aims.index(cid) + 1}"

    lines = []
    for cid in encounter.living(state, "allies"):
        cs = state.characters[cid]
        name = content.get("character", cs.source)["name"][:10]
        prefix = f"{cursor}{aims.index(cid) + 1} " if aims and cid in aims else ""
        lines.append(f"{prefix}{name:<10} {bar(frame, stats.current(content, cs, health), stats.stat(content, cs, health), length)}")
        lines += _status_line(frame, cs, width, None)
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
        line = f"{mark(cid, str(number))} {name:<8} {bar(frame, now, top, length)} {int(now)}"
        lines.append(line)
        intent = encounter.intent_line(content, state, cid) if options.get("intent", True) else None
        lines += _status_line(frame, cs, width, intent)
    return [line[:width] if visible_len(line) == len(line) else line for line in lines]


def _targets(frame: Frame) -> Optional[List[str]]:
    """While picking a target: who the picked action can be aimed at, in number order; otherwise None."""
    if frame.screen != "encounter" or frame.panel != "target" or frame.selected is None:
        return None
    tile_list = encounter.tiles(frame.content, frame.state)
    if frame.selected >= len(tile_list):
        return None
    return encounter.targets(frame.content, frame.state, frame.state.player, tile_list[frame.selected].action)


def _status_line(frame: Frame, cs, width: int, intent: Optional[str]) -> List[str]:
    """'Burning 2 · ⚠ STRIKE Juno' under a fighter: statuses with rounds left, then the intent."""
    content, style = frame.content, frame.style
    parts = []
    for inst in cs.statuses:
        record = content.get("status", inst.status)
        text = record["name"] + (f" x{inst.stacks}" if inst.stacks > 1 else "") + \
            (f" {inst.turns_left}" if inst.turns_left is not None else "")
        parts.append(style.role(text, "danger") if record.get("harmful", True) else text)
    if intent:
        parts.append(style.role(f"{frame.glyphs['intent']} {intent}", "danger"))
    if not parts:
        return []
    line = "  " + frame.glyphs["separator"].join(parts)
    return [line] if visible_len(line) <= width else ["  " + part for part in parts]


def _tile_cost(frame: Frame, tile) -> str:
    """'▲3-4 ⟳2 ×1': heat, cooldown, and uses left this fight."""
    action = frame.content.get("action", tile.action)
    cost = action.get("cost", {})
    parts = [f"{frame.glyphs['cost']}{tile.cost}"] if tile.cost else []
    if cost.get("cooldown"):
        parts.append(f"{frame.glyphs['cooldown']}{cost['cooldown']}")
    if cost.get("charges"):
        used = frame.state.encounter.charges.get(frame.state.player, {}).get(tile.action, 0)
        parts.append(f"{frame.glyphs['charges']}{max(0, cost['charges'] - used)}")
    return " ".join(parts)


def tiles(frame: Frame, width: int, options: Mapping) -> List[str]:
    """
    Action tiles as boxes: the number in the top border, the name inside, costs as symbols;
    the picked tile with the heavy border. Compact, a wrapped list ('1 Strike ▲1  2 Guard ▲1').
    """
    tile_list = encounter.tiles(frame.content, frame.state)
    picked = frame.selected if frame.screen == "encounter" else None
    if frame.compact:
        lines: List[str] = []
        for index, tile in enumerate(tile_list):
            cost = _tile_cost(frame, tile)
            mark = frame.glyphs["cursor"] if index == picked else ""
            entry = f"{mark}{tile.key} {tile.label}" + (f" {cost}" if cost else "")
            entry = entry[:width] if tile.available else frame.style.role(entry[:width], "unavailable")
            if index == picked:
                entry = frame.style.key(_plain(entry))
            if lines and visible_len(lines[-1]) + 2 + visible_len(entry) <= width:
                lines[-1] += "  " + entry
            else:
                lines.append(entry)
        return lines
    tile_width = frame.size["tile_width"]
    per_row = options.get("per_row", 0) or max(1, width // tile_width)
    per_row = min(per_row, max(1, width // tile_width))
    inner = tile_width - 2
    lines = []
    for start in range(0, len(tile_list), per_row):
        parts: List[List[str]] = [[], [], [], []]
        for index, tile in enumerate(tile_list[start:start + per_row], start):
            box = frame.glyphs["border_picked"] if index == picked else frame.glyphs["border"]
            paint = (lambda t: t) if tile.available else (lambda t: frame.style.role(t, "unavailable"))
            if index == picked:
                paint = (lambda t: frame.style.key(t)) if tile.available else paint
            top = box["horizontal"] * inner
            top = (tile.key + top)[:inner]                     # the number sits in the top border
            parts[0].append(box["top_left"] + top + box["top_right"])
            parts[1].append(paint(box["vertical"] + tile.label[:inner].ljust(inner) + box["vertical"]))
            parts[2].append(paint(box["vertical"] + _tile_cost(frame, tile)[:inner].ljust(inner) + box["vertical"]))
            parts[3].append(box["bottom_left"] + box["horizontal"] * inner + box["bottom_right"])
        lines += ["".join(p) for p in parts]
    return lines


def action(frame: Frame, width: int, options: Mapping) -> List[str]:
    """The picked action's details: name, costs, what it does in words, and why it can't be used if it can't."""
    content, state, style, ui = frame.content, frame.state, frame.style, frame.ui
    if frame.screen != "encounter" or frame.selected is None or frame.panel == "target":
        return []
    tile_list = encounter.tiles(content, state)
    if frame.selected >= len(tile_list):
        return []
    tile = tile_list[frame.selected]
    record = content.get("action", tile.action)
    lines = [style.role(line, "heading") for line in wrap(record["name"], width)]
    costs = _action_costs(frame, record, tile)
    lines += [style.role(line, "quiet") for line in _pack(costs, width, " · ")]
    if record.get("description"):
        lines += wrap(content.text(record["description"]), width)
    said = _describe(frame, record["effects"], record.get("target", "enemy"))
    if said:
        text = "; ".join(said)
        lines += wrap(text[0].upper() + text[1:] + ".", width)
    if not tile.available:
        lines += styled_lines(ui.word("action_unusable", why=tile.hint or ""), width, frame, "danger")
    return lines


def _action_costs(frame: Frame, record: Mapping, tile) -> List[str]:
    content, ui = frame.content, frame.ui
    cost = record.get("cost", {})
    parts = []
    if tile.cost:
        parts.append(ui.word("cost_heat", amount=tile.cost))
    if cost.get("cooldown"):
        parts.append(ui.word("cost_cooldown", rounds=_rounds(ui, cost["cooldown"])))
    if cost.get("charges"):
        used = frame.state.encounter.charges.get(frame.state.player, {}).get(tile.action, 0)
        parts.append(ui.word("cost_charges", left=max(0, cost["charges"] - used), total=cost["charges"]))
    consumes = cost.get("consumes")
    if consumes:
        what = content.get("item", consumes["item"])["name"] if consumes.get("item") else content.get("tag", consumes["tag"])["name"]
        parts.append(ui.word("cost_consumes", items=what + (f" x{consumes['count']}" if consumes.get("count", 1) > 1 else "")))
    if record.get("priority", 0) > 0:
        parts.append(ui.word("act_early"))
    elif record.get("priority", 0) < 0:
        parts.append(ui.word("act_late"))
    return parts or [ui.word("cost_free")]


def _turns(ui: UI, count) -> str:
    """'1 turn', '3 turns'."""
    return ui.word("turns_one") if count == 1 else ui.word("turns_many", count=count)


def _rounds(ui: UI, count) -> str:
    """'1 round', '3 rounds'."""
    return ui.word("rounds_one") if count == 1 else ui.word("rounds_many", count=count)


def _amount_words(content: Content, amount) -> str:
    """A number, a range '2-4', or a scaled value '0.5×PWR+2' / '2×Salvage'."""
    if isinstance(amount, (int, float)):
        return f"{amount:g}"
    if "min" in amount:
        return f"{amount['min']:g}-{amount['max']:g}"
    source = _stat_short(content, amount["stat"]) if amount.get("stat") else content.get("skill", amount["skill"])["name"]
    times, plus = amount.get("times", 1), amount.get("plus", 0)
    return f"{times:g}×{source}" + (f"+{plus:g}" if plus else "")


def _describe(frame: Frame, effects, target_kind: str) -> List[str]:
    """What effects do, in words: damage, statuses, stat changes, restoring, ending the fight, chances."""
    content, ui = frame.content, frame.ui
    said = []
    for effect in effects:
        op = effect["op"]
        aimed = effect.get("subject", "target" if op in ("damage", "apply_status") else "self")
        who = ui.word("target_self") if aimed == "self" else ui.word(f"target_{target_kind}") \
            if target_kind != "self" else ui.word("target_self")
        if op == "damage":
            said.append(ui.word("act_damage", amount=_amount_words(content, effect["amount"]),
                                type=content.get("damage_type", effect["damage_type"])["name"].lower(), target=who))
        elif op == "apply_status":
            said.append(ui.word("act_status", status=content.get("status", effect["status"])["name"],
                                rounds=_rounds(ui, effect.get("duration", "?")), target=who))
        elif op == "modify_stat":
            amount = _amount_words(content, effect["amount"])
            amount = amount if amount.startswith("-") else "+" + amount
            stat = _stat_short(content, effect["stat"])
            said.append(ui.word("act_stat", stat=stat, amount=amount, rounds=_rounds(ui, effect["duration"]), target=who)
                        if effect.get("duration") else ui.word("act_stat_lasting", stat=stat, amount=amount, target=who))
        elif op == "restore":
            said.append(ui.word("act_restore", stat=_stat_short(content, effect["stat"]),
                                amount=_amount_words(content, effect["amount"]), target=who))
        elif op == "remove_status":
            said.append(ui.word("act_end_status", status=content.get("status", effect["status"])["name"], target=who))
        elif op == "end_encounter":
            said.append(ui.word("act_escape") if effect.get("result") == "escaped" else ui.word("act_end"))
        elif op == "if" and effect["if"].get("check") == "chance":
            then = _describe(frame, effect.get("then", ()), target_kind)
            if then:
                said.append(ui.word("act_chance", percent=round(effect["if"]["p"] * 100), then=", ".join(then)))
    return said


# --- the map ---------------------------------------------------------------------------

def _shown_map(frame: Frame) -> atlas.RegionMap:
    regions = atlas.regions(frame.content, frame.state)
    return atlas.region_map(frame.content, frame.state, regions[frame.page % len(regions)])


def _map_glyph(frame: Frame, kind: str) -> str:
    style, glyphs = frame.style, frame.glyphs
    if kind == "here":
        return style.role(glyphs["player"], "map_player")
    if kind == "visited":
        return style.role(glyphs["place"], "map_exit")
    return style.role(glyphs["unexplored"], "quiet")


def region_map(frame: Frame, width: int, options: Mapping) -> List[str]:
    """The region's places and the ways between neighbours (lib.graph), the cursor's cell drawn inverse."""
    shown = _shown_map(frame)
    cursor = frame.cursor or atlas.start_cell(frame.content, frame.state, shown)
    across, _ = graph.fit(width, 2)
    last = graph.extent(list(shown.places) + [cursor])
    start = graph.origin(cursor, (0, 0), across, last[1] + 1)
    glyphs = {cell: _map_glyph(frame, place.kind) for cell, place in shown.places.items()}
    glyphs[cursor] = frame.style.inverse(_plain(glyphs.get(cursor, "·")))   # inverse shows without colour too
    lines = graph.draw(glyphs, shown.links, start, across, last[1] + 1, last)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def map_place(frame: Frame, width: int, options: Mapping) -> List[str]:
    """The place under the cursor: its name, whether you've been, where its exits lead; then the legend."""
    content, state, style, ui = frame.content, frame.state, frame.style, frame.ui
    shown = _shown_map(frame)
    cursor = frame.cursor or atlas.start_cell(content, state, shown)
    lines: List[str] = []
    place = shown.places.get(cursor)
    if place is not None:
        lines.append(style.role(content.get("location", place.location)["name"], "heading"))
        lines += styled_lines(ui.word(f"map_{place.kind}"), width, frame, "quiet")
        if place.kind != "known":
            leads = [content.get("location", dest)["name"] for dest in atlas.exits(content).get(place.location, [])]
            if leads:
                lines += wrap(ui.word("map_leads", places=", ".join(leads)), width)
    me = state.characters[state.player]
    if content.get("location", me.location)["region"] == shown.region \
            and not any(p.kind == "here" for p in shown.places.values()):
        lines += styled_lines(ui.word("map_nowhere"), width, frame, "quiet")
    if shown.elsewhere:
        names = ", ".join(content.get("location", dest)["name"] for dest in shown.elsewhere)
        lines += styled_lines(ui.word("map_elsewhere", places=names), width, frame, "quiet")
    if options.get("legend", True):
        parts = [_map_glyph(frame, kind) + " " + style.role(ui.word(f"map_legend_{kind}"), "hint")
                 for kind in ("here", "visited", "known")]
        lines += _pack(parts, width, frame.glyphs["separator"])
    return lines


# --- keys ------------------------------------------------------------------------------

def hint_context(frame: Frame) -> str:
    state = frame.state
    if frame.screen in SHELL or frame.screen == "quit":
        return frame.screen
    if frame.screen == "debrief":
        return "debrief"
    if frame.screen == "fitting":
        return {"item": "item", "modify": "modify"}.get(frame.panel, "fitting")
    if state.pending is not None:
        return "choice"
    if frame.screen == "encounter":
        if frame.panel == "target":
            return "target"
        return "picked" if frame.selected is not None else "encounter"
    if frame.panel == "pack":
        return "pack"
    if frame.screen == "character":
        return "sheet"
    if frame.screen == "map":
        return "map"
    if frame.screen == "talk":
        return "talk"
    if frame.panel == "inspect":
        return "panel"
    if frame.panel == "card":
        return "choice" if state.pending is not None else "card"
    if frame.panel == "history":
        return "history"
    if frame.panel == "item":
        return "item"
    if world.menu(frame.content, state, frame.ui.bound_keys) is not None:
        return "menu"
    return "walk"


def _numbered(frame: Frame, context: str) -> int:
    """How many numbered entries the context offers: what the digit keys can pick."""
    content, state = frame.content, frame.state
    if context == "choice":
        return len(state.pending.options)
    if context == "start":
        return len(frame.shell.entries)
    if context == "slots":
        return len(frame.shell.slots)
    if context in ("encounter", "picked"):
        return len(encounter.tiles(content, state))
    if context == "target":
        tile = encounter.tiles(content, state)[frame.selected]
        return len(encounter.targets(content, state, state.player, tile.action))
    if context == "fitting":
        return min(9, len(picks(content, state)))
    if context == "talk":
        return min(9, len(responses(frame)) + 1)
    if context == "modify":
        row = picked_row(frame)
        return len([o for o in build.item_options(content, state, row.slot, frame.ui.bound_keys, "fitting")
                    if o.kind == "modify"]) if row else 0
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
        if hint.get("picked"):
            if frame.selected is not None:
                parts.append(f"{frame.selected + 1} {label}")
        elif hint.get("digits"):
            count = _numbered(frame, context)
            if count:
                parts.append(f"{'1' if count == 1 else f'1-{count}'} {label}")
        elif hint.get("actions"):
            if _works(frame, context, hint["actions"]):
                parts.append("".join(_key_name(frame, a, hint.get("arrows", False)) for a in hint["actions"])
                             + f" {label}")
        else:
            parts.append(label)
    lines: List[str] = []
    for part in parts:                                # wrap between hints, never inside one
        if lines and visible_len(lines[-1]) + 2 + visible_len(part) <= width:
            lines[-1] += "  " + part
        else:
            lines += wrap(part, width)
    return [frame.style.role(line, "hint") for line in lines]


ARROWS = {"move_north": "north", "move_south": "south", "move_west": "west", "move_east": "east"}


def _key_name(frame: Frame, action: str, arrows: bool) -> str:
    if arrows and action in ARROWS:
        return frame.glyphs["arrows"][ARROWS[action]]
    return frame.ui.bindings[action].upper()


def _works(frame: Frame, context: str, actions) -> bool:
    """Whether a hint's keys do anything right now: scrolling needs something to scroll, paging more pages."""
    scrolling = set(actions) <= {"move_north", "move_south", "next_page"}
    if context == "fitting" and scrolling:
        return len(picks(frame.content, frame.state)) > 1
    if context == "map":
        return "next_page" not in actions or len(atlas.regions(frame.content, frame.state)) > 1
    if context in ("talk", "card", "choice", "history", "help") and scrolling:
        return frame.scrollable
    if not scrolling or context not in ("panel", "item", "sheet", "pack"):
        return True
    if context == "pack":
        return len(build.pack_slots(frame.content, frame.state)) > frame.size["page_size"]
    return frame.scrollable


WIDGETS: Dict[str, Draw] = {
    "title": title, "grid": grid, "status": status, "legend": legend, "log": log, "menu": menu,
    "choice": choice, "board": board, "tiles": tiles, "fighters": fighters,
    "art": art, "keys": keys, "panel": panel, "budgets": budgets, "loadout": loadout, "pick": pick,
    "portrait": portrait, "identity": identity, "skills": skills, "stats": stats_widget, "people": people,
    "conversation": conversation, "action": action, "start_menu": start_menu, "description": description,
    "slots": slots, "help": help_widget, "question": question, "region_map": region_map, "map_place": map_place,
}

# Widgets with a natural width of their own (the rest take the width they're given).
NATURAL_WIDTH: Dict[str, Callable[[Frame, Mapping], int]] = {"grid": grid_width, "art": art_width,
                                                              "portrait": portrait_width}
