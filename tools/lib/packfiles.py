"""
A game pack's JSON files, opened for editing. Entries are edited in place as plain
dicts (as written, no defaults filled in) and written back in the packs' own format:
2-space indentation, UTF-8, a newline at the end. Only changed files are written.
"""
import json
import os
from pathlib import Path
from typing import Dict, Iterator, List, NamedTuple, Optional, Tuple

from core.pack import Report, validate_pack

MANIFEST = "pack.json"
VOCAB = "vocab."                    # 'vocab.tags': a vocabulary section, edited like a kind of entry
KEYS = {"sizes": "size", "ranks": "rank", "relation_levels": "min"}     # sections keyed by a number, not an id


def key_field(kind: str) -> str:
    """The field that names an entry of a kind: 'id', or a vocabulary section's number."""
    return KEYS.get(kind[len(VOCAB):], "id") if kind.startswith(VOCAB) else "id"


class Found(NamedTuple):
    """An entry and the file it lives in."""
    file: str
    entry: dict


class PackFiles:
    """The pack's manifest and every file it lists, by kind."""

    def __init__(self, pack_dir: Path):
        self.dir = Path(pack_dir)
        self.reload()

    def reload(self) -> None:
        """Reads every file again, dropping unsaved changes."""
        self.data: Dict[str, dict] = {}          # file (relative to the pack) -> its JSON
        self.kinds: Dict[str, List[str]] = {}    # kind -> its files, in manifest order
        self.dirty: set = set()
        self.as_read: Dict[str, str] = {}        # file -> its text when read or last saved
        self.as_read[MANIFEST] = (self.dir / MANIFEST).read_text(encoding="utf-8")
        self.manifest: dict = json.loads(self.as_read[MANIFEST])
        for kind, files in self.manifest.get("files", {}).items():
            self.kinds[kind] = list(files)
            for rel in files:
                self.as_read[rel] = (self.dir / rel).read_text(encoding="utf-8")
                self.data[rel] = json.loads(self.as_read[rel])

    @property
    def id(self) -> str:
        return self.manifest.get("id", self.dir.name)

    def entries(self, kind: str) -> Iterator[Found]:
        """Every entry of a kind ('locations', 'characters'…, or a vocabulary section 'vocab.tags'), with its file."""
        if kind.startswith(VOCAB):
            for rel in self.kinds.get("vocab", []):
                for entry in self.data[rel].get(kind[len(VOCAB):], []):
                    yield Found(rel, entry)
            return
        for rel in self.kinds.get(kind, []):
            for entry in self.data[rel].get("entries", []):
                yield Found(rel, entry)

    def find(self, kind: str, entry_id) -> Optional[Found]:
        key = key_field(kind)
        return next((f for f in self.entries(kind) if f.entry.get(key) == entry_id), None)

    def siblings(self, kind: str, found: Found) -> list:
        """The list in its file that holds the entry."""
        return self.data[found.file][kind[len(VOCAB):] if kind.startswith(VOCAB) else "entries"]

    def placement(self, placement_id: str) -> Optional[Tuple[Found, dict]]:
        """A placement and the location it's in."""
        for found in self.entries("locations"):
            for p in found.entry.get("placements", []):
                if p.get("id") == placement_id:
                    return found, p
        return None

    def add(self, kind: str, entry: dict, file: Optional[str] = None) -> str:
        """Adds an entry to a file of its kind (the first, unless 'file' says which); returns the file."""
        section = kind[len(VOCAB):] if kind.startswith(VOCAB) else "entries"
        rel = file or self.kinds["vocab" if kind.startswith(VOCAB) else kind][0]
        self.data[rel].setdefault(section, []).append(entry)
        self.dirty.add(rel)
        return rel

    def remove(self, kind: str, found: Found) -> None:
        listed = self.siblings(kind, found)
        listed.remove(next(e for e in listed if e is found.entry))
        self.dirty.add(found.file)

    def touch(self, file: str) -> None:
        """Marks a file (or 'pack.json', the manifest) as changed after editing it in place."""
        self.dirty.add(file)

    def changed_elsewhere(self) -> List[str]:
        """Changed files that something else (another editor, a person) also changed on disk since they were read."""
        clash = []
        for rel in sorted(self.dirty):
            path = self.dir / rel
            now = path.read_text(encoding="utf-8") if path.exists() else None
            if now != self.as_read.get(rel):
                clash.append(rel)
        return clash

    def save(self) -> List[str]:
        """Writes the changed files (each atomically); returns which. Ask about changed_elsewhere() first."""
        written = sorted(self.dirty)
        for rel in written:
            self.as_read[rel] = _write(self.dir / rel, self.manifest if rel == MANIFEST else self.data[rel])
        self.dirty.clear()
        return written

    def check(self) -> Report:
        """The validator's report on the pack as saved on disk."""
        return validate_pack(self.dir)


def dumps(data) -> str:
    """JSON in the packs' format."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data) -> str:
    text = dumps(data)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return text
