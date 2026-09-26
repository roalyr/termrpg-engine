# SYSTEM BOOTSTRAP GDD: HARD SCI-FI FUNCTIONAL CLI RPG

---

## 1. Executive Summary & Core Design Tenets

This document specifies the technical architecture, mechanical contracts, domain models, and UX presentation for a minimalist, text-driven RPG built in pure Python 3. The system is designed for execution in constrained terminal environments (e.g., mobile Termux shells) and optimized for ingestion and iterative implementation by autonomous LLM agents.

### Core Tenets

1. **Zero External Dependencies:** Built strictly on the Python 3 standard library (`pathlib`, `typing`, `json`, `os`, `sys`, `enum`, `tty`, `termios`). No third-party packages, no build steps.
2. **Pure Functional Unidirectional Dataflow:** State is strictly immutable (`typing.NamedTuple`). State transitions are executed via pure reducers: `Action × State → State'`. No OOP classes, no internal mutation, no hidden object states.
3. **Non-Blocking Raw Input Interface:** The input loop reads single raw keystrokes via `tty`/`termios` without requiring Enter. WASD keys navigate the player cursor on the Zone 2 minimap. All arbitrary input is consumed; typed commands are explicitly initiated with a leading slash `/` (`/command`). The terminal screen is cleared before rendering each frame.
4. **Grounded Hard Sci-Fi Space Opera:** Everyday lived reality of commoners, orbital technicians, shift workers, and dock hands across orbital platforms, habitat rings, agricultural domes, and low-gravity stellar bodies (moons, asteroids). Deep gravity-well planets with punishing escape velocities are excluded. Intra-human violence exists alongside physical space hazards (vacuum, pressure differentials, radiation). Language is direct, utilitarian, and dry; technobabble, cyberpunk cliches, and jury-rigging tropes are prohibited.
5. **Lateral Qualitative Progression:** All traditional RPG tropes—manual stat distribution menus, numerical level bloat, and arbitrary tiered loot grids—are eliminated. Character advancement is tracked via an authored qualitative progression tree that unlocks situational interaction verbs, environmental tolerances, and clearance credentials.

---

## 2. Technical Stack & Architectural Invariants

### 2.1 Runtime & Environment

* **Platform:** Python 3.10+ Standard Library.
* **Terminal Constraints:** Designed for viewport widths >= 40 columns. The engine reads terminal width once per render via `os.get_terminal_size()`. If columns < 40, the engine suspends rendering and emits a resize warning to stdout.
* **Persistence:** Deterministic auto-save after every tick-advancing action into `saves/<character_name>/state.json`.
* **Preset Cloning & Modding:** Hardcoded default assets are cloned on initial startup into `presets/default-1.0/`. The runtime engine loads definitions exclusively from the active preset folder, enabling clean resets and total-conversion modding without manual file backups.

### 2.2 System Architecture Overview

```
                  +-------------------------------+
                  | Raw Keystroke / Typed Command |
                  | (tty/termios, no Enter needed)|
                  +---------------+---------------+
                                  |
          +-------------+---------+----------+
          |  WASD key   |   Interact (e)     |  Typed cmd
          |  (move)     |   (on entity tile) |  (inspect, pack …)
          v             v                    v
+------------------+     +-------------------+     +------------------+
| Current State    | --> | Dispatch & Pure   | --> | Next Immutable   |
| (NamedTuple)     |     | Reducer Functions |     | State Snapshot   |
+------------------+     +-------------------+     +--------+---------+
                                                            |
                                      +---------------------+---------------------+
                                      |                                           |
                                      v                                           v
                           +----------------------+                    +----------------------+
                           | Pure View Renderer   |                    | Atomic Persistence   |
                           | (CLI 6-Zone String)  |                    | saves/<name>/        |
                           +----------------------+                    +----------------------+
```

**Data Flow Contract:** Every user input is tokenized into an `Action`. The dispatcher selects the matching pure reducer function. The reducer returns a new `GameState`. The renderer produces a string from the new state. If the action advanced the tick, the persister writes to disk. The renderer then emits the string to stdout. No side effects occur inside reducers.

### 2.3 Directory Structure

```
project_root/
│
├── main.py                     # Entrypoint: I/O loop, char creation, dispatch
├── core/
│   ├── types.py                # NamedTuples, TypeAliases, Enums
│   ├── reducers.py             # Pure state transition functions (one per verb)
│   ├── tick.py                 # Tick processor: vitals update, integrity decay
│   ├── actions.py              # Command tokenizer & dispatch table
│   ├── presets.py              # Preset cloner, JSON deserializer
│   └── persistence.py          # Atomic JSON state serializer/deserializer
├── ui/
│   ├── render.py               # 6-zone viewport renderer (<=40 cols)
│   ├── topology_view.py        # Dedicated node graph / transit map renderer
│   └── text_tools.py           # Terminal width checker, text wrapping utils
├── presets/
│   └── default-1.0/            # Cloned editable JSON assets
│       ├── items.json          # Item definitions
│       ├── nodes.json          # World graph nodes
│       ├── companions.json     # Companion definitions
│       └── tree.json           # Progression tree definitions
└── saves/
    └── <character_name>/       # Auto-saved session snapshots
        └── state.json
```

---

## 3. Data Schema & Domain Models (`core/types.py`)

All structures are immutable `NamedTuple` classes. All enum-like fields use `enum.Enum`. Collections use immutable tuple and frozenset types.

### 3.1 Enumerations

```python
from enum import Enum

class ItemCategory(Enum):
    CREDENTIAL = "credential"
    UTILITY = "utility"
    SUSTENANCE = "sustenance"
    RECORD = "record"

class FixtureState(Enum):
    SEALED = "sealed"       # Closed, requires tag to open
    OPEN = "open"           # Passable / usable, no restriction
    LOCKED = "locked"       # Closed, requires tag to unlock
    ACTIVE = "active"       # Functional, accepts use interactions
    SPENT = "spent"         # Consumed / broken, no further interaction
    DISABLED = "disabled"   # Non-functional, requires repair

class Environment(Enum):
    PRESSURIZED = "pressurized"     # Nominal atmosphere
    DEPRESSURIZING = "depressurizing"  # Partial atmosphere, cold
    VACUUM = "vacuum"               # No atmosphere
    HIGH_RAD = "high_rad"           # Elevated radiation
    LOW_TEMP = "low_temp"           # Extreme cold

class ExposureType(Enum):
    PRESSURE = "pressure"
    RADIATION = "radiation"
    TEMPERATURE = "temperature"
```

### 3.2 Core Domain Structures

```python
from typing import NamedTuple, Tuple, Mapping, Optional, FrozenSet

class Item(NamedTuple):
    id: str                    # Unique item identifier (e.g., "fitting_copper")
    name: str                  # Display name
    category: str              # ItemCategory value
    tags: Tuple[str, ...]      # Capability tags (e.g., ("seal_fitting", "conductive"))
    integrity: int             # Current condition / charges remaining
    max_integrity: int         # 0 = indestructible/permanent; >0 = degrades
    description: str           # In-world description

class Fixture(NamedTuple):
    id: str                    # Unique fixture identifier (e.g., "hatch_berth")
    glyph: str                 # Single character rendered on grid
    name: str                  # Display name
    state: str                 # FixtureState value
    required_tag: Optional[str]  # Item/capability tag required to change state
    grants_edge: Optional[str]   # Edge ID in node.edges that this fixture gates
    on_use_effect: Optional[str] # Effect key: "refill", "repair", "unlock", None
    description: str

class Actor(NamedTuple):
    id: str                    # Unique actor identifier (e.g., "npc_kael")
    glyph: str                 # Single character rendered on grid
    name: str                  # Display name
    title: str                 # Role/occupation (e.g., "Dock Stevedore")
    status: str                # Current activity description
    trade_offered_id: Optional[str]    # Item ID this actor will give
    trade_required_tag: Optional[str]  # Tag the actor demands to complete trade
    trade_completed: bool              # Whether this actor's trade has been fulfilled
    dialogue_idle: str                 # Line spoken before trade or if no trade
    dialogue_post_trade: Optional[str] # Line spoken after trade is completed
    companion_unlock: Optional[str]    # Companion ID unlocked by completing trade (or None)

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

class NodeVitals(NamedTuple):
    pressure_kpa: float        # 101.3 = nominal; 0.0 = vacuum
    radiation_msv: float       # 0.0 = shielded; >50.0 = lethal unprotected
    temperature_c: int         # Celsius

class Node(NamedTuple):
    id: str                    # Unique node identifier
    name: str                  # Display name
    cluster: str               # Cluster grouping (e.g., "station_alpha")
    size: int                  # Grid dimension N (N x N, where N <= 8)
    depth: int                 # Vertical depth (0 = surface/concourse)
    environment: str           # Environment enum value
    base_vitals: NodeVitals    # Nominal environmental readings for this node
    grid_floor: str            # Single glyph used for empty floor tiles
    grid_wall: str             # Single glyph used for wall/boundary tiles
    fixtures: Mapping[str, Fixture]      # Keyed by fixture ID
    actors: Mapping[str, Actor]          # Keyed by actor ID
    placements: Tuple[GridPlacement, ...] # Where each fixture/actor sits on the grid
    edges: Mapping[str, Edge]            # Keyed by edge ID
    description: str                     # Short ambient description of this space
```

