import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

from core.types import (
    GameState, PlayerCharacter, Item, Exposure, Node, Fixture,
    Actor, GridPlacement, Edge, NodeVitals, Companion, TreeNode
)


def state_to_dict(state: GameState) -> Dict[str, Any]:
    """Serializes GameState to a JSON-compatible dictionary."""
    def item_to_dict(item: Item) -> Dict[str, Any]:
        return {
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "tags": list(item.tags),
            "integrity": item.integrity,
            "max_integrity": item.max_integrity,
            "description": item.description,
        }

    def companion_to_dict(comp: Companion) -> Dict[str, Any]:
        return {
            "id": comp.id,
            "name": comp.name,
            "title": comp.title,
            "status": comp.status,
            "capability_tag": comp.capability_tag,
        }

    def tree_node_to_dict(node: TreeNode) -> Dict[str, Any]:
        return {
            "id": node.id,
            "name": node.name,
            "description": node.description,
            "prerequisite": node.prerequisite,
            "unlock_condition": node.unlock_condition,
            "unlock_parameter": node.unlock_parameter,
            "attuned": node.attuned,
        }

    def node_to_dict(node: Node) -> Dict[str, Any]:
        return {
            "id": node.id,
            "name": node.name,
            "cluster": node.cluster,
            "size": node.size,
            "depth": node.depth,
            "environment": node.environment,
            "base_vitals": {
                "pressure_kpa": node.base_vitals.pressure_kpa,
                "radiation_msv": node.base_vitals.radiation_msv,
                "temperature_c": node.base_vitals.temperature_c,
            },
            "grid_floor": node.grid_floor,
            "grid_wall": node.grid_wall,
            "fixtures": {
                fid: {
                    "id": f.id,
                    "glyph": f.glyph,
                    "name": f.name,
                    "state": f.state,
                    "required_tag": f.required_tag,
                    "grants_edge": f.grants_edge,
                    "on_use_effect": f.on_use_effect,
                    "description": f.description,
                }
                for fid, f in node.fixtures.items()
            },
            "actors": {
                aid: {
                    "id": a.id,
                    "glyph": a.glyph,
                    "name": a.name,
                    "title": a.title,
                    "status": a.status,
                    "trade_offered_id": a.trade_offered_id,
                    "trade_required_tag": a.trade_required_tag,
                    "trade_completed": a.trade_completed,
                    "dialogue_idle": a.dialogue_idle,
                    "dialogue_post_trade": a.dialogue_post_trade,
                    "companion_unlock": a.companion_unlock,
                }
                for aid, a in node.actors.items()
            },
            "placements": [
                {"entity_id": p.entity_id, "row": p.row, "col": p.col}
                for p in node.placements
            ],
            "edges": {
                eid: {
                    "id": e.id,
                    "target_node_id": e.target_node_id,
                    "label": e.label,
                    "gated_by_fixture": e.gated_by_fixture,
                    "requires_capability": e.requires_capability,
                }
                for eid, e in node.edges.items()
            },
            "description": node.description,
        }

    char = state.character
    return {
        "character": {
            "name": char.name,
            "past_work": char.past_work,
            "personal_anchor": item_to_dict(char.personal_anchor),
            "inventory": [item_to_dict(i) for i in char.inventory],
            "unlocked_capabilities": list(char.unlocked_capabilities),
            "exposure": {
                "pressure_debt": char.exposure.pressure_debt,
                "radiation_dose": char.exposure.radiation_dose,
                "thermal_stress": char.exposure.thermal_stress,
            },
        },
        "current_node_id": state.current_node_id,
        "nodes": {nid: node_to_dict(n) for nid, n in state.nodes.items()},
        "companions": [companion_to_dict(c) for c in state.companions],
        "tree": [tree_node_to_dict(t) for t in state.tree],
        "visited_nodes": list(state.visited_nodes),
        "depth_ticks": {str(k): v for k, v in state.depth_ticks.items()},
        "cycle": state.cycle,
        "message_buffer": list(state.message_buffer),
        "action_log": list(state.action_log),
        "flavor_enabled": state.flavor_enabled,
        "active_view": state.active_view,
        "is_running": state.is_running,
    }


