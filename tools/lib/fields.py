"""
An entry's fields, read from the pack schemas: what each field is, how to show its value
and which input edits it. The schemas stay the one description of the data, so a field
added there shows up in the editor by itself.

Kinds of field:
  text      a line of text (labels, ids, glyphs)
  long      prose (descriptions, notes), edited in the text editor
  integer   a whole number, number  any number
  flag      yes or no
  choice    one of a few words (an enum)
  size      a size class, named in the vocabulary
  ref       the id of another entry; refs: a list of them
  colour    a palette colour or a terminal colour number
  json      anything else (effects, conditions, dialogue…), edited as JSON in the text editor
"""
import json
import re
from functools import lru_cache
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from core import schema
from core.pack import KIND_NAMESPACES, KIND_SCHEMAS, SCHEMA_DIR, VOCAB_NAMESPACES
from tools.lib.packfiles import KEYS, VOCAB, PackFiles, key_field  # noqa: F401  (key_field is for the tools)

COMMON = "common.schema.json"
LONG_TEXT = 100           # text fields longer than this are edited in the text editor
EDITABLE_KINDS = [k for k in KIND_SCHEMAS if k != "vocab"]
PREFIXES = {"regions": "reg_", "locations": "loc_", "zones": "zone_", "objects": "obj_", "actions": "action_",
            "skills": "skill_", "characters": "char_", "encounters": "enc_", "loot_tables": "loot_",
            "events": "event_", "strings": "str_", "modifications": "mod_", "art": "art_",
            "starts": "start_"}
VOCAB_PREFIXES = {"tags": "tag_", "stats": "stat_", "damage_types": "dmg_", "statuses": "status_",
                  "slot_types": "slot_", "grades": "grade_", "object_states": "state_", "phases": "phase_",
                  "factions": "faction_", "flags": "flag_"}
ITEM_PREFIXES = {"gear": "gear_", "material": "material_",
                 "consumable": "consumable_", "misc": "misc_"}


class Spec(NamedTuple):
    """One field of an entry."""
    name: str
    kind: str
    node: dict                # the field's schema, references followed
    required: bool
    namespace: str = ""       # for ref, refs
    choices: Tuple = ()       # for choice

    @property
    def description(self) -> str:
        return self.node.get("description", "")

    @property
    def default(self) -> Any:
        return self.node.get("default")

    @property
    def reserved(self) -> bool:
        return self.node.get("x-status") == "reserved"


@lru_cache(maxsize=None)
def schemas() -> schema.Schemas:
    return schema.load_schemas(SCHEMA_DIR)


def _follow(node: dict, file: str) -> Tuple[dict, str]:
    """A node with its $ref followed; the referring node's own keywords (description, x-ref) win."""
    seen = 0
    while isinstance(node, dict) and "$ref" in node and seen < 8:
        hit = schema._resolve(node["$ref"], file, schemas())
        if hit is None:
            break
        target, file = hit
        node = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
        seen += 1
    return node, file


def _ref_name(node: dict) -> str:
    """The common definition a node refers to ('colour', 'text'…), or ''."""
    ref = node.get("$ref", "")
    target, _, fragment = ref.partition("#")
    return fragment.rsplit("/", 1)[-1] if target in ("", COMMON) or target.endswith(COMMON) else ""


def vocab_kinds() -> List[str]:
    """The vocabulary's sections as kinds ('vocab.tags'…), in the schema's order."""
    root = schemas()[KIND_SCHEMAS["vocab"].partition("#")[0]]
    return [VOCAB + name for name, node in root.get("properties", {}).items() if node.get("type") == "array"]


def editable(kind: str) -> bool:
    return kind in EDITABLE_KINDS or kind in vocab_kinds()


def namespace_of(kind: str) -> str:
    """The namespace a kind's ids live in; '' for vocabulary sections nothing refers to (ranks, relation levels)."""
    if kind.startswith(VOCAB):
        section = kind[len(VOCAB):]
        return "size" if section == "sizes" else VOCAB_NAMESPACES.get(section, "")
    return KIND_NAMESPACES[kind]