### 3.3 Player & Companion Structures

```python
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

### 3.4 Progression Tree Schema

```python
class TreeNode(NamedTuple):
    id: str                              # Capability tag granted on attunement
    name: str                            # Display name
    description: str                     # What this attunement enables
    prerequisite: Optional[str]          # TreeNode ID that must be attuned first
    unlock_condition: str                # Condition type: see §8.1 for valid values
    unlock_parameter: str                # Parameter for the condition (node_id, depth, etc.)
    attuned: bool                        # Whether the player has earned this
```

### 3.5 Game State Model

```python
class GameState(NamedTuple):
    character: PlayerCharacter
    current_node_id: str
    nodes: Mapping[str, Node]
    companions: Tuple[Companion, ...]     # Active party members
    tree: Tuple[TreeNode, ...]            # Progression tree nodes
    visited_nodes: FrozenSet[str]         # Explored node IDs (for map & attunement)
    depth_ticks: Mapping[int, int]        # Ticks survived per depth without critical exposure
    cycle: int                            # Global simulation tick counter
    player_row: int                       # Player cursor row on current node grid (0-indexed)
    player_col: int                       # Player cursor column on current node grid (0-indexed)
    message_buffer: Tuple[str, ...]       # Queued output messages for next render
    action_log: Tuple[str, ...]           # Recent action history (max 20 entries)
    flavor_enabled: bool                  # Toggle for atmospheric prose
    active_view: str                      # "compartment" or "map_topology"
    proximity_menu_active: bool           # True when Zone 5 is showing the interaction menu
    is_running: bool                      # False = exit after next persist
```

---

## 4. World Graph Topology & Progressive Spatial Scaling

### 4.1 Topology Structure

The world is an adjacency graph of discrete spatial nodes representing ship compartments, station rings, cargo shuttles, and lunar surface sites. Surface-to-orbit transit is routine and accessible via shuttle hops. Deep gravity-well planets are excluded.

```
TOPOLOGY (ADJACENCY GRAPH):

[Station Alpha]                   [Station Beta]
   Hab Ring (stn_a_hab)             Array Hub (stn_b_array)
      │                                │
   Berth 04 (stn_a_berth)          Fuel Spur (stn_b_fuel)
      │                                │
   Sub-Deck (stn_a_sub) D:1        Dock Ring (stn_b_dock)
      :                                :
   <Shuttle Hop>                    <Shuttle Hop>
      :                                :
      └───────────────┬────────────────┘
                      : (orbital burn)
             =====[Surface Pad]=====
                      │
                [Habitat Dome]
                /            \
       [Smelter Flat]     [Crater Rim]
            ║                 ║
      [Deep Mine] D:1    [Lava Tube] D:1
```

**Node ID Conventions:**
- Station Alpha: `stn_a_hab`, `stn_a_berth`, `stn_a_sub`
- Station Beta: `stn_b_array`, `stn_b_fuel`, `stn_b_dock`
- Transit: `shuttle_ab` (shared shuttle node between stations)
- Lunar: `luna_pad`, `luna_dome`, `luna_smelter`, `luna_crater`, `luna_mine`, `luna_tube`

### 4.2 Progressive Spatial Scaling

Challenge does not rely on arbitrary enemy stats or mob scaling. Difficulty scales through two vectors:

1. **Radial Transit Scaling (Horizontal):** Each shuttle hop costs a `transit_clearance` tagged credential (consumed on use). Nodes far from civil docks have no vendor actors to replace spent supplies. Sustenance items degrade 1 integrity per hop.
2. **Vertical Depth Scaling (Vertical):** Nodes with `depth > 0` impose progressive environmental hazards via their `base_vitals`:
   - `Depth 0`: Pressurized, nominal temperature (18–22°C), shielded radiation. No exposure accumulation.
   - `Depth 1`: Depressurizing conduits (50–80 kPa), cold pockets (-20°C to -40°C), structural debris requiring `force_lever` tagged tools on fixtures. Exposure accumulates at +1.0 per tick for each out-of-tolerance vital.
   - `Depth 2+`: Unpressurized vacuum (0 kPa), extreme radiation (>50 mSv), requiring specific attunement capabilities from the progression tree to halve exposure rates.

### 4.3 Exposure & Consequence Model

The player has an `Exposure` record with three accumulation tracks. Each tick spent in a hostile environment accumulates exposure based on the delta between node vitals and safe thresholds:

| Vital | Safe Threshold | Accumulation Formula (per tick) |
| :--- | :--- | :--- |
| Pressure | >= 90 kPa | `+max(0, (90 - node_pressure) / 30)` |
| Radiation | <= 5 mSv | `+max(0, (node_radiation - 5) / 15)` |
| Temperature | >= -10°C | `+max(0, (-10 - node_temp) / 20)` |

**Consequence Thresholds (per track):**

| Exposure Level | Threshold | Effect |
| :--- | :--- | :--- |
| Nominal | 0.0 – 4.9 | No effect |
| Stressed | 5.0 – 9.9 | Warning messages in Zone 5. `inspect` accuracy degrades (appends "[readings unclear]" to descriptions). |
| Critical | 10.0+ | All `use` and `[G] Go` actions have a 1-tick delay (forced `wait` inserted before execution). The message buffer warns of imminent incapacitation. |
| Incapacitated | 15.0+ in any track | Game over. The reducer sets `is_running = False` and emits a final narrative line. Save is preserved for reload. |

**Recovery:** Returning to a Depth 0 pressurized node reduces all exposure tracks by 2.0 per tick (minimum 0.0). There is no healing item; recovery requires retreating to safety.

**Attunement Mitigation:** Certain progression tree capabilities halve the accumulation rate for specific exposure types (see §8.1).

---

## 5. Interaction Mechanics & Command Vocabulary

### 5.1 WASD Navigation Model

The player is represented by a cursor position `(row, col)` on the Zone 2 N×N grid, stored in `GameState`. Movement is driven by raw single-keystrokes; no Enter key is required.

**Movement Keys (non-blocking, tick-advancing):**

| Key | Direction |
| :--- | :--- |
| `w` | Up (row − 1) |
| `s` | Down (row + 1) |
| `a` | Left (col − 1) |
| `d` | Right (col + 1) |

Movement is blocked at wall tiles (border cells). Each successful move advances the tick. On arrival at a tile occupied by a fixture, actor, or edge hatch, Zone 5 immediately presents a **proximity interaction menu** (see §5.2) — no separate command needed. Stepping onto an empty floor tile shows no menu.

**Player Cursor Glyph:** A dedicated cursor marker `@` is rendered at the player's current grid position. If a fixture or actor shares that tile, the entity glyph takes priority in display, but the cursor is still registered there for interaction purposes.

### 5.2 Proximity Interaction Menu

When the player cursor lands on a tile with an entity (fixture or actor), Zone 5 auto-displays a numbered option list. The player presses a single digit key to select — no typed command required.

**Menu Construction Rules:**
- Always includes: `[I] Inspect`
- If entity is a **fixture** with a usable `on_use_effect` and the player (or party) holds a matching-tagged item: `[U] Use <item_name>`
- If entity is a **fixture** with a traversable edge (`grants_edge` → `OPEN` state): `[G] Go through → <edge_label>`
- If entity is an **actor**: `[T] Talk`
- Always includes: `[X] Cancel` (clears menu, stays on tile)

```text
ZONE 5:
  [I] Inspect   [U] Use fitting_copper   [T] Talk   [X] Cancel
