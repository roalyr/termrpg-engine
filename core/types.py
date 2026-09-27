from enum import Enum
from types import MappingProxyType
from typing import NamedTuple, Tuple, Mapping, Optional, FrozenSet

_EMPTY: Mapping = MappingProxyType({})


class ItemCategory(Enum):
    CREDENTIAL = "credential"
    UTILITY = "utility"
    SUSTENANCE = "sustenance"
    RECORD = "record"
    MATERIAL = "material"

class FixtureState(Enum):
    SEALED = "sealed"       # Closed, requires tag to open
    OPEN = "open"           # Passable / usable, no restriction
    LOCKED = "locked"       # Closed, requires tag to unlock
    ACTIVE = "active"       # Functional, accepts use interactions
    SPENT = "spent"         # Consumed / broken, no further interaction
    DISABLED = "disabled"   # Non-functional, requires repair

class Environment(Enum):
    PRESSURIZED = "pressurized"        # Nominal atmosphere
    DEPRESSURIZING = "depressurizing"  # Partial atmosphere, cold
    VACUUM = "vacuum"                  # No atmosphere
    HIGH_RAD = "high_rad"              # Elevated radiation
    LOW_TEMP = "low_temp"              # Extreme cold

class ExposureType(Enum):
    PRESSURE = "pressure"
    RADIATION = "radiation"
    TEMPERATURE = "temperature"

class Item(NamedTuple):
    id: str                    # Unique item identifier (e.g., "fitting_copper")
    name: str                  # Display name
    category: str              # ItemCategory value
    tags: Tuple[str, ...]      # Capability tags (e.g., ("seal_fitting", "conductive"))
    integrity: int             # Current condition / charges remaining
    max_integrity: int         # 0 = does not wear; >0 = degrades
    description: str           # In-world description

class NodeVitals(NamedTuple):
    pressure_kpa: float        # 101.3 = nominal; 0.0 = vacuum
    radiation_msv: float       # 0.0 = shielded; >50.0 = lethal unprotected
    temperature_c: int         # Celsius

class Fixture(NamedTuple):
    id: str                    # Unique fixture identifier (e.g., "hatch_berth")
    glyph: str                 # Single character rendered on grid
    name: str                  # Display name
    state: str                 # FixtureState value
    required_tags: Tuple[str, ...]  # Any one of these tags satisfies the fixture (empty = none)
    grants_edge: Optional[str]   # Edge ID in node.edges that this fixture gates
    on_use_effect: Optional[str] # "unlock", "refill", "repair", "scavenge", "harvest", "smelt", "override", "log"
    description: str
    yields: Tuple[str, ...] = ()            # Item IDs granted by "scavenge" / "harvest"
    log_text: Optional[str] = None          # Text shown by "log" fixtures
    log_text_locked: Optional[str] = None   # Extra text for readers with signal_analysis / signal_boost / lore
    opens_fixture: Optional[str] = None     # "override": fixture in the same node set to OPEN
    grants_capability: Optional[str] = None # "override": capability added to the player
    on_repair_vitals: Optional[NodeVitals] = None  # "repair": node vitals after the repair
    reseal_on_pass: bool = False            # Gate closes again after the player passes through

class Actor(NamedTuple):
    id: str                    # Unique actor identifier (e.g., "npc_kael")
    glyph: str                 # Single character rendered on grid
    name: str                  # Display name
    title: str                 # Role/occupation (e.g., "Dock Stevedore")
    status: str                # Current activity description
    trade_offered_id: Optional[str]    # Item ID this actor will give
    trade_required_tags: Tuple[str, ...]  # Any item carrying one of these tags is accepted
    trade_completed: bool              # Whether this actor's trade has been fulfilled
    dialogue_idle: str                 # Line spoken before trade or if no trade
    dialogue_post_trade: Optional[str] # Line spoken after trade is completed
    companion_unlock: Optional[str]    # Companion ID unlocked by completing trade (or None)
    dialogue_variants: Tuple[Tuple[str, str], ...] = ()  # (condition, text); first match replaces dialogue_idle

