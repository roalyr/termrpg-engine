"""
Command-line tools for working on content packs.

  python3 -m core.packtool check   <pack>             validate a pack (game pack or UI pack)
  python3 -m core.packtool ids     <pack> [namespace] list declared ids
  python3 -m core.packtool refs    <pack> <id>        where an id is declared and used
  python3 -m core.packtool explain [topic]            document a schema part

Topics for explain: 'checks', 'ops', 'check <name>', 'op <name>', 'item <kind>',
'vocab <section>', 'widget <name>', 'ui tokens|keys|screens|words|manifest', a schema definition name ('location', 'placement', 'event'…),
or a schema file name ('pack', 'vocab', 'world'…).
"""
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from core import schema
from core import uipack
from core.pack import SCHEMA_DIR, index_pack, main as check_main, _a

COMMON = "common.schema.json"
SIMPLE_DEFS = {  # common definitions that read better as a word than as their fields
    "id": "id", "label": "label (short name, at most 32 characters)", "text": "text", "glyph": "glyph",
    "notes": "author notes", "tags": "list of tag ids", "size": "size class (0-9)",
    "duration": "number of turns", "amount": "amount (number, {min, max} or scaled)",
    "subject": "subject", "agent": "agent", "condition": "condition", "effect": "effect",
    "effects": "list of effects", "interaction": "interaction", "item_pick": "item pick",
    "object_ref": "'this' or a placement id", "message_kind": "message kind",
}


# --- ids and refs -----------------------------------------------------------------

def cmd_ids(pack: Path, namespace: Optional[str]) -> int:
    index = index_pack(pack)
    if namespace is None:
        for ns in sorted(index.ids):
            print(f"{ns:14} {len(index.ids[ns])}")
        print("Give a namespace to list its ids, e.g.: ids <pack> item")
        return 0
    if namespace not in index.ids:
        print(f"No ids in namespace '{namespace}'. Namespaces: {', '.join(sorted(index.ids))}")
        return 1
    for key, where in sorted(index.ids[namespace].items(), key=lambda kv: str(kv[0])):
        print(f"{str(key):32} {where}")
    return 0


def cmd_refs(pack: Path, ref_id: str) -> int:
    index = index_pack(pack)
    declared = [(ns, where) for ns, known in index.ids.items() for key, where in known.items() if str(key) == ref_id]
    used = [(label, ref) for label, ref in index.refs if str(ref.value) == ref_id]
    if not declared and not used:
        print(f"'{ref_id}' is neither declared nor used.")
        return 1
    for ns, where in declared:
        print(f"declared  {ns:12} {where}")
    if not declared:
        print("declared  (nowhere: every use below is an error)")
    for label, ref in used:
        print(f"used      {ref.kind:12} {label}: {ref.path}")
    if not used:
        print("used      (nowhere)")
    return 0


# --- explain ----------------------------------------------------------------------

def _find(topic: List[str], schemas: schema.Schemas) -> Optional[Tuple[str, dict, str]]:
    """(title, schema node, file) for a topic."""
    common = schemas[COMMON]["$defs"]
    if len(topic) == 2 and topic[0] in ("check", "op"):
        key = f"{topic[0]}_{topic[1]}"
        return (f"{topic[0]} {topic[1]}", common[key], COMMON) if key in common else None
    if len(topic) == 2 and topic[0] == "item":
        defs = schemas["item.schema.json"]["$defs"]
        return (f"item kind '{topic[1]}'", defs[topic[1]], "item.schema.json") if topic[1] in defs else None
    if len(topic) == 2 and topic[0] == "widget":
        defs = schemas["ui.schema.json"]["$defs"]
        key = f"widget_{topic[1]}"
        return (f"widget '{topic[1]}'", defs[key], "ui.schema.json") if key in defs else None
    if len(topic) == 2 and topic[0] == "ui":
        defs = schemas["ui.schema.json"]["$defs"]
        key = f"{topic[1]}_file" if f"{topic[1]}_file" in defs else topic[1]
        return (f"ui {topic[1]}", defs[key], "ui.schema.json") if key in defs else None
    if len(topic) == 2 and topic[0] == "vocab":
        prop = schemas["vocab.schema.json"]["properties"].get(topic[1])
        return (f"vocab {topic[1]}", prop["items"], "vocab.schema.json") if prop else None
    if len(topic) == 1:
        name = topic[0]
        file = f"{name}.schema.json"
        if file in schemas and "properties" in schemas[file]:
            return (f"{name} ({file})", schemas[file], file)   # pack, vocab: the file is the definition
        for fname, doc in schemas.items():
            if name in doc.get("$defs", {}):
                return (name, doc["$defs"][name], fname)
        if file in schemas:
            return (f"{name} ({file})", {"description": schemas[file].get("description", "")}, file)
    return None


