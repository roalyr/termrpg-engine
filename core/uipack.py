"""
UI pack validation: the manifest, every listed file against its part of the UI schema,
and the rules a schema can't express:

- each widget appears only on the screens that allow it, at most once per screen;
- no two actions share a key, and none takes a key the engine's menus use (G, T, I and
  the gear screen's letters);
- hint labels exist in the words file; a hint shows actions or digits, not both;
- words use only their own placeholders;
- the world screen's grid row (the largest room plus the side panel) fits the minimum width.

A screen without a 'keys' widget gets a warning: its players won't see the keys.

Run from the project root:  python3 -m core.packtool check packs/ui/default
"""
import string
from pathlib import Path
from typing import Any, Dict, List, Tuple

from core import schema
from core.pack import SCHEMA_DIR, Report, _collect, _fmt, _read_json

UI_SCHEMA = "ui.schema.json"
KINDS = ("tokens", "keys", "screens", "words")
GRID_MAX_WIDTH = 12   # the world schema's widest grid


def _engine_keys() -> Dict[str, str]:
    """Keys the engine's own menu options always use, by option."""
    from engine import build, world
    keys = dict(world.MENU_KEYS)
    keys.update({kind: key for kind, key in build.ITEM_KEYS.items() if key})
    keys["modify"] = build.MODIFY_KEY
    return keys


# A binding may share an engine key when the two are never active at once: the gear
# screen's key opens it from the world, while Equip only works on that screen; the map's
# key opens it from the world, while the modifications list only opens on the gear screen.
SHARED_KEYS = {("gear", "equip"), ("map", "modify")}


def is_ui_pack(folder: Path) -> bool:
    return (folder / "ui.json").exists()


def load_merged(ui_dir: Path, schema_dir: Path = SCHEMA_DIR) -> Tuple[Report, Dict[str, Any]]:
    """Validates a UI pack and returns the report with each kind's files merged, defaults filled in."""
    errors: List[str] = []
    warnings: List[str] = []
    refs: List[Tuple[str, schema.Ref]] = []
    schemas = schema.load_schemas(schema_dir)
    manifest = _read_json(ui_dir / "ui.json", "ui.json", errors)
    if manifest is None:
        return Report(tuple(errors), tuple(warnings)), {}
    _collect(schema.validate(manifest, UI_SCHEMA, schemas), "ui.json", errors, warnings, refs)

    merged: Dict[str, Any] = {kind: {} for kind in KINDS}
    files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
    for kind in KINDS:
        for rel in files.get(kind, []) or []:
            if not isinstance(rel, str):
                continue
            data = _read_json(ui_dir / rel, rel, errors)
            if data is None:
                continue
            result = schema.validate(data, f"{UI_SCHEMA}#/$defs/{kind}_file", schemas)
            _collect(result, rel, errors, warnings, refs)
            if not result.errors and isinstance(data, dict):
                _merge(merged[kind], data)
    if errors:
        return Report(tuple(errors), tuple(warnings)), {}
    filled = {kind: schema.apply_defaults(merged[kind], f"{UI_SCHEMA}#/$defs/{kind}_file", schemas) for kind in KINDS}

    words = [e["id"] for e in filled["words"].get("entries", [])]
    for word in {w for w in words if words.count(w) > 1}:
        errors.append(f"words: duplicate word '{word}'")
    for label, ref in refs:
        if ref.kind == "word" and ref.value not in words:
            errors.append(_fmt(label, ref.path, f"unknown word '{ref.value}'"))
    _check_screens(filled["screens"], schemas, errors, warnings)
    _check_keys(filled["keys"], errors)
    _check_words(filled["words"], schemas, errors)
    _check_sizes(filled, errors)
    return Report(tuple(errors), tuple(warnings)), filled


def validate_ui_pack(ui_dir: Path, schema_dir: Path = SCHEMA_DIR) -> Report:
    return load_merged(ui_dir, schema_dir)[0]


