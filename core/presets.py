import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Tuple

from core.routine import jobs_for_day
from core.codec import parse_item, parse_companion, parse_skill, parse_job, parse_node
from core.types import (
    Item, Node, Companion, Exposure, PlayerCharacter, Skill, Job, GameState,
)

# Canonical default preset shipped with the engine. The runtime copy under
# presets/<name>/ is cloned from here and is the one players may edit.
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data" / "default-1.0"
PRESET_FILES = ("items.json", "nodes.json", "companions.json", "skills.json", "jobs.json")

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
# Your old job gives a head start in one work skill (enough for level 2).
ROUTINE_SKILLS: Dict[str, str] = {
    "seam_scraper": "engineering",
    "algae_tender": "survival",
    "cargo_handler": "logistics",
}
ROUTINE_START_XP = 30


MANIFEST_NAME = ".defaults.json"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_presets(presets_dir: Path) -> None:
    """
    Keeps the runtime preset copy in step with the shipped defaults.
    Missing files are copied. A file the player has not edited (its hash still matches
    the one recorded when it was copied) is refreshed when the defaults change.
    Edited files are left alone. A copy with no record at all predates tracking; its
    files are kept as <name>.old before being refreshed.
    """
    presets_dir.mkdir(parents=True, exist_ok=True)
    if presets_dir.resolve() == DEFAULT_DATA_DIR.resolve():
        return
    manifest_path = presets_dir / MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = None
    tracked = manifest is not None
    manifest = manifest or {}
    changed = False
    for name in PRESET_FILES:
        source, target = DEFAULT_DATA_DIR / name, presets_dir / name
        source_hash = _digest(source)
        if target.exists():
            current = _digest(target)
            if current == source_hash:
                if manifest.get(name) != source_hash:
                    manifest[name] = source_hash
                    changed = True
                continue
            if tracked and manifest.get(name) != current:
                continue  # edited by the player: keep it
            if not tracked:
                shutil.copyfile(target, target.with_name(name + ".old"))
        shutil.copyfile(source, target)
        manifest[name] = source_hash
        changed = True
    if changed or not tracked:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


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


def load_skills(path: Path) -> Tuple[Skill, ...]:
    """Pure deserializer for skills.json."""
    return tuple(_load_list(path, "Skill", {"id", "name", "perks"}, parse_skill))


def load_jobs(path: Path) -> Tuple[Job, ...]:
    """Pure deserializer for jobs.json."""
    return tuple(_load_list(path, "Job", {"id", "title", "kind", "target", "skill", "xp"}, parse_job))


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
    skill_catalog = load_skills(presets_dir / "skills.json")
    job_catalog = load_jobs(presets_dir / "jobs.json")

    anchor_item = item_catalog[ANCHOR_CHOICES.get(anchor_choice, "fitting_copper")]
    past_work, initial_capability = ROUTINE_CHOICES.get(routine_choice, ROUTINE_CHOICES[1])
    skills = {sk.id: 0 for sk in skill_catalog}
    skills[ROUTINE_SKILLS[past_work]] = ROUTINE_START_XP
    perk_caps = {p.grants for sk in skill_catalog for p in sk.perks if skills[sk.id] >= p.xp}

    character = PlayerCharacter(
        name=character_name.strip() or "Vaelen",
        past_work=past_work,
        personal_anchor=anchor_item,
        inventory=(anchor_item,),
        unlocked_capabilities=frozenset({initial_capability} | perk_caps),
        exposure=Exposure(0.0, 0.0, 0.0),
    )

    start_node_id = "stn_a_bunkroom"
    start_node = nodes[start_node_id]

    return GameState(
        character=character,
        current_node_id=start_node_id,
        nodes=nodes,
        companions=(),
        visited_nodes=frozenset({start_node_id}),
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
        skills=skills,
        skill_catalog=skill_catalog,
        job_catalog=job_catalog,
        jobs=jobs_for_day(job_catalog, 1),
        day=1,
        woke_at=0,
    )
