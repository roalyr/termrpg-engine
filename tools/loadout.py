"""
The loadout editor: what a character wears, fits and carries, with the budgets the
checker holds it to. Pick a character; the top shows their picture (when the screen
has the room), size, place, power, mass, heat and cargo as bars, and their other
stats. Below, the frame, every slot of the frame and the body, and the inventory.

Enter changes the picked line: another frame, the item in a slot (only items that go
in it are offered, with what they use), a stack's count, or a new item to carry.
R takes it out. The bars and the problems follow every change, before saving.
G opens the character's room, V shows or hides the picture.

  python3 -m tools.loadout packs/test     on its own
  python3 editor.py                       from the editor's menu
"""
import sys
from typing import Callable, List, NamedTuple, Optional, Tuple

from lib import pixels, term
from lib.text import bar as text_bar
from tools.lib import forms, loadout, screen
from tools.lib.loadout import Sheet, Slot
from tools.lib.packfiles import Found, PackFiles
from tools.room import Room

NONE = object()
PICTURE_ROWS = 10              # the list keeps at least this many lines when the picture shows
MOVES = {"up": -1, "down": 1}


class Row(NamedTuple):
    """A line of the list: a heading, the frame, a slot, a carried stack, or 'add'."""
    kind: str                  # 'heading', 'frame', 'slot', 'item', 'add'
    text: str
    right: str = ""
    slot: Optional[Slot] = None
    index: int = -1            # the stack's place in the inventory
    danger: bool = False


