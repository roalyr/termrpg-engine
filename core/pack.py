"""
Content pack validation: the manifest, every listed data file against its schema,
unique ids, cross-references between files, and rules a schema alone can't express.

Run from the project root:  python3 -m core.pack packs/test
"""
import json
import re
import string
import sys
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Set, Tuple

from core import schema

ROOT_DIR = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT_DIR / "schemas"

# Data file kind -> schema (a file, or a definition inside one). Kinds whose schema doesn't exist yet can't be loaded.
KIND_SCHEMAS = {
    "vocab": "vocab.schema.json",
    "regions": "world.schema.json#/$defs/regions_file",
    "locations": "world.schema.json#/$defs/locations_file",
    "zones": "world.schema.json#/$defs/zones_file",
    "objects": "object.schema.json",
    "items": "item.schema.json",
    "actions": "action.schema.json",
    "skills": "skill.schema.json",
    "characters": "character.schema.json",
    "encounters": "encounter.schema.json",
    "loot_tables": "loot.schema.json",
    "events": "event.schema.json",
    "strings": "strings.schema.json",
    "modifications": "modification.schema.json",
}

# Entity kind -> reference namespace. Entity files hold {"entries": [{"id": ...}, ...]}.
KIND_NAMESPACES = {
    "regions": "region", "locations": "location", "zones": "zone", "objects": "object", "items": "item",
    "actions": "action", "skills": "skill", "characters": "character", "encounters": "encounter",
    "loot_tables": "loot_table", "events": "event", "strings": "string", "modifications": "modification",
}

# Vocabulary section -> reference namespace.
VOCAB_NAMESPACES = {
    "tags": "tag", "stats": "stat", "damage_types": "damage_type", "statuses": "status",
    "slot_types": "slot_type", "object_states": "object_state", "phases": "phase",
    "factions": "faction", "flags": "flag", "grades": "grade",
}

STAT_ROLES = ("health", "power", "mass", "heat", "initiative", "cargo")
POOL_ROLES = ("health", "heat")

Entries = Dict[str, Dict[str, dict]]  # kind -> id -> entry


class Report(NamedTuple):
    errors: Tuple[str, ...]
    warnings: Tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


class PackIndex(NamedTuple):
    """Everything the validator learned about a pack: its report, declared ids and references."""
    report: Report
    ids: Dict[str, Dict[Any, str]]            # namespace -> id -> where it is declared
    refs: Tuple[Tuple[str, schema.Ref], ...]  # (file, reference) for every reference found


def validate_pack(pack_dir: Path, schema_dir: Path = SCHEMA_DIR) -> Report:
    """Validates a content pack folder. Errors make the pack unusable; warnings don't."""
    return index_pack(pack_dir, schema_dir).report


