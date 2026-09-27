import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

from core.codec import (
    to_jsonable, parse_item, parse_companion, parse_tree_node, parse_node, parse_exposure,
)
from core.presets import DEFAULT_DATA_DIR, load_catalogs
from core.rules import exposure_thresholds, max_exposure, REVIVE_NODE_ID
from core.types import GameState, PlayerCharacter, Exposure

SCHEMA_VERSION = 3

# Authored fields refreshed from the default preset when upgrading an older save.
# Progress fields (state, trade_completed, attuned, vitals) are kept from the save.
_STATIC_FIXTURE_FIELDS = (
    "required_tags", "yields", "log_text", "log_text_locked", "opens_fixture",
    "grants_capability", "on_repair_vitals", "reseal_on_pass", "description", "name",
)
_STATIC_ACTOR_FIELDS = (
    "trade_required_tags", "dialogue_variants", "name", "title", "status",
    "dialogue_idle", "dialogue_post_trade",
)
_STATIC_TREE_FIELDS = ("unlock_parameter", "description", "name")
_STATIC_ITEM_FIELDS = ("name", "description", "tags")


def _upgrade(data: Dict[str, Any]) -> Dict[str, Any]:
    """Merges current world data and wording from the default preset into an older save without losing progress."""
    with open(DEFAULT_DATA_DIR / "nodes.json", "r", encoding="utf-8") as f:
        defaults = {n["id"]: n for n in json.load(f)}
    with open(DEFAULT_DATA_DIR / "tree.json", "r", encoding="utf-8") as f:
        tree_defaults = {t["id"]: t for t in json.load(f)}

    for nid, node in data["nodes"].items():
        ref = defaults.get(nid)
        if not ref:
            continue
        placed = {p["entity_id"] for p in node.get("placements", [])}
        for fid, ref_fixture in ref["fixtures"].items():
            fixture = node["fixtures"].get(fid)
            if fixture is None:
                node["fixtures"][fid] = dict(ref_fixture)
                node["placements"] += [p for p in ref["placements"] if p["entity_id"] == fid]
                continue
            fixture.pop("required_tag", None)
            for key in _STATIC_FIXTURE_FIELDS:
                if key in ref_fixture:
                    fixture[key] = ref_fixture[key]
        for aid, ref_actor in ref["actors"].items():
            actor = node["actors"].get(aid)
            if actor is not None:
                actor.pop("trade_required_tag", None)
                for key in _STATIC_ACTOR_FIELDS:
                    if key in ref_actor:
                        actor[key] = ref_actor[key]
                recruited = actor.get("trade_completed") and actor.get("companion_unlock")
                if recruited and aid in placed:
                    node["placements"] = [p for p in node["placements"] if p["entity_id"] != aid]
        for eid, ref_edge in ref["edges"].items():
            node["edges"].setdefault(eid, dict(ref_edge))["label"] = ref_edge["label"]
        node["name"] = ref["name"]
        node["description"] = ref["description"]

    for entry in data.get("tree", []):
        ref = tree_defaults.get(entry["id"])
        if ref:
            for key in _STATIC_TREE_FIELDS:
                entry[key] = ref[key]

    with open(DEFAULT_DATA_DIR / "items.json", "r", encoding="utf-8") as f:
        item_defaults = {i["id"]: i for i in json.load(f)}
    with open(DEFAULT_DATA_DIR / "companions.json", "r", encoding="utf-8") as f:
        companion_defaults = {c["id"]: c for c in json.load(f)}
    char = data["character"]
    for item in char["inventory"] + [char["personal_anchor"]]:
        ref = item_defaults.get(item["id"])
        if ref:
            for key in _STATIC_ITEM_FIELDS:
                item[key] = ref[key]
    for comp in data.get("companions", []):
        ref = companion_defaults.get(comp["id"])
        if ref:
            comp.update({k: ref[k] for k in ("name", "title", "status")})
    # Catalogues are rebuilt from the default preset so new wording applies everywhere.
    data.pop("item_catalog", None)
    data.pop("companion_catalog", None)
    return data