def prefix_of(kind: str) -> str:
    return VOCAB_PREFIXES.get(kind[len(VOCAB):], "") if kind.startswith(VOCAB) else PREFIXES.get(kind, "")


def entry_target(kind: str) -> str:
    """The schema target for one entry of a kind: 'object.schema.json#/$defs/object'."""
    if kind.startswith(VOCAB):
        return f"{KIND_SCHEMAS['vocab'].partition('#')[0]}#/properties/{kind[len(VOCAB):]}/items"
    target = KIND_SCHEMAS[kind]
    file, _, fragment = target.partition("#")
    root, file = _follow(schema._resolve(target, file, schemas())[0], file)
    items = root["properties"]["entries"]["items"]
    _, _, frag = items["$ref"].partition("#")
    return f"{file}#{frag}"


def _entry_node(kind: str, entry: dict) -> Tuple[dict, str]:
    """The entry's definition; for kinds with variants (items) the variant its discriminator names."""
    file, _, fragment = entry_target(kind).partition("#")
    node, file = _follow(schema._resolve(entry_target(kind), file, schemas())[0], file)
    key = node.get("x-discriminator")
    if key:
        for branch in node.get("oneOf", []):
            resolved, bfile = _follow(branch, file)
            const = resolved.get("properties", {}).get(key, {}).get("const")
            if const == entry.get(key):
                return resolved, bfile
    return node, file


def variants(kind: str) -> List[str]:
    """The values of a kind's discriminator (item kinds), or []."""
    file, _, _ = entry_target(kind).partition("#")
    node, file = _follow(schema._resolve(entry_target(kind), file, schemas())[0], file)
    key = node.get("x-discriminator")
    if not key:
        return []
    return [_follow(b, file)[0].get("properties", {}).get(key, {}).get("const") for b in node.get("oneOf", [])]


def discriminator(kind: str) -> str:
    file, _, _ = entry_target(kind).partition("#")
    return _follow(schema._resolve(entry_target(kind), file, schemas())[0], file)[0].get("x-discriminator", "")


def fields(kind: str, entry: dict) -> List[Spec]:
    """Every field the entry may have, in the schema's order."""
    node, file = _entry_node(kind, entry)
    required = set(node.get("required", []))
    specs = []
    for name, raw in node.get("properties", {}).items():
        if name == "$schema" or not isinstance(raw, dict):
            continue
        specs.append(_spec(name, raw, file, name in required))
    return specs


def _spec(name: str, raw: dict, file: str, required: bool) -> Spec:
    common = _ref_name(raw)
    node, file = _follow(raw, file)
    if common == "colour":
        return Spec(name, "colour", node, required)
    if "const" in node:
        return Spec(name, "fixed", node, required)
    if node.get("x-ref") == "size":
        return Spec(name, "size", node, required, "size")
    if "x-ref" in node and node.get("type") in ("string", "integer"):
        return Spec(name, "ref", node, required, node["x-ref"])
    if node.get("type") == "array":
        items, _ = _follow(node.get("items", {}), file)
        if "x-ref" in items and items.get("type") == "string":
            return Spec(name, "refs", node, required, items["x-ref"])
    if "enum" in node:
        return Spec(name, "choice", node, required, choices=tuple(node["enum"]))
    kind = node.get("type")
    if kind == "string":
        long = common in ("text", "notes") or node.get("maxLength", 0) > LONG_TEXT or "maxLength" not in node and common != "id"
        return Spec(name, "long" if long and common not in ("label", "glyph", "id") else "text", node, required)
    if kind in ("integer", "number"):
        return Spec(name, kind, node, required)
    if kind == "boolean":
        return Spec(name, "flag", node, required)
    return Spec(name, "json", node, required)


def id_spec() -> Spec:
    """The id field, the same for every kind."""
    return _spec("id", {"$ref": f"{COMMON}#/$defs/id"}, COMMON, True)


def key_spec(kind: str) -> Spec:
    """The field that names an entry: the id, or a vocabulary section's number (a size, a rank…)."""
    key = key_field(kind)
    if key == "id":
        return id_spec()
    spec = next(s for s in fields(kind, {}) if s.name == key)
    return spec._replace(kind="integer", node={**spec.node, "type": "integer"}, namespace="")


