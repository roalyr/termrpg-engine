"""
The entries editor: any entry of the pack (objects, items, characters, actions, events…)
field by field. The fields come from the pack schemas, so every kind works the same way.

Pick a kind, then an entry (or make a new one). Up and down pick a field, Enter edits it:
words and numbers in a line, choices and ids from a list, colours from the colour
picker, descriptions and everything bigger (effects, conditions, dialogue) in your text
editor ($EDITOR, nano by default) as text or JSON. Leaving a field empty takes it out,
so its default applies. E lists what works on the whole entry: edit it all as JSON,
rename its id (every use follows), duplicate, delete, save. The vocabulary's sections
(tags, stats, sizes…) are the last choice of kinds, edited the same way.

  python3 -m tools.entries packs/test_scifi     on its own
  python3 editor.py                       from the editor's menu
"""
import copy
import json
import sys
from typing import Any, Callable, List, Optional, Tuple

from lib import term
from lib import forms, screen
from tools.lib import colours, fields, glance, refs, sources
from tools.lib.fields import Spec
from tools.lib.tool import Tool, run_tool
from tools.lib.packfiles import Found, PackFiles

NEW = object()
VOCABULARY = "vocab"     # the list of vocabulary sections
NONE = object()          # "take the field out": its default applies
ADD = object()
MOVES = {"up": -1, "down": 1}
ID_ABOUT = "What other entries call it. Enter renames it, and every use changes with it."


def kind_title(kind: str) -> str:
    if kind == VOCABULARY:
        return "Vocabulary"
    return kind.split(".")[-1].replace("_", " ").capitalize()


