"""
Where an id is used, found in the pack as it is in memory (saved or not), the way the
checker finds references: by the schemas' x-ref marks, plus '@id' texts for strings.
Renaming an id changes every use with it.
"""
import re
from typing import Any, List, Tuple

from core import schema
from core.pack import KIND_SCHEMAS
from tools.lib.fields import schemas
from tools.lib.packfiles import PackFiles

PACK_SCHEMA = "pack.schema.json"
DECLARED = re.compile(r"^sizes\[\d+\]\.size$")
STEP = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def _files(pack: PackFiles):
    """(file, data, schema target) for the manifest and every pack file."""
    yield "pack.json", pack.manifest, PACK_SCHEMA
    for kind, files in pack.kinds.items():
        if kind in KIND_SCHEMAS:
            for rel in files:
                yield rel, pack.data[rel], KIND_SCHEMAS[kind]


def uses(pack: PackFiles, namespace: str, ident: Any) -> List[Tuple[str, str]]:
    """(file, path) of every reference to the id, its own declaration not included."""
    found = []
    for rel, data, target in _files(pack):
        for ref in schema.validate(data, target, schemas()).refs:
            if target == KIND_SCHEMAS.get("vocab") and DECLARED.match(ref.path):
                continue                                    # a size class's own number
            if ref.kind == namespace and ref.value == ident:
                found.append((rel, ref.path))
        if namespace == "string":
            found += [(rel, path) for path in _texts(data, "", f"@{ident}")]
    return found


def _texts(node: Any, path: str, text: str) -> List[str]:
    if node == text:
        return [path]
    if isinstance(node, dict):
        return [p for k, v in node.items() for p in _texts(v, f"{path}.{k}" if path else k, text)]
    if isinstance(node, list):
        return [p for i, v in enumerate(node) for p in _texts(v, f"{path}[{i}]", text)]
    return []


def _steps(path: str) -> List[Any]:
    return [int(index) if index else key for key, index in STEP.findall(path)]


def rename(pack: PackFiles, namespace: str, old: str, new: str) -> int:
    """Changes every use of an id to the new one (the declaration is up to the caller); returns how many."""
    places = uses(pack, namespace, old)
    data_of = {rel: data for rel, data, _ in _files(pack)}
    for rel, path in places:
        *parents, last = _steps(path)
        node = data_of[rel]
        for step in parents:
            node = node[step]
        if isinstance(node, dict) and last == old and node.get(old) != old:     # a key, e.g. a skill level
            items = list(node.items())
            node.clear()
            node.update({(new if k == old else k): v for k, v in items})
        elif node[last] == f"@{old}":
            node[last] = f"@{new}"
        else:
            node[last] = new
        pack.touch(rel)
    return len(places)