def index_pack(pack_dir: Path, schema_dir: Path = SCHEMA_DIR) -> PackIndex:
    """Validates a pack and returns the report together with its ids and references."""
    errors: List[str] = []
    warnings: List[str] = []
    schemas = schema.load_schemas(schema_dir)

    manifest = _read_json(pack_dir / "pack.json", "pack.json", errors)
    if manifest is None:
        return PackIndex(Report(tuple(errors), tuple(warnings)), {}, ())
    refs: List[Tuple[str, schema.Ref]] = []
    _collect(schema.validate(manifest, "pack.schema.json", schemas), "pack.json", errors, warnings, refs)

    ids: Dict[str, Dict[Any, str]] = {}      # namespace -> id -> where it was declared
    checkable: Set[str] = {"size"}           # namespaces whose ids are known
    vocab: Dict[str, Any] = {}
    entries: Entries = {}
    where: Dict[Tuple[str, str], str] = {}   # (kind, id) -> "file: entries[i]"
    loaded: List[Tuple[str, str, Any]] = []  # (kind, file, data)

    files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
    for kind, paths in files.items():
        if kind not in KIND_SCHEMAS or not isinstance(paths, list):
            continue  # already reported by the manifest schema
        target = KIND_SCHEMAS[kind]
        if not schema.resolves(target, schemas):
            errors.append(f"pack.json: files.{kind}: there is no schema for '{kind}' yet")
            continue
        if kind in KIND_NAMESPACES:
            checkable.add(KIND_NAMESPACES[kind])
        if kind == "locations":
            checkable.add("placement")
        for rel in paths:
            if not isinstance(rel, str):
                continue
            data = _read_json(pack_dir / rel, rel, errors)
            if data is None:
                continue
            _collect(schema.validate(data, target, schemas), rel, errors, warnings, refs)
            loaded.append((kind, rel, data))
            if kind == "vocab" and isinstance(data, dict):
                _declare_vocab(data, rel, ids, vocab, errors)
            elif kind in KIND_NAMESPACES and isinstance(data, dict):
                for i, entry in enumerate(data.get("entries", [])):
                    if not (isinstance(entry, dict) and isinstance(entry.get("id"), str)):
                        continue
                    label = f"{rel}: entries[{i}]"
                    _declare(ids, KIND_NAMESPACES[kind], entry["id"], label, errors)
                    entries.setdefault(kind, {}).setdefault(entry["id"], entry)
                    where.setdefault((kind, entry["id"]), label)
                    if kind == "locations":
                        for j, p in enumerate(_placements(entry)):
                            if isinstance(p.get("id"), str):
                                _declare(ids, "placement", p["id"], f"{label}.placements[{j}]", errors)
    if "vocab" in files:
        checkable.update(VOCAB_NAMESPACES.values())

    _check_refs(refs, ids, checkable, errors, warnings)
    _check_vocab_rules(manifest, vocab, errors, warnings)
    _check_world_rules(manifest, entries, where, errors)
    _check_item_rules(entries, vocab, where, errors)
    _check_skill_rules(manifest, entries, where, errors)
    _check_character_rules(manifest, entries, vocab, where, errors)
    _check_loot_rules(entries, where, errors)
    _check_event_roles(loaded, errors)
    _check_strings(loaded, schemas, ids, "strings" in files, errors, warnings)
    return PackIndex(Report(tuple(errors), tuple(warnings)), ids, tuple(refs))


# --- Loading and bookkeeping ------------------------------------------------------

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


def _a(word: Any) -> str:
    """'a module', 'an implant'."""
    word = str(word)
    return f"{'an' if word[:1] in 'aeiou' else 'a'} {word}"


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


def _placements(location: dict) -> List[dict]:
    return [p for p in location.get("placements", []) or [] if isinstance(p, dict)]


# --- Checks -----------------------------------------------------------------------

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


def _check_vocab_rules(manifest: dict, vocab: Dict[str, Any], errors: List[str], warnings: List[str]) -> None:
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


