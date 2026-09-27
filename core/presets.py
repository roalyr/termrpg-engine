import json
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Tuple

from core.codec import parse_item, parse_companion, parse_tree_node, parse_node
from core.types import (
    Item, Node, Companion, Exposure, PlayerCharacter, TreeNode, GameState,
)

# Canonical default preset shipped with the engine. The runtime copy under
# presets/<name>/ is cloned from here and is the one players may edit.
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data" / "default-1.0"
PRESET_FILES = ("items.json", "nodes.json", "companions.json", "tree.json")

ANCHOR_CHOICES: Dict[int, str] = {
    1: "fitting_copper",
    2: "pass_work",
    3: "dice_steel",
    4: "slate_tally",
}

ROUTINE_CHOICES: Dict[int, Tuple[str, str]] = {
    1: ("seam_scraper", "seal_fitting"),
    2: ("algae_tender", "bio_filter"),
    3: ("cargo_handler", "heavy_lift"),
}


def ensure_presets(presets_dir: Path) -> None:
    """Clones any missing default preset files into presets_dir. Existing files are left untouched."""
    presets_dir.mkdir(parents=True, exist_ok=True)
    for name in PRESET_FILES:
        target = presets_dir / name
        if not target.exists():
            shutil.copyfile(DEFAULT_DATA_DIR / name, target)


def _load_list(path: Path, label: str, required_keys: set,
               parse: Callable[[Dict[str, Any]], Any]) -> List[Any]:
    if not path.exists():
        raise FileNotFoundError(f"{label} preset not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path.name} root must be a list")
    parsed = []
    for idx, raw in enumerate(data):
        missing = required_keys - set(raw.keys())
        if missing:
            raise ValueError(f"{label} #{idx} missing required fields: {missing}")
        parsed.append(parse(raw))
    return parsed


def load_items(path: Path) -> Tuple[Item, ...]:
    """Pure deserializer for items.json."""
    keys = {"id", "name", "category", "tags", "integrity", "max_integrity", "description"}
    return tuple(_load_list(path, "Item", keys, parse_item))


def load_companions(path: Path) -> Tuple[Companion, ...]:
    """Pure deserializer for companions.json."""
    return tuple(_load_list(path, "Companion", {"id", "name", "title", "status"}, parse_companion))


def load_tree(path: Path) -> Tuple[TreeNode, ...]:
    """Pure deserializer for tree.json."""
    keys = {"id", "name", "description", "prerequisite", "unlock_condition", "unlock_parameter", "attuned"}
    return tuple(_load_list(path, "TreeNode", keys, parse_tree_node))


def load_nodes(path: Path) -> Mapping[str, Node]:
    """Pure deserializer for nodes.json."""
    keys = {
        "id", "name", "cluster", "size", "depth", "environment", "base_vitals",
        "grid_floor", "grid_wall", "fixtures", "actors", "placements", "edges", "description",
    }
    return {node.id: node for node in _load_list(path, "Node", keys, parse_node)}


def load_catalogs(presets_dir: Path) -> Tuple[Mapping[str, Item], Mapping[str, Companion]]:
    """Item and companion definitions keyed by ID."""
    items = load_items(presets_dir / "items.json")
    companions = load_companions(presets_dir / "companions.json")
    return {i.id: i for i in items}, {c.id: c for c in companions}


def init_game_state(
    presets_dir: Path,
    character_name: str,
    anchor_choice: int,
    routine_choice: int,
) -> GameState:
    """Constructs a fresh initial GameState from loaded presets and character creation choices."""
    ensure_presets(presets_dir)
    item_catalog, companion_catalog = load_catalogs(presets_dir)
    nodes = load_nodes(presets_dir / "nodes.json")
    tree = load_tree(presets_dir / "tree.json")

    anchor_item = item_catalog[ANCHOR_CHOICES.get(anchor_choice, "fitting_copper")]
    past_work, initial_capability = ROUTINE_CHOICES.get(routine_choice, ROUTINE_CHOICES[1])

    character = PlayerCharacter(
        name=character_name.strip() or "Vaelen",
        past_work=past_work,
        personal_anchor=anchor_item,
        inventory=(anchor_item,),
        unlocked_capabilities=frozenset({initial_capability}),
        exposure=Exposure(0.0, 0.0, 0.0),
    )

    start_node_id = "stn_a_bunkroom"
    start_node = nodes[start_node_id]

    return GameState(
        character=character,
        current_node_id=start_node_id,
        nodes=nodes,
        companions=(),
        tree=tree,
        visited_nodes=frozenset({start_node_id}),
        depth_ticks={},
        cycle=0,
        player_row=start_node.size // 2,
        player_col=start_node.size // 2,
        message_buffer=(
            f"You wake in the Bunkroom, {character.name}.",
            "Walk onto things to use them. Type /help for help.",
        ),
        action_log=("Awoke in bunkroom.",),
        flavor_enabled=True,
        active_view="compartment",
        proximity_menu_active=False,
        is_running=True,
        item_catalog=item_catalog,
        companion_catalog=companion_catalog,
    )
