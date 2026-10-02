"""
The six-zone screen, drawn from content and state. A pure function: the same state
always draws the same frame. Every word on screen comes from the pack.

  1 header: location, region, hazards       4 legend: what each glyph is
  2 the room grid  | 3 status panel          5 messages, then the menu, choice or panel
                                             6 key hints
"""
from typing import List, Optional

from engine import build, context, craft, encounter, stats, world
from engine.content import Content
from engine.state import GameState, day_of, phase_of
from tui.text import ANSI, Style, pad, visible_len, wrap

MIN_COLUMNS, MIN_ROWS = 40, 20


def render(content: Content, state: GameState, columns: int, rows: int = 60,
           panel: Optional[str] = None, colour: bool = True, selected: Optional[int] = None,
           page: int = 0) -> str:
    style = Style(colour)
    if columns < MIN_COLUMNS or rows < MIN_ROWS:
        return content.message("terminal_too_small", columns=MIN_COLUMNS, rows=MIN_ROWS) + "\n"
    inner = columns - 2
    if state.encounter is not None:
        return _render_encounter(content, state, inner, style, selected)
    player = state.characters[state.player]
    location = content.get("location", player.location)

    out: List[str] = [_rule("┌", "┐", inner)]
    out += _box(_header(content, location, inner, style), inner)
    out.append(_rule("├", "┤", inner))
    grid_lines = _grid(content, state, location, style)
    grid_width = visible_len(grid_lines[0])
    side_width = inner - grid_width - 1
    side = _status(content, state, side_width, style)
    for i in range(max(len(grid_lines), len(side))):
        left = grid_lines[i] if i < len(grid_lines) else " " * grid_width
        right = side[i] if i < len(side) else ""
        out.append(f"│{left}│{pad(right, side_width)}│")
    out.append(_rule("├", "┤", inner))
    out += _box(_legend(content, state, location, inner, style), inner)
    out.append(_rule("├", "┤", inner))
    out += _box(_messages(content, state, inner, panel, style, selected, page), inner)
    out.append(_rule("├", "┤", inner))
    out += _box(_hints(content, state, inner, style, panel), inner)
    out.append(_rule("└", "┘", inner))
    return "\n".join(out) + "\n"


def _rule(left: str, right: str, inner: int) -> str:
    return left + "─" * inner + right


def _box(lines: List[str], inner: int) -> List[str]:
    return [f"│{pad(' ' + line, inner)}│" for line in lines]


# --- Encounters ------------------------------------------------------------------------

TILE = 10  # width of one action tile


def _render_encounter(content: Content, state: GameState, inner: int, style: Style,
                      selected: Optional[int]) -> str:
    """Zone 2 shows the target's picture, zone 3 both sides with intents, zone 4 the action tiles."""
    enc = state.encounter
    record = content.get("encounter", enc.id)
    out: List[str] = [_rule("┌", "┐", inner)]
    out += _box([style.bold(content.message("encounter_round", encounter=record["name"], round=enc.round))], inner)
    out.append(_rule("├", "┤", inner))
    enemies = encounter.living(state, "enemies")
    art = _art(content, state, enemies[0] if enemies else None)
    art_width = max(visible_len(line) for line in art)
    side = _fighters(content, state, inner - art_width - 1, style)
    for i in range(max(len(art), len(side))):
        left = art[i] if i < len(art) else " " * art_width
        out.append(f"│{left}│{pad(side[i] if i < len(side) else '', inner - art_width - 1)}│")
    out.append(_rule("├", "┤", inner))
    out += _box(_tiles(content, state, inner - 2, style), inner)
    out.append(_rule("├", "┤", inner))
    out += _box(_messages(content, state, inner, None, style), inner)
    out.append(_rule("├", "┤", inner))
    key = "keys_target" if selected is not None else "keys_encounter"
    out += _box([style.dim(line) for line in wrap(content.message(key), inner - 2)], inner)
    out.append(_rule("└", "┘", inner))
    return "\n".join(out) + "\n"