def state_to_dict(state: GameState) -> Dict[str, Any]:
    """Serializes GameState to a JSON-compatible dictionary."""
    data = to_jsonable(state)
    data["schema_version"] = SCHEMA_VERSION
    return data


def state_from_dict(data: Dict[str, Any]) -> GameState:
    """Deserializes a save dictionary. Older schemas are upgraded first."""
    if int(data.get("schema_version", 1)) < SCHEMA_VERSION:
        data = _upgrade(data)
    craw = data["character"]
    exposure = parse_exposure(craw["exposure"])
    character = PlayerCharacter(
        name=str(craw["name"]),
        past_work=str(craw["past_work"]),
        personal_anchor=parse_item(craw["personal_anchor"]),
        inventory=tuple(parse_item(i) for i in craw["inventory"]),
        unlocked_capabilities=frozenset(str(c) for c in craw["unlocked_capabilities"]),
        exposure=exposure,
    )

    nodes = {nid: parse_node(n) for nid, n in data["nodes"].items()}
    if data.get("item_catalog") and data.get("companion_catalog"):
        item_catalog = {k: parse_item(v) for k, v in data["item_catalog"].items()}
        companion_catalog = {k: parse_companion(v) for k, v in data["companion_catalog"].items()}
    else:
        item_catalog, companion_catalog = load_catalogs(DEFAULT_DATA_DIR)

    cur_node_id = str(data["current_node_id"])
    cur_node = nodes.get(cur_node_id)
    default_pos = cur_node.size // 2 if cur_node else 0
    player_row = int(data.get("player_row", default_pos))
    player_col = int(data.get("player_col", default_pos))
    proximity_menu_active = bool(data.get("proximity_menu_active", False))

    # Saves written by v1 could stop at the moment of collapse; revive them here (§4.3).
    if max_exposure(exposure) >= exposure_thresholds(character.unlocked_capabilities).incapacitated:
        character = character._replace(exposure=Exposure(0.0, 0.0, 0.0))
        cur_node_id = REVIVE_NODE_ID
        revive_node = nodes.get(cur_node_id)
        player_row = player_col = revive_node.size // 2 if revive_node else 0
        proximity_menu_active = False

    return GameState(
        character=character,
        current_node_id=cur_node_id,
        nodes=nodes,
        companions=tuple(parse_companion(c) for c in data.get("companions", [])),
        tree=tuple(parse_tree_node(t) for t in data.get("tree", [])),
        visited_nodes=frozenset(str(v) for v in data.get("visited_nodes", [])),
        depth_ticks={int(k): int(v) for k, v in data.get("depth_ticks", {}).items()},
        cycle=int(data["cycle"]),
        player_row=player_row,
        player_col=player_col,
        message_buffer=tuple(str(m) for m in data.get("message_buffer", ())),
        action_log=tuple(str(entry) for entry in data.get("action_log", ())),
        flavor_enabled=bool(data.get("flavor_enabled", True)),
        active_view=str(data.get("active_view", "compartment")),
        proximity_menu_active=proximity_menu_active,
        is_running=True,
        item_catalog=item_catalog,
        companion_catalog=companion_catalog,
        color_enabled=bool(data.get("color_enabled", True)),
    )


def save_state(state: GameState, save_dir: Path) -> None:
    """
    Deterministically and atomically writes state snapshot to saves/<name>/state.json.
    Writes first to a temporary file, flushes/syncs, then atomically renames.
    """
    save_dir.mkdir(parents=True, exist_ok=True)
    target_file = save_dir / "state.json"
    temp_file = save_dir / "state.json.tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(state_to_dict(state), f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())

    os.replace(temp_file, target_file)


def load_state(save_dir: Path) -> Optional[GameState]:
    """Loads and deserializes GameState from save_dir / state.json if present."""
    target_file = save_dir / "state.json"
    if not target_file.exists():
        return None
    with open(target_file, "r", encoding="utf-8") as f:
        return state_from_dict(json.load(f))
