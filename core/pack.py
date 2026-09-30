"""
Content pack validation: the manifest, every listed data file against its schema,
unique ids, cross-references between files, and rules a schema alone can't express.

Run from the project root:  python3 -m core.pack packs/test
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Set, Tuple

from core import schema

ROOT_DIR = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT_DIR / "schemas"

# Data file kind -> schema file. Kinds whose schema doesn't exist yet can't be loaded.
KIND_SCHEMAS = {
    "vocab": "vocab.schema.json",
    "regions": "world.schema.json",
    "locations": "world.schema.json",
    "objects": "object.schema.json",
    "items": "item.schema.json",
    "actions": "action.schema.json",
    "skills": "skill.schema.json",
    "characters": "character.schema.json",
    "encounters": "encounter.schema.json",
    "loot_tables": "loot.schema.json",
    "events": "event.schema.json",
    "strings": "strings.schema.json",
    "recipes": "recipe.schema.json",
}

# Entity kind -> reference namespace. Entity files hold {"entries": [{"id": ...}, ...]}.
KIND_NAMESPACES = {
    "regions": "region", "locations": "location", "objects": "object", "items": "item",
    "actions": "action", "skills": "skill", "characters": "character", "encounters": "encounter",
    "loot_tables": "loot_table", "events": "event", "strings": "string", "recipes": "recipe",
}

# Vocabulary section -> reference namespace.
VOCAB_NAMESPACES = {
    "tags": "tag", "stats": "stat", "damage_types": "damage_type", "statuses": "status",
    "slot_types": "slot_type", "object_states": "object_state", "phases": "phase",
    "factions": "faction", "flags": "flag",
}

STAT_ROLES = ("health", "power", "mass", "heat", "initiative")
POOL_ROLES = ("health", "heat")


class Report(NamedTuple):
    errors: Tuple[str, ...]
    warnings: Tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_pack(pack_dir: Path, schema_dir: Path = SCHEMA_DIR) -> Report:
    """Validates a content pack folder. Errors make the pack unusable; warnings don't."""
    errors: List[str] = []
    warnings: List[str] = []
    schemas = schema.load_schemas(schema_dir)

    manifest = _read_json(pack_dir / "pack.json", "pack.json", errors)
    if manifest is None:
        return Report(tuple(errors), tuple(warnings))
    refs: List[Tuple[str, schema.Ref]] = []
    _collect(schema.validate(manifest, "pack.schema.json", schemas), "pack.json", errors, warnings, refs)

    ids: Dict[str, Dict[Any, str]] = {}      # namespace -> id -> where it was declared
    checkable: Set[str] = {"size"}           # namespaces whose ids are known
    vocab: Dict[str, Any] = {}

    files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
    for kind, paths in files.items():
        if kind not in KIND_SCHEMAS or not isinstance(paths, list):
            continue  # already reported by the manifest schema
        schema_file = KIND_SCHEMAS[kind]
        if schema_file not in schemas:
            errors.append(f"pack.json: files.{kind}: there is no schema for '{kind}' yet")
            continue
        if kind in KIND_NAMESPACES:
            checkable.add(KIND_NAMESPACES[kind])
        for rel in paths:
            if not isinstance(rel, str):
                continue
            data = _read_json(pack_dir / rel, rel, errors)
            if data is None:
                continue
            _collect(schema.validate(data, schema_file, schemas), rel, errors, warnings, refs)
            if kind == "vocab" and isinstance(data, dict):
                _declare_vocab(data, rel, ids, vocab, errors)
            elif kind in KIND_NAMESPACES and isinstance(data, dict):
                for i, entry in enumerate(data.get("entries", [])):
                    if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                        _declare(ids, KIND_NAMESPACES[kind], entry["id"], f"{rel}: entries[{i}]", errors)
    if "vocab" in files:
        checkable.update(VOCAB_NAMESPACES.values())

    _check_refs(refs, ids, checkable, errors, warnings)
    _check_rules(manifest, vocab, errors, warnings)
    return Report(tuple(errors), tuple(warnings))


# --- Steps ---------------------------------------------------------------------

def _read_json(path: Path, label: str, errors: List[str]) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"{label}: file not found")
    except json.JSONDecodeError as e:
        errors.append(f"{label}: line {e.lineno}, column {e.colno}: invalid JSON ({e.msg})")
    return None


def _collect(result: schema.Result, label: str, errors: List[str], warnings: List[str],
             refs: List[Tuple[str, schema.Ref]]) -> None:
    errors.extend(_fmt(label, e.path, e.message) for e in result.errors)
    warnings.extend(_fmt(label, r.path, r.message) for r in result.reserved)
    refs.extend((label, r) for r in result.refs)