def _merge(into: Dict[str, Any], data: Dict[str, Any]) -> None:
    """Later files win key by key; nested objects merge; word entries add up."""
    for key, value in data.items():
        if key == "$schema":
            continue
        if key == "entries" and isinstance(value, list):
            into.setdefault("entries", []).extend(value)
        elif isinstance(value, dict) and isinstance(into.get(key), dict):
            _merge(into[key], value)
        else:
            into[key] = value


def _widgets(layout: Any) -> List[str]:
    if not isinstance(layout, dict):
        return []
    if "widget" in layout:
        return [layout["widget"]]
    return [w for part in layout.get("row", layout.get("stack", [])) for w in _widgets(part)]


def _check_screens(screens: Dict[str, Any], schemas: schema.Schemas, errors: List[str], warnings: List[str]) -> None:
    defs = schemas[UI_SCHEMA]["$defs"]
    for screen, zones in screens.items():
        if screen in ("$schema", "notes") or not isinstance(zones, list):
            continue
        found = [w for zone in zones for w in _widgets(zone.get("content"))]
        for widget in dict.fromkeys(found):
            allowed = defs[f"widget_{widget}"]["x-screens"]
            if screen not in allowed:
                errors.append(f"screens: {screen}: widget '{widget}' isn't allowed here (only on {', '.join(allowed)})")
            if found.count(widget) > 1:
                errors.append(f"screens: {screen}: widget '{widget}' appears {found.count(widget)} times")
        if "keys" not in found:
            warnings.append(f"screens: {screen}: has no 'keys' widget, so players won't see the keys")


def _check_keys(keys: Dict[str, Any], errors: List[str]) -> None:
    by_key: Dict[str, List[str]] = {}
    for action, key in keys.get("bindings", {}).items():
        by_key.setdefault(key, []).append(action)
    engine_keys = {key: option for option, key in _engine_keys().items()}
    for key, actions in by_key.items():
        if len(actions) > 1:
            errors.append(f"keys: '{key}' is bound to {' and '.join(actions)}")
        if key.lower() in engine_keys and not all((a, engine_keys[key.lower()]) in SHARED_KEYS for a in actions):
            errors.append(f"keys: '{key}' ({' and '.join(actions)}) is the engine's key for "
                          f"'{engine_keys[key.lower()]}'; pick another")
    for context, hints in keys.get("hints", {}).items():
        for i, hint in enumerate(hints):
            if hint.get("actions") and hint.get("digits"):
                errors.append(f"keys: hints.{context}[{i}]: show actions or digits, not both")


def _check_words(words: Dict[str, Any], schemas: schema.Schemas, errors: List[str]) -> None:
    defs = schemas[UI_SCHEMA]["$defs"]["words_file"]["properties"]["engine"]["properties"]
    for key, template in words.get("engine", {}).items():
        allowed = defs.get(key, {}).get("x-placeholders", [])
        try:
            fields = [f for _, f, _, _ in string.Formatter().parse(template) if f is not None]
        except ValueError as e:
            errors.append(f"words: engine.{key}: broken braces ({e})")
            continue
        for field in fields:
            if field not in allowed:
                known = ", ".join("{" + a + "}" for a in allowed) or "none"
                errors.append(f"words: engine.{key}: unknown placeholder {{{field}}} (allowed: {known})")


def _check_sizes(ui: Dict[str, Any], errors: List[str]) -> None:
    tokens = ui["tokens"]
    size = tokens["size"]
    columns = size["min_columns"]
    world = [w for zone in ui["screens"].get("world", []) for w in _widgets(zone.get("content"))]
    if "grid" in world:
        cell = size["cell_width"]
        grid = GRID_MAX_WIDTH + (GRID_MAX_WIDTH - 1) * (cell - 1) + 4   # the largest room, in its own box
        needed = 2 + grid + 1 + size["side_min_width"]         # outer borders, grid, divider, side panel
        if needed > columns:
            errors.append(f"tokens: the world screen needs {needed} columns for the largest grid and the side panel, "
                          f"but min_columns is {columns}")
