"""
Completion for effects typed as a line: 'op field=value field=value', e.g.

  give_item item=gear_cutter count=2
  move_to location=loc_storage
  join_party subject=char_juno
  message text="The lights flicker."

What may come next is read from the schemas: the op names, then each op's fields, then
the values a field takes (the ids of its kind, a subject's words and the characters, a
placed object, an enum's words). The ids come from whoever asks (the game's content, or
a pack being edited), so the game's console and the tools can share it. A value starting
with '{' or '[' is JSON (an amount range, a condition); effects that hold other effects
('if', 'choose') are written as JSON instead.
"""
import json
import re
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple

from core import schema
from tools.lib.fields import COMMON, _follow, _ref_name, schemas

Ids = Callable[[str], Sequence[Tuple[str, str]]]      # namespace -> [(id, name)]
NESTED = ("if", "choose")                              # ops that hold effects: JSON only
SUBJECT_WORDS = ("self", "target", "player", "party")
AGENT_WORDS = ("self", "target", "player")
NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


class Suggestion(NamedTuple):
    text: str              # what completing puts in place of the word being typed
    detail: str = ""       # a name or a description, shown quietly beside it


class Completer:
    """Suggests the next word of an effect line and turns a finished line into an effect."""

    def __init__(self, ids: Ids, commands: Optional[Dict[str, str]] = None):
        self.ids, self.commands = ids, dict(commands or {})
        root = schemas()[COMMON]["$defs"]
        self.ops: Dict[str, Tuple[dict, str]] = {}      # op -> (its definition, schema file)
        for branch in root["effect"]["oneOf"]:
            node, file = _follow(branch, COMMON)
            op = node["properties"]["op"]["const"]
            if op not in NESTED:
                self.ops[op] = (node, file)

    # --- what an op takes ----------------------------------------------------------

    def fields(self, op: str) -> Dict[str, dict]:
        node, _ = self.ops[op]
        return {name: raw for name, raw in node["properties"].items() if name != "op"}

    def required(self, op: str) -> List[str]:
        return [f for f in self.ops[op][0].get("required", []) if f != "op"]

    def about(self, op: str) -> str:
        """The op's description and its fields, required ones marked '*'."""
        node, _ = self.ops[op]
        need = set(self.required(op))
        listed = " ".join(f"{name}{'*' if name in need else ''}" for name in self.fields(op))
        return f"{node.get('description', '')} Fields: {listed}".strip()

    def _kind(self, op: str, name: str) -> Tuple[str, dict]:
        """('subject' | 'agent' | 'object' | 'ref' | 'enum' | 'boolean' | 'other', resolved node)."""
        raw = self.fields(op).get(name, {})
        common = _ref_name(raw)
        node, _ = _follow(raw, self.ops[op][1])
        if common in ("subject", "agent"):
            return common, node
        if common == "object_ref":
            return "object", node
        if "x-ref" in node:
            return "ref", node
        if "enum" in node:
            return "enum", node
        if node.get("type") == "boolean":
            return "boolean", node
        return "other", node

    def values(self, op: str, name: str) -> List[Suggestion]:
        kind, node = self._kind(op, name)
        if kind == "subject":
            return [Suggestion(w) for w in SUBJECT_WORDS] + self._named("character")
        if kind == "agent":
            return [Suggestion(w) for w in AGENT_WORDS] + self._named("character") + self._named("faction")
        if kind == "object":
            return [Suggestion("this")] + self._named("placement")
        if kind == "ref":
            return self._named(node["x-ref"])
        if kind == "enum":
            return [Suggestion(str(v)) for v in node["enum"]]
        if kind == "boolean":
            return [Suggestion("true"), Suggestion("false")]
        return []

    def _named(self, namespace: str) -> List[Suggestion]:
        return [Suggestion(str(i), str(n) if n != i else "") for i, n in self.ids(namespace)]

    # --- suggesting ----------------------------------------------------------------

    def suggest(self, text: str) -> Tuple[int, List[Suggestion]]:
        """Where the word being typed starts in the text, and what it could be (matching what's typed so far)."""
        start = text.rfind(" ") + 1
        word, before = text[start:], text[:start].split()
        if not before:
            found = [Suggestion(c, d) for c, d in self.commands.items()]
            found += [Suggestion(op, self.ops[op][0].get("description", "")) for op in self.ops]
            return start, [s for s in found if s.text.startswith(word)]
        op = before[0]
        if op not in self.ops:
            return start, []
        if "=" in word:
            name, _, typed = word.partition("=")
            if name not in self.fields(op):
                return start, []
            return start + len(name) + 1, [s for s in self.values(op, name) if s.text.startswith(typed)]
        used = {w.partition("=")[0] for w in before[1:]}
        need = set(self.required(op))
        found = [Suggestion(f"{name}=", "required" if name in need else "")
                 for name in self.fields(op) if name not in used]
        return start, [s for s in found if s.text.startswith(word)]

    def complete(self, text: str, choice: Optional[Suggestion] = None) -> str:
        """The text with the word being typed completed: to 'choice', or as far as every suggestion agrees."""
        start, found = self.suggest(text)
        if choice is None:
            if not found:
                return text
            if len(found) == 1:
                choice = found[0]
            else:
                common = _common_prefix([s.text for s in found])
                return text[:start] + common if len(common) > len(text) - start else text
        ending = "" if choice.text.endswith("=") else " "
        return text[:start] + choice.text + ending

    # --- building ------------------------------------------------------------------

    def build(self, text: str) -> Tuple[Optional[dict], str]:
        """The effect a finished line means, or None and what's wrong."""
        try:
            words = split(text)
        except ValueError as error:
            return None, str(error)
        if not words:
            return None, "Type an op, e.g. give_item."
        op = words[0]
        if op not in self.ops:
            return None, f"Unknown op '{op}'." + (" Write it as JSON." if op in NESTED else "")
        effect: Dict[str, Any] = {"op": op}
        for word in words[1:]:
            name, eq, value = word.partition("=")
            if not eq:
                return None, f"'{word}': write field=value."
            if name not in self.fields(op):
                return None, f"{op} has no field '{name}'. Its fields: {', '.join(self.fields(op))}."
            try:
                effect[name] = self._value(op, name, value)
            except ValueError as error:
                return None, f"{name}: {error}"
        problem = self.check(effect)
        return (None, problem) if problem else (effect, "")

    def check(self, effect: Any) -> str:
        """What's wrong with an effect (written any way), or '': the schema, then that every id it names exists."""
        found = schema.validate(effect, f"{COMMON}#/$defs/effect", schemas())
        if found.errors:
            first = found.errors[0]
            return f"{first.path}: {first.message}" if first.path else first.message
        for ref in found.refs:
            known = {i for i, _ in self.ids(ref.kind)}
            if known and ref.value not in known:
                return f"{ref.path}: unknown {ref.kind.replace('_', ' ')} '{ref.value}'"
        return ""

    def _value(self, op: str, name: str, text: str) -> Any:
        if text[:1] in "{[":
            return json.loads(text)
        kind, node = self._kind(op, name)
        if kind in ("subject", "agent"):
            if text in (SUBJECT_WORDS if kind == "subject" else AGENT_WORDS):
                return text
            if kind == "agent" and text in {i for i, _ in self.ids("faction")}:
                return {"faction": text}
            return {"character": text}
        if kind == "boolean":
            if text not in ("true", "false"):
                raise ValueError("true or false")
            return text == "true"
        if NUMBER.match(text) and kind != "ref":
            return float(text) if "." in text else int(text)
        return text


def split(text: str) -> List[str]:
    """
    The line's words, split at spaces: not inside "quotes" (which go) nor inside {…} or
    […] (kept whole, quotes and all, as JSON).
    """
    words, word, depth, quoted, started = [], "", 0, False, False
    for ch in text:
        if depth == 0 and ch == '"':
            quoted, started = not quoted, True
        elif depth == 0 and not quoted and ch == " ":
            if started:
                words.append(word)
            word, started = "", False
        else:
            if not quoted and ch in "{[":
                depth += 1
            elif not quoted and ch in "}]":
                depth -= 1
            word, started = word + ch, True
    if quoted:
        raise ValueError("A quote isn't closed.")
    if depth:
        raise ValueError("A { or [ isn't closed.")
    if started:
        words.append(word)
    return words


def _common_prefix(words: Sequence[str]) -> str:
    first, last = min(words), max(words)
    size = 0
    while size < len(first) and first[size] == last[size]:
        size += 1
    return first[:size]