def state_from_dict(data: Dict[str, Any]) -> GameState:
    """Deserializes dictionary into pure immutable GameState NamedTuple structure."""
    def dict_to_item(raw: Dict[str, Any]) -> Item:
        return Item(
            id=str(raw["id"]),
            name=str(raw["name"]),
            category=str(raw["category"]),
            tags=tuple(str(t) for t in raw["tags"]),
            integrity=int(raw["integrity"]),
            max_integrity=int(raw["max_integrity"]),
            description=str(raw["description"]),
        )

    def dict_to_companion(raw: Dict[str, Any]) -> Companion:
        return Companion(
            id=str(raw["id"]),
            name=str(raw["name"]),
            title=str(raw["title"]),
            status=str(raw["status"]),
            capability_tag=raw.get("capability_tag"),
        )

    def dict_to_tree_node(raw: Dict[str, Any]) -> TreeNode:
        return TreeNode(
            id=str(raw["id"]),
            name=str(raw["name"]),
            description=str(raw["description"]),
            prerequisite=raw.get("prerequisite"),
            unlock_condition=str(raw["unlock_condition"]),
            unlock_parameter=str(raw["unlock_parameter"]),
            attuned=bool(raw["attuned"]),
        )

    def dict_to_node(raw: Dict[str, Any]) -> Node:
        vraw = raw["base_vitals"]
        vitals = NodeVitals(
            pressure_kpa=float(vraw["pressure_kpa"]),
            radiation_msv=float(vraw["radiation_msv"]),
            temperature_c=int(vraw["temperature_c"]),
        )
        fixtures = {
            fid: Fixture(
                id=str(f["id"]),
                glyph=str(f["glyph"]),
                name=str(f["name"]),
                state=str(f["state"]),
                required_tag=f.get("required_tag"),
                grants_edge=f.get("grants_edge"),
                on_use_effect=f.get("on_use_effect"),
                description=str(f["description"]),
            )
            for fid, f in raw.get("fixtures", {}).items()
        }
        actors = {
            aid: Actor(
                id=str(a["id"]),
                glyph=str(a["glyph"]),
                name=str(a["name"]),
                title=str(a["title"]),
                status=str(a["status"]),
                trade_offered_id=a.get("trade_offered_id"),
                trade_required_tag=a.get("trade_required_tag"),
                trade_completed=bool(a.get("trade_completed", False)),
                dialogue_idle=str(a["dialogue_idle"]),
                dialogue_post_trade=a.get("dialogue_post_trade"),
                companion_unlock=a.get("companion_unlock"),
            )
            for aid, a in raw.get("actors", {}).items()
        }
        placements = tuple(
            GridPlacement(
                entity_id=str(p["entity_id"]),
                row=int(p["row"]),
                col=int(p["col"]),
            )
            for p in raw.get("placements", [])
        )
        edges = {
            eid: Edge(
                id=str(e["id"]),
                target_node_id=str(e["target_node_id"]),
                label=str(e["label"]),
                gated_by_fixture=e.get("gated_by_fixture"),
                requires_capability=e.get("requires_capability"),
            )
            for eid, e in raw.get("edges", {}).items()
        }
        return Node(
            id=str(raw["id"]),
            name=str(raw["name"]),
            cluster=str(raw["cluster"]),
            size=int(raw["size"]),
            depth=int(raw["depth"]),
            environment=str(raw["environment"]),
            base_vitals=vitals,
            grid_floor=str(raw["grid_floor"]),
            grid_wall=str(raw["grid_wall"]),
            fixtures=fixtures,
            actors=actors,
            placements=placements,
            edges=edges,
            description=str(raw["description"]),
        )

    craw = data["character"]
    eraw = craw["exposure"]
    exposure = Exposure(
        pressure_debt=float(eraw["pressure_debt"]),
        radiation_dose=float(eraw["radiation_dose"]),
        thermal_stress=float(eraw["thermal_stress"]),
    )
    character = PlayerCharacter(
        name=str(craw["name"]),
        past_work=str(craw["past_work"]),
        personal_anchor=dict_to_item(craw["personal_anchor"]),
        inventory=tuple(dict_to_item(i) for i in craw["inventory"]),
        unlocked_capabilities=frozenset(str(c) for c in craw["unlocked_capabilities"]),
        exposure=exposure,
    )

    nodes = {nid: dict_to_node(n) for nid, n in data["nodes"].items()}
    companions = tuple(dict_to_companion(c) for c in data.get("companions", []))
    tree = tuple(dict_to_tree_node(t) for t in data.get("tree", []))
    visited = frozenset(str(v) for v in data.get("visited_nodes", []))
    depth_ticks = {int(k): int(v) for k, v in data.get("depth_ticks", {}).items()}

    return GameState(
        character=character,
        current_node_id=str(data["current_node_id"]),
        nodes=nodes,
        companions=companions,
        tree=tree,
        visited_nodes=visited,
        depth_ticks=depth_ticks,
        cycle=int(data["cycle"]),
        message_buffer=tuple(str(m) for m in data.get("message_buffer", ())),
        action_log=tuple(str(l) for l in data.get("action_log", ())),
        flavor_enabled=bool(data.get("flavor_enabled", True)),
        active_view=str(data.get("active_view", "compartment")),
        is_running=bool(data.get("is_running", True)),
    )


def save_state(state: GameState, save_dir: Path) -> None:
    """
    Deterministically and atomically writes state snapshot to saves/<name>/state.json.
    Writes first to a temporary file, flushes/syncs, then atomically renames.
    """
    save_dir.mkdir(parents=True, exist_ok=True)
    target_file = save_dir / "state.json"
    temp_file = save_dir / "state.json.tmp"

    data = state_to_dict(state)
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())

    os.replace(temp_file, target_file)


def load_state(save_dir: Path) -> Optional[GameState]:
    """Loads and deserializes GameState from save_dir / state.json if present."""
    target_file = save_dir / "state.json"
    if not target_file.exists():
        return None

    with open(target_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    return state_from_dict(data)