def _type_of(node: dict, file: str, schemas: schema.Schemas) -> str:
    if "x-ref" in node:
        return f"id of {_a(node['x-ref'].replace('_', ' '))}" if node["x-ref"] != "size" else SIMPLE_DEFS["size"]
    if "$ref" in node:
        target_file, _, frag = node["$ref"].partition("#")
        name = frag.split("/")[-1]
        if (target_file or file) == COMMON and name in SIMPLE_DEFS:
            return SIMPLE_DEFS[name]
        return name.replace("_", " ")
    if "const" in node:
        return f"always {node['const']!r}"
    if "enum" in node:
        return "one of: " + ", ".join(str(v) for v in node["enum"])
    kind = node.get("type", "")
    if kind == "array":
        return "list of " + _type_of(node.get("items", {}), file, schemas)
    if kind == "object" and "x-ref-keys" in node:
        return f"map of {node['x-ref-keys'].replace('_', ' ')} id to {_type_of(node.get('additionalProperties', {}), file, schemas)}"
    if "oneOf" in node or "anyOf" in node:
        return " or ".join(_type_of(b, file, schemas) for b in node.get("oneOf", node.get("anyOf")))
    return kind or "value"


def _limits(node: dict) -> str:
    parts = []
    for key, word in (("minimum", ">="), ("maximum", "<="), ("exclusiveMinimum", ">"), ("exclusiveMaximum", "<")):
        if key in node:
            parts.append(f"{word} {node[key]}")
    if "maxLength" in node:
        parts.append(f"at most {node['maxLength']} characters")
    if "maxItems" in node:
        parts.append(f"at most {node['maxItems']} items")
    if "default" in node:
        parts.append(f"default {node['default']!r}")
    return f" ({', '.join(parts)})" if parts else ""


def _print_fields(node: dict, file: str, schemas: schema.Schemas, indent: str) -> None:
    required = set(node.get("required", []))
    for name, prop in node.get("properties", {}).items():
        if name in ("$schema", "notes") or not isinstance(prop, dict):
            continue
        mark = "*" if name in required else " "
        reserved = " [reserved]" if prop.get("x-status") == "reserved" else ""
        print(f"{indent}{mark} {name}: {_type_of(prop, file, schemas)}{_limits(prop)}{reserved}")
        if prop.get("description"):
            print(f"{indent}    {prop['description']}")
        inner, inner_file = (prop.get("items", prop) if prop.get("type") == "array" else prop), file
        if isinstance(inner, dict) and "$ref" in inner and "x-ref" not in inner:
            target_file, _, frag = inner["$ref"].partition("#")
            if not ((target_file or file) == COMMON and frag.split("/")[-1] in SIMPLE_DEFS):
                hit = schema._resolve(inner["$ref"], file, schemas)
                inner, inner_file = hit if hit else (inner, file)
        if isinstance(inner, dict) and inner.get("type") == "object" and "properties" in inner and len(indent) < 16:
            _print_fields(inner, inner_file, schemas, indent + "    ")
    for combo in ("oneOf", "anyOf"):
        rules = [r.get("required") for r in node.get(combo, []) if isinstance(r, dict) and set(r) == {"required"}]
        if rules:
            word = "exactly one" if combo == "oneOf" else "at least one"
            print(f"{indent}  Give {word} of: {', '.join(r[0] for r in rules)}")


def cmd_explain(topic: List[str]) -> int:
    schemas = schema.load_schemas(SCHEMA_DIR)
    common = schemas[COMMON]["$defs"]
    if not topic:
        print(__doc__.split("Topics for explain:")[1].strip())
        print("\nSchema files: " + ", ".join(f.replace(".schema.json", "") for f in sorted(schemas)))
        return 0
    if topic in (["checks"], ["ops"]):
        prefix = "check_" if topic == ["checks"] else "op_"
        for key in sorted(k for k in common if k.startswith(prefix)):
            print(f"{key[len(prefix):]:16} {common[key].get('description', '')}")
        return 0
    found = _find(topic, schemas)
    if found is None:
        print(f"Nothing called '{' '.join(topic)}'. Try: explain checks, explain ops, explain item gear, "
              f"explain location. Run 'explain' alone for all topics.")
        return 2
    title, node, file = found
    print(title.upper())
    if node.get("description"):
        print(node["description"])
    if node.get("x-status") == "reserved":
        print("[reserved: designed, not supported by the engine yet]")
    if "properties" in node:
        print("\nFields (* required):")
        _print_fields(node, file, schemas, "  ")
    elif "oneOf" in node:
        print("\nForms: " + " | ".join(_type_of(b, file, schemas) for b in node["oneOf"]))
    return 0


def _check_ui(folder: Path) -> int:
    report = uipack.validate_ui_pack(folder)
    for line in report.errors:
        print(f"ERROR   {line}")
    for line in report.warnings:
        print(f"warning {line}")
    print(f"{'OK' if report.ok else 'FAILED'}: {len(report.errors)} error(s), {len(report.warnings)} warning(s)")
    return 0 if report.ok else 1


def main(argv: List[str]) -> int:
    if not argv:
        print(__doc__.strip())
        return 2
    command, args = argv[0], argv[1:]
    if command == "check" and len(args) == 1:
        if uipack.is_ui_pack(Path(args[0])):
            return _check_ui(Path(args[0]))
        return check_main(args)
    if command == "ids" and len(args) in (1, 2):
        return cmd_ids(Path(args[0]), args[1] if len(args) == 2 else None)
    if command == "refs" and len(args) == 2:
        return cmd_refs(Path(args[0]), args[1])
    if command == "explain":
        return cmd_explain(args)
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
