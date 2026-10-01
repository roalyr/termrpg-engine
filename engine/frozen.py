"""Read-only copies of JSON data: dicts become mappingproxies, lists become tuples."""
from types import MappingProxyType
from typing import Any, Mapping

Record = Mapping[str, Any]  # a read-only JSON object


def freeze(value: Any) -> Any:
    """A deep read-only copy of a JSON value."""
    if isinstance(value, dict):
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    return value


def thaw(value: Any) -> Any:
    """A plain, mutable JSON copy of a frozen value (for saving or printing)."""
    if isinstance(value, Mapping):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [thaw(v) for v in value]
    return value
