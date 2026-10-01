"""
A content pack loaded for the engine.

load_pack() validates a pack, refuses it if it has errors, fills in every default the
schemas declare, and returns read-only Content. Everything the engine knows about the
world comes from here.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, NamedTuple, Tuple

from core import schema
from core.pack import KIND_NAMESPACES, KIND_SCHEMAS, SCHEMA_DIR, Report, index_pack
from engine.frozen import Record, freeze

# Vocabulary sections with ids, and the namespace each declares.
VOCAB_SECTIONS = {
    "tags": "tag", "stats": "stat", "damage_types": "damage_type", "statuses": "status",
    "slot_types": "slot_type", "grades": "grade", "object_states": "object_state",
    "phases": "phase", "factions": "faction", "flags": "flag",
}

# Fields a placement takes from its object template.
TEMPLATE_FIELDS = ("name", "glyph", "description", "size", "holds_size", "solid", "states",
                   "state_glyphs", "storage", "workshop")


class PackError(Exception):
    """The pack failed validation. The report holds every error and warning."""

    def __init__(self, pack_dir: Path, report: Report):
        self.report = report
        lines = "\n".join(f"  {e}" for e in report.errors)
        super().__init__(f"The pack in {pack_dir} has {len(report.errors)} error(s):\n{lines}")


class Content(NamedTuple):
    """
    A loaded pack. Every record is read-only and has its defaults filled in.

    index maps a namespace ('item', 'location', 'tag', 'placement'…) to its records by
    id. Placement records are already merged with their object template and carry the
    id of the location they are in.
    """
    pack: Record                               # pack.json, with settings filled in
    index: Mapping[str, Mapping[str, Record]]  # namespace -> id -> record
    sizes: Mapping[int, Record]                # size class -> its vocabulary entry
    ranks: Tuple[Record, ...]                  # lowest first
    relation_levels: Tuple[Record, ...]        # lowest min first
    stat_roles: Mapping[str, str]              # role -> stat id
    messages: Mapping[str, str]                # engine message key -> the pack's wording
    warnings: Tuple[str, ...]

    @property
    def settings(self) -> Record:
        return self.pack["settings"]

    def get(self, namespace: str, record_id: str) -> Record:
        """The record with this id. Raises KeyError naming what is missing."""
        try:
            return self.index[namespace][record_id]
        except KeyError:
            raise KeyError(f"unknown {namespace.replace('_', ' ')} '{record_id}'") from None

    def all(self, namespace: str) -> Mapping[str, Record]:
        """Every record in a namespace, by id (empty if the pack has none)."""
        return self.index.get(namespace, {})

    def role_stat(self, role: str) -> str:
        """The id of the stat that carries a role: health, power, mass, heat, initiative, cargo."""
        return self.stat_roles[role]

    def text(self, value: str) -> str:
        """Player-facing text: '@id' becomes that strings entry, anything else is returned as is."""
        if value.startswith("@") and value[1:] in self.index.get("string", {}):
            return self.index["string"][value[1:]]["text"]
        return value

    def message(self, key: str, **fields: Any) -> str:
        """An engine message in the pack's words. A message the pack lacks is shown as its key."""
        template = self.messages.get(key)
        if template is None:
            return key
        return template.format(**{k: v for k, v in fields.items()})


def load_pack(pack_dir: Path, schema_dir: Path = SCHEMA_DIR) -> Content:
    """Validates and loads a pack. Raises PackError if the validator finds any error."""
    report = index_pack(pack_dir, schema_dir).report
    if report.errors:
        raise PackError(pack_dir, report)
    schemas = schema.load_schemas(schema_dir)

    manifest = schema.apply_defaults(_read(pack_dir / "pack.json"), "pack.schema.json", schemas)
    manifest.setdefault("settings", schema.apply_defaults({}, "pack.schema.json#/properties/settings", schemas))

    index: Dict[str, Dict[str, Any]] = {}
    vocab: Dict[str, List[dict]] = {}
    messages: Dict[str, str] = {}
    for kind, paths in manifest["files"].items():
        for rel in paths:
            data = schema.apply_defaults(_read(pack_dir / rel), KIND_SCHEMAS[kind], schemas)
            if kind == "vocab":
                for section, entries in data.items():
                    if isinstance(entries, list):
                        vocab.setdefault(section, []).extend(entries)
            elif kind == "strings":
                messages.update(data.get("engine", {}))
                for entry in data.get("entries", []):
                    index.setdefault("string", {})[entry["id"]] = entry
            else:
                for entry in data.get("entries", []):
                    index.setdefault(KIND_NAMESPACES[kind], {})[entry["id"]] = entry

    for section, namespace in VOCAB_SECTIONS.items():
        index[namespace] = {e["id"]: e for e in vocab.get(section, [])}
    index["placement"] = _placements(index.get("location", {}), index.get("object", {}))

    stat_roles = {s["role"]: s["id"] for s in vocab.get("stats", []) if s.get("role")}
    return Content(
        pack=freeze(manifest),
        index=freeze(index),
        sizes=freeze({e["size"]: e for e in vocab.get("sizes", [])}),
        ranks=freeze(sorted(vocab.get("ranks", []), key=lambda e: e["rank"])),
        relation_levels=freeze(sorted(vocab.get("relation_levels", []), key=lambda e: e["min"])),
        stat_roles=freeze(stat_roles),
        messages=freeze(messages),
        warnings=report.warnings,
    )


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _placements(locations: Dict[str, dict], objects: Dict[str, dict]) -> Dict[str, dict]:
    """Every placement merged with its object template, keyed by placement id."""
    placed: Dict[str, dict] = {}
    for loc_id, loc in locations.items():
        for p in loc.get("placements", []):
            template = objects[p["object"]]
            merged = {field: template[field] for field in TEMPLATE_FIELDS if field in template}
            merged.update({k: p[k] for k in ("name", "glyph", "description") if k in p})
            tags = list(template.get("tags", []))
            tags += [t for t in p.get("tags", []) if t not in tags]
            interactions = {i["id"]: i for i in template.get("interactions", [])}
            for interaction in p.get("interactions", []):
                interactions[interaction["id"]] = interaction  # same id replaces, new id adds
            states = template.get("states", [])
            merged.update({
                "id": p["id"],
                "object": p["object"],
                "location": loc_id,
                "at": p["at"],
                "tags": tags,
                "interactions": list(interactions.values()),
                "state": p.get("state", template.get("state", states[0] if states else None)),
                "exit": p.get("exit"),
                "dock_port": p.get("dock_port", False),
            })
            placed[p["id"]] = merged
    return placed
