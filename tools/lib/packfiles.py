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
        self.manifest: dict = _read(self.dir / "pack.json")
        self.data: Dict[str, dict] = {}          # file (relative to the pack) -> its JSON
        self.kinds: Dict[str, List[str]] = {}    # kind -> its files, in manifest order
        self.dirty: set = set()
        for kind, files in self.manifest.get("files", {}).items():
            self.kinds[kind] = list(files)
            for rel in files:
                self.data[rel] = _read(self.dir / rel)

    @property
    def id(self) -> str:
        return self.manifest.get("id", self.dir.name)

    def entries(self, kind: str) -> Iterator[Found]:
        """Every entry of a kind ('locations', 'characters'…), with its file."""
        for rel in self.kinds.get(kind, []):
            for entry in self.data[rel].get("entries", []):
                yield Found(rel, entry)

    def find(self, kind: str, entry_id: str) -> Optional[Found]:
        return next((f for f in self.entries(kind) if f.entry.get("id") == entry_id), None)

    def placement(self, placement_id: str) -> Optional[Tuple[Found, dict]]:
        """A placement and the location it's in."""
        for found in self.entries("locations"):
            for p in found.entry.get("placements", []):
                if p.get("id") == placement_id:
                    return found, p
        return None

    def add(self, kind: str, entry: dict, file: Optional[str] = None) -> str:
        """Adds an entry to a file of its kind (the first, unless 'file' says which); returns the file."""
        rel = file or self.kinds[kind][0]
        self.data[rel].setdefault("entries", []).append(entry)
        self.dirty.add(rel)
        return rel

    def touch(self, file: str) -> None:
        """Marks a file as changed after editing one of its entries in place."""
        self.dirty.add(file)

    def save(self) -> List[str]:
        """Writes the changed files (each atomically); returns which."""
        written = sorted(self.dirty)
        for rel in written:
            _write(self.dir / rel, self.data[rel])
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


def _write(path: Path, data) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(dumps(data), encoding="utf-8")
    os.replace(tmp, path)