def _art(content: Content, state: GameState, cid: Optional[str]) -> List[str]:
    record = content.get("character", state.characters[cid].source) if cid else {}
    lines = list(record.get("art", ())) or [f" {record.get('glyph') or record.get('name', ' ')[0]} "]
    width = max(len(line) for line in lines) + 2
    return ["┌" + "─" * width + "┐"] + [f"│ {line.ljust(width - 2)} │" for line in lines] + ["└" + "─" * width + "┘"]


def _fighters(content: Content, state: GameState, width: int, style: Style) -> List[str]:
    health = content.stat_roles["health"]
    lines = []
    for cid in encounter.living(state, "allies"):
        cs = state.characters[cid]
        name = content.get("character", cs.source)["name"][:10]
        lines.append(f" {name:<10} {_bar(stats.current(content, cs, health), stats.stat(content, cs, health), 6)}")
    heat = content.stat_roles["heat"]
    me = state.characters[state.player]
    if stats.stat(content, me, heat) > 0:
        short = content.get("stat", heat).get("short") or "heat"
        lines.append(f" {short:<10} {_bar(stats.current(content, me, heat), stats.stat(content, me, heat), 6)}")
    lines.append("")
    for number, cid in enumerate(encounter.living(state, "enemies"), 1):
        cs = state.characters[cid]
        name = content.get("character", cs.source)["name"][:8]
        now, top = stats.current(content, cs, health), stats.stat(content, cs, health)
        lines.append(f" {number} {name:<8} {_bar(now, top, 6)} {int(now)}")
        intent = encounter.intent_line(content, state, cid)
        if intent:
            lines.append(style.danger(f"   ⚠ {intent}"[:width]))
    return lines