```

Selecting an option dispatches the corresponding action to the reducer directly, identical to the equivalent typed command. Zone 5 reverts to the message buffer after the action resolves.

### 5.3 Command Tokenization (Typed Commands)

Typed commands remain available for non-movement, non-interaction actions. Input drops into a conventional `> ` prompt (Zone 6) only when needed. All input is normalized to lowercase, split on whitespace, and matched as `[verb, *args]` against the dispatch table. Unknown verbs emit `"Unknown command. Type 'help' for available actions."` to the `message_buffer`.

### 5.4 System Command Grammar

| Verb / Key | Syntax | Reducer Logic | Advances Tick? |
| :--- | :--- | :--- | :--- |
| `w` / `a` / `s` / `d` | *(raw key)* | Moves player cursor one tile in the corresponding direction. On landing on an entity tile, triggers proximity menu in Zone 5. Blocked by wall tiles. | Yes |
| `e` / `[I]` | *(proximity menu)* | Equivalent to `inspect <entity_id>` for the tile under cursor. | No |
| `[U]` | *(proximity menu)* | Equivalent to `use <best_match_item_id> <fixture_id>` for the tile under cursor. Auto-selects the first inventory item whose tags satisfy the fixture's `required_tag`. | Yes |
| `[G]` | *(proximity menu)* | Traverses the open edge granted by the fixture under cursor. Equivalent to former `leave <edge_id>`. Checks capability requirements. | Yes |
| `[T]` | *(proximity menu)* | Equivalent to `talk <actor_id>` for the actor under cursor. | Yes |
| `inspect` | `inspect <target_id>` | Looks up fixture, actor, or inventory item by ID. Appends description + state to `message_buffer`. If target is a fixture: includes state and required_tag hint. If actor: includes status and dialogue_idle (or dialogue_post_trade if trade_completed). Does not modify game state beyond message_buffer. | No |
| `talk` | `talk <actor_id>` | Checks actor exists in current node. If actor has incomplete trade AND player inventory contains an item with matching `trade_required_tag`: executes trade (see §5.5). Otherwise: appends actor's `dialogue_idle` (or `dialogue_post_trade`) to `message_buffer`. | Yes |
| `use` | `use <item_id> <fixture_id>` | Validates item is in inventory. Validates fixture is in current node. Checks if ANY tag in item.tags matches fixture.required_tag. On match: executes the fixture's `on_use_effect` (see §5.6), reduces item integrity by 1 (removed from inventory at 0), transitions fixture state. On failure: appends `"That doesn't work here."` to message_buffer. | Yes |
| `wait` | `wait` | Advances cycle by 1. Runs tick processor (§5.7). | Yes |
| `map` | `map` | Sets `active_view = "map_topology"`. | No |
| `back` | `back` | Sets `active_view = "compartment"` (only valid from map view). | No |
| `log` | `log` | Appends last 10 entries of `action_log` to `message_buffer`. | No |
| `pack` | `pack` | Appends formatted inventory listing (name, integrity, tags) to `message_buffer`. | No |
| `character` | `character` | Appends progression tree view to `message_buffer` showing all nodes, attunement status, and next available unlock conditions. | No |
| `party` | `party` | Appends companion listing (name, title, status, capability) to `message_buffer`. | No |
| `flavor` | `flavor [on\|off]` | Toggles `flavor_enabled`. Appends confirmation to `message_buffer`. | No |
| `help` | `help` | Appends verb listing with syntax to `message_buffer`. | No |
| `quit` | `quit` / `q` | Sets `is_running = False`. Persistence layer saves before exit. | No |

### 5.5 Trade Protocol (`talk` with Eligible Actor)

When `talk <actor_id>` is issued and all conditions are met, the trade executes atomically within the reducer:

1. **Preconditions:** Actor's `trade_completed == False` AND player inventory contains at least one item where `trade_required_tag in item.tags`.
2. **Execution:**
   a. The first matching item in inventory has integrity reduced by 1. If integrity reaches 0, the item is removed from inventory.
   b. The actor's `trade_offered_id` item is looked up from the preset item definitions and added to player inventory at full integrity.
   c. The actor record is updated: `trade_completed = True`.
   d. If the actor has `companion_unlock`, the corresponding companion is added to `companions`.
   e. The actor's `dialogue_post_trade` is appended to `message_buffer`.
3. **Post-Trade:** Subsequent `talk` commands to this actor return `dialogue_post_trade`. The actor remains in the node but offers no further trades.

### 5.6 Fixture Use Effects (`on_use_effect`)

When `use <item_id> <fixture_id>` succeeds (tag match), the fixture's `on_use_effect` determines the outcome:

| Effect Key | Behavior |
| :--- | :--- |
| `"unlock"` | Fixture state transitions: `SEALED → OPEN` or `LOCKED → OPEN`. The edge gated by `grants_edge` becomes traversable. |
| `"refill"` | The used item's integrity is restored to `max_integrity`. Fixture remains `ACTIVE`. |
| `"repair"` | Fixture state transitions: `DISABLED → ACTIVE`. No item consumed (integrity still decremented by 1 from the base `use` logic). |
| `None` | No additional effect beyond the standard item integrity decrement. Fixture state unchanged. |

**State Transition Validation:** If a fixture is already `OPEN` or `SPENT`, `use` on it appends `"Already done."` to `message_buffer` and does not advance the tick.

### 5.7 Tick Processor (`core/tick.py`)

The tick processor is a pure function called after every tick-advancing action: `process_tick(state: GameState) -> GameState`. It executes the following steps in order:

1. **Cycle Increment:** `cycle += 1`.
2. **Exposure Accumulation:** Calculate exposure deltas from current node's `base_vitals` against safe thresholds (§4.3 table). If player has mitigating attunements, halve the relevant delta. Add deltas to `exposure` tracks.
3. **Exposure Recovery:** If current node is `depth == 0` and `environment == "pressurized"`, reduce all exposure tracks by 2.0 (min 0.0).
4. **Exposure Consequences:** Check each track against thresholds. Append appropriate warnings to `message_buffer`. If any track >= 15.0, set `is_running = False` and append incapacitation narrative.
5. **Integrity Decay:** For every sustenance item in inventory, decrement integrity by 1 if `cycle % 10 == 0` (every 10 ticks). Remove items at integrity 0 and append `"<item_name> is used up."` to message_buffer.
6. **Action Log:** Append a summary of the action that triggered this tick to `action_log` (keep max 20 entries, drop oldest).


---

## 6. UI Viewport & Terminal Constraints

### 6.1 Viewport Constraints

* Terminal width must satisfy >= 40 columns.
* Viewport is rendered as sequential newline-separated text. The terminal is cleared prior to each render cycle to provide a persistent, flicker-free viewport.
* Visual grids are bounded to N x N where N <= 8 (max grid width = 15 character columns, leaving >= 22 for Zone 3).
* **Prohibited:** Emojis, ANSI 16/256/RGB color palettes.
* **Player Cursor:** `@` marks the player's current tile on the Zone 2 grid. When the player cursor overlaps with an item, fixture, or actor tile, the entity glyph is displayed with inverted colors (`\033[7m`), clearly indicating cursor position while preserving the entity icon.
* **Permitted:** Box-drawing characters (`┌ ─ ┐ │ └ ┘ ├ ┤ ┬ ┴ ┼`), block elements (`█ ▓ ▒ ░`), math/technical symbols (`= ⌸ ⎅ ≡ ⚲ ⊞ ▲ ~ ◆ ■`), ANSI reverse-video video inversion (`\033[7m`) for cursor overlap.

### 6.2 Dynamic Zone Width Calculation

The renderer calculates zone widths dynamically based on the current node's grid size:

```
terminal_width = max(40, os.get_terminal_size().columns)
grid_char_width = (node.size * 2) - 1  # Each glyph + space, minus trailing
zone2_width = grid_char_width + 4       # 2 border chars + 2 padding
zone3_width = terminal_width - zone2_width - 3  # 3 = middle border + outer borders
```

For the default N=5: `zone2=13, zone3=24`. For N=8: `zone2=19, zone3=18`. Both are viable.

### 6.3 The 6-Zone Layout Specification

```text
+──────────────────────────────────────+ <- ZONE 1: LOCATION HEADER
│ LOCATION NAME [CLUSTER]             │    Node name, cluster tag, and
│ ATM:101kPa TMP:21C RAD:NOM          │    current vitals from base_vitals.
+──────────────────────────────────────+
│ ZONE 2: MAP    │ ZONE 3: STATUS     │ <- Split Upper Viewport
│ (N×N Grid)     │                    │    Zone 2: Spatial grid. Player
│ ┌─────────┐    │ CYCLE: 088         │    cursor @ moves via WASD.
│ │ · · = · │    │ EXPOSURE: NOM      │    Zone 3: Tick counter, exposure
│ │ · ⌸ · · │    │                    │    status, and compact inventory.
│ │ · @ · · │    │ PACK:              │
│ │ · · ⚲ · │    │  fitting_copper(1) │
│ └─────────┘    │  flask_water(3)    │
+────────────────+────────────────────+
│ ZONE 4: LEGEND                       │ <- Glyph key from node.fixtures
│  = : Transit hatch (sealed)         │    and node.actors. Shows ID in
│  ⌸ : Water spigot [spigot_01]       │    brackets for command targeting.
│  ⚲ : Survey pylon [pylon_01]        │
+──────────────────────────────────────+
│ ZONE 5: MESSAGES / INTERACTION MENU  │ <- message_buffer contents OR
│  [I] Inspect  [G] Go → Berth 04     │    proximity menu when cursor is
│  [X] Cancel                         │    on an entity tile. Menu clears
│  [!] Radiation elevated.            │    after selection or [X].
+──────────────────────────────────────+
│ WASD: move  /: cmd  M: map  Q: quit  │ <- ZONE 6: NAVIGATION / HINT BAR
+──────────────────────────────────────+   '/' opens command entry prompt.
```

**Zone Rendering Rules:**
- **Zone 1:** Always rendered. 2 lines: node name + vitals.
- **Zone 2 + 3:** Side-by-side. Zone 2 width is computed from node grid size. Zone 3 fills remainder. Player `@` is drawn at `(player_row, player_col)`; entity glyphs take priority when co-located.
- **Zone 4:** Legend block. One line per placed fixture/actor: `<glyph> : <name> [<id>]`. The `[<id>]` suffix is the target string used in typed commands.
- **Zone 5:** Dual-purpose. In **message mode** (default): renders `message_buffer` then clears it (max 6 lines, older messages truncate; omitted if empty). In **proximity-menu mode** (when cursor lands on entity tile): replaces buffer with the interaction option list (§5.2). Menu is dismissed by selection or `[X]`.
- **Zone 6:** Passive key-hint line: `WASD: move  /: cmd  M: map  Q: quit`. Command entry is initiated exclusively with `/`; all other non-action keystrokes are silently consumed without interrupting navigation.

### 6.4 Dedicated Map Topology View (`map`)

Invoked via `map`. Replaces the 6-zone view with an ASCII adjacency graph:

```text
TOPOLOGY [SECTOR GRAPH]
────────────────────────────────────────
 STATION ALPHA        STATION BETA
 [hab] ── [*brt]      [arr] ── [fuel]
            │            \    /
          (D:1)          [dock]
          [sub]            │
            : shuttle      : shuttle
            :··············:
                   :
          ════════[pad]════════ (Surface)
                   │
               [dome]
               /      \
          [smlt]      [crtr]
            ║            ║
          [mine]D:1   [tube]D:1
────────────────────────────────────────
[*brt] Berth 04 (HERE)     [hab] Hab Ring
[sub]  Sub-Deck (D:1)      [arr] Array Hub
[fuel] Fuel Spur            [dock] Dock Ring
[pad]  Lunar Surface Pad   [dome] Habitat Dome
[smlt] Smelter Flat        [crtr] Crater Rim
[mine] Deep Mine (D:1)    [tube] Lava Tube (D:1)
────────────────────────────────────────
CMD: back (return to compartment view — navigate via WASD on re-entry)
> 
```

**Map Legend Rules:** Current node is prefixed with `*`. Nodes the player has visited are shown with their short ID. Unvisited nodes reachable by one hop are shown. Unreachable nodes (2+ hops or gated) are shown as `[???]`.

---

## 7. Character Creation Sequence

Character creation runs as a sequential CLI flow. Each step maps directly to a field on `PlayerCharacter` and the initial `GameState`.

```text
[STEP 1: IDENTIFIER]
Enter callsign or name:
> Vaelen

[STEP 2: THE PERSONAL ANCHOR]
What did you keep in your pocket?
  1. A copper pipe fitting (clean threads).
  2. A stamped paper work-pass (expired).
  3. A pair of steel dice (pips worn flat).
> 1

[STEP 3: THE ROUTINE]
What did you do for work?
  1. Pipe cleaning and seam scraping.
  2. Algae-bed tending and filter rinsing.
  3. Cargo handling and skid lashing.
> 1

[STEP 4: CONFIRMATION]
Vaelen. Former scraper, copper fitting in pocket.
Starting in: Deck 4 - Shared Bunkroom.
Begin? [y/n]:
> y
```

### 7.1 Creation-to-State Mapping

| Step | Selection | State Effect |
| :--- | :--- | :--- |
| Step 1: Name | Free text | `character.name` |
| Step 2: Anchor | Choice 1: `fitting_copper` | `character.personal_anchor` = item; also placed in `character.inventory` |
| | Choice 2: `pass_work` | Same mapping |
| | Choice 3: `dice_steel` | Same mapping (item must be defined in items.json) |
| Step 3: Routine | Choice 1: Scraper | `character.past_work = "seam_scraper"`; `unlocked_capabilities` += `{"seal_fitting"}` |
| | Choice 2: Tender | `character.past_work = "algae_tender"`; `unlocked_capabilities` += `{"bio_filter"}` |
| | Choice 3: Handler | `character.past_work = "cargo_handler"`; `unlocked_capabilities` += `{"heavy_lift"}` |
| All | — | `current_node_id = "stn_a_bunkroom"`; `cycle = 0`; `exposure = Exposure(0,0,0)`; `player_row = node.size // 2`; `player_col = node.size // 2`; `proximity_menu_active = False` |

**Starting location is always `stn_a_bunkroom`**. The character creation flow was simplified from the original 5-step version to remove a starting-location choice that referenced undefined nodes. Starting in the bunkroom provides a safe Depth 0 tutorial space.

---

## 8. Progression, Capabilities & Party Mechanics

### 8.1 Qualitative Progression Tree

Character progression is an authored directed tree accessed via `character`. Each `TreeNode` has a specific `unlock_condition` that determines how it is earned.

```
PROGRESSION TREE:

[seam_discipline] ──── [bulkhead_ear] ──── [deep_well]
        │
[cold_bypass] ──────── [vacuum_walk] ──── [trench_hardened]
```

**Unlock Condition Types:**

| Condition Type | Parameter | Trigger |
| :--- | :--- | :--- |
| `"visit_node"` | Node ID | Player enters the specified node for the first time |
| `"survive_depth"` | Depth int as string | Player completes 5 ticks at the specified depth without reaching Critical exposure |
| `"complete_trade"` | Actor ID | Player completes a trade with the specified actor |
| `"use_fixture"` | Fixture ID | Player successfully uses the specified fixture |

**Tree Node Definitions:**

| ID | Name | Prerequisite | Condition | Parameter | Effect |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `seam_discipline` | Seam Discipline | None | `use_fixture` | `spigot_01` | `inspect` on sealed fixtures reveals leak state and required tool tag |
| `bulkhead_ear` | Bulkhead Ear | `seam_discipline` | `visit_node` | `stn_a_sub` | `inspect` on sealed edges reveals destination node's pressure level before opening |
| `cold_bypass` | Cold-Line Bypass | None | `survive_depth` | `1` | Halves `temperature` exposure accumulation rate |
| `vacuum_walk` | Vacuum Walk | `cold_bypass` | `complete_trade` | `npc_kael` | Halves `pressure` exposure accumulation rate; unlocks `vacuum_traverse` capability tag |
| `deep_well` | Deep-Well Attunement | `bulkhead_ear` | `survive_depth` | `2` | Halves `radiation` exposure accumulation rate |
| `trench_hardened` | Trench Hardened | `vacuum_walk` | `visit_node` | `luna_mine` | All exposure thresholds increased by 5.0 (Stressed at 10, Critical at 15, Incapacitated at 20) |

**Attunement Check:** After each tick, the tick processor checks all un-attuned tree nodes whose prerequisites are met. If the current action satisfies the node's unlock condition, the node is attuned: its `id` is added to `unlocked_capabilities`, a message is appended to `message_buffer`, and the tree node's `attuned` flag is set to `True` in state.

### 8.2 Inventory Assets

Items represent material possessions with narrative and physical utility. All items are defined in `presets/default-1.0/items.json`.

| ID | Name | Category | Tags | Max Integrity | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `fitting_copper` | Copper Pipe Fitting | utility | `seal_fitting`, `conductive` | 1 | Anchor option. Consumed on first use. |
| `pass_work` | Stamped Work Pass | credential | `dock_clearance`, `id_verified` | 0 | Anchor option. Indestructible. |
| `dice_steel` | Steel Dice | record | `morale`, `barter_token` | 0 | Anchor option. Indestructible. |
| `chit_transit` | Transit Token | credential | `transit_clearance` | 1 | Consumed on shuttle hop. |
| `tool_prybar` | Thermal Pry-Bar | utility | `force_lever`, `heavy_duty` | 4 | Opens stuck hatches and debris. |
| `flask_water` | Insulated Canteen | sustenance | `hydration`, `refillable` | 3 | Refilled at active spigots. Decays per §5.6. |
| `ration_dry` | Compressed Ration | sustenance | `nutrition` | 3 | Decays per §5.6. No refill. |
| `tool_spanner` | Filter Spanner | utility | `bio_filter`, `wrench` | 3 | Used on biological filtration fixtures. |
| `slate_tally` | Chalk Slate | record | `record`, `marking` | 0 | Indestructible. Narrative item. |

### 8.3 Companions & Party

Companions are persistent crew members unlocked via specific actor trades (§5.4, `companion_unlock` field). They are **not** inventory items.

**Companion Definitions (`companions.json`):**

| ID | Name | Title | Capability Tag | Unlock Source |
| :--- | :--- | :--- | :--- | :--- |
| `comp_radek` | Radek | Cargo Rigger | `two_person_lift` | Actor `npc_kael` trade |
| `comp_mira` | Mira | Array Technician | `signal_boost` | Actor in Station Beta (TBD) |

**Party Mechanics:**
- Companions contribute their `capability_tag` to available capabilities during `use` checks. When the player uses an item on a fixture, the system checks both `item.tags` and all companion `capability_tag` values for a match against `fixture.required_tag`.
- Some fixtures have `required_tag` values that only companions provide (e.g., `"two_person_lift"` for heavy cargo hatches), creating hard gates that require party recruitment.
- Companions persist across node transitions. They cannot be dismissed, lost, or killed in v1.0 scope.
- The `party` command displays each companion's name, title, and current status.

---

## 9. Preset Reference Dataset (`presets/default-1.0/`)

### 9.1 Items (`items.json`)

```json
[
  {
    "id": "fitting_copper",
    "name": "Copper Pipe Fitting",
    "category": "utility",
    "tags": ["seal_fitting", "conductive"],
    "integrity": 1,
    "max_integrity": 1,
    "description": "Standard threaded pipe collar with a clean silicone ring."
  },
  {
    "id": "pass_work",
    "name": "Stamped Work Pass",
    "category": "credential",
    "tags": ["dock_clearance", "id_verified"],
    "integrity": 0,
    "max_integrity": 0,
    "description": "Laminated shift card signed by the transit stevedore office."
  },
  {
    "id": "dice_steel",
    "name": "Steel Dice",
    "category": "record",
    "tags": ["morale", "barter_token"],
    "integrity": 0,
    "max_integrity": 0,
    "description": "Two milled steel cubes, pips worn flat from rolling on deck plate."
  },
  {
    "id": "chit_transit",
    "name": "Transit Token",
    "category": "credential",
    "tags": ["transit_clearance"],
    "integrity": 1,
    "max_integrity": 1,
    "description": "Stamped metal token granting single-hop shuttle boarding."
  },
  {
    "id": "tool_prybar",
    "name": "Thermal Pry-Bar",
    "category": "utility",
    "tags": ["force_lever", "heavy_duty"],
    "integrity": 4,
    "max_integrity": 4,
    "description": "Flat-nosed iron lever rated for stuck latches and warped plates."
  },
  {
    "id": "flask_water",
    "name": "Insulated Canteen",
    "category": "sustenance",
    "tags": ["hydration", "refillable"],
    "integrity": 3,
    "max_integrity": 3,
    "description": "Metal drinking flask fitted with a screw seal."
  },
  {
    "id": "ration_dry",
    "name": "Compressed Ration",
    "category": "sustenance",
    "tags": ["nutrition"],
    "integrity": 3,
    "max_integrity": 3,
    "description": "Dense calorie block in foil wrap. Tastes like salted chalk."
  },
  {
    "id": "tool_spanner",
    "name": "Filter Spanner",
    "category": "utility",
    "tags": ["bio_filter", "wrench"],
    "integrity": 3,
    "max_integrity": 3,
    "description": "Offset ring spanner sized for standard filtration cartridge bolts."
  },
  {
    "id": "slate_tally",
    "name": "Chalk Slate",
    "category": "record",
    "tags": ["record", "marking"],
    "integrity": 0,
    "max_integrity": 0,
    "description": "Flat stone slab with a nub of calcium carbonate chalk."
  }
]
```

### 9.2 Starting Nodes (`nodes.json`)

The v1.0 preset defines the starting cluster (Station Alpha) in full detail. Additional clusters are defined with minimal fixtures to establish the graph skeleton.

```json
[
  {
    "id": "stn_a_bunkroom",
    "name": "Deck 4 - Shared Bunkroom",
    "cluster": "station_alpha",
    "size": 5,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {"pressure_kpa": 101.3, "radiation_msv": 0.1, "temperature_c": 20},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hatch_berth": {
        "id": "hatch_berth",
        "glyph": "=",
        "name": "Transit Hatch",
        "state": "open",
        "required_tag": null,
        "grants_edge": "to_berth",
        "on_use_effect": null,
        "description": "Standard oval pressure seal leading to the primary berths."
      },
      "spigot_01": {
        "id": "spigot_01",
        "glyph": "⌸",
        "name": "Water Spigot",
        "state": "active",
        "required_tag": "refillable",
        "grants_edge": null,
        "on_use_effect": "refill",
        "description": "Push-valve tap metering gray-line recycled water."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "hatch_berth", "row": 0, "col": 2},
      {"entity_id": "spigot_01", "row": 3, "col": 1}
    ],
    "edges": {
      "to_berth": {
        "id": "to_berth",
        "target_node_id": "stn_a_berth",
        "label": "Berth 04",
        "gated_by_fixture": null,
        "requires_capability": null
      }
    },
    "description": "Narrow compartment lined with fold-down bunks. Recycled air tastes of copper and cleaning solvent."
  },
  {
    "id": "stn_a_berth",
    "name": "Berth 04 - Transfer Platform",
    "cluster": "station_alpha",
    "size": 7,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {"pressure_kpa": 101.3, "radiation_msv": 0.2, "temperature_c": 18},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hatch_bunks": {
        "id": "hatch_bunks",
        "glyph": "◆",
        "name": "Bunkroom Hatch",
        "state": "open",
        "required_tag": null,
        "grants_edge": "to_bunks",
        "on_use_effect": null,
        "description": "Hatch back to the shared sleeping quarters."
      },
      "cargo_hoist": {
        "id": "cargo_hoist",
        "glyph": "⎅",
        "name": "Cargo Hoist Platform",
        "state": "locked",
        "required_tag": "dock_clearance",
        "grants_edge": "to_subdeck",
        "on_use_effect": "unlock",
        "description": "Chain-driven freight platform descending into the lower conduit well."
      },
      "shuttle_gate": {
        "id": "shuttle_gate",
        "glyph": "=",
        "name": "Shuttle Boarding Gate",
        "state": "sealed",
        "required_tag": "transit_clearance",
        "grants_edge": "to_shuttle",
        "on_use_effect": "unlock",
        "description": "Flexible boarding seal clamped to the exterior hopper vessel."
      },
      "freight_skid": {
        "id": "freight_skid",
        "glyph": "▓",
        "name": "Lashed Freight Skid",
        "state": "active",
        "required_tag": null,
        "grants_edge": null,
        "on_use_effect": null,
        "description": "Heavy cargo skid lashed down with tension clamps. Manifest reads: machine parts, Luna-bound."
      },
      "hab_hatch": {
        "id": "hab_hatch",
        "glyph": "≡",
        "name": "Hab Ring Corridor",
        "state": "open",
        "required_tag": null,
        "grants_edge": "to_hab",
        "on_use_effect": null,
        "description": "Wide corridor hatch leading up to the hab ring common gallery."
      }
    },
    "actors": {
      "npc_kael": {
        "id": "npc_kael",
        "glyph": "K",
        "name": "Kael",
        "title": "Dock Stevedore",
        "status": "Checking tension clamps on freight skid",
        "trade_offered_id": "pass_work",
        "trade_required_tag": "seal_fitting",
        "trade_completed": false,
        "dialogue_idle": "Hopper to the moon pad is spooling. Need a replacement collar for this hydraulic line before I can endorse any passes.",
        "dialogue_post_trade": "Collar's seated. Here — shift pass, endorsed. Radek down on the sub-deck could use a hand with the cargo platform.",
        "companion_unlock": null
      }
    },
    "placements": [
      {"entity_id": "hatch_bunks", "row": 0, "col": 3},
      {"entity_id": "freight_skid", "row": 2, "col": 2},
      {"entity_id": "npc_kael", "row": 2, "col": 4},
      {"entity_id": "hab_hatch", "row": 3, "col": 0},
      {"entity_id": "shuttle_gate", "row": 3, "col": 6},
      {"entity_id": "cargo_hoist", "row": 5, "col": 3}
    ],
    "edges": {
      "to_bunks": {
        "id": "to_bunks",
        "target_node_id": "stn_a_bunkroom",
        "label": "Bunkroom",
        "gated_by_fixture": null,
        "requires_capability": null
      },
      "to_hab": {
        "id": "to_hab",
        "target_node_id": "stn_a_hab",
        "label": "Hab Ring",
        "gated_by_fixture": null,
        "requires_capability": null
      },
      "to_shuttle": {
        "id": "to_shuttle",
        "target_node_id": "shuttle_ab",
        "label": "Shuttle Hopper",
        "gated_by_fixture": "shuttle_gate",
        "requires_capability": null
      },
      "to_subdeck": {
        "id": "to_subdeck",
        "target_node_id": "stn_a_sub",
        "label": "Sub-Deck",
        "gated_by_fixture": "cargo_hoist",
        "requires_capability": null
      }
    },
    "description": "Open transfer bay smelling of hydraulic fluid and ozone. Cargo skids line the deck under industrial lighting."
  },
  {
    "id": "stn_a_sub",
    "name": "Sub-Deck - Conduit Well",
    "cluster": "station_alpha",
    "size": 6,
    "depth": 1,
    "environment": "depressurizing",
    "base_vitals": {"pressure_kpa": 65.0, "radiation_msv": 2.0, "temperature_c": -25},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hoist_up": {
        "id": "hoist_up",
        "glyph": "⎅",
        "name": "Cargo Hoist (Up)",
        "state": "open",
        "required_tag": null,
        "grants_edge": "to_berth",
        "on_use_effect": null,
        "description": "Chain platform ascending back to Berth 04."
      },
      "jammed_valve": {
        "id": "jammed_valve",
        "glyph": "■",
        "name": "Jammed Pressure Valve",
        "state": "disabled",
        "required_tag": "force_lever",
        "grants_edge": null,
        "on_use_effect": "repair",
        "description": "Manual shutoff valve seized by thermal contraction. Frozen in the closed position."
      }
    },
    "actors": {
      "npc_radek": {
        "id": "npc_radek",
        "glyph": "R",
        "name": "Radek",
        "title": "Cargo Rigger",
        "status": "Crouched by a frozen conduit junction",
        "trade_offered_id": "ration_dry",
        "trade_required_tag": "force_lever",
        "trade_completed": false,
        "dialogue_idle": "Valve's seized. Can't move freight until someone levers it open. Got a bar?",
        "dialogue_post_trade": "That did it. Pressure's equalizing. Take this ration — I packed extra. I'll stick around if you're heading deeper.",
        "companion_unlock": "comp_radek"
      }
    },
    "placements": [
      {"entity_id": "hoist_up", "row": 0, "col": 3},
      {"entity_id": "jammed_valve", "row": 3, "col": 1},
      {"entity_id": "npc_radek", "row": 3, "col": 4}
    ],
    "edges": {
      "to_berth": {
        "id": "to_berth",
        "target_node_id": "stn_a_berth",
        "label": "Berth 04 (Up)",
        "gated_by_fixture": null,
        "requires_capability": null
      }
    },
    "description": "Low-ceilinged conduit passage. Frost crusts the pipe manifolds. The air is thin and bites cold."
  },
  {
    "id": "stn_a_hab",
    "name": "Hab Ring - Common Gallery",
    "cluster": "station_alpha",
    "size": 6,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {"pressure_kpa": 101.3, "radiation_msv": 0.1, "temperature_c": 21},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hatch_to_berth": {
        "id": "hatch_to_berth",
        "glyph": "=",
        "name": "Berth Access Hatch",
        "state": "open",
        "required_tag": null,
        "grants_edge": "to_berth",
        "on_use_effect": null,
        "description": "Wide corridor hatch leading down to the transfer berths."
      },
      "notice_board": {
        "id": "notice_board",
        "glyph": "≡",
        "name": "Station Notice Board",
        "state": "active",
        "required_tag": null,
        "grants_edge": null,
        "on_use_effect": null,
        "description": "Laminated postings: shift rosters, water ration schedules, a missing-persons notice dated three cycles back."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "hatch_to_berth", "row": 5, "col": 3},
      {"entity_id": "notice_board", "row": 2, "col": 2}
    ],
    "edges": {
      "to_berth": {
        "id": "to_berth",
        "target_node_id": "stn_a_berth",
        "label": "Berth 04",
        "gated_by_fixture": null,
        "requires_capability": null
      }
    },
    "description": "Curved corridor segment with brushed-metal walls. Handrails run at waist height. Faint hum of air recyclers."
  },
  {
    "id": "shuttle_ab",
    "name": "Inter-Station Shuttle",
    "cluster": "transit",
    "size": 4,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {"pressure_kpa": 98.0, "radiation_msv": 1.5, "temperature_c": 16},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "gate_alpha": {
        "id": "gate_alpha",
        "glyph": "◆",
        "name": "Station Alpha Umbilical",
        "state": "open",
        "required_tag": null,
        "grants_edge": "to_stn_a",
        "on_use_effect": null,
        "description": "Docking collar sealed to Station Alpha's Berth 04."
      },
      "gate_beta": {
        "id": "gate_beta",
        "glyph": "=",
        "name": "Station Beta Umbilical",
        "state": "sealed",
        "required_tag": "transit_clearance",
        "grants_edge": "to_stn_b",
        "on_use_effect": "unlock",
        "description": "Docking collar to Station Beta's Dock Ring. Requires transit token."
      },
      "gate_luna": {
        "id": "gate_luna",
        "glyph": "▲",
        "name": "Lunar Descent Hatch",
        "state": "sealed",
        "required_tag": "transit_clearance",
        "grants_edge": "to_luna",
        "on_use_effect": "unlock",
        "description": "Descent module hatch for the surface run to Lunar Pad."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "gate_alpha", "row": 0, "col": 1},
      {"entity_id": "gate_beta", "row": 0, "col": 2},
      {"entity_id": "gate_luna", "row": 3, "col": 1}
    ],
    "edges": {
      "to_stn_a": {
        "id": "to_stn_a",
        "target_node_id": "stn_a_berth",
        "label": "Station Alpha",
        "gated_by_fixture": null,
        "requires_capability": null
      },
      "to_stn_b": {
        "id": "to_stn_b",
        "target_node_id": "stn_b_dock",
        "label": "Station Beta",
        "gated_by_fixture": "gate_beta",
        "requires_capability": null
      },
      "to_luna": {
        "id": "to_luna",
        "target_node_id": "luna_pad",
        "label": "Lunar Surface",
        "gated_by_fixture": "gate_luna",
        "requires_capability": null
      }
    },
    "description": "Cramped shuttle cabin with four acceleration couches. Viewport shows the slow rotation of station superstructure."
  },
  {
    "id": "stn_b_dock",
    "name": "Dock Ring - Bay 7",
    "cluster": "station_beta",
    "size": 6,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {"pressure_kpa": 100.5, "radiation_msv": 0.3, "temperature_c": 19},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "shuttle_return": {
        "id": "shuttle_return",
        "glyph": "◆",
        "name": "Shuttle Docking Port",
        "state": "open",
        "required_tag": null,
        "grants_edge": "to_shuttle",
        "on_use_effect": null,
        "description": "Umbilical back to the inter-station shuttle."
      },
      "hatch_array": {
        "id": "hatch_array",
        "glyph": "=",
        "name": "Array Corridor Hatch",
        "state": "open",
        "required_tag": null,
        "grants_edge": "to_array",
        "on_use_effect": null,
        "description": "Pressure hatch leading to the communications array hub."
      },
      "hatch_fuel": {
        "id": "hatch_fuel",
        "glyph": "▲",
        "name": "Fuel Spur Access",
        "state": "sealed",
        "required_tag": "id_verified",
        "grants_edge": "to_fuel",
        "on_use_effect": "unlock",
        "description": "Heavy blast door to the fuel processing spur. ID verification required."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "shuttle_return", "row": 0, "col": 3},
      {"entity_id": "hatch_array", "row": 3, "col": 0},
      {"entity_id": "hatch_fuel", "row": 3, "col": 5}
    ],
    "edges": {
      "to_shuttle": {
        "id": "to_shuttle",
        "target_node_id": "shuttle_ab",
        "label": "Shuttle",
        "gated_by_fixture": null,
        "requires_capability": null
      },
      "to_array": {
        "id": "to_array",
        "target_node_id": "stn_b_array",
        "label": "Array Hub",
        "gated_by_fixture": null,
        "requires_capability": null
      },
      "to_fuel": {
        "id": "to_fuel",
        "target_node_id": "stn_b_fuel",
        "label": "Fuel Spur",
        "gated_by_fixture": "hatch_fuel",
        "requires_capability": null
      }
    },
    "description": "Wide docking bay with magnetic clamp rails and loading gantries. The air smells of fuel volatiles and sealant."
  },
  {
    "id": "stn_b_array",
    "name": "Array Hub - Comms Center",
    "cluster": "station_beta",
    "size": 5,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {"pressure_kpa": 101.0, "radiation_msv": 0.2, "temperature_c": 20},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hatch_dock": {
        "id": "hatch_dock",
        "glyph": "◆",
        "name": "Dock Ring Hatch",
        "state": "open",
        "required_tag": null,
        "grants_edge": "to_dock",
        "on_use_effect": null,
        "description": "Corridor back to Dock Ring Bay 7."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "hatch_dock", "row": 4, "col": 2}
    ],
    "edges": {
      "to_dock": {
        "id": "to_dock",
        "target_node_id": "stn_b_dock",
        "label": "Dock Ring",
        "gated_by_fixture": null,
        "requires_capability": null
      }
    },
    "description": "Hexagonal chamber packed with signal processing racks. Status LEDs blink in steady patterns. Quiet."
  },
  {
    "id": "stn_b_fuel",
    "name": "Fuel Spur - Processing Bay",
    "cluster": "station_beta",
    "size": 5,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {"pressure_kpa": 99.0, "radiation_msv": 1.0, "temperature_c": 22},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hatch_dock_fuel": {
        "id": "hatch_dock_fuel",
        "glyph": "◆",
        "name": "Dock Ring Hatch",
        "state": "open",
        "required_tag": null,
        "grants_edge": "to_dock",
        "on_use_effect": null,
        "description": "Blast door back to Dock Ring."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "hatch_dock_fuel", "row": 4, "col": 2}
    ],
    "edges": {
      "to_dock": {
        "id": "to_dock",
        "target_node_id": "stn_b_dock",
        "label": "Dock Ring",
        "gated_by_fixture": null,
        "requires_capability": null
      }
    },
    "description": "Processing bay with pressurized fuel lines running floor to ceiling. Warning placards on every surface."
  },
  {
    "id": "luna_pad",
    "name": "Lunar Surface Pad",
    "cluster": "lunar_base",
    "size": 7,
    "depth": 0,
    "environment": "vacuum",
    "base_vitals": {"pressure_kpa": 0.0, "radiation_msv": 25.0, "temperature_c": -80},
    "grid_floor": "~",
    "grid_wall": "░",
    "fixtures": {
      "lander_hatch": {
        "id": "lander_hatch",
        "glyph": "▲",
        "name": "Lander Ascent Hatch",
        "state": "open",
        "required_tag": null,
        "grants_edge": "to_shuttle",
        "on_use_effect": null,
        "description": "Ascent module hatch back to the shuttle."
      },
      "dome_airlock": {
        "id": "dome_airlock",
        "glyph": "=",
        "name": "Habitat Dome Airlock",
        "state": "open",
        "required_tag": null,
        "grants_edge": "to_dome",
        "on_use_effect": null,
        "description": "Reinforced airlock cylinder leading into the pressurized dome."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "lander_hatch", "row": 0, "col": 3},
      {"entity_id": "dome_airlock", "row": 6, "col": 3}
    ],
    "edges": {
      "to_shuttle": {
        "id": "to_shuttle",
        "target_node_id": "shuttle_ab",
        "label": "Shuttle (Ascent)",
        "gated_by_fixture": null,
        "requires_capability": "vacuum_traverse"
      },
      "to_dome": {
        "id": "to_dome",
        "target_node_id": "luna_dome",
        "label": "Habitat Dome",
        "gated_by_fixture": null,
        "requires_capability": "vacuum_traverse"
      }
    },
    "description": "Flat regolith landing apron under unfiltered starlight. Boot prints fade into gray dust. Silence."
  },
  {
    "id": "luna_dome",
    "name": "Habitat Dome - Central Bay",
    "cluster": "lunar_base",
    "size": 7,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {"pressure_kpa": 95.0, "radiation_msv": 3.0, "temperature_c": 17},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "airlock_pad": {
        "id": "airlock_pad",
        "glyph": "=",
        "name": "Surface Pad Airlock",
        "state": "open",
        "required_tag": null,
        "grants_edge": "to_pad",
        "on_use_effect": null,
        "description": "Airlock back to the open surface pad."
      },
      "hatch_smelter": {
        "id": "hatch_smelter",
        "glyph": "◆",
        "name": "Smelter Corridor",
        "state": "open",
        "required_tag": null,
        "grants_edge": "to_smelter",
        "on_use_effect": null,
        "description": "Heated corridor leading to the smelting facility."
      },
      "hatch_crater": {
        "id": "hatch_crater",
        "glyph": "▲",
        "name": "Crater Rim Access",
        "state": "sealed",
        "required_tag": "heavy_duty",
        "grants_edge": "to_crater",
        "on_use_effect": "unlock",
        "description": "Heavy exterior hatch to the crater rim observation path."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "airlock_pad", "row": 0, "col": 3},
      {"entity_id": "hatch_smelter", "row": 3, "col": 0},
      {"entity_id": "hatch_crater", "row": 3, "col": 6}
    ],
    "edges": {
      "to_pad": {
        "id": "to_pad",
        "target_node_id": "luna_pad",
        "label": "Surface Pad",
        "gated_by_fixture": null,
        "requires_capability": null
      },
      "to_smelter": {
        "id": "to_smelter",
        "target_node_id": "luna_smelter",
        "label": "Smelter Flat",
        "gated_by_fixture": null,
        "requires_capability": null
      },
      "to_crater": {
        "id": "to_crater",
        "target_node_id": "luna_crater",
        "label": "Crater Rim",
        "gated_by_fixture": "hatch_crater",
        "requires_capability": null
      }
    },
    "description": "Geodesic dome interior with hydroponic trays and water recyclers. Artificial daylight panels overhead."
  },
  {
    "id": "luna_smelter",
    "name": "Smelter Flat - Processing Floor",
    "cluster": "lunar_base",
    "size": 6,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {"pressure_kpa": 93.0, "radiation_msv": 5.0, "temperature_c": 35},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hatch_dome_smelter": {
        "id": "hatch_dome_smelter",
        "glyph": "◆",
        "name": "Dome Corridor",
        "state": "open",
        "required_tag": null,
        "grants_edge": "to_dome",
        "on_use_effect": null,
        "description": "Corridor back to the habitat dome."
      },
      "mine_shaft": {
        "id": "mine_shaft",
        "glyph": "⎅",
        "name": "Mine Shaft Cage",
        "state": "locked",
        "required_tag": "two_person_lift",
        "grants_edge": "to_mine",
        "on_use_effect": "unlock",
        "description": "Two-person cage lift descending into the deep mine. Requires two operators."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "hatch_dome_smelter", "row": 0, "col": 3},
      {"entity_id": "mine_shaft", "row": 5, "col": 3}
    ],
    "edges": {
      "to_dome": {
        "id": "to_dome",
        "target_node_id": "luna_dome",
        "label": "Habitat Dome",
        "gated_by_fixture": null,
        "requires_capability": null
      },
      "to_mine": {
        "id": "to_mine",
        "target_node_id": "luna_mine",
        "label": "Deep Mine",
        "gated_by_fixture": "mine_shaft",
        "requires_capability": null
      }
    },
    "description": "Industrial floor vibrating with furnace resonance. Ore dust coats every surface. Heat radiates from smelting crucibles."
  },
  {
    "id": "luna_crater",
    "name": "Crater Rim - Observation Path",
    "cluster": "lunar_base",
    "size": 6,
    "depth": 0,
    "environment": "vacuum",
    "base_vitals": {"pressure_kpa": 0.0, "radiation_msv": 30.0, "temperature_c": -120},
    "grid_floor": "~",
    "grid_wall": "░",
    "fixtures": {
      "hatch_dome_crater": {
        "id": "hatch_dome_crater",
        "glyph": "◆",
        "name": "Dome Access",
        "state": "open",
        "required_tag": null,
        "grants_edge": "to_dome",
        "on_use_effect": null,
        "description": "Hatch back to the habitat dome."
      },
      "tube_entrance": {
        "id": "tube_entrance",
        "glyph": "⎅",
        "name": "Lava Tube Descent",
        "state": "sealed",
        "required_tag": "force_lever",
        "grants_edge": "to_tube",
        "on_use_effect": "unlock",
        "description": "Bolted hatch covering a natural lava tube opening. Pry marks around the rim."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "hatch_dome_crater", "row": 0, "col": 3},
      {"entity_id": "tube_entrance", "row": 5, "col": 3}
    ],
    "edges": {
      "to_dome": {
        "id": "to_dome",
        "target_node_id": "luna_dome",
        "label": "Habitat Dome",
        "gated_by_fixture": null,
        "requires_capability": "vacuum_traverse"
      },
      "to_tube": {
        "id": "to_tube",
        "target_node_id": "luna_tube",
        "label": "Lava Tube",
        "gated_by_fixture": "tube_entrance",
        "requires_capability": null
      }
    },
    "description": "Narrow path carved into the crater wall. Earth hangs above the horizon line. No sound at all."
  },
  {
    "id": "luna_mine",
    "name": "Deep Mine - Primary Shaft",
    "cluster": "lunar_base",
    "size": 5,
    "depth": 1,
    "environment": "depressurizing",
    "base_vitals": {"pressure_kpa": 50.0, "radiation_msv": 15.0, "temperature_c": -30},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "cage_up": {
        "id": "cage_up",
        "glyph": "⎅",
        "name": "Mine Cage (Up)",
        "state": "open",
        "required_tag": null,
        "grants_edge": "to_smelter",
        "on_use_effect": null,
        "description": "Cage lift back to the smelter floor."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "cage_up", "row": 0, "col": 2}
    ],
    "edges": {
      "to_smelter": {
        "id": "to_smelter",
        "target_node_id": "luna_smelter",
        "label": "Smelter Flat (Up)",
        "gated_by_fixture": null,
        "requires_capability": null
      }
    },
    "description": "Rough-hewn shaft descending into basalt. Drill marks line the walls. Cold seeps from the rock."
  },
  {
    "id": "luna_tube",
    "name": "Lava Tube - Natural Chamber",
    "cluster": "lunar_base",
    "size": 6,
    "depth": 1,
    "environment": "low_temp",
    "base_vitals": {"pressure_kpa": 40.0, "radiation_msv": 8.0, "temperature_c": -45},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "ascent_hatch": {
        "id": "ascent_hatch",
        "glyph": "⎅",
        "name": "Crater Rim Ascent",
        "state": "open",
        "required_tag": null,
        "grants_edge": "to_crater",
        "on_use_effect": null,
        "description": "Ladder and hatch back up to the crater rim."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "ascent_hatch", "row": 0, "col": 3}
    ],
    "edges": {
      "to_crater": {
        "id": "to_crater",
        "target_node_id": "luna_crater",
        "label": "Crater Rim (Up)",
        "gated_by_fixture": null,
        "requires_capability": null
      }
    },
    "description": "Vast natural tube of frozen basalt. The ceiling vanishes into darkness. Something drips in the distance."
  }
]
```

### 9.3 Companions (`companions.json`)

```json
[
  {
    "id": "comp_radek",
    "name": "Radek",
    "title": "Cargo Rigger",
    "status": "Ready to work",
    "capability_tag": "two_person_lift"
  }
]
```

### 9.4 Progression Tree (`tree.json`)

```json
[
  {
    "id": "seam_discipline",
    "name": "Seam Discipline",
    "description": "Inspect sealed fixtures to reveal leak state and required tool tags.",
    "prerequisite": null,
    "unlock_condition": "use_fixture",
    "unlock_parameter": "spigot_01",
    "attuned": false
  },
  {
    "id": "bulkhead_ear",
    "name": "Bulkhead Ear",
    "description": "Inspect sealed edge fixtures to reveal destination pressure before opening.",
    "prerequisite": "seam_discipline",
    "unlock_condition": "visit_node",
    "unlock_parameter": "stn_a_sub",
    "attuned": false
  },
  {
    "id": "cold_bypass",
    "name": "Cold-Line Bypass",
    "description": "Halves temperature exposure accumulation rate.",
    "prerequisite": null,
    "unlock_condition": "survive_depth",
    "unlock_parameter": "1",
    "attuned": false
  },
  {
    "id": "vacuum_walk",
    "name": "Vacuum Walk",
    "description": "Halves pressure exposure accumulation. Grants vacuum_traverse capability.",
    "prerequisite": "cold_bypass",
    "unlock_condition": "complete_trade",
    "unlock_parameter": "npc_kael",
    "attuned": false
  },
  {
    "id": "deep_well",
    "name": "Deep-Well Attunement",
    "description": "Halves radiation exposure accumulation rate.",
    "prerequisite": "bulkhead_ear",
    "unlock_condition": "survive_depth",
    "unlock_parameter": "2",
    "attuned": false
  },
  {
    "id": "trench_hardened",
    "name": "Trench Hardened",
    "description": "All exposure thresholds increased by 5.0 (stressed at 10, critical at 15, incapacitated at 20).",
    "prerequisite": "vacuum_walk",
    "unlock_condition": "visit_node",
    "unlock_parameter": "luna_mine",
    "attuned": false
  }
]
```

---

## 10. Grid Rendering Algorithm

The renderer constructs the N×N grid dynamically from node data rather than storing pre-baked row strings:

```python
def build_grid(node: Node, player_row: int, player_col: int) -> Tuple[str, ...]:
    """Construct N×N grid rows from node walls, floor, and placements."""
    n = node.size
    # Initialize grid with floor tiles
    grid = [[node.grid_floor] * n for _ in range(n)]

    # Set border walls (row 0, row n-1, col 0, col n-1)
    for r in range(n):
        for c in range(n):
            if r == 0 or r == n - 1 or c == 0 or c == n - 1:
                grid[r][c] = node.grid_wall

    # Place fixtures and actors by their GridPlacement coordinates
    for placement in node.placements:
        entity = node.fixtures.get(placement.entity_id) or \
                 node.actors.get(placement.entity_id)
        if entity:
            grid[placement.row][placement.col] = entity.glyph

    # Overlay player cursor (@) on floor; invert entity glyph color on overlap
    cell = grid[player_row][player_col]
    if cell == node.grid_floor:
        grid[player_row][player_col] = '@'
    else:
        grid[player_row][player_col] = f"\033[7m{cell}\033[0m"

    # Convert to display strings
    return tuple(' '.join(row) for row in grid)
```

**This resolves the original glyph-collision problem:** Multiple fixtures can share the same glyph character (e.g., two `=` hatches) because they are addressed by their unique `entity_id`, not by their glyph. The glyph is purely a display character. The legend in Zone 4 maps each placed glyph to its fixture/actor `[id]`, which the player uses in commands.

---

## 11. Agent Bootstrapping Directives

When an LLM agent implements or refactors this repository, it must adhere to this phased pipeline. Each phase has explicit acceptance criteria.

### Phase 1: Domain Typing (`core/types.py`)

**Task:** Implement all NamedTuples, Enums, and type aliases from §3.

**Acceptance Criteria:**
- All structures use `typing.NamedTuple`. No `@dataclass`, no `class` inheritance.
- All enums use `enum.Enum`.
- Zero mutable attributes. All collections are `Tuple`, `FrozenSet`, or `Mapping`.
- Module imports only from the standard library.
- File contains no function definitions, only type declarations.

### Phase 2: Preset Bootstrapping (`core/presets.py`)

**Task:** Implement the preset cloner and JSON deserializer.

**Acceptance Criteria:**
- If `presets/default-1.0/` does not exist, create it and write all JSON files from hardcoded dict literals.
- Pure functions parse each JSON file into the corresponding typed structures: `load_items(path) -> Tuple[Item, ...]`, `load_nodes(path) -> Mapping[str, Node]`, `load_companions(path) -> Tuple[Companion, ...]`, `load_tree(path) -> Tuple[TreeNode, ...]`.
- The deserialization functions validate required fields and raise `ValueError` with descriptive messages on schema violations.
- Constructs a complete initial `GameState` from loaded presets + character creation data.

### Phase 3: Pure State Reducers (`core/reducers.py`)

**Task:** Implement one pure function per verb/action from §5.4.

**Function Signatures:**
```python
def reduce_move(state: GameState, direction: str) -> GameState          # direction: "w"|"a"|"s"|"d"
def reduce_interact_go(state: GameState) -> GameState                   # traverse edge at cursor tile
def reduce_inspect(state: GameState, target_id: str) -> GameState
def reduce_talk(state: GameState, actor_id: str) -> GameState
def reduce_use(state: GameState, item_id: str, fixture_id: str) -> GameState
def reduce_wait(state: GameState) -> GameState
# Non-tick commands:
def reduce_map(state: GameState) -> GameState
def reduce_back(state: GameState) -> GameState
def reduce_pack(state: GameState) -> GameState
def reduce_character(state: GameState) -> GameState
def reduce_party(state: GameState) -> GameState
def reduce_log(state: GameState) -> GameState
def reduce_flavor(state: GameState, toggle: str) -> GameState
def reduce_help(state: GameState) -> GameState
```

**Acceptance Criteria:**
- Every reducer is a pure function: `GameState -> GameState`. No I/O, no globals, no side effects.
- State updates use `state._replace(...)` and construct fresh immutable tuples/mappings.
- `reduce_move`: clamps to grid bounds; blocked by wall tiles (border cells). On landing on an entity tile, sets `proximity_menu_active = True` and populates `message_buffer` with the menu options (§5.2). Advances tick.
- `reduce_interact_go`: looks up the entity at `(player_row, player_col)`, finds its open `grants_edge`, checks capability, transitions `current_node_id`, resets `player_row`/`player_col` to grid centre of new node, advances tick.
- Tick-advancing reducers (`reduce_move`, `reduce_interact_go`, `reduce_talk`, `reduce_use`, `reduce_wait`) call the tick processor from `core/tick.py` before returning.
- The trade protocol (§5.5) is implemented inside `reduce_talk`.
- The fixture use effect table (§5.6) is implemented inside `reduce_use`.
- All error cases append descriptive messages to `message_buffer` and return state without advancing the tick.
- Attunement checks (§8.1) are evaluated inside the tick processor.

### Phase 4: Tick Processor (`core/tick.py`)

**Task:** Implement the tick processing pipeline from §5.7.

**Function Signature:**
```python
def process_tick(state: GameState, action_summary: str) -> GameState
```

**Acceptance Criteria:**
- Implements all 6 steps from §5.7 in order.
- Exposure formulas match §4.3 exactly.
- Attunement mitigation checks reference `unlocked_capabilities`.
- Sustenance decay triggers every 10 cycles.
- Action log maintains max 20 entries.
- Returns a new GameState; the input is not modified.

### Phase 5: Viewport & Presentation (`ui/render.py`, `ui/topology_view.py`)

**Task:** Implement the 6-zone renderer and topology map view.

**Acceptance Criteria:**
- `render_frame(state: GameState, terminal_width: int) -> str` returns a complete frame string.
- Dynamic zone width calculation per §6.2.
- Grid is built via the algorithm in §10; player `@` is overlaid at `(player_row, player_col)` unless that cell holds an entity glyph.
- Zone 4 legend entries show `[id]` suffix for typed command targeting.
- Zone 5 renders proximity menu when `state.proximity_menu_active`, otherwise renders `message_buffer` (max 6 lines).
- Zone 6 renders `WASD: move  /: cmd  M: map  Q: quit` during raw keystroke mode; switches to `/ ` prompt when slash command entry is initiated.
- `render_topology(state: GameState, terminal_width: int) -> str` renders the map view per §6.4.
- Terminal width < 40 emits a resize warning string instead of the frame.
- `ui/text_tools.py` provides `wrap_text(text: str, width: int) -> Tuple[str, ...]`, `check_terminal() -> int`, `clear_terminal() -> None`, and `read_raw_key() -> str` (uses `tty`/`termios` to return a single character without blocking on Enter).

### Phase 6: Atomic Persistence (`core/persistence.py`)

**Task:** Implement save/load for GameState.

**Acceptance Criteria:**
- `save_state(state: GameState, save_dir: Path) -> None` writes to `saves/<name>/state.json` atomically (write to temp file, then rename).
- `load_state(save_dir: Path, presets: ...) -> Optional[GameState]` returns `None` if no save exists.
- Serialization handles all NamedTuple nesting, Enums, FrozenSets, and Mappings, including the new `player_row`, `player_col`, and `proximity_menu_active` fields.
- Save occurs after every tick-advancing action.

### Phase 7: Input Runner (`main.py`)

**Task:** Implement the top-level raw-keystroke I/O loop.

**Acceptance Criteria:**
- On startup: check for existing save. If found, load it. If not, run character creation (§7). Character creation uses conventional `input()` prompts.
- Clone presets if missing (Phase 2).
- Main loop (raw keystroke mode):
  1. `clear_terminal()` — clear terminal screen before rendering.
  2. `print(render_frame(state))` — emit the full frame.
  3. `key = read_raw_key()` — read a single character without blocking on Enter.
  4. If `key` is `w`/`a`/`s`/`d`: dispatch `reduce_move`.
  5. If `state.proximity_menu_active` and `key` is `i`/`u`/`g`/`t`/`x`: dispatch the corresponding proximity action reducer.
  6. If `key` is `m`/`b`/`e`: dispatch matching shortcut.
  7. If `key` is `/`: initiate command entry via `input("\n/ ")`, tokenize (stripping leading slash), dispatch to matching reducer.
  8. All other raw input is consumed silently without opening a prompt.
  9. Reduce → persist if ticked → loop.
- `KeyboardInterrupt` and `EOFError` trigger clean save and exit.
- `q` / `quit` saves and exits.
- The loop is the **only** place with I/O side effects (`print`, `input`, `read_raw_key`, `clear_terminal`, file writes). All other modules are pure.


---

## 12. Scope Boundaries & Deferred Features

The following are explicitly **out of scope** for v1.0 and must not be implemented:

- **Combat system:** No attack verbs, no enemy AI, no hit points for actors.
- **Procedural generation:** All nodes, items, and actors are preset-authored. No random generation.
- **Crafting:** No item combination or synthesis mechanics.
- **Multiple save slots:** One save per character name.
- **ANSI colors or formatting:** Pure unformatted text output.
- **Companion dismissal or death:** Companions are permanent once acquired.
- **Dynamic actor movement:** Actors remain at their placed grid positions permanently.
- **Sound or multimedia:** Text-only interface.