def _check_world_rules(manifest: dict, entries: Entries, where: Dict[Tuple[str, str], str],
                       errors: List[str]) -> None:
    locations = entries.get("locations", {})
    objects = entries.get("objects", {})
    regions = entries.get("regions", {})
    placement_home = {p["id"]: loc_id for loc_id, loc in locations.items()
                      for p in _placements(loc) if isinstance(p.get("id"), str)}

    # Regions: nesting must not loop.
    for region_id in regions:
        seen, current = set(), region_id
        while current in regions and current not in seen:
            seen.add(current)
            current = regions[current].get("parent")
        if current in seen:
            errors.append(f"{where[('regions', region_id)]}: region '{region_id}' is its own ancestor")

    # Storage contents must fit the object's storage and holds_size.
    items = entries.get("items", {})

    def check_contents(holder: dict, contents: list, label: str) -> None:
        if not contents:
            return
        if not holder.get("storage"):
            errors.append(f"{label}: has contents but no storage")
            return
        stacks = 0
        for entry in contents:
            item = items.get(entry.get("item")) if isinstance(entry, dict) else None
            if item is None:
                continue
            stacks += -(-entry.get("count", 1) // item.get("stack", 1)) if "condition" not in item else entry.get("count", 1)
            if holder.get("holds_size") is not None and item.get("size", 0) > holder["holds_size"]:
                errors.append(f"{label}: '{entry['item']}' is too big for it (holds_size {holder['holds_size']})")
        if stacks > holder["storage"]:
            errors.append(f"{label}: contents need {stacks} storage stacks, it holds {holder['storage']}")

    for obj_id, obj in objects.items():
        check_contents(obj, obj.get("contents", []), where[("objects", obj_id)])
    for loc_id, loc in locations.items():
        for j, p in enumerate(_placements(loc)):
            template = objects.get(p.get("object"))
            if template is not None and "contents" in p:
                check_contents(template, p["contents"], f"{where[('locations', loc_id)]}.placements[{j}]")

    # Objects: the initial state and state glyphs must use the object's states.
    for obj_id, obj in objects.items():
        states = obj.get("states", [])
        label = where[("objects", obj_id)]
        if "state" in obj and obj["state"] not in states:
            errors.append(f"{label}: state '{obj['state']}' is not one of its states")
        for state in obj.get("state_glyphs", {}) or {}:
            if state not in states:
                errors.append(f"{label}: state_glyphs names '{state}', which is not one of its states")

    for loc_id, loc in locations.items():
        label = where[("locations", loc_id)]
        grid = loc.get("grid", {}) if isinstance(loc.get("grid"), dict) else {}
        tiles = _tiles(grid, label, errors)
        if loc.get("entry") and placement_home.get(loc["entry"], loc_id) != loc_id:
            errors.append(f"{label}: entry '{loc['entry']}' is placed in another location")
        taken: Dict[Tuple[int, int], str] = {}
        for j, p in enumerate(_placements(loc)):
            p_label = f"{label}.placements[{j}]"
            at = p.get("at")
            if isinstance(at, list) and len(at) == 2 and all(isinstance(n, int) for n in at):
                pos = (at[0], at[1])
                if tiles is not None and tiles.get(pos, " ") == " ":
                    errors.append(f"{p_label}: position {list(pos)} is outside the grid")
                if pos in taken:
                    errors.append(f"{p_label}: position {list(pos)} is already taken by '{taken[pos]}'")
                taken.setdefault(pos, p.get("id", "?"))
            template = objects.get(p.get("object"))
            if template and "state" in p and p["state"] not in template.get("states", []):
                errors.append(f"{p_label}: state '{p['state']}' is not one of the object's states")
            exit_ = p.get("exit") if isinstance(p.get("exit"), dict) else {}
            dest = exit_.get("location")
            if dest in locations and locations[dest].get("template"):
                errors.append(f"{p_label}: exit leads to '{dest}', which is a template")
            if dest and exit_.get("entry") and placement_home.get(exit_["entry"], dest) != dest:
                errors.append(f"{p_label}: exit arrives at '{exit_['entry']}', which is not in '{dest}'")

    for zone_id, zone in entries.get("zones", {}).items():
        for k, room in enumerate(zone.get("room_pool", []) or []):
            loc = locations.get(room.get("location")) if isinstance(room, dict) else None
            if loc is not None and not loc.get("template"):
                errors.append(f"{where[('zones', zone_id)]}.room_pool[{k}]: '{room['location']}' is not a template")

    start = manifest.get("start", {}) if isinstance(manifest.get("start"), dict) else {}
    start_loc = start.get("location")
    if start_loc in locations and locations[start_loc].get("template"):
        errors.append(f"pack.json: start.location '{start_loc}' is a template")
    if start_loc and start.get("entry") and placement_home.get(start["entry"], start_loc) != start_loc:
        errors.append(f"pack.json: start.entry '{start['entry']}' is not in '{start_loc}'")


def _check_item_rules(entries: Entries, vocab: Dict[str, Any], where: Dict[Tuple[str, str], str],
                      errors: List[str]) -> None:
    hosts = {s["id"]: s.get("host") for s in vocab.get("slot_types", [])}
    for item_id, item in entries.get("items", {}).items():
        label = where[("items", item_id)]
        wanted = "body" if item.get("kind") == "implant" else "frame"
        slot_types = [item.get("slot_type")] + [s.get("slot_type") for s in item.get("slots", []) or []
                                                 if isinstance(s, dict)]
        for slot_type in slot_types:
            if slot_type in hosts and hosts[slot_type] != wanted:
                errors.append(f"{label}: slot type '{slot_type}' is a {hosts[slot_type]} slot; "
                              f"{_a(item.get('kind'))} needs a {wanted} slot")
        if item.get("stack", 1) > 1 and "condition" in item:
            errors.append(f"{label}: items that stack can't have a condition (worn items don't stack)")
        if "repair" in item and "condition" not in item:
            errors.append(f"{label}: has repair costs but no condition, so it never wears")
        yields = (item.get("salvage", {}) or {}).get("yields", []) if isinstance(item.get("salvage"), dict) else []
        if any(isinstance(y, dict) and y.get("item") == item_id for y in yields):
            errors.append(f"{label}: dismantling it can't give back the item itself")

    items = entries.get("items", {})
    for mod_id, mod in entries.get("modifications", {}).items():
        material = items.get(mod.get("material"))
        if material is not None and material.get("kind") != "material":
            errors.append(f"{where[('modifications', mod_id)]}: '{mod['material']}' is {_a(material.get('kind'))}, "
                          f"not a material")


def _check_skill_rules(manifest: dict, entries: Entries, where: Dict[Tuple[str, str], str],
                       errors: List[str]) -> None:
    settings = manifest.get("settings", {}) if isinstance(manifest.get("settings"), dict) else {}
    max_level = settings.get("skill_max_level", 5)
    for skill_id, skill in entries.get("skills", {}).items():
        label = where[("skills", skill_id)]
        levels = [lv for lv in skill.get("levels", []) or [] if isinstance(lv, dict)]
        numbers = [lv.get("level") for lv in levels]
        xps = [lv.get("xp") for lv in levels]
        if numbers != sorted(set(numbers), key=lambda n: (n is None, n)):
            errors.append(f"{label}: levels must be listed once each, lowest first")
        elif any(isinstance(a, int) and isinstance(b, int) and a >= b for a, b in zip(xps, xps[1:])):
            errors.append(f"{label}: each level must need more xp than the one before")
        for i, lv in enumerate(levels):
            if isinstance(lv.get("level"), int) and isinstance(max_level, int) and lv["level"] > max_level:
                errors.append(f"{label}.levels[{i}]: level {lv['level']} is above skill_max_level ({max_level})")
            if lv.get("level") == 1 and lv.get("xp", 0) != 0:
                errors.append(f"{label}.levels[{i}]: level 1 needs 0 xp")


def _check_character_rules(manifest: dict, entries: Entries, vocab: Dict[str, Any],
                           where: Dict[Tuple[str, str], str], errors: List[str]) -> None:
    items = entries.get("items", {})
    locations = entries.get("locations", {})
    characters = entries.get("characters", {})
    role_stat = {s.get("role"): s["id"] for s in vocab.get("stats", []) if s.get("role")}
    hosts = {s["id"]: s.get("host") for s in vocab.get("slot_types", [])}
    settings = manifest.get("settings", {}) if isinstance(manifest.get("settings"), dict) else {}
    max_level = settings.get("skill_max_level", 5)
    occupied: Dict[Tuple[str, int, int], str] = {}
    for loc_id, loc in locations.items():
        for p in _placements(loc):
            at = p.get("at")
            if isinstance(at, list) and len(at) == 2:
                occupied[(loc_id, at[0], at[1])] = f"placement '{p.get('id')}'"

    for char_id, char in characters.items():
        label = where[("characters", char_id)]
        if char.get("template") and ("location" in char or "at" in char):
            errors.append(f"{label}: templates are spawned by encounters and zones, so they have no location")
        if "at" in char:
            _check_standing(char, char_id, label, locations, occupied, errors)
        _check_leader_chain(char_id, characters, label, errors)

        body = char.get("body", {}) if isinstance(char.get("body"), dict) else {}
        body_slots: Dict[str, int] = {}
        for slot in body.get("slots", []) or []:
            if isinstance(slot, dict) and slot.get("slot_type"):
                if hosts.get(slot["slot_type"], "body") != "body":
                    errors.append(f"{label}: body slot '{slot['slot_type']}' is not a body slot type")
                body_slots[slot["slot_type"]] = body_slots.get(slot["slot_type"], 0) + slot.get("count", 1)

        worn: List[dict] = [body]
        frame = items.get(char.get("frame"))
        if frame is not None and frame.get("kind") != "frame":
            errors.append(f"{label}: '{char['frame']}' is worn as a frame but is {_a(frame.get('kind'))}")
            frame = None
        if frame is not None:
            worn.append(frame)
        frame_slots: Dict[str, int] = {}
        for slot in (frame or {}).get("slots", []) or []:
            if isinstance(slot, dict) and slot.get("slot_type"):
                frame_slots[slot["slot_type"]] = frame_slots.get(slot["slot_type"], 0) + slot.get("count", 1)
        if char.get("fitted") and "frame" not in char:
            errors.append(f"{label}: has fitted modules but wears no frame")

        used_slots: Dict[str, int] = {}
        used = {"power": 0.0, "mass": 0.0, "heat": 0.0}
        for group, kind, capacity in (("fitted", "module", frame_slots), ("implants", "implant", body_slots)):
            for item_id in char.get(group, []) or []:
                item = items.get(item_id)
                if item is None:
                    continue  # unknown ids are reported as bad references
                if item.get("kind") != kind:
                    errors.append(f"{label}: {group} lists '{item_id}', which is {_a(item.get('kind'))}, not {_a(kind)}")
                    continue
                worn.append(item)
                slot_type = item.get("slot_type")
                used_slots[slot_type] = used_slots.get(slot_type, 0) + 1
                if used_slots[slot_type] > capacity.get(slot_type, 0):
                    host = "frame" if kind == "module" else "body"
                    errors.append(f"{label}: no free '{slot_type}' slot in the {host} for '{item_id}'")
                for budget, amount in (item.get("uses", {}) or {}).items():
                    used[budget] = used.get(budget, 0.0) + amount

        # skill levels add stats too, as the engine counts them (stats.stat)
        for skill_id, level in (char.get("skills", {}) or {}).items():
            skill = entries.get("skills", {}).get(skill_id)
            for lv in (skill or {}).get("levels", []) or []:
                if isinstance(lv, dict) and isinstance(level, int) and lv.get("level", 0) <= level:
                    worn.append(lv)
        provided = {role: sum(w.get("stats", {}).get(role_stat[role], 0) for w in worn if isinstance(w.get("stats"), dict))
                    for role in ("power", "mass", "heat", "cargo") if role in role_stat}
        for budget in ("power", "mass"):
            if budget in provided and used[budget] > provided[budget]:
                errors.append(f"{label}: fitted gear needs {used[budget]:g} {budget}, the loadout provides {provided[budget]:g}")
        if "heat" in provided and used["heat"] and used["heat"] >= provided["heat"]:
            errors.append(f"{label}: constant heat {used['heat']:g} leaves no room below maximum heat {provided['heat']:g}")
        if "cargo" in provided:
            stacks = 0
            for entry in char.get("inventory", []) or []:
                item = items.get(entry.get("item")) if isinstance(entry, dict) else None
                if item is not None:
                    stacks += -(-entry.get("count", 1) // item.get("stack", 1))
            if stacks > provided["cargo"]:
                errors.append(f"{label}: inventory needs {stacks} cargo stacks, the loadout carries {provided['cargo']:g}")

        for skill_id, level in (char.get("skills", {}) or {}).items():
            if isinstance(level, int) and isinstance(max_level, int) and level > max_level:
                errors.append(f"{label}: skill '{skill_id}' at level {level} is above skill_max_level ({max_level})")

    start = manifest.get("start", {}) if isinstance(manifest.get("start"), dict) else {}
    player = characters.get(start.get("player"))
    if player is not None:
        if player.get("template"):
            errors.append(f"pack.json: start.player '{start['player']}' is a template")
        elif player.get("location") not in (None, start.get("location")):
            errors.append(f"pack.json: start.player '{start['player']}' is placed in '{player['location']}', "
                          f"not the start location '{start.get('location')}'")

    for enc_id, enc in entries.get("encounters", {}).items():
        for side in ("enemies", "allies"):
            for i, entry in enumerate(enc.get(side, []) or []):
                char = characters.get(entry.get("character")) if isinstance(entry, dict) else None
                if char is not None and not char.get("template") and "count" in entry:
                    errors.append(f"{where[('encounters', enc_id)]}.{side}[{i}]: '{entry['character']}' is unique; "
                                  f"only templates take a count")


def _check_standing(char: dict, char_id: str, label: str, locations: Dict[str, dict],
                    occupied: Dict[Tuple[str, int, int], str], errors: List[str]) -> None:
    loc = locations.get(char.get("location"))
    at = char.get("at")
    if "location" not in char:
        errors.append(f"{label}: 'at' needs a location")
        return
    if loc is None or not (isinstance(at, list) and len(at) == 2):
        return
    grid = loc.get("grid", {}) if isinstance(loc.get("grid"), dict) else {}
    tiles = _tiles(grid, label, [])
    key = (char["location"], at[0], at[1])
    if tiles is not None and tiles.get((at[0], at[1])) != ".":
        errors.append(f"{label}: position {at} is not a floor tile of '{char['location']}'")
    elif key in occupied:
        errors.append(f"{label}: position {at} is already taken by {occupied[key]}")
    occupied.setdefault(key, f"character '{char_id}'")


def _check_leader_chain(char_id: str, characters: Dict[str, dict], label: str, errors: List[str]) -> None:
    seen, current = set(), char_id
    while current in characters and current not in seen:
        seen.add(current)
        current = characters[current].get("leader")
    if current in seen:
        errors.append(f"{label}: '{char_id}' ends up leading itself through 'leader'")


def _check_loot_rules(entries: Entries, where: Dict[Tuple[str, str], str], errors: List[str]) -> None:
    tables = entries.get("loot_tables", {})

    def nested(table_id: str) -> List[str]:
        return [e["table"] for e in tables.get(table_id, {}).get("entries", []) or []
                if isinstance(e, dict) and isinstance(e.get("table"), str)]

    for table_id in tables:
        stack, seen = list(nested(table_id)), set()
        while stack:
            current = stack.pop()
            if current == table_id:
                errors.append(f"{where[('loot_tables', table_id)]}: loot table '{table_id}' rolls itself")
                break
            if current not in seen:
                seen.add(current)
                stack.extend(nested(current))


STRING_REF = re.compile(r"^@[a-z][a-z0-9_]*$")  # text that is a strings-file id


def _role_uses(node: Any, path: str) -> List[Tuple[str, str]]:
    """(path, role) for every {"role": name} reference inside a value."""
    found: List[Tuple[str, str]] = []
    if isinstance(node, dict):
        if set(node) == {"role"} and isinstance(node["role"], str):
            return [(path, node["role"])]
        for key, value in node.items():
            found += _role_uses(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found += _role_uses(value, f"{path}[{i}]")
    return found


def _check_event_roles(loaded: List[Tuple[str, str, Any]], errors: List[str]) -> None:
    for kind, rel, data in loaded:
        if kind != "events":
            for path, role in _role_uses(data, ""):
                errors.append(f"{rel}: {path}: role '{role}' used outside an event")
            continue
        for i, entry in enumerate(data.get("entries", []) if isinstance(data, dict) else []):
            if not isinstance(entry, dict):
                continue
            label = f"{rel}: entries[{i}]"
            filled: List[str] = []
            for j, member in enumerate(entry.get("cast", []) or []):
                if not isinstance(member, dict):
                    continue
                for path, role in _role_uses(member.get("when"), f"cast[{j}].when"):
                    if role not in filled:
                        errors.append(f"{label}.{path}: role '{role}' is not filled yet at this point of the cast")
                name = member.get("role")
                if name in filled:
                    errors.append(f"{label}.cast[{j}]: role '{name}' is cast twice")
                filled.append(name)
            rest = {k: v for k, v in entry.items() if k != "cast"}
            for path, role in _role_uses(rest, ""):
                if role not in filled:
                    errors.append(f"{label}.{path}: role '{role}' is not in the event's cast")


def _check_strings(loaded: List[Tuple[str, str, Any]], schemas: schema.Schemas, ids: Dict[str, Dict[Any, str]],
                   has_strings: bool, errors: List[str], warnings: List[str]) -> None:
    engine_defs = schemas.get("strings.schema.json", {}).get("$defs", {}).get("engine", {}).get("properties", {})
    covered: Set[str] = set()
    for kind, rel, data in loaded:
        if kind != "strings" or not isinstance(data, dict):
            continue
        for key, template in (data.get("engine", {}) or {}).items():
            if key not in engine_defs or not isinstance(template, str):
                continue  # reported by the schema
            covered.add(key)
            allowed = engine_defs[key].get("x-placeholders", [])
            try:
                fields = [f for _, f, _, _ in string.Formatter().parse(template) if f is not None]
            except ValueError as e:
                errors.append(f"{rel}: engine.{key}: broken braces ({e})")
                continue
            for field in fields:
                if field not in allowed:
                    known = ", ".join("{" + a + "}" for a in allowed) or "none"
                    errors.append(f"{rel}: engine.{key}: unknown placeholder {{{field}}} (allowed: {known})")
    if has_strings and engine_defs:
        missing = sorted(set(engine_defs) - covered)
        if missing:
            warnings.append(f"strings: {len(missing)} engine message(s) not written yet, shown as their keys: "
                            f"{', '.join(missing)}")

    def texts(node: Any, path: str) -> List[Tuple[str, str]]:
        if isinstance(node, str):
            return [(path, node)] if STRING_REF.match(node) else []
        if isinstance(node, dict):
            return [t for k, v in node.items() for t in texts(v, f"{path}.{k}" if path else k)]
        if isinstance(node, list):
            return [t for i, v in enumerate(node) for t in texts(v, f"{path}[{i}]")]
        return []

    for kind, rel, data in loaded:
        for path, text in texts(data, ""):
            if text[1:] not in ids.get("string", {}):
                where = "" if has_strings else " (the pack loads no strings)"
                errors.append(f"{rel}: {path}: unknown string '{text}'{where}")


def _tiles(grid: dict, label: str, errors: List[str]) -> Optional[Dict[Tuple[int, int], str]]:
    """Tile map ('#' wall, '.' floor) for a grid, or None if the grid itself is unusable."""
    width, height = grid.get("width"), grid.get("height")
    if not (isinstance(width, int) and isinstance(height, int)):
        return None
    rows = grid.get("rows")
    if rows is None:
        return {(r, c): "#" if r in (0, height - 1) or c in (0, width - 1) else "."
                for r in range(height) for c in range(width)}
    if len(rows) != height or any(len(row) != width for row in rows if isinstance(row, str)):
        errors.append(f"{label}.grid: rows must be {height} strings of {width} characters")
        return None
    return {(r, c): ch for r, row in enumerate(rows) for c, ch in enumerate(row)}


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