def _tiles(content: Content, state: GameState, width: int, style: Style) -> List[str]:
    tiles = encounter.tiles(content, state)
    per_row = max(1, width // TILE)
    lines: List[str] = []
    for start in range(0, len(tiles), per_row):
        row = tiles[start:start + per_row]
        parts = [[], [], [], []]
        for tile in row:
            paint = (lambda t: t) if tile.available else style.dim
            inner_width = TILE - 2
            parts[0].append("┌" + "─" * inner_width + "┐")
            parts[1].append(paint("│" + f"{tile.key} {tile.label}"[:inner_width].ljust(inner_width) + "│"))
            parts[2].append(paint("│" + (f"▲{tile.cost}" if tile.cost else "").ljust(inner_width) + "│"))
            parts[3].append("└" + "─" * inner_width + "┘")
        lines += ["".join(p) for p in parts]
    return lines


# --- Zone 1 ----------------------------------------------------------------------------

def _header(content: Content, location, inner: int, style: Style) -> List[str]:
    region = content.get("region", location["region"])["name"]
    name = location["name"]
    gap = max(1, inner - 2 - len(name) - len(region))
    lines = [style.bold(name) + " " * gap + region]
    hazards = [content.get("tag", t)["name"] for t in location.get("tags", ())
               if content.get("tag", t).get("hazard")]
    if hazards:
        lines.append(style.danger(", ".join(hazards)))
    return lines


# --- Zones 2 and 3 ------------------------------------------------------------------------

def _grid(content: Content, state: GameState, location, style: Style) -> List[str]:
    grid = location["grid"]
    player = state.characters[state.player]
    people = {tuple(state.characters[cid].at): cid for cid in world.others_here(state)}
    lines = ["┌" + "─" * (grid["width"] * 2 + 1) + "┐"]
    for row in range(grid["height"]):
        cells = []
        for col in range(grid["width"]):
            pos = (row, col)
            glyph = _cell(content, state, location, pos, people)
            if pos == tuple(player.at):
                glyph = style.inverse(glyph if glyph.strip() not in ("", grid["floor"]) else "@")
            cells.append(glyph)
        lines.append("│ " + " ".join(cells) + " │")
    lines.append("└" + "─" * (grid["width"] * 2 + 1) + "┘")
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


def _bar(value: float, top: float, width: int = 8) -> str:
    filled = 0 if top <= 0 else round(width * max(0, min(value, top)) / top)
    return "█" * filled + "░" * (width - filled)


def _status(content: Content, state: GameState, width: int, style: Style) -> List[str]:
    player = state.characters[state.player]
    phase = content.get("phase", phase_of(content, state.turn))["name"]
    lines = [" " + content.message("day_phase", day=day_of(content, state.turn), phase=phase)]
    for stat_id, record in content.all("stat").items():
        if record.get("kind") != "pool":
            continue
        top = stats.stat(content, player, stat_id)
        now = stats.current(content, player, stat_id)
        label = record.get("short") or record["name"][:3]
        line = f" {label:<4}{_bar(now, top)} {int(now)}/{int(top)}"
        low = (record.get("role") == "health" and now <= top / 3) or (record.get("role") == "heat" and now >= top * 0.8)
        lines.append(style.danger(line) if low else line)
    for inst in player.statuses:
        record = content.get("status", inst.status)
        text = f" {record.get('glyph', '*')} {record['name']}" + (f" x{inst.stacks}" if inst.stacks > 1 else "")
        lines.append(style.danger(text) if record.get("harmful", True) else text)
    party = context.party_of(state, state.player)[1:]
    if party:
        names = ", ".join(content.get("character", state.characters[c].source)["name"] for c in party)
        lines += [" " + line for line in wrap(content.message("party", names=names), width - 1)]
    return lines


# --- Zone 4 -------------------------------------------------------------------------------

def _legend(content: Content, state: GameState, location, inner: int, style: Style) -> List[str]:
    entries = {}
    for placed in content.all("placement").values():
        if placed["location"] != location["id"]:
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
        for i, line in enumerate(wrap(" · ".join(names), inner - 4)):
            lines.append(f"{glyph if i == 0 else ' '} {style.dim(line)}")
    return lines


# --- Zone 5 -------------------------------------------------------------------------------

KIND_MARK = {"danger": "! ", "gain": "+ ", "plain": "", "quiet": ""}
KIND_ORDER = {"danger": 0, "gain": 1, "plain": 2, "quiet": 3}


def _messages(content: Content, state: GameState, inner: int, panel: Optional[str], style: Style,
              selected: Optional[int] = None, page: int = 0) -> List[str]:
    width = inner - 2
    lines: List[str] = []
    for message in sorted(state.messages, key=lambda m: KIND_ORDER.get(m.kind, 2)):
        for i, line in enumerate(wrap(KIND_MARK.get(message.kind, "") + message.text, width)):
            if message.kind == "danger":
                line = style.danger(line)
            elif message.kind == "gain":
                line = style.bold(line)
            elif message.kind == "quiet":
                line = style.dim(line)
            lines.append(line)
    if state.pending is not None:
        if state.pending.prompt:
            lines += wrap(state.pending.prompt, width)
        for i, option in enumerate(state.pending.options, 1):
            lines += wrap(f"{i} {content.text(option['label'])}", width)
        return lines
    if panel == "pack":
        return lines + _pack(content, state, width, style, selected, page)
    if panel == "character":
        return lines + _character(content, state, width, style)
    current = world.menu(content, state)
    if current is not None:
        lines.append(style.bold(current.title))
        for option in current.options:
            entry = f"{style.key(option.key.upper())} {option.label}"
            if not option.available:
                entry = style.dim(f"{option.key.upper()} {option.label}")
                if option.hint:
                    entry += style.dim(f" - {option.hint}")
            lines += _wrap_styled(entry, width)
    return lines


def _wrap_styled(text: str, width: int) -> List[str]:
    """Styled text on one line if it fits, otherwise wrapped as plain text."""
    return [text] if visible_len(text) <= width else wrap(ANSI.sub("", text), width)


PAGE = 9  # pack entries per page: picked with 1-9


def _pack(content: Content, state: GameState, width: int, style: Style, selected: Optional[int],
          page: int = 0) -> List[str]:
    """The fitting board: budgets, numbered items by where they are (nine per page), and the picked item's options."""
    player = state.characters[state.player]
    budgets = []
    for role, used in (("power", stats.budget_used(content, player, "power")),
                       ("mass", stats.budget_used(content, player, "mass")),
                       ("cargo", len(player.inventory))):
        stat_id = content.stat_roles.get(role)
        if stat_id:
            short = content.get("stat", stat_id).get("short") or content.get("stat", stat_id)["name"]
            budgets.append(f"{short} {used:g}/{stats.budget_provided(content, player, role):g}")
    lines = [style.dim("  ".join(budgets))]
    slots = build.pack_slots(content, state)
    heading = {"fitted": content.message("pack_fitted"), "inventory": content.message("pack_carried")}
    shown = set()
    where_store = build.storage_here(content, state)
    pages = max(1, -(-len(slots) // PAGE))
    page = page % pages
    first = page * PAGE
    for number, slot in enumerate(slots[first:first + PAGE], 1):
        group = slot[0] if slot[0] in ("inventory", "storage", "design") else "fitted"
        if group not in shown:
            shown.add(group)
            if group == "storage":
                lines.append(content.message("pack_stored", container=content.get("placement", where_store)["name"]))
            elif group == "design":
                lines.append(content.message("pack_designs"))
            else:
                lines.append(heading[group])
        if slot[0] == "design":
            text = content.get("item", craft.designs(content, state)[slot[1]])["name"]
        else:
            inst = build.stored(state, where_store)[slot[1]] if slot[0] == "storage" else stats.item_at(player, slot)
            text = _item_line(content, inst)
        entry = f"{number} {text}"
        lines.append(style.key(entry) if selected == first + number - 1 else entry)
    if pages > 1:
        lines.append(style.dim(content.message("pack_more", page=page + 1, pages=pages)))
    if selected is not None and selected < len(slots):
        for option in build.item_options(content, state, slots[selected]):
            if option.available:
                lines += _wrap_styled(f"{style.key(option.key.upper())} {option.label}", width)
            else:
                lines += wrap(f"{option.key.upper()} {option.label}" + (f" - {option.hint}" if option.hint else ""), width)
    return [line if visible_len(line) <= width else line[:width] for line in lines]


def _item_line(content: Content, inst) -> str:
    view = stats.item_view(content, inst)
    text = view["name"] + (f" x{inst.count}" if inst.count > 1 else "")
    if inst.condition is not None:
        text += f" {inst.condition}/{view['max_condition']}"
    return text


def _character(content: Content, state: GameState, width: int, style: Style) -> List[str]:
    player = state.characters[state.player]
    record = content.get("character", player.source)
    lines = [style.bold(content.message("character_title", name=record["name"]))]
    top = content.settings["skill_max_level"]
    for skill_id, level in player.skills.items():
        skill = content.get("skill", skill_id)
        following = [lv["xp"] for lv in skill["levels"] if lv["level"] > level and lv["level"] <= top]
        progress = f" ({player.xp.get(skill_id, 0)}/{min(following)})" if following else ""
        lines.append(f"  {skill['name']} {level}{progress}")
    for stat_id, stat in content.all("stat").items():
        if stat.get("kind") != "pool":
            lines.append(f"  {stat.get('short') or stat['name']} {stats.stat(content, player, stat_id):g}")
    return [line[:width] if visible_len(line) == len(line) else line for line in lines]


# --- Zone 6 -------------------------------------------------------------------------------

def _hints(content: Content, state: GameState, inner: int, style: Style, panel: Optional[str] = None) -> List[str]:
    if state.pending is not None:
        key = "keys_choice"
    elif panel == "pack":
        key = "keys_pack"
    elif world.menu(content, state) is not None:
        key = "keys_menu"
    else:
        key = "keys_walk"
    return [style.dim(line) for line in wrap(content.message(key), inner - 2)]
