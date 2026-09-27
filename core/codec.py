"""JSON <-> domain conversion shared by preset loading and save files."""
from typing import Any, Dict, Mapping, Optional

from core.types import (
    Item, Fixture, Actor, GridPlacement, Edge, NodeVitals, Node,
    Companion, Exposure, Perk, Skill, Job,
)


def to_jsonable(value: Any) -> Any:
    """Recursively converts NamedTuples, mappings and collections to JSON-compatible values."""
    if hasattr(value, "_asdict"):
        return {k: to_jsonable(v) for k, v in value._asdict().items()}
    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, frozenset):
        return sorted(to_jsonable(v) for v in value)
    if isinstance(value, (tuple, list)):
        return [to_jsonable(v) for v in value]
    return value


def _tags(raw: Dict[str, Any], plural: str, singular: str) -> tuple:
    """Reads an any-of tag list, folding in the legacy single-tag field."""
    tags = [str(t) for t in raw.get(plural) or []]
    legacy = raw.get(singular)
    if legacy and legacy not in tags:
        tags.append(str(legacy))
    return tuple(tags)


def parse_vitals(raw: Optional[Dict[str, Any]]) -> Optional[NodeVitals]:
    if raw is None:
        return None
    return NodeVitals(
        pressure_kpa=float(raw["pressure_kpa"]),
        radiation_msv=float(raw["radiation_msv"]),
        temperature_c=int(raw["temperature_c"]),
    )


def parse_item(raw: Dict[str, Any]) -> Item:
    return Item(
        id=str(raw["id"]),
        name=str(raw["name"]),
        category=str(raw["category"]),
        tags=tuple(str(t) for t in raw["tags"]),
        integrity=int(raw["integrity"]),
        max_integrity=int(raw["max_integrity"]),
        description=str(raw["description"]),
    )


def parse_companion(raw: Dict[str, Any]) -> Companion:
    return Companion(
        id=str(raw["id"]),
        name=str(raw["name"]),
        title=str(raw["title"]),
        status=str(raw["status"]),
        capability_tag=raw.get("capability_tag"),
    )


def parse_skill(raw: Dict[str, Any]) -> Skill:
    return Skill(
        id=str(raw["id"]),
        name=str(raw["name"]),
        earned_by=str(raw.get("earned_by", "")),
        perks=tuple(
            Perk(level=int(p["level"]), xp=int(p["xp"]), grants=str(p["grants"]), text=str(p["text"]))
            for p in raw.get("perks", [])
        ),
    )


def parse_job(raw: Dict[str, Any]) -> Job:
    return Job(
        id=str(raw["id"]),
        title=str(raw["title"]),
        kind=str(raw["kind"]),
        target=str(raw["target"]),
        skill=str(raw["skill"]),
        xp=int(raw["xp"]),
        reward_items=tuple(str(i) for i in raw.get("reward_items") or []),
        item=raw.get("item"),
        count=int(raw.get("count", 1)),
        progress=int(raw.get("progress", 0)),
        done=bool(raw.get("done", False)),
    )


def parse_fixture(raw: Dict[str, Any]) -> Fixture:
    return Fixture(
        id=str(raw["id"]),
        glyph=str(raw["glyph"]),
        name=str(raw["name"]),
        state=str(raw["state"]),
        required_tags=_tags(raw, "required_tags", "required_tag"),
        grants_edge=raw.get("grants_edge"),
        on_use_effect=raw.get("on_use_effect"),
        description=str(raw["description"]),
        yields=tuple(str(i) for i in raw.get("yields") or []),
        log_text=raw.get("log_text"),
        log_text_locked=raw.get("log_text_locked"),
        opens_fixture=raw.get("opens_fixture"),
        grants_capability=raw.get("grants_capability"),
        on_repair_vitals=parse_vitals(raw.get("on_repair_vitals")),
        reseal_on_pass=bool(raw.get("reseal_on_pass", False)),
        restock=bool(raw.get("restock", False)),
    )


def parse_actor(raw: Dict[str, Any]) -> Actor:
    return Actor(
        id=str(raw["id"]),
        glyph=str(raw["glyph"]),
        name=str(raw["name"]),
        title=str(raw["title"]),
        status=str(raw["status"]),
        trade_offered_id=raw.get("trade_offered_id"),
        trade_required_tags=_tags(raw, "trade_required_tags", "trade_required_tag"),
        trade_completed=bool(raw.get("trade_completed", False)),
        dialogue_idle=str(raw["dialogue_idle"]),
        dialogue_post_trade=raw.get("dialogue_post_trade"),
        companion_unlock=raw.get("companion_unlock"),
        dialogue_variants=tuple((str(c), str(t)) for c, t in raw.get("dialogue_variants") or []),
    )


def parse_node(raw: Dict[str, Any]) -> Node:
    return Node(
        id=str(raw["id"]),
        name=str(raw["name"]),
        cluster=str(raw["cluster"]),
        size=int(raw["size"]),
        depth=int(raw["depth"]),
        environment=str(raw["environment"]),
        base_vitals=parse_vitals(raw["base_vitals"]),
        grid_floor=str(raw["grid_floor"]),
        grid_wall=str(raw["grid_wall"]),
        fixtures={fid: parse_fixture(f) for fid, f in raw.get("fixtures", {}).items()},
        actors={aid: parse_actor(a) for aid, a in raw.get("actors", {}).items()},
        placements=tuple(
            GridPlacement(entity_id=str(p["entity_id"]), row=int(p["row"]), col=int(p["col"]))
            for p in raw.get("placements", [])
        ),
        edges={
            eid: Edge(
                id=str(e["id"]),
                target_node_id=str(e["target_node_id"]),
                label=str(e["label"]),
                gated_by_fixture=e.get("gated_by_fixture"),
                requires_capability=e.get("requires_capability"),
            )
            for eid, e in raw.get("edges", {}).items()
        },
        description=str(raw["description"]),
    )


def parse_exposure(raw: Dict[str, Any]) -> Exposure:
    return Exposure(
        pressure_debt=float(raw["pressure_debt"]),
        radiation_dose=float(raw["radiation_dose"]),
        thermal_stress=float(raw["thermal_stress"]),
    )