# --- values -------------------------------------------------------------------------

def summary(spec: Spec, value: Any, width: int) -> str:
    """A field's value in one short line."""
    if value is None:
        return ""
    if spec.kind == "flag":
        return "yes" if value else "no"
    if spec.kind == "refs":
        text = ", ".join(str(v) for v in value)
    elif spec.kind == "json":
        if isinstance(value, list):
            text = f"{len(value)} entr{'y' if len(value) == 1 else 'ies'}"
        elif isinstance(value, dict):
            text = ", ".join(f"{k}: {_short(v)}" for k, v in value.items())
        else:
            text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value).replace("\n", " ")
    return text if len(text) <= width else text[:max(1, width - 1)] + "…"


def _short(value: Any) -> str:
    if isinstance(value, list) and all(not isinstance(v, (list, dict)) for v in value):
        return " ".join(str(v) for v in value) or "[]"
    if isinstance(value, (list, dict)):
        return "…" if value else json.dumps(value)
    return str(value)


def default_text(spec: Spec) -> str:
    """How a field left out reads: its default, or nothing."""
    if spec.default is None:
        return ""
    if spec.kind == "flag":
        return "yes" if spec.default else "no"
    return json.dumps(spec.default, ensure_ascii=False) if isinstance(spec.default, (list, dict)) else str(spec.default)


def problem(spec: Spec, value: Any) -> str:
    """Why a value doesn't fit the field's own rules (the checker sees the rest), or ''."""
    node = spec.node
    if spec.kind in ("text", "long"):
        if "minLength" in node and len(value) < node["minLength"]:
            return f"At least {node['minLength']} character(s)."
        if "maxLength" in node and len(value) > node["maxLength"]:
            return f"At most {node['maxLength']} characters (this is {len(value)})."
        if "pattern" in node:
            if not re.search(node["pattern"], value):
                return "Lower case letters, digits and _ , starting with a letter." if spec.name == "id" \
                    else f"Doesn't match {node['pattern']}."
    if spec.kind in ("integer", "number"):
        for key, word in (("minimum", "at least"), ("maximum", "at most")):
            if key in node and (value < node[key] if key == "minimum" else value > node[key]):
                return f"Must be {word} {node[key]}."
    return ""


# --- ids ----------------------------------------------------------------------------

def ids(pack: PackFiles, namespace: str) -> List[Tuple[Any, str]]:
    """(id, name) of everything in a namespace, from the pack as it is in memory."""
    kinds = {v: k for k, v in KIND_NAMESPACES.items()}
    if namespace in kinds:
        return [(f.entry.get("id"), f.entry.get("name") or f.entry.get("text", "")) for f in pack.entries(kinds[namespace])
                if f.entry.get("id")]
    if namespace == "placement":
        return [(p.get("id"), f"{f.entry.get('name', '')}") for f in pack.entries("locations")
                for p in f.entry.get("placements", []) if p.get("id")]
    vocab: Dict[str, Any] = {}
    for rel in pack.kinds.get("vocab", []):
        vocab.update(pack.data[rel])
    if namespace == "size":
        return [(s.get("size"), s.get("name", "")) for s in vocab.get("sizes", [])]
    sections = {v: k for k, v in VOCAB_NAMESPACES.items()}
    if namespace in sections:
        return [(e.get("id"), e.get("name", "")) for e in vocab.get(sections[namespace], []) if isinstance(e, dict)]
    return []


def entry_problems(kind: str, entry: dict) -> List[str]:
    """What the schema says is wrong with the entry on its own (references are checked on save)."""
    result = schema.validate(entry, entry_target(kind), schemas())
    return [f"{issue.path or 'entry'}: {issue.message}" if issue.path else issue.message for issue in result.errors]


def next_free(ident: str, taken) -> str:
    """'ident_2', 'ident_3'…: the first that 'taken' doesn't know."""
    n = 2
    while taken(f"{ident}_{n}"):
        n += 1
    return f"{ident}_{n}"
