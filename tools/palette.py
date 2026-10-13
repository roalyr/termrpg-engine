"""
The palette editor: the pack's named colours (palette.json), the only place colour
numbers are written. Every other colour in the pack (map colours, grade colours, the
letters of pictures) is one of these names, so changing a colour here changes it
everywhere it's used.

The default colours (grey, white, green…) are always listed: the interface's styles use
them, so they can be changed but not renamed or deleted. The pack's own colours can be
renamed (every use follows) and deleted (uses move to another colour first). A pack
without a palette file gets palette.json, with the default colours, on its first change.

  python3 -m tools.palette packs/test_scifi     on its own
  python3 editor.py                       from the editor's menu
"""
import sys
from typing import Callable, Dict, List, Optional, Tuple

from lib.text import DEFAULT_COLOURS
from lib import forms, screen
from tools.lib import colours, refs
from tools.lib.tool import run_tool, save_safely
from tools.lib.packfiles import Found, PackFiles

NAME_WIDTH = 14


class Palette:
    name = "Palette"
    about = "The pack's named colours: change one and it changes everywhere it's used."

    def __init__(self, pack: PackFiles, look: screen.Look):
        self.pack, self.look = pack, look
        self.selected = 0
        self.form = None
        self.after: Optional[Callable] = None
        self.message: Tuple[str, str] = ("", "quiet")
        self.closed = False
        self._uses: Optional[Dict[str, List[Tuple[str, str]]]] = None

    # --- helpers -------------------------------------------------------------------

    def ask(self, form, after: Callable) -> None:
        self.form, self.after = form, after

    def say(self, text: str, role: str = "quiet") -> None:
        self.message = (text, role)

    def colours(self) -> List[Tuple[str, int]]:
        return colours.names(self.pack)

    def current(self) -> Tuple[str, int]:
        listed = self.colours()
        self.selected = max(0, min(self.selected, len(listed) - 1))
        return listed[self.selected]

    def found(self, name: str) -> Optional[Found]:
        return self.pack.find(colours.KIND, name)

    def uses(self) -> Dict[str, List[Tuple[str, str]]]:
        """Where each colour is used in the pack: name -> [(file, path)]. Worked out again after each change."""
        if self._uses is None:
            self._uses = refs.by_value(self.pack, "colour")
        return self._uses

    def interface_roles(self, name: str) -> List[str]:
        """The UI pack's style roles drawn in this colour."""
        return [role for role, spec in self.look.ui.tokens["styles"].items() if spec.get("colour") == name]

    def changed(self, words: str) -> None:
        self._uses = None
        self.say(words)

    # --- drawing -------------------------------------------------------------------

    def swatch(self, code: int, wide: int = 2) -> str:
        return self.look.style.pixels("█" * wide, code, None) if self.look.style.colour else " " * wide

    def body(self, width: int) -> Tuple[List[str], int]:
        style, cursor = self.look.style, self.look.glyphs["cursor"]
        uses = self.uses()
        lines = [""]
        if not self.pack.kinds.get(colours.KIND):
            lines = screen.quiet(self.look, "No palette file yet: the first change makes palette.json, "
                                            "with the default colours.", width) + [""]
        top = len(lines)
        self.current()
        for index, (name, code) in enumerate(self.colours()):
            count = len(uses.get(name, []))
            note = "default" if name in DEFAULT_COLOURS else (f"{count} use" + ("s" if count != 1 else "") if count else "unused")
            label = f"{name[:NAME_WIDTH]:<{NAME_WIDTH}} {code:>3}"
            text = f"{self.swatch(code)} " + (style.key(label) if index == self.selected else label)
            lines.append((cursor if index == self.selected else " ") + text + "  " + style.role(note, "quiet"))
        return lines, top + self.selected

    def detail(self, width: int) -> List[str]:
        """Where the picked colour is used, and the last message."""
        style = self.look.style
        name, code = self.current()
        places = self.uses().get(name, [])
        owners: List[str] = []
        for rel, path in places:
            who = refs.owner(self.pack, rel, path)
            if who not in owners:
                owners.append(who)
        words = f"{name} · {code}"
        if owners:
            words += " · used by " + ", ".join(owners[:4]) + (f" and {len(owners) - 4} more" if len(owners) > 4 else "")
        elif name not in DEFAULT_COLOURS:
            words += " · nothing uses it"
        lines = [style.role(line, "quiet") for line in screen.wrap(words, width)[:2]]
        roles = self.interface_roles(name)
        if roles:
            lines += [style.role(line, "quiet") for line in screen.wrap("Interface: " + ", ".join(roles), width)[:1]]
        text, role = self.message
        if text:
            lines += [style.role(part, role) for part in screen.wrap(text, width)[:2]]
        return lines

    def hints(self) -> List[str]:
        return ["↑↓ pick", "Enter actions", "C change", "N new", f"{self.look.key('back')} back"]

    def render(self, columns: int, rows: int) -> str:
        look, width = self.look, screen.inner_width(self.look, columns)
        right = self.pack.manifest.get("name", self.pack.id) + (" *" if self.pack.dirty else "")
        if self.form is not None:
            title = getattr(self.form, "title", "") or self.name
            lines, focus = self.form.lines(width)
            notice = screen.quiet(look, getattr(self.form, "notice", ""), width)
            about = screen.wrap(self.form.about(), width)[:3] if self.form.about() else []
            bands = [screen.title(look, title, right, width), notice + lines,
                     [look.style.role(line, "quiet") for line in about], screen.hints(look, self.form.hints(), width)]
            return screen.draw(look, [b for b in bands if b], columns, rows, flex=1, focus=focus + len(notice)).text
        lines, focus = self.body(width)
        bands = [screen.title(look, self.name, right, width), lines, self.detail(width),
                 screen.hints(look, self.hints(), width)]
        return screen.draw(look, bands, columns, rows, flex=1, focus=focus).text

    # --- changes -------------------------------------------------------------------

    def set_code(self, name: str, code: int) -> None:
        """Gives a colour a terminal number; a default colour not yet in the file is written into it."""
        colours.ensure_file(self.pack)                       # a new file already lists the defaults
        found = self.found(name)
        if found is None:
            colours.add(self.pack, name, code)
        else:
            found.entry["code"] = code
            self.pack.touch(found.file)

    def change(self) -> None:
        name, code = self.current()

        def done(number):
            self.set_code(name, number)
            self.changed(f"{name} is now {number}.")
        self.ask(colours.grid(self, code), done)

    def new(self) -> None:
        name, code = self.current()

        def done(new_name):
            self.selected = next(i for i, (n, _) in enumerate(self.colours()) if n == new_name)
            self.changed(f"New colour {new_name}.")
        colours.new(self, done, code)

    def rename(self) -> None:
        name, _ = self.current()
        if name in DEFAULT_COLOURS:
            return self.say("The default colours keep their names: the interface uses them.", "danger")

        def done(new_name):
            count = refs.rename(self.pack, "colour", name, new_name)
            found = self.found(name)
            found.entry["id"] = new_name
            self.pack.touch(found.file)
            self.changed(f"{name} is now called {new_name}" + (f", in {count} place(s)." if count else "."))
        self.ask(forms.Field(self.look, f"New name for {name}", name,
                             lambda text: "" if text == name else colours.check_name(self.pack, text),
                             "Every use of the colour is renamed with it."), done)

    def reset(self) -> None:
        name, _ = self.current()
        self.set_code(name, DEFAULT_COLOURS[name])
        self.changed(f"{name} is back to {DEFAULT_COLOURS[name]}.")

    def delete(self) -> None:
        name, _ = self.current()
        found, places = self.found(name), self.uses().get(name, [])

        def remove(replacement=None):
            moved = refs.rename(self.pack, "colour", name, replacement) if replacement else 0
            self.pack.remove(colours.KIND, found)
            self.changed(f"Deleted {name}" + (f"; {moved} use(s) are now {replacement}." if moved else "."))
        if not places:
            return self.ask(forms.Question(self.look, f"Delete {name}? Nothing uses it.", [("y", "delete", True)]),
                            lambda _: remove())
        others = [forms.Choice(f"{colours.sample(self.look, n)} {n}", n, str(c)) for n, c in self.colours() if n != name]
        picker = forms.Picker(self.look, f"Delete {name}: its uses become", others)
        picker.notice = f"{len(places)} use(s) of {name} move to the colour you pick."
        self.ask(picker, remove)

    def actions(self) -> List[tuple]:
        name, code = self.current()
        found = [("c", f"Change {name}…", self.change), ("n", "New colour…", self.new)]
        if name in DEFAULT_COLOURS:
            if code != DEFAULT_COLOURS[name]:
                found.append(("", f"Back to the default ({DEFAULT_COLOURS[name]})", self.reset))
        else:
            found += [("r", f"Rename {name}…", self.rename), ("", f"Delete {name}…", self.delete)]
        if self.pack.dirty:
            found.append(("", "Save changes", self.save))
        return found

    # --- keys ----------------------------------------------------------------------

    def handle(self, key: str) -> bool:
        if self.form is not None:
            result = self.form.handle(key)
            if result is forms.CANCEL:
                self.form = None
            elif result is not None:
                self.form, after = None, self.after
                after(result)
            return not self.closed
        action = self.look.action(key)
        if action == "up":
            self.selected = max(0, self.selected - 1)
        elif action == "down":
            self.selected = min(len(self.colours()) - 1, self.selected + 1)
        elif action in ("back", "quit"):
            self.leave()
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

    def close(self) -> None:
        self.closed = True

    def save(self, then: Optional[Callable[[str], None]] = None) -> None:
        """Saves (asking first if a file changed on disk meanwhile), then says how it went, or hands that to 'then'."""
        def write():
            written = self.pack.save()
            report = self.pack.check()
            words = f"Saved {len(written)} file(s). Checker: {len(report.errors)} error(s), {len(report.warnings)} warning(s)."
            words += " " + report.errors[0] if report.errors else ""
            if then:
                then(words)
            else:
                self.say(words, "danger" if report.errors else "quiet")
        save_safely(self, write)


if __name__ == "__main__":
    sys.exit(run_tool(Palette, sys.argv[1:]))