class GridPlacement(NamedTuple):
    entity_id: str             # Fixture or Actor ID
    row: int                   # 0-indexed row on the grid
    col: int                   # 0-indexed column on the grid

class Edge(NamedTuple):
    id: str                    # Edge identifier
    target_node_id: str        # Destination node ID
    label: str                 # Display label (e.g., "Berth 04", "Subdeck")
    gated_by_fixture: Optional[str]  # Fixture ID that must be OPEN to traverse
    requires_capability: Optional[str]  # Capability tag player must have

class Node(NamedTuple):
    id: str                    # Unique node identifier
    name: str                  # Display name
    cluster: str               # Cluster grouping (e.g., "station_alpha")
    size: int                  # Grid dimension N (N x N, where N <= 10)
    depth: int                 # Vertical depth (0 = surface/concourse)
    environment: str           # Environment enum value
    base_vitals: NodeVitals    # Current environmental readings (changed by repairs)
    grid_floor: str            # Single glyph used for empty floor tiles
    grid_wall: str             # Single glyph used for wall/boundary tiles
    fixtures: Mapping[str, Fixture]      # Keyed by fixture ID
    actors: Mapping[str, Actor]          # Keyed by actor ID
    placements: Tuple[GridPlacement, ...] # Where each fixture/actor sits on the grid
    edges: Mapping[str, Edge]            # Keyed by edge ID
    description: str                     # Short ambient description of this space

class Companion(NamedTuple):
    id: str                    # Unique companion identifier
    name: str                  # Display name
    title: str                 # Role (e.g., "Cargo Rigger")
    status: str                # Current state description
    capability_tag: Optional[str]  # Tag contributed to party (e.g., "two_person_lift")

class Exposure(NamedTuple):
    pressure_debt: float       # Accumulated decompression stress (0.0 = healthy)
    radiation_dose: float      # Accumulated radiation (0.0 = clean)
    thermal_stress: float      # Accumulated cold/heat stress (0.0 = comfortable)

class PlayerCharacter(NamedTuple):
    name: str
    past_work: str             # Chosen survival context string
    personal_anchor: Item      # Mundane starting possession (also in inventory)
    inventory: Tuple[Item, ...] # All carried items including personal_anchor
    unlocked_capabilities: FrozenSet[str]  # Earned traversal tags & clearances
    exposure: Exposure         # Accumulated environmental harm

class TreeNode(NamedTuple):
    id: str                              # Capability tag granted on attunement
    name: str                            # Display name
    description: str                     # What this attunement enables
    prerequisite: Optional[str]          # TreeNode ID that must be attuned first
    unlock_condition: str                # "visit_node", "survive_depth", "complete_trade", "use_fixture"
    unlock_parameter: str                # node_id, "depth:ticks", actor_id or fixture_id
    attuned: bool                        # Whether the player has earned this

class GameState(NamedTuple):
    character: PlayerCharacter
    current_node_id: str
    nodes: Mapping[str, Node]
    companions: Tuple[Companion, ...]     # Active party members
    tree: Tuple[TreeNode, ...]            # Progression tree nodes
    visited_nodes: FrozenSet[str]         # Explored node IDs (for map & attunement)
    depth_ticks: Mapping[int, int]        # Hostile ticks survived per depth without critical exposure
    cycle: int                            # Global simulation tick counter
    player_row: int                       # Player cursor row on current node grid (0-indexed)
    player_col: int                       # Player cursor column on current node grid (0-indexed)
    message_buffer: Tuple[str, ...]       # Queued output messages for next render
    action_log: Tuple[str, ...]           # Recent action history (max 20 entries)
    flavor_enabled: bool                  # Toggle for atmospheric prose
    active_view: str                      # "compartment" or "map_topology"
    proximity_menu_active: bool           # True when Zone 5 is showing the interaction menu
    is_running: bool                      # False = exit after next persist
    item_catalog: Mapping[str, Item] = _EMPTY            # Item definitions from the active preset
    companion_catalog: Mapping[str, Companion] = _EMPTY  # Companion definitions from the active preset
    color_enabled: bool = True                           # Bold/dim/inverse styles and the orange accent
