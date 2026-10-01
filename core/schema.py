"""
A small JSON Schema (draft 2020-12) checker for the subset the pack schemas use.
Standard library only.

Besides plain validation it collects what the pack validator needs next:
  - references: values under an 'x-ref' keyword (and keys under 'x-ref-keys'),
  - uses of definitions marked 'x-status': 'reserved'.
'x-discriminator' names the key ('check', 'op') that picks one branch of a oneOf,
so a typo reports "unknown op 'dmg'" instead of every branch failing.
"""
import json
import re
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

SUPPORTED_KEYWORDS = frozenset({
    "$schema", "$id", "$defs", "$ref", "title", "description", "default", "$comment",
    "type", "enum", "const", "pattern", "minLength", "maxLength",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "items", "minItems", "maxItems", "uniqueItems",
    "properties", "required", "additionalProperties", "propertyNames",
    "oneOf", "anyOf", "allOf",
    "x-ref", "x-ref-keys", "x-discriminator", "x-status", "x-schema-version", "x-placeholders",
})

Schemas = Dict[str, dict]  # file name -> parsed schema


class Issue(NamedTuple):
    path: str
    message: str


class Ref(NamedTuple):
    kind: str   # namespace named by x-ref, e.g. "item"
    value: Any  # the referenced id (or size number)
    path: str


class Result(NamedTuple):
    errors: Tuple[Issue, ...]
    refs: Tuple[Ref, ...]
    reserved: Tuple[Issue, ...]


class _Acc:
    """Accumulator for one validation pass; oneOf/anyOf branches get their own and merge the winner."""

    def __init__(self) -> None:
        self.errors: List[Issue] = []
        self.refs: List[Ref] = []
        self.reserved: List[Issue] = []

    def merge(self, other: "_Acc") -> None:
        self.errors += other.errors
        self.refs += other.refs
        self.reserved += other.reserved


def load_schemas(schema_dir: Path) -> Schemas:
    """Every *.schema.json in the folder, keyed by file name."""
    return {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(schema_dir.glob("*.schema.json"))}


def validate(instance: Any, target: str, schemas: Schemas) -> Result:
    """Checks an instance against a schema file's root, or a definition in it ('file#/$defs/name')."""
    acc = _Acc()
    hit = _resolve(target, target.partition("#")[0], schemas)
    if hit is None:
        raise KeyError(f"no schema at '{target}'")
    _check(instance, hit[0], hit[1], "", schemas, acc)
    return Result(tuple(acc.errors), tuple(acc.refs), tuple(acc.reserved))


def resolves(target: str, schemas: Schemas) -> bool:
    """Whether 'file' or 'file#/pointer' names a schema node."""
    return _resolve(target, target.partition("#")[0], schemas) is not None


def apply_defaults(instance: Any, target: str, schemas: Schemas) -> Any:
    """
    A copy of a valid instance with every missing field that has a default filled in.
    Defaults come from the field itself or from the definition it refers to, so the
    engine never needs to know them. Run it only on data that passed validate().
    """
    hit = _resolve(target, target.partition("#")[0], schemas)
    if hit is None:
        raise KeyError(f"no schema at '{target}'")
    return _fill(instance, hit[0], hit[1], schemas)


def schema_problems(schemas: Schemas) -> List[str]:
    """Unresolvable $refs and keywords this checker does not implement."""
    problems: List[str] = []

    def walk(node: Any, file: str, where: str, is_schema: bool) -> None:
        if isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, file, f"{where}[{i}]", is_schema)
            return
        if not isinstance(node, dict):
            return
        if not is_schema:  # a map of names to schemas ($defs, properties)
            for k, v in node.items():
                walk(v, file, f"{where}/{k}", True)
            return
        for key, value in node.items():
            if key not in SUPPORTED_KEYWORDS:
                problems.append(f"{file}{where}: unsupported keyword '{key}'")
            if key == "$ref" and _resolve(value, file, schemas) is None:
                problems.append(f"{file}{where}: unresolved $ref '{value}'")
            if key in ("$defs", "properties"):
                walk(value, file, f"{where}/{key}", False)
            elif key in ("items", "additionalProperties", "propertyNames", "oneOf", "anyOf", "allOf"):
                walk(value, file, f"{where}/{key}", True)

    for file, schema in schemas.items():
        walk(schema, file, "", True)
    return problems


