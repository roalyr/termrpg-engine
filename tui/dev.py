"""
The command line and the dev menu, for makers playtesting a pack.

'/' in a game opens the command line. It takes 'dev', which opens the dev menu, or any
effect as 'op field=value…' (give_item item=gear_cutter count=2) or as JSON; Tab
completes what's being typed from the schemas and the pack's ids (tools.lib.complete).
The menu changes the game through the engine's own effects, run by the player as if an
interaction had run them (give an item, go somewhere, set a flag, start a fight…), so
nothing it does is out of the rules' reach. It also shows the game's state and starts
the game again from one of the pack's starts. Everything is drawn with the tools' look
(tools.lib), in place of the game, until it closes.
"""
import json
import random
from typing import Callable, List, Optional, Sequence

from core import schema
from core.pack import SCHEMA_DIR
from engine import events, journal, starts
from engine.content import Content
from engine.effects import run
from engine.frozen import freeze
from engine.state import Ctx, GameState, Message, char_key, day_length, day_of, new_game, phase_of
from lib.ui import UI
from tools.lib import forms, screen
from tools.lib.complete import Completer, Suggestion

COMMANDS = {"dev": "the dev menu"}
FULL = 9999                     # enough to fill any pool


def _schemas():
    return schema.load_schemas(SCHEMA_DIR)


class Text:
    """Lines to read: up and down scroll, Esc or the close key goes back."""

    def __init__(self, look: screen.Look, title: str, lines: Sequence[str]):
        self.look, self.title, self.text, self.top = look, title, list(lines), 0

    def lines(self, width: int):
        wrapped: List[str] = []
        for line in self.text:
            wrapped += screen.wrap(line, width) if line else [""]
        self.top = max(0, min(self.top, len(wrapped) - 1))
        return wrapped, self.top

    def about(self) -> str:
        return ""

    def hints(self) -> List[str]:
        return ["↑↓ scroll", "Esc back"]

    def handle(self, key: str):
        action = self.look.action(key)
        if key == "esc" or action == "back":
            return forms.CANCEL
        if action == "up":
            self.top = max(0, self.top - 1)
        elif action == "down":
            self.top += 1
        return None