def _fmt(label: str, path: str, message: str) -> str:
    return f"{label}: {path}: {message}" if path else f"{label}: {message}"


def _declare(ids: Dict[str, Dict[Any, str]], namespace: str, key: Any, where: str, errors: List[str]) -> None:
    known = ids.setdefault(namespace, {})
    if key in known:
        errors.append(f"{where}: duplicate {namespace} '{key}' (first declared in {known[key]})")
    else:
        known[key] = where


def _declare_vocab(data: dict, label: str, ids: Dict[str, Dict[Any, str]], vocab: Dict[str, Any],
                   errors: List[str]) -> None:
    for section, namespace in VOCAB_NAMESPACES.items():
        for i, entry in enumerate(data.get(section, []) or []):
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                _declare(ids, namespace, entry["id"], f"{label}: {section}[{i}]", errors)
                vocab.setdefault(section, []).append(entry)
    for i, entry in enumerate(data.get("sizes", []) or []):
        if isinstance(entry, dict) and isinstance(entry.get("size"), int):
            _declare(ids, "size", entry["size"], f"{label}: sizes[{i}]", errors)
    for section in ("ranks", "relation_levels"):
        vocab.setdefault(section, []).extend(e for e in data.get(section, []) or [] if isinstance(e, dict))


def _check_refs(refs: List[Tuple[str, schema.Ref]], ids: Dict[str, Dict[Any, str]], checkable: Set[str],
                errors: List[str], warnings: List[str]) -> None:
    unchecked: Dict[str, int] = {}
    for label, ref in refs:
        if ref.kind == "pack":
            continue  # 'extends' is reserved and reported as such
        if ref.kind not in checkable:
            unchecked[ref.kind] = unchecked.get(ref.kind, 0) + 1
            continue
        if ref.value not in ids.get(ref.kind, {}):
            what = "size class" if ref.kind == "size" else ref.kind.replace("_", " ")
            hint = " (name it in the vocabulary's sizes)" if ref.kind == "size" else ""
            errors.append(_fmt(label, ref.path, f"unknown {what} '{ref.value}'{hint}"))
    for kind, count in sorted(unchecked.items()):
        warnings.append(f"{count} reference(s) to {kind.replace('_', ' ')}s not checked: "
                        f"the pack loads no {kind.replace('_', ' ')}s (or they have no schema yet)")


def _check_rules(manifest: dict, vocab: Dict[str, Any], errors: List[str], warnings: List[str]) -> None:
    stats = vocab.get("stats", [])
    for role in STAT_ROLES:
        holders = [s["id"] for s in stats if s.get("role") == role]
        if len(holders) != 1:
            found = f"found {', '.join(holders)}" if holders else "found none"
            errors.append(f"vocab: stat role '{role}' must be given to exactly one stat ({found})")
        elif role in POOL_ROLES and next(s for s in stats if s["id"] == holders[0]).get("kind") != "pool":
            errors.append(f"vocab: stat '{holders[0]}' has role '{role}' and must be a pool")

    for status in vocab.get("statuses", []):
        if "max_stacks" in status and status.get("stacking") != "stack":
            warnings.append(f"vocab: status '{status['id']}' sets max_stacks but doesn't stack")

    for section, key in (("ranks", "rank"), ("relation_levels", "min")):
        values = [e.get(key) for e in vocab.get(section, [])]
        if len(values) != len(set(values)):
            errors.append(f"vocab: {section} repeats a {key} value")

    settings = manifest.get("settings", {}) if isinstance(manifest.get("settings"), dict) else {}
    low, high = settings.get("relation_min", -100), settings.get("relation_max", 100)
    default = settings.get("relation_default", 0)
    if isinstance(low, int) and isinstance(high, int) and isinstance(default, int):
        if low >= high:
            errors.append("pack.json: settings: relation_min must be below relation_max")
        elif not low <= default <= high:
            errors.append("pack.json: settings: relation_default must lie between relation_min and relation_max")


def main(argv: List[str]) -> int:
    if len(argv) != 1:
        print("Usage: python3 -m core.pack <pack folder>")
        return 2
    report = validate_pack(Path(argv[0]))
    for line in report.errors:
        print(f"ERROR   {line}")
    for line in report.warnings:
        print(f"warning {line}")
    print(f"{'OK' if report.ok else 'FAILED'}: {len(report.errors)} error(s), {len(report.warnings)} warning(s)")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