# --- Internals ---------------------------------------------------------------

def _resolve(ref: str, file: str, schemas: Schemas) -> Optional[Tuple[dict, str]]:
    target_file, _, fragment = ref.partition("#")
    target_file = target_file or file
    node: Any = schemas.get(target_file)
    for part in [p for p in fragment.split("/") if p]:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return (node, target_file) if isinstance(node, dict) else None


def _join(path: str, key: Any) -> str:
    if isinstance(key, int):
        return f"{path}[{key}]"
    return f"{path}.{key}" if path else str(key)


def _is_type(value: Any, type_name: str) -> bool:
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "integer":
        return (isinstance(value, int) and not isinstance(value, bool)) or (
            isinstance(value, float) and value.is_integer())
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "null":
        return value is None
    return False


def _same(a: Any, b: Any) -> bool:
    """JSON equality: true and 1 are different values."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    return a == b


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _branch_const(branch: dict, file: str, key: str, schemas: Schemas) -> Tuple[Optional[Any], dict, str]:
    """(value of properties[key].const or None, resolved branch, its file)."""
    resolved, bfile = branch, file
    if "$ref" in branch:
        hit = _resolve(branch["$ref"], file, schemas)
        if hit:
            resolved, bfile = hit
    prop = resolved.get("properties", {}).get(key, {})
    return (prop.get("const") if isinstance(prop, dict) else None), resolved, bfile


def _check(inst: Any, node: dict, file: str, path: str, schemas: Schemas, acc: _Acc) -> None:
    errors_before = len(acc.errors)

    if "$ref" in node:
        hit = _resolve(node["$ref"], file, schemas)
        if hit is None:
            acc.errors.append(Issue(path, f"schema error: unresolved $ref '{node['$ref']}'"))
            return
        _check(inst, hit[0], hit[1], path, schemas, acc)

    if "type" in node:
        types = node["type"] if isinstance(node["type"], list) else [node["type"]]
        if not any(_is_type(inst, t) for t in types):
            acc.errors.append(Issue(path, f"expected {' or '.join(types)}, got {_describe(inst)}"))
            return

    if "const" in node and not _same(inst, node["const"]):
        acc.errors.append(Issue(path, f"must be {json.dumps(node['const'])}"))
    if "enum" in node and not any(_same(inst, v) for v in node["enum"]):
        acc.errors.append(Issue(path, f"must be one of: {', '.join(json.dumps(v) for v in node['enum'])}"))

    if isinstance(inst, str):
        if "minLength" in node and len(inst) < node["minLength"]:
            acc.errors.append(Issue(path, "must not be empty" if node["minLength"] == 1
                                    else f"must be at least {node['minLength']} characters"))
        if "maxLength" in node and len(inst) > node["maxLength"]:
            acc.errors.append(Issue(path, f"must be at most {node['maxLength']} characters"))
        if "pattern" in node and not re.search(node["pattern"], inst):
            acc.errors.append(Issue(path, f"'{inst}' does not match the pattern {node['pattern']}"))

    if _is_type(inst, "number"):
        if "minimum" in node and inst < node["minimum"]:
            acc.errors.append(Issue(path, f"must be at least {node['minimum']}"))
        if "maximum" in node and inst > node["maximum"]:
            acc.errors.append(Issue(path, f"must be at most {node['maximum']}"))
        if "exclusiveMinimum" in node and inst <= node["exclusiveMinimum"]:
            acc.errors.append(Issue(path, f"must be above {node['exclusiveMinimum']}"))
        if "exclusiveMaximum" in node and inst >= node["exclusiveMaximum"]:
            acc.errors.append(Issue(path, f"must be below {node['exclusiveMaximum']}"))

    if isinstance(inst, list):
        if "minItems" in node and len(inst) < node["minItems"]:
            acc.errors.append(Issue(path, f"needs at least {node['minItems']} item(s)"))
        if "maxItems" in node and len(inst) > node["maxItems"]:
            acc.errors.append(Issue(path, f"allows at most {node['maxItems']} item(s)"))
        if node.get("uniqueItems"):
            seen: Dict[str, int] = {}
            for i, item in enumerate(inst):
                key = _canonical(item)
                if key in seen:
                    acc.errors.append(Issue(_join(path, i), f"duplicate of item {seen[key]}"))
                seen.setdefault(key, i)
        if "items" in node:
            for i, item in enumerate(inst):
                _check(item, node["items"], file, _join(path, i), schemas, acc)

    if isinstance(inst, dict):
        props = node.get("properties", {})
        for key in node.get("required", []):
            if key not in inst:
                acc.errors.append(Issue(path, f"missing required field '{key}'"))
        extra = node.get("additionalProperties", True)
        for key, value in inst.items():
            sub = _join(path, key)
            if key in props:
                _check(value, props[key], file, sub, schemas, acc)
            elif extra is False:
                acc.errors.append(Issue(path, f"unknown field '{key}'"))
            elif isinstance(extra, dict):
                _check(value, extra, file, sub, schemas, acc)
            if "propertyNames" in node:
                _check(key, node["propertyNames"], file, sub, schemas, acc)
            if "x-ref-keys" in node and isinstance(key, str):
                acc.refs.append(Ref(node["x-ref-keys"], key, sub))

    if "allOf" in node:
        for branch in node["allOf"]:
            _check(inst, branch, file, path, schemas, acc)
    if "anyOf" in node:
        _any_of(inst, node["anyOf"], file, path, schemas, acc)
    if "oneOf" in node:
        _one_of(inst, node, file, path, schemas, acc)

    if len(acc.errors) == errors_before:
        if "x-ref" in node and isinstance(inst, (str, int)) and not isinstance(inst, bool):
            acc.refs.append(Ref(node["x-ref"], inst, path))
        if node.get("x-status") == "reserved":
            acc.reserved.append(Issue(path, "uses a reserved feature the engine does not support yet"))


def _default_of(node: dict, file: str, schemas: Schemas) -> Tuple[bool, Any]:
    """(has a default, the default) for a property, looking through $refs."""
    seen = 0
    while isinstance(node, dict) and seen < 10:
        if "default" in node:
            return True, node["default"]
        if "$ref" not in node:
            break
        hit = _resolve(node["$ref"], file, schemas)
        if hit is None:
            break
        node, file = hit
        seen += 1
    return False, None


def _fill(inst: Any, node: dict, file: str, schemas: Schemas) -> Any:
    if "$ref" in node:
        hit = _resolve(node["$ref"], file, schemas)
        if hit is not None:
            inst = _fill(inst, hit[0], hit[1], schemas)
    for combo in ("oneOf", "anyOf"):
        if combo in node:
            branch = _matching_branch(inst, node, node[combo], file, schemas)
            if branch is not None:
                inst = _fill(inst, branch[0], branch[1], schemas)
    for branch in node.get("allOf", []):
        inst = _fill(inst, branch, file, schemas)

    if isinstance(inst, list) and isinstance(node.get("items"), dict):
        return [_fill(v, node["items"], file, schemas) for v in inst]
    if isinstance(inst, dict) and ("properties" in node or isinstance(node.get("additionalProperties"), dict)):
        props = node.get("properties", {})
        extra = node.get("additionalProperties")
        out = {}
        for key, value in inst.items():
            if key in props:
                out[key] = _fill(value, props[key], file, schemas)
            elif isinstance(extra, dict):
                out[key] = _fill(value, extra, file, schemas)
            else:
                out[key] = value
        for key, prop in props.items():
            if key not in out:
                has, default = _default_of(prop, file, schemas)
                if has:
                    out[key] = json.loads(json.dumps(default))  # a fresh copy
        return out
    return inst


def _matching_branch(inst: Any, node: dict, branches: List[dict], file: str,
                     schemas: Schemas) -> Optional[Tuple[dict, str]]:
    """The oneOf/anyOf branch a valid instance took, resolved."""
    disc = node.get("x-discriminator")
    if disc and isinstance(inst, dict) and disc in inst:
        for b in branches:
            const, resolved, bfile = _branch_const(b, file, disc, schemas)
            if const == inst[disc]:
                return resolved, bfile
        return None
    for b in branches:
        if not _try(inst, b, file, "", schemas).errors:
            hit = _resolve(b["$ref"], file, schemas) if "$ref" in b else (b, file)
            return hit
    return None


def _try(inst: Any, branch: dict, file: str, path: str, schemas: Schemas) -> _Acc:
    trial = _Acc()
    _check(inst, branch, file, path, schemas, trial)
    return trial


def _any_of(inst: Any, branches: List[dict], file: str, path: str, schemas: Schemas, acc: _Acc) -> None:
    trials = [_try(inst, b, file, path, schemas) for b in branches]
    passing = [t for t in trials if not t.errors]
    if passing:
        acc.merge(passing[0])
    elif all(_only_missing(t) for t in trials):
        needs = sorted({e.message.split("'")[1] for t in trials for e in t.errors})
        acc.errors.append(Issue(path, f"needs at least one of: {', '.join(needs)}"))
    else:
        acc.merge(_closest(trials, path))


def _closest(trials: List[_Acc], path: str) -> _Acc:
    """The failed branch most likely meant: one whose type fits the value, then fewest errors."""
    def wrong_shape(t: _Acc) -> bool:
        return any(e.path == path and (e.message.startswith("expected ") or e.message.startswith("must be one of"))
                   for e in t.errors)
    return min(trials, key=lambda t: (wrong_shape(t), len(t.errors)))


def _only_missing(trial: _Acc) -> bool:
    return all(e.message.startswith("missing required field") for e in trial.errors)


def _one_of(inst: Any, node: dict, file: str, path: str, schemas: Schemas, acc: _Acc) -> None:
    branches: List[dict] = node["oneOf"]
    disc = node.get("x-discriminator")
    if disc:
        tagged, untagged = {}, []
        for b in branches:
            const, resolved, bfile = _branch_const(b, file, disc, schemas)
            if const is None:
                untagged.append(b)
            else:
                tagged[const] = (resolved, bfile)
        if isinstance(inst, dict) and disc in inst:
            if inst[disc] in tagged:
                resolved, bfile = tagged[inst[disc]]
                _check(inst, resolved, bfile, path, schemas, acc)
            else:
                acc.errors.append(Issue(_join(path, disc), f"unknown {disc} '{inst[disc]}'. "
                                        f"Known: {', '.join(sorted(tagged))}"))
            return
        trials = [_try(inst, b, file, path, schemas) for b in untagged]
        passing = [t for t in trials if not t.errors]
        if len(passing) == 1:
            acc.merge(passing[0])
        else:
            forms = [f for f in (_first_required(b, file, schemas) for b in untagged) if f]
            acc.errors.append(Issue(path, f"needs '{disc}', or one of: {', '.join(forms)}" if forms
                                    else f"needs '{disc}'"))
        return

    trials = [_try(inst, b, file, path, schemas) for b in branches]
    passing = [t for t in trials if not t.errors]
    if len(passing) == 1:
        acc.merge(passing[0])
    elif len(passing) > 1:
        fields = [f for f in (_first_required(b, file, schemas) for b, t in zip(branches, trials) if not t.errors) if f]
        acc.errors.append(Issue(path, f"use only one of: {', '.join(fields)}" if len(fields) == len(passing)
                                else "matches more than one allowed form; remove the extra fields"))
    elif all(_only_missing(t) for t in trials):
        needs = sorted({e.message.split("'")[1] for t in trials for e in t.errors})
        acc.errors.append(Issue(path, f"needs exactly one of: {', '.join(needs)}"))
    else:
        acc.merge(_closest(trials, path))


def _first_required(branch: dict, file: str, schemas: Schemas) -> str:
    if "$ref" in branch:
        hit = _resolve(branch["$ref"], file, schemas)
        branch = hit[0] if hit else branch
    required = branch.get("required", [])
    return required[0] if required else ""


def _describe(value: Any) -> str:
    if isinstance(value, bool):
        return "true/false"
    if value is None:
        return "null"
    if isinstance(value, dict):
        return "an object"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, str):
        return f"text '{value}'" if len(value) < 30 else "text"
    return f"the number {value}"
