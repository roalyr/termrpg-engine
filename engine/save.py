"""
Saving and loading. A save holds the state only, never content, together with the
pack's id and version it was made with. Loading refuses a save from another pack or
from another major version of the pack (ids may have changed).

Every state type is a NamedTuple; it is written as an object tagged with its type
name and read back into the same type. Mappings become objects, tuples become lists.
Files are written atomically: a crash mid-save leaves the previous save intact.
"""
import json
import os
from pathlib import Path
from typing import Any

from engine import encounter, rng, state as st
from engine.content import Content
from engine.frozen import freeze

TYPES = {cls.__name__: cls for cls in (
    st.GameState, st.CharState, st.ItemInst, st.StatMod, st.StatusInst, st.Message, st.Ctx, st.Pending, rng.Rng,
    st.Debrief,
    encounter.EncounterState)}
FORMAT = 1


class SaveError(Exception):
    pass


def encode(value: Any) -> Any:
    if isinstance(value, tuple) and hasattr(value, "_fields"):
        return {"__type": type(value).__name__, **{f: encode(getattr(value, f)) for f in value._fields}}
    if hasattr(value, "items"):
        return {str(k): encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    return value


def decode(value: Any) -> Any:
    if isinstance(value, dict):
        if "__type" in value:
            cls = TYPES[value["__type"]]
            fields = {k: decode(v) for k, v in value.items() if k != "__type"}
            return cls(**fields)
        return freeze({k: decode(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(decode(v) for v in value)
    return value


def to_json(content: Content, state: st.GameState) -> str:
    return json.dumps({"format": FORMAT, "pack": content.pack["id"], "pack_version": content.pack["version"],
                       "state": encode(state)}, ensure_ascii=False, indent=1)


def from_json(content: Content, text: str) -> st.GameState:
    data = json.loads(text)
    if data.get("format") != FORMAT:
        raise SaveError(f"save format {data.get('format')} is not supported")
    if data.get("pack") != content.pack["id"]:
        raise SaveError(f"the save is for pack '{data.get('pack')}', not '{content.pack['id']}'")
    saved_major = str(data.get("pack_version", "0")).split(".")[0]
    if saved_major != content.pack["version"].split(".")[0]:
        raise SaveError(f"the save is for version {data.get('pack_version')} of the pack, "
                        f"which isn't compatible with {content.pack['version']}")
    state = decode(data["state"])
    return state._replace(characters=freeze(dict(state.characters)))


def save(content: Content, state: st.GameState, path: Path) -> None:
    """Writes the save atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(to_json(content, state), encoding="utf-8")
    os.replace(tmp, path)


def load(content: Content, path: Path) -> st.GameState:
    return from_json(content, path.read_text(encoding="utf-8"))