class Entries(Tool):
    name = "Entries"
    about = "Every entry of the pack by kind: objects, items, characters and the rest, field by field."

    def __init__(self, pack: PackFiles, look: screen.Look, kind: Optional[str] = None, entry_id: Any = None):
        self.pack, self.look = pack, look
        self.kind: Optional[str] = None
        self.found: Optional[Found] = None
        self.selected = 0
        self.form = None
        self.after: Optional[Callable] = None
        self.message: Tuple[str, str] = ("", "quiet")
        self.closed = False
        self.trail: List[Tuple[str, str]] = []       # (kind, id) of the entries a use was opened from
        self.edit_text = term.edit_text              # tests put a stand-in here
        if kind and entry_id is not None and pack.find(kind, entry_id):
            self.kind = kind
            self.open(pack.find(kind, entry_id))
        elif kind:
            self.choose_entry(kind)
        else:
            self.choose_kind()

    # --- helpers -------------------------------------------------------------------

    @property
    def entry(self) -> dict:
        return self.found.entry

    @property
    def namespace(self) -> str:
        return fields.namespace_of(self.kind)

    @property
    def key(self) -> str:
        """The field that names the entry: 'id', or a vocabulary section's number ('size', 'rank', 'min')."""
        return fields.key_field(self.kind)

    @property
    def ident(self) -> Any:
        return self.entry.get(self.key)

    @property
    def vocab(self) -> bool:
        return self.kind is not None and self.kind.startswith(fields.VOCAB)

    def specs(self) -> List[Spec]:
        """The entry's fields: the id, then what kind of entry it is, then the rest in the schema's order.
        Reserved fields show only when the entry uses them."""
        specs = [s for s in fields.fields(self.kind, self.entry) if not s.reserved or s.name in self.entry]
        rest = [s for s in specs if s.name != self.key]
        first = [fields.key_spec(self.kind)] + [s for s in rest if s.kind == "fixed"]
        return first + [s for s in rest if s not in first]

    def changed(self, words: str) -> None:
        self.pack.touch(self.found.file)
        self.say(words)

    def taken(self, ident: Any) -> bool:
        if self.vocab:
            return self.pack.find(self.kind, ident) is not None
        return any(i == ident for i, _ in fields.ids(self.pack, self.namespace))

    # --- choosing --------------------------------------------------------------------

    def choose_kind(self, notice: str = "", selected: Optional[str] = None) -> None:
        self.kind, self.found = None, None
        choices = [forms.Choice(kind_title(kind), kind, str(sum(1 for _ in self.pack.entries(kind))))
                   for kind in fields.EDITABLE_KINDS if kind in self.pack.kinds]
        if "vocab" in self.pack.kinds:
            choices.append(forms.Choice("Vocabulary…", VOCABULARY, "tags, stats, sizes…",
                                        "The words the rest of the pack refers to: tags, stats, slot types, sizes, "
                                        "factions, flags and the rest."))
        picker = forms.Picker(self.look, "Entries", choices, selected)
        picker.notice = notice
        self.ask(picker, lambda kind: self.choose_section() if kind == VOCABULARY else self.choose_entry(kind))

    def choose_section(self, selected: Optional[str] = None) -> None:
        """The vocabulary's sections, in the schema's order, with how many entries each has."""
        self.kind, self.found = VOCABULARY, None
        choices = [forms.Choice(kind_title(kind), kind, str(sum(1 for _ in self.pack.entries(kind))))
                   for kind in fields.vocab_kinds()]
        self.ask(forms.Picker(self.look, "Vocabulary", choices, selected), self.choose_entry)

    def choose_entry(self, kind: str, selected: Any = None) -> None:
        self.kind, self.found, self.trail = kind, None, []
        choices = []
        for found in self.pack.entries(kind):
            e = found.entry
            key = fields.key_field(kind)
            label = e.get("name") or e.get("text") or e.get(key, "?")
            glyph = e.get("glyph")
            choices.append(forms.Choice(f"{glyph} {label}" if glyph else str(label), e.get(key),
                                        str(e.get(key, "")), e.get("description", "")))
        choices.append(forms.Choice("New…", NEW))
        self.ask(forms.Picker(self.look, kind_title(kind), choices, selected),
                 lambda picked: self.start_new() if picked is NEW else self.open(self.pack.find(kind, picked)))

    def open(self, found: Found) -> None:
        self.found, self.selected = found, 0
        self.say("")

    # --- the screen ------------------------------------------------------------------

    def render(self, columns: int, rows: int) -> str:
        look, width = self.look, screen.inner_width(self.look, columns)
        right = self.pack.manifest.get("name", self.pack.id) + (" *" if self.pack.dirty else "")
        if self.form is not None:
            return self.form_screen(columns, rows, self.heading)
        bands = [screen.title(look, self.heading(), right, width), glance.lines(self.pack, look, self.kind, self.entry, width),
                 self.body(width), self.detail(width), screen.hints(look, self.hints(), width)]
        flex = 2 if bands[1] else 1
        return screen.draw(look, [b for b in bands if b], columns, rows, flex=flex, focus=self.selected).text

    def heading(self) -> str:
        if self.found is None:
            return f"Entries · {kind_title(self.kind)}" if self.kind else "Entries"
        return f"{kind_title(self.kind)} · {self.entry.get('name') or self.ident or ''}"

    def body(self, width: int) -> List[str]:
        """One line per field: its name, then its value (or its default, quietly)."""
        style, cursor = self.look.style, self.look.glyphs["cursor"]
        specs = self.specs()
        self.selected = max(0, min(self.selected, len(specs) - 1))
        name_width = min(14, max(len(s.name) for s in specs))
        lines = []
        for index, spec in enumerate(specs):
            value = self.entry.get(spec.name)
            room = max(4, width - name_width - 2)
            if value is None:
                shown = style.role("missing", "danger") if spec.required else style.role(fields.default_text(spec), "quiet")
            elif spec.kind == "colour":
                shown = f"{colours.sample(self.look, value)} {value}"
            elif spec.kind == "size":
                shown = f"{value} {dict(fields.ids(self.pack, 'size')).get(value, '')}".strip()
            else:
                shown = fields.summary(spec, value, room)
            name = spec.name[:name_width].ljust(name_width)
            if index == self.selected:
                lines.append(cursor + style.key(name) + " " + shown)
            else:
                lines.append(" " + name + " " + shown)
        return lines

    def detail(self, width: int) -> List[str]:
        """The picked field's description, what's wrong with the entry, and the last message."""
        style = self.look.style
        specs = self.specs()
        spec = specs[self.selected] if specs else None
        about = self.key_about() if spec is not None and spec.name == self.key else spec.description if spec else ""
        lines = screen.wrap(about, width)[:3]
        lines = [style.role(line, "quiet") for line in lines]
        problems = fields.entry_problems(self.kind, self.entry)
        for problem in problems[:3]:
            lines += [style.role(line, "danger") for line in screen.wrap(problem, width)]
        if len(problems) > 3:
            lines.append(style.role(f"…and {len(problems) - 3} more.", "danger"))
        text, role = self.message
        if text:
            lines += [style.role(line, role) for line in screen.wrap(text, width)]
        return lines

    def key_about(self) -> str:
        if self.key == "id":
            return ID_ABOUT
        if self.namespace:
            return f"The {self.key} number other entries use. Enter changes it, and every use changes with it."
        return fields.key_spec(self.kind).description or f"The {self.key} this entry is for."

    def hints(self) -> List[str]:
        return ["↑↓ field", "Enter edit", "E entry…", "U uses", f"{self.look.key('back')} back"]

    # --- keys ------------------------------------------------------------------------

    def handle(self, key: str) -> bool:
        keep = self._handle(key)
        return keep and not self.closed

    def _handle(self, key: str) -> bool:
        if self.form is not None:
            result = self.form.handle(key)
            if result is forms.CANCEL:
                self.form = None
                if self.kind is None:                       # the kind list: leave the tool
                    return self.leave()
                if self.found is None and self.vocab:       # a section's entries: back to the sections
                    self.choose_section(self.kind)
                elif self.found is None:                    # an entry list or the sections: back to the kinds,
                    self.choose_kind(selected=self.kind)    # on the one just left
            elif result is not None:
                self.form, after = None, self.after
                after(result)
            return True
        action = self.look.action(key)
        if action in MOVES:
            self.selected += MOVES[action]
            self.say("")
        elif action in ("back", "quit") and self.trail:            # opened from a use: back to where it was
            self.kind, ident = self.trail.pop()
            self.open(self.pack.find(self.kind, ident) or self.found)
        elif action in ("back", "quit"):
            self.choose_entry(self.kind, self.ident)
        elif key == "enter":
            specs = self.specs()
            if specs:
                self.edit(specs[self.selected])
        elif key.lower() == "e":
            self.entry_actions()
        elif key.lower() == "u":
            self.show_uses()
        return True

    # --- where it's used -----------------------------------------------------------------

    def show_uses(self) -> None:
        """Where the entry is used (for items, where it comes from first); Enter opens that entry."""
        ident = self.ident
        found = sources.item_uses(self.pack, ident) if self.kind == "items" else sources.uses(self.pack, self.namespace, ident)
        if not found:
            return self.say(f"Nothing uses {ident}." + (" " + glance.NOWHERE if self.kind == "items" else ""),
                            "danger" if self.kind == "items" else "quiet")
        choices = []
        for use in found:
            mark = "+ " if use.source else "  "
            words = use.words + (f", {use.problem}" if use.problem else "")
            choices.append(forms.Choice(mark + use.name, (use.kind, use.entry_id), words))
        picker = forms.Picker(self.look, f"Uses of {ident}", choices)
        picker.notice = "+ marks where the player gets it." if self.kind == "items" else ""
        back = (self.kind, ident)

        def picked(where):
            kind, entry_id = where
            target = self.pack.find(kind, entry_id) if fields.editable(kind) else None
            if target is None:
                return self.say("That's in pack.json; edit it there." if kind == "pack" else f"Can't open {entry_id} here.")
            self.trail.append(back)
            self.kind = kind
            self.open(target)
            self.say(f"{self.look.key('back')} goes back to {back[1]}.")
        self.ask(picker, picked)

    # --- editing a field -------------------------------------------------------------

    def edit(self, spec: Spec) -> None:
        value = self.entry.get(spec.name)
        if spec.name == self.key:
            return self.start_rename()
        if spec.kind == "fixed":
            return self.say(f"The {spec.name} is chosen when the entry is made.")
        if spec.kind == "flag":
            new = not (value if value is not None else bool(spec.default))
            return self.put(spec, None if new == bool(spec.default) else new)
        if spec.kind in ("text", "integer", "number"):
            return self.edit_line(spec, value)
        if spec.kind == "long":
            return self.edit_long(spec, value)
        if spec.kind in ("choice", "size", "ref"):
            return self.edit_choice(spec, value)
        if spec.kind == "refs":
            return self.edit_list(spec)
        if spec.kind == "colour":
            return colours.choose(self, f"Colour: {spec.name}", lambda c: self.put(spec, None if c is colours.DEFAULT else c),
                                  value, default="Default")
        return self.edit_json(spec, value)

    def put(self, spec: Spec, value: Any) -> None:
        """Sets a field; None takes it out (its default applies)."""
        if value is None:
            self.entry.pop(spec.name, None)
            self.changed(f"{spec.name}: " + (f"back to the default ({fields.default_text(spec)})"
                                             if fields.default_text(spec) else "taken out") + ".")
        else:
            self.entry[spec.name] = value
            self.changed(f"{spec.name}: {fields.summary(spec, value, 40)}.")

    def edit_line(self, spec: Spec, value: Any) -> None:
        def check(text: str) -> str:
            if not text:
                return "It's required." if spec.required else ""
            if spec.kind != "text":
                try:
                    number = int(text) if spec.kind == "integer" else float(text)
                except ValueError:
                    return "A whole number." if spec.kind == "integer" else "A number."
                return fields.problem(spec, number)
            return fields.problem(spec, text)

        def done(text: str):
            if not text:
                return self.put(spec, None)
            self.put(spec, text if spec.kind == "text" else int(text) if spec.kind == "integer" else float(text))
        note = spec.description + (" Empty takes it out." if not spec.required else "")
        self.ask(forms.Field(self.look, spec.name, "" if value is None else str(value), check, note), done)

    def edit_long(self, spec: Spec, value: Any) -> None:
        text = self.edit_text("" if value is None else str(value), ".txt")
        if text is None:
            return self.say("The text editor didn't save. Nothing changed.", "danger")
        text = text.strip()
        if not text:
            return self.say(f"{spec.name} is required: kept as it was.", "danger") if spec.required else self.put(spec, None)
        problem = fields.problem(spec, text)
        if problem:
            return self.say(f"{spec.name}: {problem} Kept as it was.", "danger")
        self.put(spec, text)

    def edit_choice(self, spec: Spec, value: Any) -> None:
        if spec.kind == "choice":
            choices = [forms.Choice(str(c), c) for c in spec.choices]
        else:
            known = fields.ids(self.pack, spec.namespace)
            if not known and spec.kind == "ref":
                return self.edit_line(spec._replace(kind="text"), value)
            choices = [forms.Choice(str(i), i, name) for i, name in known]
        if not spec.required:
            default = fields.default_text(spec)
            choices.insert(0, forms.Choice(f"(default: {default})" if default else "(none)", NONE))
        self.ask(forms.Picker(self.look, spec.name, choices, value),
                 lambda picked: self.put(spec, None if picked is NONE else picked))

    def edit_list(self, spec: Spec) -> None:
        """A list of ids: Enter on one takes it out, Add… puts one in; Esc is done."""
        current = list(self.entry.get(spec.name, []))
        names = dict(fields.ids(self.pack, spec.namespace))
        choices = [forms.Choice(str(i), ("remove", n), names.get(i, ""), "Enter takes it out.") for n, i in enumerate(current)]
        choices.append(forms.Choice("Add…", ADD))

        def picked(choice):
            if choice is ADD:
                left = [(i, name) for i, name in fields.ids(self.pack, spec.namespace) if i not in current]
                if not left:
                    self.say("Nothing left to add.")
                    return self.edit_list(spec)
                return self.ask(forms.Picker(self.look, f"Add to {spec.name}", [forms.Choice(str(i), i, n) for i, n in left]),
                                lambda new: (self.put(spec, current + [new]), self.edit_list(spec)))
            del current[choice[1]]
            self.put(spec, current or None)
            self.edit_list(spec)
        picker = forms.Picker(self.look, spec.name, choices)
        picker.notice = spec.description
        self.ask(picker, picked)

    def edit_json(self, spec: Spec, value: Any, text: Optional[str] = None) -> None:
        """Bigger values as JSON in the text editor. A mistake can be fixed straight away."""
        if text is None:
            start = value if value is not None else ([] if spec.node.get("type") == "array" else {})
            text = json.dumps(start, indent=2, ensure_ascii=False) + "\n"
        edited = self.edit_text(text, ".json")
        if edited is None:
            return self.say("The text editor didn't save. Nothing changed.", "danger")
        if not edited.strip():
            return self.say(f"{spec.name} is required: kept as it was.", "danger") if spec.required else self.put(spec, None)
        try:
            new = json.loads(edited)
        except json.JSONDecodeError as error:
            question = forms.Question(self.look, f"That isn't valid JSON: {error.msg} (line {error.lineno}). "
                                                 "Edit it again, or drop the change?",
                                      [("e", "edit again", True), ("n", "drop it", False)])
            return self.ask(question, lambda again: self.edit_json(spec, value, edited) if again
                            else self.say("Dropped. Nothing changed."))
        self.put(spec, None if new in ([], {}) and not spec.required else new)

    # --- the whole entry ---------------------------------------------------------------

    def entry_actions(self) -> None:
        rename = "Rename the id…" if self.key == "id" else f"Change the {self.key}…"
        actions = [("Edit it all as JSON", self.edit_all), (rename, self.start_rename),
                   ("Duplicate…", self.start_duplicate), ("Delete", self.start_delete)]
        if self.vocab:                                       # order matters in some sections (phases, levels)
            actions += [("Move earlier", lambda: self.move(-1)), ("Move later", lambda: self.move(1))]
        if self.pack.dirty:
            actions.append(("Save changes", self.save))
        self.ask(forms.Picker(self.look, f"{kind_title(self.kind)} · {self.ident}",
                              [forms.Choice(label, fn) for label, fn in actions]), lambda fn: fn())

    def edit_all(self, text: Optional[str] = None) -> None:
        if text is None:
            text = json.dumps(self.entry, indent=2, ensure_ascii=False) + "\n"
        edited = self.edit_text(text, ".json")
        if edited is None:
            return self.say("The text editor didn't save. Nothing changed.", "danger")
        try:
            new = json.loads(edited)
            if not isinstance(new, dict):
                raise ValueError("an entry is an object: { … }")
        except (json.JSONDecodeError, ValueError) as error:
            words = f"{error.msg} (line {error.lineno})" if isinstance(error, json.JSONDecodeError) else str(error)
            question = forms.Question(self.look, f"That isn't a valid entry: {words}. Edit it again, or drop the change?",
                                      [("e", "edit again", True), ("n", "drop it", False)])
            return self.ask(question, lambda again: self.edit_all(edited) if again else self.say("Dropped. Nothing changed."))
        if new.get(self.key) != self.ident:
            how = "Rename" if self.key == "id" else f"Change the {self.key}"
            return self.say(f"Change the {self.key} with {how}, so its uses follow. Nothing changed.", "danger")
        self.entry.clear()
        self.entry.update(new)
        self.changed("Entry changed.")

    def new_id_field(self, title: str, start: Any, done: Callable[[Any], None], note: str = "") -> None:
        """Asks for a new id (or a section's number) that nothing else has."""
        key_spec = fields.key_spec(self.kind)

        def check(text: str) -> str:
            if key_spec.kind == "integer":
                try:
                    number = int(text)
                except ValueError:
                    return "A whole number."
                return fields.problem(key_spec, number) or (f"{number} is taken." if self.taken(number) else "")
            return fields.problem(key_spec, text) or (f"{text} is taken." if self.taken(text) else "")
        self.ask(forms.Field(self.look, title, str(start), check, note),
                 lambda text: done(int(text) if key_spec.kind == "integer" else text))

    def next_key(self) -> Any:
        """A free id like this one's ('_2'…), or the number after the section's highest."""
        if self.key == "id":
            return fields.next_free(self.ident or "", lambda i: self.taken(i))
        numbers = [f.entry.get(self.key) for f in self.pack.entries(self.kind) if isinstance(f.entry.get(self.key), int)]
        return max(numbers, default=-1) + 1

    def start_rename(self) -> None:
        old, key = self.ident, self.key
        used = refs.uses(self.pack, self.namespace, old) if self.namespace else []

        def done(new: Any) -> None:
            if new == old:
                return
            count = refs.rename(self.pack, self.namespace, old, new) if self.namespace else 0
            self.entry[key] = new
            if key != "id" and not self.namespace:
                return self.changed(f"{key}: {new}.")
            self.changed(f"Changed to {new}; {count} use(s) changed with it. Saved games that know {old} won't "
                         "find it: raise the pack's major version.")
        title = "New id" if key == "id" else f"New {key}"
        note = f"Used in {len(used)} place(s); they all change with it." if self.namespace else ""
        self.new_id_field(title, old, done, note)

    def start_duplicate(self) -> None:
        def done(new: Any) -> None:
            twin = copy.deepcopy(self.entry)
            twin[self.key] = new
            self.pack.add(self.kind, twin, self.found.file)
            self.open(self.pack.find(self.kind, new))
            self.say(f"A copy of it as {new}.")
        self.new_id_field("Id of the copy" if self.key == "id" else f"The copy's {self.key}", self.next_key(), done)

    def start_delete(self) -> None:
        ident = self.ident
        used = refs.uses(self.pack, self.namespace, ident) if self.namespace else []
        if used:
            files = sorted({rel for rel, _ in used})
            return self.say(f"Still used in {len(used)} place(s) ({', '.join(files)}). Change those first.", "danger")

        def done(_) -> None:
            self.pack.remove(self.kind, self.found)
            self.choose_entry(self.kind)
            self.form.notice = f"Deleted {ident}."
        self.ask(forms.Question(self.look, f"Delete {ident}?", [("y", "delete", True)]), done)

    def move(self, step: int) -> None:
        """Moves a vocabulary entry earlier or later in its section."""
        listed = self.pack.siblings(self.kind, self.found)
        here = next(i for i, e in enumerate(listed) if e is self.entry)
        there = here + step
        if not 0 <= there < len(listed):
            return self.say("It's already " + ("first." if step < 0 else "last."))
        listed[here], listed[there] = listed[there], listed[here]
        self.changed(f"Now {there + 1} of {len(listed)} in {kind_title(self.kind).lower()}.")

    def start_new(self) -> None:
        variants = fields.variants(self.kind)
        if variants:
            return self.ask(forms.Picker(self.look, f"New {kind_title(self.kind).lower()}: which kind?",
                                         [forms.Choice(v, v) for v in variants]), self.name_new)
        self.name_new(None)

    def name_new(self, variant: Optional[str]) -> None:
        prefix = fields.ITEM_PREFIXES.get(variant, "") if variant else fields.prefix_of(self.kind)
        if self.key != "id":
            numbers = [f.entry.get(self.key) for f in self.pack.entries(self.kind) if isinstance(f.entry.get(self.key), int)]
            prefix = max(numbers, default=-1) + 1

        def done(new: Any) -> None:
            entry = {self.key: new}
            if variant:
                entry[fields.discriminator(self.kind)] = variant
            self.pack.add(self.kind, entry)
            self.open(self.pack.find(self.kind, new))
            self.say("Made. Fill in what it's missing (in red below); Enter edits a field.")
        self.new_id_field("Id of the new entry" if self.key == "id" else f"The new entry's {self.key}", prefix, done,
                          "Lower case, words joined by _." if self.key == "id" else "")


if __name__ == "__main__":
    sys.exit(run_tool(Entries, sys.argv[1:]))