class CommandLine:
    """
    A line that suggests its next word: the suggestions show under it, matching what's
    typed; up and down pick one, Tab completes (as far as they agree, or to the pick),
    Enter gives the line.
    """

    SHOWN = 8

    def __init__(self, look: screen.Look, title: str, completer: Completer, note: str = ""):
        self.look, self.title, self.completer, self.note = look, title, completer, note
        self.value, self.problem, self.selected = "", "", 0

    def suggestions(self) -> List[Suggestion]:
        if self.value.lstrip().startswith("{"):
            return []                                        # JSON: no help
        return self.completer.suggest(self.value)[1]

    def lines(self, width: int):
        style = self.look.style
        lines = ["", f"{self.title}:", "/" + (style.inverse(self.value + " ") if style.colour else self.value + "_"), ""]
        if self.problem:
            lines += [style.role(line, "danger") for line in screen.wrap(self.problem, width)]
        found = self.suggestions()
        self.selected = max(0, min(self.selected, len(found) - 1))
        top = max(0, min(self.selected - self.SHOWN // 2, len(found) - self.SHOWN))
        for index, s in enumerate(found[top:top + self.SHOWN], start=top):
            detail = "  " + style.role(s.detail[:max(0, width - len(s.text) - 3)], "quiet") if s.detail else ""
            lines.append((self.look.glyphs["cursor"] + style.key(s.text) if index == self.selected else " " + s.text)
                         + detail)
        if len(found) > self.SHOWN:
            lines.append(style.role(f" {len(found)} in all: type to narrow", "quiet"))
        return lines, 2

    def about(self) -> str:
        words = self.value.split()
        if words and words[0] in self.completer.ops:
            return self.completer.about(words[0])
        return self.note

    def hints(self) -> List[str]:
        return ["Tab complete", "↑↓ pick", "Enter run", "Esc back"]

    def handle(self, key: str):
        if key == "esc":
            return forms.CANCEL
        found = self.suggestions()
        if key == "enter":
            return self.value
        if key == "tab" and found:
            completed = self.completer.complete(self.value)
            if completed == self.value:                      # nothing in common to add: take the pick
                completed = self.completer.complete(self.value, found[min(self.selected, len(found) - 1)])
            self.value, self.selected = completed, 0
        elif key == "up":
            self.selected = max(0, self.selected - 1)
        elif key == "down":
            self.selected = min(max(0, len(found) - 1), self.selected + 1)
        elif key == "backspace":
            self.value, self.selected = self.value[:-1], 0
        elif len(key) == 1 and key.isprintable():
            self.value, self.selected = self.value + key, 0
        self.problem = ""
        return None


class Console:
    """
    The command line, then the dev menu and its questions. get() and put() reach the
    game's state; put(state, fresh=True) replaces the game (a start), and the game saves it.
    """

    def __init__(self, content: Content, ui: UI, colour: bool, get: Callable[[], GameState],
                 put: Callable[..., None]):
        self.content, self.get, self.put = content, get, put
        self.look = screen.look(colour, ui, palette=content.palette)
        self.form = None
        self.after: Optional[Callable] = None
        self.stack: List[tuple] = []      # forms to go back to on Esc, with what they lead to
        self.closed = False

        def ids(namespace: str):
            return [(rid, str(record.get("name", rid))) for rid, record in content.all(namespace).items()]
        self.completer = Completer(ids, COMMANDS)
        self.ask(self.command_line(), self.command, top=True)

    def command_line(self) -> CommandLine:
        return CommandLine(self.look, "Command", self.completer,
                           "dev opens the dev menu. Or an effect, run by you: give_item item=gear_cutter "
                           "count=2, or JSON. Tab completes.")

    # --- plumbing ------------------------------------------------------------------

    def ask(self, form, after: Callable, top: bool = False) -> None:
        if self.form is not None and not top:
            self.stack.append((self.form, self.after))
        self.form, self.after = form, after

    def back(self) -> None:
        if self.stack:
            self.form, self.after = self.stack.pop()
        else:
            self.closed = True

    def render(self, columns: int, rows: int) -> str:
        look, width = self.look, screen.inner_width(self.look, columns)
        right = self.content.pack.get("name", "")
        lines, focus = self.form.lines(width)
        notice = screen.quiet(look, getattr(self.form, "notice", ""), width)
        about = screen.wrap(self.form.about(), width)[:3] if self.form.about() else []
        bands = [screen.title(look, getattr(self.form, "title", "") or "Dev", right, width), notice + lines,
                 [look.style.role(line, "quiet") for line in about], screen.hints(look, self.form.hints(), width)]
        if isinstance(self.form, Text):
            drawn = screen.draw(look, [b for b in bands if b], columns, rows, flex=1, scroll=self.form.top)
            self.form.top = drawn.scroll
            return drawn.text
        return screen.draw(look, [b for b in bands if b], columns, rows, flex=1, focus=focus + len(notice)).text

    def handle(self, key: str) -> bool:
        """One key; False once the console has closed."""
        result = self.form.handle(key)
        if result is forms.CANCEL:
            self.back()
        elif result is not None:
            after = self.after
            after(result)
        return not self.closed

    # --- the command line ----------------------------------------------------------

    def command(self, text: str) -> None:
        """Runs a finished line: a command, an effect as words, or an effect as JSON."""
        line = text.strip().lstrip("/")
        if line.lower() in COMMANDS:
            self.stack.clear()
            self.form = None
            return self.menu()
        if line.startswith("{"):
            effect, problem = self.parse_json(line)
        else:
            effect, problem = self.completer.build(line)
        if effect is None:
            self.form.problem = problem
            return
        self.apply([effect])

    def parse_json(self, text: str):
        try:
            effect = json.loads(text)
        except ValueError as error:
            return None, f"Not JSON: {error}"
        problem = self.completer.check(effect)
        return (None, problem) if problem else (effect, "")

    # --- the dev menu --------------------------------------------------------------

    def menu(self) -> None:
        entries = [
            ("Give an item…", self.give_item), ("Go to a location…", self.go_to), ("Set a flag…", self.set_flag),
            ("Change an object here…", self.set_object), ("Start an encounter…", self.start_encounter),
            ("Trigger an event…", self.trigger_event), ("Bring someone into the party…", self.join_party),
            ("Next day", self.next_day), ("Full heal (the party)", self.heal),
            ("Type an effect…", self.type_effect), ("State", self.show_state),
            ("Start again from a start…", self.restart)]
        picker = forms.Picker(self.look, "Dev", [forms.Choice(label, fn) for label, fn in entries])
        picker.notice = "Changes run through the game's own effects, as the player."
        self.ask(picker, lambda fn: fn(), top=not self.stack)

    def apply(self, effects: Sequence[dict], words: str = "") -> None:
        """Runs effects as the player, settles what they set off, and goes back to the game."""
        before = self.get()
        try:
            filled = [schema.apply_defaults(e, "common.schema.json#/$defs/effect", _schemas()) for e in effects]
            state = run(self.content, before, Ctx(self_id=before.player), freeze(filled))
            state = events.settle(self.content, state)
        except (KeyError, ValueError, TypeError) as error:
            return self.ask(Text(self.look, "That didn't work", [str(error)]), lambda _: None)
        if words:
            state = state._replace(messages=state.messages + (Message("quiet", words),))
        self.put(journal.record(before, state))
        self.closed = True

    def pick(self, title: str, choices: List[forms.Choice], then: Callable, notice: str = "") -> None:
        picker = forms.Picker(self.look, title, choices)
        picker.notice = notice
        if not choices:
            picker.notice = notice or "There's nothing to pick."
        self.ask(picker, then)

    def number(self, title: str, value: str, then: Callable[[int], None], note: str = "") -> None:
        def check(text):
            try:
                int(text)
                return ""
            except ValueError:
                return "A whole number."
        self.ask(forms.Field(self.look, title, value, check, note), lambda text: then(int(text)))

    def named(self, namespace: str, ids=None) -> List[forms.Choice]:
        records = self.content.all(namespace)
        return [forms.Choice(str(r.get("name", rid)), rid, rid) for rid, r in records.items()
                if ids is None or rid in ids]

    def give_item(self) -> None:
        def count(item_id):
            self.number("How many", "1", lambda n: self.apply([{"op": "give_item", "item": item_id, "count": n}]))
        self.pick("Give an item", self.named("item"), count)

    def go_to(self) -> None:
        here = self.get().characters[self.get().player].location
        choices = [c for c in self.named("location") if not self.content.get("location", c.value).get("template")]
        self.pick("Go to", choices, lambda loc: self.apply([{"op": "move_to", "location": loc}]),
                  f"You are in {here}.")

    def set_flag(self) -> None:
        flags = self.get().flags
        choices = [forms.Choice(fid, fid, f"now {flags.get(fid, 0)}") for fid in self.content.all("flag")]

        def value(flag_id):
            self.number(f"Value of {flag_id}", str(flags.get(flag_id, 0)),
                        lambda n: self.apply([{"op": "set_flag", "flag": flag_id, "value": n}]))
        self.pick("Set a flag", choices, value)

    def set_object(self) -> None:
        state = self.get()
        here = state.characters[state.player].location
        placed = [p for p in self.content.all("placement").values() if p["location"] == here and p.get("states")]
        choices = [forms.Choice(str(p.get("name", p["id"])), p["id"],
                                f"{p['id']} · {state.object_states.get(p['id'], p.get('state'))}") for p in placed]

        def to_state(placement_id):
            record = self.content.get("placement", placement_id)
            now = state.object_states.get(placement_id, record.get("state"))
            options = [forms.Choice(s, s, "now" if s == now else "") for s in record["states"]]
            self.pick(f"State of {placement_id}", options,
                      lambda s: self.apply([{"op": "set_state", "object": placement_id, "state": s}]))
        self.pick("Change an object here", choices, to_state, "" if choices else "Nothing here has states.")

    def start_encounter(self) -> None:
        self.pick("Start an encounter", self.named("encounter"),
                  lambda enc: self.apply([{"op": "start_encounter", "encounter": enc}]))

    def trigger_event(self) -> None:
        self.pick("Trigger an event", self.named("event"),
                  lambda ev: self.apply([{"op": "trigger_event", "event": ev}]),
                  "It still needs its cast and 'when'; chance and cooldown are skipped.")

    def join_party(self) -> None:
        state = self.get()
        ids = [cid for cid, cs in state.characters.items()
               if cid != state.player and cs.source == cid and cs.leader != state.player]
        self.pick("Bring into the party", self.named("character", ids),
                  lambda cid: self.apply([{"op": "join_party", "subject": {"character": cid}}]))

    def next_day(self) -> None:
        state = self.get()
        length = day_length(self.content)
        self.apply([{"op": "spend_time", "turns": length - state.turn % length}])

    def heal(self) -> None:
        health = self.content.role_stat("health")
        self.apply([{"op": "restore", "stat": health, "amount": FULL, "subject": "party"}], "Dev: the party is healed.")

    def type_effect(self) -> None:
        self.ask(self.command_line(), self.command)

    def show_state(self) -> None:
        self.ask(Text(self.look, "State", state_lines(self.content, self.get())), lambda _: None)

    def restart(self) -> None:
        choices = [forms.Choice("The pack's own start", "", "a new game")]
        choices += [forms.Choice(str(s["name"]), sid, sid, str(s.get("description", "")))
                    for sid, s in self.content.all("start").items()]

        def begin(start_id):
            seed = random.randrange(1, 2 ** 31)
            if not start_id:
                state = new_game(self.content, seed)
            else:
                state = starts.begin(self.content, seed, start_id)
            self.put(state, fresh=True)
            self.closed = True
        self.pick("Start again from", choices, begin, "The game in this slot is replaced.")


def state_lines(content: Content, state: GameState) -> List[str]:
    """What the game holds right now, for reading: time, where everyone is, flags, objects, relations, events."""
    me = state.characters[state.player]
    lines = [f"Day {day_of(content, state.turn)}, {phase_of(content, state.turn)}, turn {state.turn}",
             f"You: {me.location} {list(me.at) if me.at else ''}", ""]
    lines.append("Flags: " + (", ".join(f"{f} {state.flags.get(f, 0)}" for f in content.all("flag")) or "none"))
    here = [p for p in content.all("placement").values() if p["location"] == me.location and p.get("states")]
    if here:
        lines.append("Here: " + ", ".join(f"{p['id']} {state.object_states.get(p['id'], p.get('state'))}" for p in here))
    lines += ["", "People:"]
    for cid, cs in sorted(state.characters.items()):
        if cid == state.player:
            continue
        party = " (party)" if cs.leader == state.player else ""
        lines.append(f"{cid}: {cs.location or 'nowhere'}{party}{' down' if cs.down else ''}")
    mine = char_key(state.player)
    views = [(a, b, v) for a, row in state.relations.items() for b, v in row.items() if mine in (a, b)]
    if views:
        bare = lambda key: key.partition(":")[2]                  # 'character:<id>' -> '<id>'
        lines += ["", "Relations (who → whom):"] + [f"{bare(a)} → {bare(b)}: {v}" for a, b, v in sorted(views)]
    lines += ["", "Events (last fired on day):"]
    for eid, event in content.all("event").items():
        last = state.event_log.get(eid)
        lines.append(f"{eid} [{event['trigger']}]: " + (f"day {last}" if last is not None else "never"))
    waiting = list(state.event_requests) + ([state.encounter_request] if state.encounter_request else [])
    if waiting:
        lines += ["", "Waiting: " + ", ".join(waiting)]
    return lines
