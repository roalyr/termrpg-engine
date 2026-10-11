"""
The art editor: the pack's pictures, drawn as the game draws them (half blocks, two
pixels per text cell), painted pixel by pixel.

Pick a picture (or make a new one), move the cursor over its pixels and paint with
the current colour; Tab steps through the palette and see-through. Enter lists what
else works: pick the colour under the cursor, mirror left and right, undo, add or
change a colour, resize, delete an unused picture, save.

  python3 -m tools.art packs/test     on its own
  python3 editor.py                   from the editor's menu
"""
import re
import sys
from typing import Callable, List, Optional, Tuple

from lib import term
from tools.lib import colours, forms, screen
from tools.lib.colours import code
from tools.lib.packfiles import Found, PackFiles

LETTERS = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CLEAR = "."                                   # see-through
CURSOR = 201                                  # the cursor's pixel colour (a bright magenta)
NEW = object()
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
MOVES = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}


def size(picture: dict) -> Tuple[int, int]:
    """(width, height) in pixels."""
    rows = picture.get("rows", [])
    return (max((len(r) for r in rows), default=0), len(rows))


class Art:
    name = "Art"
    about = "The pack's pictures in pixels, drawn as the game shows them: paint, mirror, undo, colours."

    def __init__(self, pack: PackFiles, look: screen.Look, art_id: Optional[str] = None):
        self.pack, self.look = pack, look
        self.found: Optional[Found] = None
        self.cursor: Tuple[int, int] = (0, 0)       # (row, column) in pixels
        self.view: Tuple[int, int] = (0, 0)
        self.current = CLEAR
        self.mirror = False
        self.undo: List[Tuple[list, dict]] = []
        self.form = None
        self.after: Optional[Callable] = None
        self.message: Tuple[str, str] = ("", "quiet")
        self.closed = False
        if art_id is not None:
            self.open(art_id)
        else:
            self.choose_picture()

    # --- helpers -------------------------------------------------------------------

    @property
    def picture(self) -> dict:
        return self.found.entry

    def ask(self, form, after: Callable) -> None:
        self.form, self.after = form, after

    def say(self, text: str, role: str = "quiet") -> None:
        self.message = (text, role)

    def users(self, art_id: str) -> List[str]:
        """The names of the characters that show this picture."""
        return [f.entry.get("name", f.entry["id"]) for f in self.pack.entries("characters") if f.entry.get("art") == art_id]

    def open(self, art_id: str) -> None:
        self.found = self.pack.find("art", art_id)
        width, height = size(self.picture)
        self.cursor, self.view, self.undo = (height // 2, width // 2), (0, 0), []
        letters = list(self.picture.get("palette", {}))
        self.current = letters[0] if letters else CLEAR
        self.say("")

    def choose_picture(self, notice: str = "") -> None:
        choices = []
        for f in self.pack.entries("art"):
            width, height = size(f.entry)
            users = self.users(f.entry["id"])
            detail = f"{width}×{height}" + (f" · {', '.join(users)}" if users else " · unused")
            choices.append(forms.Choice(f.entry["id"], f.entry["id"], detail, f.entry.get("notes", "")))
        if "art" in self.pack.kinds:
            choices.append(forms.Choice("New picture…", NEW))
        picker = forms.Picker(self.look, "Art · pictures", choices, self.found.entry["id"] if self.found else None)
        picker.notice = notice or ("" if "art" in self.pack.kinds else "This pack lists no art files in pack.json.")
        picker.pictures = True
        self.found = None
        self.ask(picker, lambda picked: self.start_new() if picked is NEW else self.open(picked))

    # --- drawing -------------------------------------------------------------------

    def render(self, columns: int, rows: int) -> str:
        look, width = self.look, screen.inner_width(self.look, columns)
        right = self.pack.manifest.get("name", self.pack.id) + (" *" if self.pack.dirty else "")
        if self.form is not None:
            title = getattr(self.form, "title", "") or f"Art · {self.picture['id']}"
            lines, focus = self.form.lines(width)
            notice = screen.quiet(look, getattr(self.form, "notice", ""), width)
            about = screen.wrap(self.form.about(), width)[:3] if self.form.about() else []
            bands = [screen.title(look, title, right, width), notice + lines,
                     [look.style.role(line, "quiet") for line in about], screen.hints(look, self.form.hints(), width)]
            return screen.draw(look, [b for b in bands if b], columns, rows, flex=1, focus=focus + len(notice)).text
        others = [self.detail(width), screen.hints(look, self.hints(), width)]
        title = screen.title(look, f"Art · {self.picture['id']}", right, width)
        room = max(1, rows - len(title) - sum(len(b) for b in others) - (len(others) + 2) - 1)
        return screen.draw(look, [title, self.body(width, room)] + others, columns, rows).text

    def body(self, width: int, height: int) -> List[str]:
        """The canvas, scrolled to keep the cursor in view, and beside it the palette."""
        palette = self.palette_lines()
        side = max(len(screen.strip(line)) for line in palette)
        across = max(2, width - side - 3)
        canvas = self.canvas(across, height)
        canvas_width = max(len(screen.strip(line)) for line in canvas) if canvas else 0
        bar = self.look.glyphs["border"]["vertical"]
        return [screen.pad(canvas[i] if i < len(canvas) else "", canvas_width) + f" {bar} "
                + (palette[i] if i < len(palette) else "") for i in range(max(len(canvas), len(palette)))]

    def canvas(self, across: int, lines: int) -> List[str]:
        style, picture = self.look.style, self.picture
        width, height = size(picture)
        down = max(2, lines * 2)
        row, col = self.cursor
        vy = min(max(self.view[0], row - down + 1), row) // 2 * 2
        vx = min(max(self.view[1], col - across + 1), col)
        self.view = (vy, vx)
        rows = picture["rows"]
        palette = picture.get("palette", {})

        def pixel(y, x):
            if (y, x) == self.cursor:
                return "cursor"
            if y >= height or x >= len(rows[y]) or rows[y][x] in " .":
                return None
            return code(palette.get(rows[y][x], "white"))

        out = []
        for y in range(vy, min(vy + down, height), 2):
            cells = []
            for x in range(vx, min(vx + across, width)):
                upper, lower = pixel(y, x), pixel(y + 1, x) if y + 1 < height else None
                cursor_here = "cursor" in (upper, lower)
                if not style.colour:
                    shape = {(True, True): "█", (True, False): "▀", (False, True): "▄", (False, False): "·"}
                    cell = shape[(upper is not None, lower is not None)]
                    cells.append(style.inverse(cell if cell != "·" else " ") if cursor_here else
                                 (style.role(cell, "quiet") if cell == "·" else cell))
                    continue
                upper = CURSOR if upper == "cursor" else upper
                lower = CURSOR if lower == "cursor" else lower
                if upper is None and lower is None:
                    cells.append(style.role("·", "quiet"))
                elif upper is None:
                    cells.append(style.pixels("▄", lower, None))
                elif lower is None or lower == upper:
                    cells.append(style.pixels("█" if lower == upper else "▀", upper, None))
                else:
                    cells.append(style.pixels("▀", upper, lower))
            out.append("".join(cells))
        return out

    def palette_lines(self) -> List[str]:
        style, cursor = self.look.style, self.look.glyphs["cursor"]
        lines = []
        for letter, colour in list(self.picture.get("palette", {}).items()) + [(CLEAR, None)]:
            sample = (style.pixels("█", code(colour), None) if style.colour else "█") if colour is not None else " "
            words = str(colour) if colour is not None else "see-through"
            mark = cursor if letter == self.current else " "
            lines.append(f"{mark}{letter} {sample} {words}")
        return lines

    def detail(self, width: int) -> List[str]:
        style = self.look.style
        row, col = self.cursor
        here = self.letter_at(row, col)
        line = f"[{row},{col}] {here}" + (" · mirror" if self.mirror else "")
        users = self.users(self.picture["id"])
        lines = [line + style.role(" · " + (f"used by {', '.join(users)}" if users else "unused"), "quiet")]
        text, role = self.message
        if text:
            lines += [style.role(part, role) for part in screen.wrap(text, width)[:2]]
        return [screen.pad(line, width) if len(screen.strip(line)) > width else line for line in lines]

    def hints(self) -> List[str]:
        return ["←↑↓→ move", "Space paint", "Tab colour", "Enter actions", f"{self.look.key('back')} back"]

    # --- pixels --------------------------------------------------------------------

    def letter_at(self, row: int, col: int) -> str:
        rows = self.picture["rows"]
        letter = rows[row][col] if row < len(rows) and col < len(rows[row]) else CLEAR
        return CLEAR if letter == " " else letter

    def remember(self) -> None:
        """Keeps the picture as it is, for undo."""
        self.undo.append((list(self.picture["rows"]), dict(self.picture.get("palette", {}))))
        del self.undo[:-100]

    def set_pixel(self, row: int, col: int, letter: str) -> None:
        rows = self.picture["rows"]
        rows[row] = rows[row][:col] + letter + rows[row][col + 1:]

    def paint(self) -> None:
        row, col = self.cursor
        width, _ = size(self.picture)
        spots = {(row, col)} | ({(row, width - 1 - col)} if self.mirror else set())
        if all(self.letter_at(r, c) == self.current for r, c in spots):
            return
        self.remember()
        for r, c in spots:
            self.set_pixel(r, c, self.current)
        self.pack.touch(self.found.file)

    def next_colour(self) -> None:
        letters = list(self.picture.get("palette", {})) + [CLEAR]
        self.current = letters[(letters.index(self.current) + 1) % len(letters)] if self.current in letters else letters[0]

    def pick_colour(self) -> None:
        self.current = self.letter_at(*self.cursor)
        self.say(f"Painting with {self.current}.")

    def toggle_mirror(self) -> None:
        self.mirror = not self.mirror
        self.say("Mirror on: painting does both sides." if self.mirror else "Mirror off.")

    def step_back(self) -> None:
        if not self.undo:
            return self.say("Nothing to undo.")
        rows, palette = self.undo.pop()
        self.picture["rows"], self.picture["palette"] = rows, palette
        if self.current not in palette:
            self.current = CLEAR
        width, height = size(self.picture)
        self.cursor = (min(self.cursor[0], height - 1), min(self.cursor[1], width - 1))
        self.pack.touch(self.found.file)
        self.say("Undone.")

    # --- colours -------------------------------------------------------------------

    def choose_colour(self, title: str, then: Callable, selected=None) -> None:
        colours.choose(self, title, then, selected)

    def sample(self, colour) -> str:
        return colours.sample(self.look, colour)

    def new_colour(self) -> None:
        palette = self.picture.setdefault("palette", {})
        letter = next((c for c in LETTERS if c not in palette), None)
        if letter is None:
            return self.say("Every letter is in use.", "danger")

        def done(colour):
            self.remember()
            palette[letter] = colour
            self.current = letter
            self.pack.touch(self.found.file)
            self.say(f"New colour {letter}: {colour}.")
        self.choose_colour(f"Colour for {letter}", done)

    def change_colour(self) -> None:
        letter, palette = self.current, self.picture.get("palette", {})

        def done(colour):
            self.remember()
            palette[letter] = colour
            self.pack.touch(self.found.file)
            self.say(f"{letter} is now {colour}.")
        self.choose_colour(f"New colour for {letter}", done, palette.get(letter))

    def remove_colour(self) -> None:
        letter = self.current
        self.remember()
        self.picture["rows"] = [r.replace(letter, CLEAR) for r in self.picture["rows"]]
        del self.picture["palette"][letter]
        self.current = CLEAR
        self.pack.touch(self.found.file)
        self.say(f"Removed {letter}: its pixels are see-through.")

    # --- the picture ---------------------------------------------------------------

    def start_size(self) -> None:
        width, height = size(self.picture)

        def check(text):
            parts = text.lower().replace("×", "x").split("x")
            if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
                return "Write it as width x height, e.g. 24x24."
            w, h = (int(p) for p in parts)
            return "" if 2 <= w <= 32 and 2 <= h <= 32 else "Each side is 2 to 32 pixels."

        def done(text):
            w, h = (int(p) for p in text.lower().replace("×", "x").split("x"))
            self.remember()
            rows = [r[:w].ljust(w, CLEAR) for r in self.picture["rows"][:h]]
            self.picture["rows"] = rows + [CLEAR * w] * (h - len(rows))
            self.cursor = (min(self.cursor[0], h - 1), min(self.cursor[1], w - 1))
            self.pack.touch(self.found.file)
            self.say(f"The picture is now {w}×{h}.")
        self.ask(forms.Field(self.look, "Size (width x height)", f"{width}x{height}", check,
                             "2 to 32 pixels each way; 24x24 fills the default art zone. "
                             "The top-left part is kept."), done)

    def start_new(self) -> None:
        taken = {f.entry["id"] for f in self.pack.entries("art")}

        def check(text):
            if not ID_PATTERN.match(text):
                return "Lower case letters, digits and _, starting with a letter."
            return "That id is taken." if text in taken else ""

        def done(art_id):
            entry = {"id": art_id, "rows": [CLEAR * 24] * 24, "palette": {"a": "white"}}
            self.pack.add("art", entry)
            self.open(art_id)
            self.say("A blank 24×24 picture. Z changes the size, N adds colours.")
        self.ask(forms.Field(self.look, "Id of the new picture", "art_", check,
                             "Characters use it by this id, in their 'art'."), done)

    def delete(self) -> None:
        art_id = self.picture["id"]

        def done(_):
            data = self.pack.data[self.found.file]
            data["entries"] = [e for e in data["entries"] if e is not self.picture]
            self.pack.touch(self.found.file)
            self.choose_picture(f"Deleted {art_id}.")
        self.ask(forms.Question(self.look, f"Delete {art_id}? Nothing uses it.", [("y", "delete", True)]), done)

    # --- keys ----------------------------------------------------------------------

    def actions(self) -> List[tuple]:
        found = [("", "Paint (Space)", self.paint),
                 ("k", "Pick the colour under the cursor", self.pick_colour),
                 ("m", "Mirror: " + ("turn off" if self.mirror else "paint both sides at once"), self.toggle_mirror)]
        if self.undo:
            found.append(("u", "Undo", self.step_back))
        found.append(("n", "New colour…", self.new_colour))
        if self.current != CLEAR:
            found += [("c", f"Change colour {self.current}…", self.change_colour),
                      ("", f"Remove colour {self.current}", self.remove_colour)]
        found.append(("z", "Size…", self.start_size))
        if not self.users(self.picture["id"]):
            found.append(("", "Delete this picture", self.delete))
        if self.pack.dirty:
            found.append(("", "Save changes", self.save))
        return found

    def handle(self, key: str) -> bool:
        if self.form is not None:
            result = self.form.handle(key)
            if result is forms.CANCEL:
                listing, self.form = getattr(self.form, "pictures", False), None
                if listing:
                    self.leave()
                elif self.found is None:
                    self.choose_picture()
            elif result is not None:
                self.form, after = None, self.after
                after(result)
            return not self.closed
        action = self.look.action(key)
        if action in MOVES:
            width, height = size(self.picture)
            step = MOVES[action]
            self.cursor = (min(max(0, self.cursor[0] + step[0]), height - 1),
                           min(max(0, self.cursor[1] + step[1]), width - 1))
        elif key == " ":
            self.paint()
        elif key == "tab":
            self.next_colour()
        elif action in ("back", "quit"):
            self.back_to_list()
        elif key == "enter":
            choices = [forms.Choice(label, fn, letter.upper()) for letter, label, fn in self.actions()]
            self.ask(forms.Picker(self.look, "Actions", choices), lambda fn: fn())
        else:
            for letter, _, fn in self.actions():
                if letter and key.lower() == letter:
                    fn()
                    break
        return not self.closed

    # --- leaving -------------------------------------------------------------------

    def back_to_list(self) -> None:
        if not self.pack.dirty:
            return self.choose_picture()

        def done(answer):
            if answer == "save":
                self.save(then=lambda words: self.choose_picture(words))
            else:
                self.pack.reload()
                self.choose_picture("Changes discarded.")
        self.ask(forms.Question(self.look, "Save your changes?", [("y", "save", "save"), ("n", "discard", "discard")]),
                 done)

    def leave(self) -> None:
        if not self.pack.dirty:
            self.closed = True
            return

        def done(answer):
            if answer == "save":
                self.save(then=lambda words: self.close())
            else:
                self.pack.reload()
                self.close()
        self.ask(forms.Question(self.look, "Save your changes?", [("y", "save", "save"), ("n", "discard", "discard")]),
                 done)

    def save_words(self) -> str:
        written = self.pack.save()
        report = self.pack.check()
        words = f"Saved {len(written)} file(s). Checker: {len(report.errors)} error(s), {len(report.warnings)} warning(s)."
        return words + (" " + report.errors[0] if report.errors else "")

    def close(self) -> None:
        self.closed = True

    def save(self, then: Optional[Callable[[str], None]] = None) -> None:
        """Saves (asking first if a file changed on disk meanwhile), then says how it went, or hands that to 'then'."""
        def write():
            words = self.save_words()
            if then:
                then(words)
            else:
                self.say(words, "danger" if "0 error(s)" not in words else "quiet")
        forms.save_safely(self, write)


if __name__ == "__main__":
    sys.exit(term.run_tool(Art, sys.argv[1:]))