class Loadout:
    name = "Loadout"
    about = "A character's frame, modules, implants and inventory, against their power, mass, heat and cargo."

    def __init__(self, pack: PackFiles, look: screen.Look, character_id: Optional[str] = None):
        self.pack, self.look = pack, look
        self.found: Optional[Found] = None
        self.selected = 0
        self.form = None
        self.after: Optional[Callable] = None
        self.message: Tuple[str, str] = ("", "quiet")
        self.show_picture = True
        self.room: Optional[Room] = None
        self.closed = False
        if character_id and pack.find("characters", character_id):
            self.open(character_id)
        else:
            self.choose_character()

    # --- helpers -------------------------------------------------------------------

    @property
    def char(self) -> dict:
        return self.found.entry

    def ask(self, form, after: Callable) -> None:
        self.form, self.after = form, after

    def say(self, text: str, role: str = "quiet") -> None:
        self.message = (text, role)

    def changed(self, words: str) -> None:
        self.pack.touch(self.found.file)
        self.say(words)

    def item(self, item_id: Optional[str]) -> dict:
        return loadout.items(self.pack).get(item_id, {}) if item_id else {}

    def item_name(self, item_id: Optional[str]) -> str:
        return self.item(item_id).get("name", item_id or "")

    def slot_name(self, slot_type: str) -> str:
        return loadout.vocab(self.pack).slot_types.get(slot_type, {}).get("name", slot_type or "?")

    # --- choosing -------------------------------------------------------------------

    def choose_character(self, notice: str = "", selected: Optional[str] = None) -> None:
        self.found = None
        choices = []
        for found in self.pack.entries("characters"):
            c = found.entry
            where = "template" if c.get("template") else self.location_name(c.get("location"))
            choices.append(forms.Choice(c.get("name", c.get("id", "?")), c.get("id"),
                                        f"{c.get('id', '')}  {where}".rstrip(), c.get("description", "")))
        picker = forms.Picker(self.look, "Loadout", choices, selected)
        picker.notice = notice
        self.ask(picker, self.open)

    def open(self, character_id: str) -> None:
        self.found, self.selected = self.pack.find("characters", character_id), 1
        self.say("")

    def location_id(self) -> Optional[str]:
        """Where the character stands: their location, or for the player the pack's start."""
        start = self.pack.manifest.get("start", {})
        if self.char.get("location"):
            return self.char["location"]
        return start.get("location") if start.get("player") == self.char.get("id") else None

    def location_name(self, location_id: Optional[str]) -> str:
        found = self.pack.find("locations", location_id) if location_id else None
        return found.entry.get("name", location_id) if found else (location_id or "")

    # --- the screen ------------------------------------------------------------------

    def render(self, columns: int, rows: int) -> str:
        if self.room is not None:
            return self.room.render(columns, rows)
        look, width = self.look, screen.inner_width(self.look, columns)
        right = self.pack.manifest.get("name", self.pack.id) + (" *" if self.pack.dirty else "")
        if self.form is not None:
            title = getattr(self.form, "title", "") or self.heading()
            lines, focus = self.form.lines(width)
            notice = screen.quiet(look, getattr(self.form, "notice", ""), width)
            about = screen.wrap(self.form.about(), width)[:3] if self.form.about() else []
            bands = [screen.title(look, title, right, width), notice + lines,
                     [look.style.role(line, "quiet") for line in about], screen.hints(look, self.form.hints(), width)]
            return screen.draw(look, [b for b in bands if b], columns, rows, flex=1, focus=focus + len(notice)).text
        sheet = loadout.sheet(self.pack, self.char)
        rows_list = self.rows(sheet)
        self.selected = self.pickable_index(rows_list, self.selected)
        detail, hints = self.detail(sheet, rows_list, width), screen.hints(look, self.hints(), width)
        head = self.head(sheet, width, picture=False)
        if self.show_picture and self.char.get("art"):
            framed = self.head(sheet, width, picture=True)
            if rows - (1 + len(framed) + len(detail) + len(hints) + 6) >= PICTURE_ROWS:    # title, bands, borders
                head = framed
        bands = [screen.title(look, self.heading(), right, width), head, self.list_lines(rows_list, width), detail, hints]
        return screen.draw(look, [b for b in bands if b], columns, rows, flex=2, focus=self.selected).text

    def heading(self) -> str:
        return f"Loadout · {self.char.get('name', self.char.get('id', ''))}" if self.found else "Loadout"

    def head(self, sheet: Sheet, width: int, picture: bool) -> List[str]:
        """Who it is and the budgets; beside the picture when it's shown."""
        art = self.picture() if picture else []
        across = width - (len(screen.strip(art[0])) + 2 if art else 0)
        info = self.info(sheet, across)
        if not art:
            return info
        return [screen.pad(art[i] if i < len(art) else "", len(screen.strip(art[0]))) + "  " + (info[i] if i < len(info) else "")
                for i in range(max(len(art), len(info)))]

    def info(self, sheet: Sheet, width: int) -> List[str]:
        style, char = self.look.style, self.char
        size = self.item(sheet.frame).get("size") if sheet.frame else char.get("body", {}).get("size")
        if char.get("template"):
            where = "template"
        elif self.location_id():
            where = self.location_name(self.location_id()) + ("" if char.get("location") else " (start)")
        else:
            where = "nowhere"
        lines = [style.role(screen.wrap(f"Size {size} · {where}", width)[0], "quiet")]
        if char.get("title"):
            lines.insert(0, screen.wrap(char["title"], width)[0])
        numbers = [f"{b.used:g}/{b.provided:g}" for b in sheet.budgets]
        tail = max((len(n) for n in numbers), default=0)
        pairs = width >= 2 * (5 + 4 + 1 + tail) + 3                       # two bars to a line when they fit
        across = (width - 3) // 2 if pairs else width
        length = max(0, min(self.look.ui.tokens["size"]["bar_length"], across - 6 - tail))
        glyphs = self.look.glyphs
        bars = []
        for budget, number in zip(sheet.budgets, numbers):
            bar = text_bar(budget.used, budget.provided, length, glyphs["bar_full"], glyphs["bar_empty"])
            text = screen.pad(f"{budget.short[:4]:<4} {bar}{' ' if bar else ''}{number}", across)
            bars.append(style.role(text, "danger") if budget.over else text)
        step = 2 if pairs else 1
        lines += ["   ".join(bars[i:i + step]).rstrip() for i in range(0, len(bars), step)]
        stats = loadout.vocab(self.pack).stats
        words = " ".join(f"{stats[s].get('short', s)} {v:g}" for s, v in sheet.stats.items())
        lines += [style.role(line, "quiet") for line in screen.wrap(words, width)] if words else []
        return lines

    def picture(self) -> List[str]:
        """The character's art in half-block pixels, centred in the game's art zone."""
        art = next((f.entry for f in self.pack.entries("art") if f.entry.get("id") == self.char.get("art")), None)
        size = self.look.ui.tokens["size"]
        pw, ph = size.get("art_width", 24), size.get("art_height", 24)
        ph += ph % 2
        grid = pixels.centred(art.get("rows", []), art.get("palette", {}), pw, ph) if art else [[None] * pw for _ in range(ph)]
        return pixels.half_blocks(self.look.style, grid)

    def rows(self, sheet: Sheet) -> List[Row]:
        known = loadout.items(self.pack)
        words = loadout.vocab(self.pack)
        rows = [Row("heading", "Frame")]
        frame = known.get(sheet.frame, {})
        rows.append(Row("frame", frame.get("name", sheet.frame) if sheet.frame else "(no frame)",
                        f"size {frame.get('size')}" if sheet.frame else ""))
        for host in ("frame", "body"):
            slots = [s for s in sheet.slots if s.host == host]
            extra = [s for s in sheet.extra if s.host == host]
            if host == "body" and (slots or extra):
                rows.append(Row("heading", "Body"))
            names = [self.slot_name(s.slot_type) for s in slots + extra]
            name_width = max((len(n) for n in names), default=0)
            for slot in slots:
                label = self.slot_name(slot.slot_type).ljust(name_width)
                item = known.get(slot.item, {})
                text = f"{label}  {item.get('name', slot.item)}" if slot.item else f"{label}  (empty)"
                rows.append(Row("slot", text, loadout.uses_text(item, words) if slot.item else "", slot))
            for slot in extra:
                text = f"{self.slot_name(slot.slot_type).ljust(name_width)}  {self.item_name(slot.item)}  (no slot)"
                rows.append(Row("slot", text, "", slot, danger=True))
        rows.append(Row("heading", "Inventory"))
        for index, entry in enumerate(self.char.get("inventory", []) or []):
            item_id = entry.get("item") if isinstance(entry, dict) else None
            item = known.get(item_id, {})
            count = entry.get("count", 1) if isinstance(entry, dict) else 1
            stacks = -(-count // item.get("stack", 1))
            text = item.get("name", item_id) + (f" x{count}" if count > 1 else "")
            rows.append(Row("item", text, f"{stacks} stack{'s' if stacks != 1 else ''}", index=index, danger=not item))
        rows.append(Row("add", "Carry another item…"))
        return rows

    @staticmethod
    def pickable_index(rows: List[Row], selected: int) -> int:
        """The selection moved off headings: to the next pickable line, or the last one."""
        selected = max(0, min(selected, len(rows) - 1))
        while selected < len(rows) - 1 and rows[selected].kind == "heading":
            selected += 1
        return selected

    def list_lines(self, rows: List[Row], width: int) -> List[str]:
        style, cursor = self.look.style, self.look.glyphs["cursor"]
        lines = []
        for index, row in enumerate(rows):
            if row.kind == "heading":
                lines.append(style.role(row.text, "heading"))
                continue
            room = width - 1 - len(row.text)
            text = row.text + (" " * (room - len(row.right)) + row.right if row.right and room - len(row.right) >= 2 else "")
            text = text[:width - 1]
            if index == self.selected:
                lines.append(cursor + style.key(text))
            else:
                lines.append(" " + (style.role(text, "danger") if row.danger else text))
        return lines

    def detail(self, sheet: Sheet, rows: List[Row], width: int) -> List[str]:
        """The picked line's item, what's wrong with the loadout, and the last message."""
        style = self.look.style
        row = rows[self.selected] if rows else None
        item_id = None
        if row is not None and row.kind == "frame":
            item_id = sheet.frame
        elif row is not None and row.kind == "slot":
            item_id = row.slot.item
        elif row is not None and row.kind == "item":
            item_id = self.char["inventory"][row.index].get("item")
        about = self.item(item_id).get("description", "") if item_id else ""
        lines = [style.role(line, "quiet") for line in screen.wrap(about, width)[:2]] if about else []
        for problem in sheet.problems[:3]:
            lines += [style.role(line, "danger") for line in screen.wrap(problem, width)]
        if len(sheet.problems) > 3:
            lines.append(style.role(f"…and {len(sheet.problems) - 3} more.", "danger"))
        text, role = self.message
        if text:
            lines += [style.role(line, role) for line in screen.wrap(text, width)]
        return lines

    def hints(self) -> List[str]:
        hints = ["↑↓ pick", "Enter change", "R remove"]
        if self.location_id():
            hints.append("G room")
        if self.char.get("art"):
            hints.append("V picture")
        return hints + [f"{self.look.key('back')} back"]

    # --- keys ------------------------------------------------------------------------

    def handle(self, key: str) -> bool:
        keep = self._handle(key)
        return keep and not self.closed

    def _handle(self, key: str) -> bool:
        if self.room is not None:
            if not self.room.handle(key):
                self.room = None
            return True
        if self.form is not None:
            result = self.form.handle(key)
            if result is forms.CANCEL:
                self.form = None
                if self.found is None:                          # the character list: leave the tool
                    return self.leave()
            elif result is not None:
                self.form, after = None, self.after
                after(result)
            return True
        action = self.look.action(key)
        rows = self.rows(loadout.sheet(self.pack, self.char))
        if action in MOVES:
            step = MOVES[action]
            target = self.selected + step
            while 0 <= target < len(rows) and rows[target].kind == "heading":
                target += step
            if 0 <= target < len(rows):
                self.selected = target
            self.say("")
        elif action in ("back", "quit"):
            self.choose_character(selected=self.char.get("id"))
        elif key == "enter":
            self.change(rows[self.selected])
        elif key.lower() == "r":
            self.remove(rows[self.selected])
        elif key.lower() == "g" and self.location_id():
            self.go_to_room()
        elif key.lower() == "v" and self.char.get("art"):
            self.show_picture = not self.show_picture
        return True

    # --- changing ------------------------------------------------------------------------

    def change(self, row: Row) -> None:
        if row.kind == "frame":
            return self.choose_frame()
        if row.kind == "slot":
            return self.choose_for_slot(row.slot)
        if row.kind == "item":
            return self.ask_count(row.index)
        if row.kind == "add":
            return self.choose_new_item()

    def remove(self, row: Row) -> None:
        if row.kind == "frame" and "frame" in self.char:
            name = self.item_name(self.char.pop("frame"))
            return self.changed(f"Took off the {name}." + (" Its modules have nowhere to go now." if self.char.get("fitted") else ""))
        if row.kind == "slot" and row.slot.item is not None:
            return self.put_in_slot(row.slot, None)
        if row.kind == "item":
            entry = self.char["inventory"].pop(row.index)
            if not self.char["inventory"]:
                del self.char["inventory"]
            return self.changed(f"No longer carries {self.item_name(entry.get('item'))}.")
        self.say("Nothing to remove there.")

    def item_choices(self, kind: str, slot_type: Optional[str] = None) -> List[forms.Choice]:
        words = loadout.vocab(self.pack)
        return [forms.Choice(item.get("name", item_id), item_id, loadout.uses_text(item, words), item.get("description", ""))
                for item_id, item in loadout.items(self.pack).items()
                if item.get("kind") == kind and (slot_type is None or item.get("slot_type") == slot_type)]

    def choose_frame(self) -> None:
        choices = [forms.Choice("(no frame)", NONE)] + self.item_choices("frame")

        def done(picked):
            if picked is NONE:
                return self.remove(Row("frame", ""))
            self.char["frame"] = picked
            self.changed(f"Wears the {self.item_name(picked)}.")
        self.ask(forms.Picker(self.look, "Frame", choices, self.char.get("frame")), done)

    def choose_for_slot(self, slot: Slot) -> None:
        kind = "module" if slot.host == "frame" else "implant"
        choices = self.item_choices(kind, slot.slot_type or None)
        if slot.item is not None:
            choices.insert(0, forms.Choice("(empty)", NONE))
        if not choices:
            return self.say(f"No {kind} goes in a {self.slot_name(slot.slot_type)} slot.")
        title = f"{self.slot_name(slot.slot_type)} slot" if slot.slot_type else f"A {kind}"
        self.ask(forms.Picker(self.look, title, choices, slot.item),
                 lambda picked: self.put_in_slot(slot, None if picked is NONE else picked))

    def put_in_slot(self, slot: Slot, item_id: Optional[str]) -> None:
        group = loadout.GROUPS["module" if slot.host == "frame" else "implant"]
        listed = list(self.char.get(group, []))
        if slot.index >= 0 and item_id is None:
            gone = listed.pop(slot.index)
            words = f"Took out the {self.item_name(gone)}."
        elif slot.index >= 0:
            listed[slot.index] = item_id
            words = f"Fitted the {self.item_name(item_id)}."
        else:
            listed.append(item_id)
            words = f"Fitted the {self.item_name(item_id)}."
        if listed:
            self.char[group] = listed
        else:
            self.char.pop(group, None)
        self.changed(words)

    def count_field(self, title: str, start: int, done: Callable[[int], None], zero: bool) -> None:
        def check(text: str) -> str:
            if not text.isdigit() or (int(text) == 0 and not zero):
                return "A whole number, 1 or more." if not zero else "A whole number; 0 takes it out."
            return ""
        self.ask(forms.Field(self.look, title, str(start), check, "0 takes it out." if zero else ""),
                 lambda text: done(int(text)))

    def ask_count(self, index: int) -> None:
        entry = self.char["inventory"][index]

        def done(count: int) -> None:
            if count == 0:
                return self.remove(Row("item", "", index=index))
            if count == 1:
                entry.pop("count", None)
            else:
                entry["count"] = count
            self.changed(f"Carries {self.item_name(entry.get('item'))} x{count}.")
        self.count_field(f"How many {self.item_name(entry.get('item'))}", entry.get("count", 1), done, zero=True)

    def choose_new_item(self) -> None:
        choices = [forms.Choice(item.get("name", item_id), item_id, item.get("kind", ""), item.get("description", ""))
                   for item_id, item in loadout.items(self.pack).items()]

        def picked(item_id):
            def done(count: int) -> None:
                inventory = self.char.setdefault("inventory", [])
                same = next((e for e in inventory if isinstance(e, dict) and e.get("item") == item_id), None)
                if same is not None:
                    total = same.get("count", 1) + count
                    same["count"] = total
                    return self.changed(f"Carries {self.item_name(item_id)} x{total}.")
                inventory.append({"item": item_id, "count": count} if count > 1 else {"item": item_id})
                self.changed(f"Carries {self.item_name(item_id)}" + (f" x{count}." if count > 1 else "."))
            self.count_field(f"How many {self.item_name(item_id)}", 1, done, zero=False)
        self.ask(forms.Picker(self.look, "Carry which item?", choices), picked)

    # --- the room ------------------------------------------------------------------------

    def go_to_room(self) -> None:
        location = self.location_id()
        if not self.pack.find("locations", location):
            return self.say(f"No location {location}.", "danger")
        self.room = Room(self.pack, self.look, location, single=True)
        at = self.char.get("at")
        if isinstance(at, list) and len(at) == 2 and self.char.get("location"):
            self.room.cursor = tuple(at)

    # --- leaving ------------------------------------------------------------------------

    def leave(self) -> bool:
        if not self.pack.dirty:
            self.closed = True
            return False

        def done(answer):
            if answer == "save":
                self.save(then=self.close)
            else:
                self.pack.reload()
                self.close()
        self.ask(forms.Question(self.look, "Save your changes?", [("y", "save", "save"), ("n", "discard", "discard")]),
                 done)
        return True

    def close(self) -> None:
        self.closed = True

    def save(self, then: Optional[Callable[[], None]] = None) -> None:
        def write():
            written = self.pack.save()
            report = self.pack.check()
            words = f"Saved {len(written)} file(s). Checker: {len(report.errors)} error(s), {len(report.warnings)} warning(s)."
            self.say(words + (" " + report.errors[0] if report.errors else ""), "danger" if report.errors else "quiet")
            if then:
                then()
        forms.save_safely(self, write)


if __name__ == "__main__":
    sys.exit(term.run_tool(Loadout, sys.argv[1:]))
