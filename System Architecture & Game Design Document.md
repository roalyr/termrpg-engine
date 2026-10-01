# SYSTEM BOOTSTRAP GDD: HARD SCI-FI FUNCTIONAL CLI RPG

> **Obsolete: kept only as a description of the old engine.** The game's direction is
> in [VISION.md](VISION.md), the content format in [README.md](README.md), and the
> rebuild plan in [ROADMAP.md](ROADMAP.md). Parts of this document are removed as the
> new engine replaces them; it is deleted at version 1.0. Don't use it for new work.

---

## 1. Executive Summary & Core Design Tenets

This document specifies the technical architecture, mechanical contracts, domain models, and UX presentation for a minimalist, text-driven open-world RPG built in pure Python 3. The system is designed for execution in constrained terminal environments (e.g., mobile Termux shells) and optimized for ingestion and iterative implementation by autonomous LLM agents.

### Core Tenets

1. **Zero External Dependencies:** Built strictly on the Python 3 standard library (`pathlib`, `typing`, `json`, `os`, `sys`, `enum`, `tty`, `termios`). No third-party packages, no external build steps.
2. **Pure Functional Unidirectional Dataflow:** State is strictly immutable (`typing.NamedTuple`). State transitions are executed exclusively via pure reducers: `Action × State → State'`. No OOP classes with mutable attributes, no internal side effects, no hidden object state.
3. **Non-Blocking Raw Input Interface:** The input loop reads single raw keystrokes via `tty`/`termios` without requiring Enter. WASD keys navigate the player cursor on the Zone 2 minimap. All arbitrary input is consumed; typed commands are explicitly initiated with a leading slash `/` (`/command`). The terminal screen is cleared prior to each render cycle to provide a persistent, flicker-free viewport.
4. **Grounded Hard Sci-Fi Space Opera & Living World:** Everyday lived reality of commoners, orbital technicians, shift workers, and dock hands across orbital platforms, habitat rings, agricultural domes, and low-gravity stellar bodies (moons, asteroids). Deep gravity-well planets with punishing escape velocities are excluded. Physical space hazards (vacuum, pressure differentials, cryogenic cold, ionizing radiation) govern survival. Language is direct, utilitarian, and dry; technobabble, fantasy tropes, and cyberpunk cliches are prohibited.
5. **Open-World Emergence & Lateral Agency:** The game world is an open spatial web, not a linear quest funnel. Players possess genuine freedom to explore all 14 nodes across 4 clusters, choose their own survival priorities, and solve challenges through diverse disciplines: technical engineering, environmental resilience, or logistics and crew coordination. Artificial choke-points and single-key locks are replaced with multiple traversal pathways (service ducts, crawlways, mechanical overrides, companion aid) and realistic environmental gating.
6. **Work, Routine and Levels:** Progress comes from doing the job. Three work skills (Engineering, Survival, Logistics) level from 1 to 5 on experience earned by the matching work, and each level brings a concrete perk. Days follow a routine: shifts, fatigue, sleep, daily jobs, and stock that refills overnight, so repeating honest work (grinding) is a valid way to get stronger. Numbers stay small and every bonus is stated in plain words. Combat is postponed: the world is small and the threat is the environment.

---

## 2. Technical Stack & Architectural Invariants

### 2.1 Runtime & Environment

* **Platform:** Python 3.10+ Standard Library.
* **Terminal Constraints:** Designed for viewport widths >= 40 columns. The engine reads terminal width once per render via `os.get_terminal_size()`. If columns < 40, the engine suspends rendering and emits a resize warning to stdout.
* **Persistence:** Deterministic auto-save after every tick-advancing action into `saves/<character_name>/state.json`. Saves are self-contained (world, item catalogue, companion catalogue) and carry `schema_version`; v1 saves are upgraded on load without losing progress. Restored games always resume with `is_running = True`.
* **Preset Cloning & Modding:** The canonical default preset ships in `core/data/default-1.0/` (JSON only; there are no Python copies). Missing files are cloned on startup into the runtime folder `presets/default-1.0/`, which players may edit. A new game reads items, companions, nodes and the tree exclusively from the active preset folder, enabling clean resets and total-conversion modding.

### 2.2 System Architecture Overview

```
                  +-------------------------------+
                  | Raw Keystroke / Typed Command |
                  | (tty/termios, no Enter needed)|
                  +---------------+---------------+
                                  |
          +-------------+---------+----------+
          |  WASD key   |   Proximity key    |  Typed cmd (/...)
          |  (move)     |   (i, u, g, t, s)  |  (/inspect, /pack …)
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
├── core/                           # Pure functional domain layer
│   ├── __init__.py
│   ├── types.py                    # Domain models, Enums, NamedTuples
│   ├── rules.py                    # Shared rules: requirement resolution, wear, exposure thresholds
│   ├── codec.py                    # JSON <-> domain conversion for presets and saves
│   ├── actions.py                  # Action definitions & tokenization dispatcher
│   ├── reducers.py                 # Pure reducer functions (Action x State -> State)
│   ├── tick.py                     # Tick processing pipeline (exposure, decay, experience, jobs, fatigue)
│   ├── routine.py                  # Work skills, daily jobs, fatigue and the day cycle
│   ├── persistence.py              # Save / Load serialization and v1 save migration
│   ├── presets.py                  # Preset cloning and loaders
│   └── data/default-1.0/           # Canonical default preset (items, nodes, companions, skills, jobs)
│
├── ui/                             # Pure presentation layer (string output)
│   ├── __init__.py
│   ├── render.py                   # 6-zone viewport assembler
│   ├── text_tools.py               # Raw input, ANSI clearing, visible length math
│   └── topology_view.py            # ASCII node map renderer
│
├── presets/                        # Runtime preset copies, cloned from core/data (git-ignored)
│   └── default-1.0/
│       ├── items.json              # Item definitions, tags, integrities
│       ├── nodes.json              # Full 14-node world topology, fixtures, actors
│       ├── companions.json         # Recruitable crew members & capabilities
│       ├── skills.json             # Work skills, level thresholds and perks
│       └── jobs.json               # Daily job templates
│
├── saves/                          # Persistent runtime save files (git-ignored)
│   └── <character_name>/
│       └── state.json
│
├── tests/                          # Automated unit and E2E test suite
│   ├── test_types.py
│   ├── test_presets.py
│   ├── test_reducers.py
│   ├── test_tick.py
│   ├── test_persistence.py
│   ├── test_ui.py
│   ├── test_e2e.py
│   ├── test_open_world.py
│   └── test_rules_and_mechanics.py # Regression, solvability and save-migration checks
│
├── main.py                         # Non-blocking input loop & runtime entry point
└── System Architecture & Game Design Document.md
```

---

## 3. Data Schema & Domain Models (`core/types.py`)

### 3.1 Enumerations

```python
class ItemCategory(Enum):
    CREDENTIAL = "credential"  # Passes, tokens, identity manifests
    UTILITY = "utility"        # Tools, repair components, wiring, prybars
    SUSTENANCE = "sustenance"  # Water, rations, biomass, emergency medical packs
    RECORD = "record"          # Data slates, dice, personal journals, charts
    MATERIAL = "material"      # Raw ore, scrap metal, refined components

class FixtureState(Enum):
    SEALED = "sealed"       # Closed, requires tool/tag or manual override
    OPEN = "open"           # Passable / accessible without restriction
    LOCKED = "locked"       # Keyed or credential-gated hatch/container
    ACTIVE = "active"       # Functional mechanism (spigots, vats, crucibles)
    SPENT = "spent"         # Exhausted resource node or scavenged container
    DISABLED = "disabled"   # Damaged machinery requiring repair or bypass

class Environment(Enum):
    PRESSURIZED = "pressurized"        # Nominal atmosphere (101.3 kPa, 20°C)
    DEPRESSURIZING = "depressurizing"  # Partial air loss, cold, failing scrubbers
    VACUUM = "vacuum"                  # Complete absence of pressure (0.0 kPa)
    HIGH_RAD = "high_rad"              # Dangerous radiation field (>15 mSv)
    LOW_TEMP = "low_temp"              # Cryogenic conditions (<-40°C)

class ExposureType(Enum):
    PRESSURE = "pressure"      # Decompression debt
    RADIATION = "radiation"    # Ionizing dose
    TEMPERATURE = "temperature"# Hypothermic / thermal stress
```

### 3.2 Core Domain Structures

```python
class Item(NamedTuple):
    id: str                    # Unique identifier (e.g. "tool_prybar")
    name: str                  # Display name
    category: str              # ItemCategory value
    tags: Tuple[str, ...]      # Functional tags (e.g. ("force_lever", "heavy_duty"))
    integrity: int             # Current condition / remaining charges
    max_integrity: int         # 0 = does not wear; >0 = degrades with use
    description: str           # Utility-focused hard sci-fi description

class NodeVitals(NamedTuple):
    pressure_kpa: float        # Atmospheric pressure (101.3 nominal, 0.0 vacuum)
    radiation_msv: float       # Ambient radiation field
    temperature_c: int         # Ambient temperature in Celsius

class Fixture(NamedTuple):
    id: str                    # Unique fixture identifier (e.g. "salvage_bin")
    glyph: str                 # Single glyph rendered on minimap
    name: str                  # Display name
    state: str                 # FixtureState value
    required_tags: Tuple[str, ...]  # Any ONE of these tags satisfies the fixture (empty = none)
    grants_edge: Optional[str] # Edge ID in node.edges that this fixture gates
    on_use_effect: Optional[str]# "unlock", "refill", "repair", "scavenge", "harvest", "smelt", "override", "log"
    description: str           # Physical description with interactive clues
    yields: Tuple[str, ...] = ()            # Items granted by "scavenge" / "harvest"
    log_text: Optional[str] = None          # Text shown by "log" fixtures
    log_text_locked: Optional[str] = None   # Extra text for readers with signal_analysis / signal_boost / lore
    opens_fixture: Optional[str] = None     # "override": fixture in the same node set to OPEN
    grants_capability: Optional[str] = None # "override": capability added to the player
    on_repair_vitals: Optional[NodeVitals] = None  # "repair": node vitals after the repair
    reseal_on_pass: bool = False            # Gate closes again after the player passes through
    restock: bool = False                   # Container or harvest spot refills at dawn

class Actor(NamedTuple):
    id: str                    # Unique actor identifier (e.g. "npc_mira")
    glyph: str                 # Single glyph rendered on minimap
    name: str                  # Display name
    title: str                 # Profession / role (e.g. "Hab Botanist")
    status: str                # Current observational activity
    trade_offered_id: Optional[str]    # Item offered in primary exchange
    trade_required_tags: Tuple[str, ...]  # Any carried item with one of these tags is accepted
    trade_completed: bool              # Whether primary trade fulfilled
    dialogue_idle: str                 # Initial ambient dialogue & rumors
    dialogue_post_trade: Optional[str] # Follow-up dialogue acknowledging changes
    companion_unlock: Optional[str]    # Companion ID recruited on alliance
    dialogue_variants: Tuple[Tuple[str, str], ...] = ()  # (condition, text); first match replaces dialogue_idle
                                       # conditions: "past_work:<id>", "visited:<node>", "party:<companion>", "has_cap:<cap>"

class GridPlacement(NamedTuple):
    entity_id: str             # Fixture or Actor ID
    row: int                   # 0-indexed row on the grid
    col: int                   # 0-indexed column on the grid

class Edge(NamedTuple):
    id: str                    # Edge identifier (e.g. "to_subdeck")
    target_node_id: str        # Destination node ID
    label: str                 # Display label (e.g. "Sub-Deck Conduits")
    gated_by_fixture: Optional[str]  # Fixture that must be OPEN to traverse
    requires_capability: Optional[str]# Capability tag player must possess

class Node(NamedTuple):
    id: str                    # Unique node ID
    name: str                  # Display name
    cluster: str               # Cluster grouping ("station_alpha", "transit", etc.)
    size: int                  # Grid dimension N (N x N, where N <= 10)
    depth: int                 # Vertical depth (0 = surface/concourse, 1+ = subterranean)
    environment: str           # Environment enum value
    base_vitals: NodeVitals    # Current sensor readings (changed by repairs)
    grid_floor: str            # Empty floor glyph (e.g. "·", "~")
    grid_wall: str             # Border wall glyph (e.g. "░", "█")
    fixtures: Mapping[str, Fixture]       # Fixtures keyed by ID
    actors: Mapping[str, Actor]           # Actors keyed by ID
    placements: Tuple[GridPlacement, ...] # Entity coordinates
    edges: Mapping[str, Edge]             # Adjacency edges
    description: str                      # Concise sensory prose
```

### 3.3 Player, Companion & Progression Structures

```python
class Companion(NamedTuple):
    id: str                    # Unique companion ID (e.g. "comp_radek")
    name: str                  # Display name
    title: str                 # Role (e.g. "Cargo Rigger")
    status: str                # Current status
    capability_tag: Optional[str]  # Contributed team tag ("two_person_lift", "signal_boost")

class Exposure(NamedTuple):
    pressure_debt: float       # Decompression stress (0.0 = clean)
    radiation_dose: float      # Accumulated dose (0.0 = clean)
    thermal_stress: float      # Cold/heat accumulation (0.0 = comfortable)

class PlayerCharacter(NamedTuple):
    name: str                  # Character callsign
    past_work: str             # Background routine ("seam_scraper", "algae_tender", "cargo_handler")
    personal_anchor: Item      # Starting keepsake item
    inventory: Tuple[Item, ...] # Carried items
    unlocked_capabilities: FrozenSet[str]  # Earned capabilities and clearances
    exposure: Exposure         # Environmental damage record

class Perk(NamedTuple):
    level: int                 # Skill level that grants this perk
    xp: int                    # Experience needed to reach that level
    grants: str                # Capability tag added to the player
    text: str                  # Plain description shown to the player

class Skill(NamedTuple):
    id: str                    # "engineering", "survival", "logistics"
    name: str
    earned_by: str             # How experience is earned (character panel)
    perks: Tuple[Perk, ...]    # One per level from 2 upward

class Job(NamedTuple):
    id: str
    title: str
    kind: str                  # "use" a fixture, "deliver" items to a room, "stay" turns in a room
    target: str                # Fixture ID ("use") or node ID ("deliver", "stay")
    skill: str                 # Skill that earns the experience
    xp: int
    reward_items: Tuple[str, ...] = ()
    item: Optional[str] = None # "deliver": item handed over
    count: int = 1             # "deliver": items needed; "stay": turns needed
    progress: int = 0
    done: bool = False

class GameState(NamedTuple):
    character: PlayerCharacter
    current_node_id: str
    nodes: Mapping[str, Node]
    companions: Tuple[Companion, ...]
    visited_nodes: FrozenSet[str]
    cycle: int
    player_row: int
    player_col: int
    message_buffer: Tuple[str, ...]
    action_log: Tuple[str, ...]
    flavor_enabled: bool
    active_view: str                  # "compartment" or "map_topology"
    proximity_menu_active: bool       # True when Zone 5 presents proximity options
    is_running: bool
    item_catalog: Mapping[str, Item]            # Item definitions from the active preset
    companion_catalog: Mapping[str, Companion]  # Companion definitions from the active preset
    color_enabled: bool                         # Styles and the orange accent (/color)
    skills: Mapping[str, int]                   # Experience per skill ID
    skill_catalog: Tuple[Skill, ...]            # Skill and perk definitions from the active preset
    job_catalog: Tuple[Job, ...]                # Job templates from the active preset
    jobs: Tuple[Job, ...]                       # Today's jobs with progress
    day: int                                    # Advances when the player sleeps
    woke_at: int                                # Cycle when the player last woke (fatigue clock)
```

---

## 4. World Graph Topology & Progressive Spatial Scaling

### 4.1 Open World Graph Topology

The game world is a multi-path, non-linear spatial graph representing 14 functional compartments across 4 interconnected clusters. Rather than forcing the player down a single quest sequence, nodes offer multiple entry and exit points, maintenance ducts, and bypass routes:

```
WORLD TOPOLOGY (MULTI-PATH ADJACENCY GRAPH):

[Station Alpha: Habitation & Transit Hub]
   Shared Bunkroom (stn_a_bunkroom) <══════> Hab Ring Gallery (stn_a_hab)
        │                 \ (service vent)        │
        │ (transit hatch)  \                      │ (corridor hatch)
        v                   v                     v
   Berth 04 Platform (stn_a_berth) <══════════════╝
        │                      \ (conduit bypass)
        │ (cargo hoist)         v
   Sub-Deck Conduits (stn_a_sub) [D:1 Depressurizing]
        │
   <Shuttle Hopper> (shuttle_ab) [Inter-Station Orbital Transit]
     /              \
    / (orbital burn) \ (station transfer)
   v                  v
[Lunar Base: Surface & Depths]          [Station Beta: Industrial & Comms]
   Surface Pad (luna_pad) [Vacuum]         Dock Ring Bay 7 (stn_b_dock)
      │                                      │           │
   Habitat Dome (luna_dome) [Pressurized]  Array Hub   Fuel Spur
     /          \                          (stn_b_array) (stn_b_fuel)
    /            \
Smelter Flat   Crater Rim (luna_crater) [Vacuum]
(luna_smelter)     │
    ║              ║ (lava tube descent)
Deep Mine      Lava Tube (luna_tube) [D:1 Basalt Cavern]
(luna_mine) [D:1]
```

#### Multi-Path Traversal & Anti-Linear Bypass Design
Fixtures take an any-of list (`required_tags`), and every lock below has at least two answers. A static solvability test checks that all 12 starts (4 anchors x 3 routines) can reach all 14 nodes and recruit all 3 companions.
1. **Sub-Deck Access (Station Alpha):**
   - *Cargo Hoist* from Berth 04: `dock_clearance` | `force_lever` | `heavy_lift` | `two_person_lift`. A forged clearance from the Station Beta crypto terminal also counts.
   - *Service Crawlway* from the Bunkroom: `seal_fitting` | `wrench`.
2. **Shuttle Boarding (Berth 04).** The boarding gate reseals after every crossing:
   - *Route A:* present `transit_clearance` (a Shuttle Token is spent per boarding; Deep Traveler waives the fare).
   - *Route B:* re-seat the Docking Collar with `wrench` | `seal_fitting` to cycle the gate open once.
   - *Route C:* release the Cargo Clamps (`force_lever` | `heavy_lift` | `two_person_lift`) and stow away in the shuttle hold. Repeatable; the clamps relock behind you.
3. **Station Beta Access:**
   - Unlocked via shuttle transfer. The Dock Ring grants immediate access to the Comms Array Hub and Fuel Processing Spur.
4. **Lunar Surface & Subterranean Depths:**
   - The shuttle lands on `luna_pad`. Because the surface is unpressurized vacuum, traversal is gated by **environmental survival and preparation** rather than locked doors. Players can make a dash across the regolith into the pressurized `luna_dome`.
   - The Smelter Cage Lift to `luna_mine` takes `two_person_lift` | `heavy_lift`. The Crater Rim descent to `luna_tube` is open.

### 4.2 Progressive Spatial Scaling & Environmental Gating

Challenge scales through authentic environmental hostility and operational logistics rather than arbitrary enemy hit points:

1. **Environmental Gating Over Keycard Gating:**
   - Safe Pressurized Havens (`depth == 0`, `environment == "pressurized"`): `stn_a_bunkroom`, `stn_a_berth`, `stn_a_hab`, `stn_b_dock`, `stn_b_array`, `stn_b_fuel`, `luna_dome`, `luna_smelter`. Exposure naturally recovers here by 2.0 per tick.
   - Hostile Subterranean Conduits (`depth == 1`): `stn_a_sub`, `luna_mine`, `luna_tube`. Depressurized atmospheres, freezing cold, and unshielded rock. Every turn spent where exposure is building up pays Survival experience (§8.1). Repairs change a room's vitals: freeing the Sub-Deck valve raises it to 92 kPa / -5°C, and patching the Lava Tube breach raises it to 78 kPa / -20°C.
   - Unprotected Vacuum (`environment == "vacuum"`): `luna_pad`, `luna_crater`. Zero pressure, cosmic radiation, and temperature extremes. Exploration requires planning, rapid movement, and Survival levels.
2. **Resource Logistics:**
   - Sustenance items (`flask_water`, `ration_dry`, `algae_paste`) lose 1 integrity every 10 ticks. Sustenance is consumed with `/consume` to shed exposure (see §5.3), so spigots, algae basins and food trades feed directly into survival planning.

### 4.3 Exposure & Consequence Model

Each tick in a hostile environment accumulates exposure based on the delta between node vitals and safe human biological tolerances:

| Vital | Safe Tolerance | Accumulation Formula (per tick) |
| :--- | :--- | :--- |
| Pressure | >= 90.0 kPa | `+max(0.0, (90.0 - node_pressure) / 30.0)` |
| Radiation | <= 5.0 mSv | `+max(0.0, (node_radiation - 5.0) / 15.0)` |
| Temperature | >= -10.0°C | `+max(0.0, (-10.0 - node_temp) / 20.0)` |

**Consequence Thresholds:**

| Exposure Level | Threshold | Behavioral Effect |
| :--- | :--- | :--- |
| Nominal | 0.0 – 4.9 | Full operational capacity. |
| Stressed | 5.0 – 9.9 | Cautionary telemetry alerts in Zone 5. `inspect` readings report blurred diagnostic telemetry. |
| Critical | 10.0 – 14.9 | Imminent collapse warning. Hands-on work (use, search, barter) costs two cycles. Walking still costs one. |
| Incapacitated | 15.0+ | Systems fail; unconsciousness. The session continues: medics carry the player to `stn_a_bunkroom`, the night passes (a new day starts, §8.4) and one sustenance item is used. |

*Survival and Logistics perks:* `cold_bypass`, `vacuum_walk` and `deep_well` (Survival 2–4) halve pressure, radiation and thermal accumulation. `trench_hardened` (Survival 5) raises every threshold by +5.0, and all systems (tick, UI, save loading) read thresholds from the same rule. `crew_coordination` (Logistics 3) subtracts 0.2 per track while any companion travels with the player.

---

## 5. Interaction Mechanics & Command Vocabulary

### 5.1 WASD Navigation Model

Movement on the Zone 2 N×N grid is non-blocking and driven by single raw keystrokes:

| Key | Direction | Coordinate Delta |
| :--- | :--- | :--- |
| `w` | North / Up | `row - 1` |
| `s` | South / Down | `row + 1` |
| `a` | West / Left | `col - 1` |
| `d` | East / Right | `col + 1` |

- Border walls block movement. Each valid move increments `cycle` by 1 and runs the tick processor.
- Player position is indicated by `@`. When overlapping a fixture or actor tile, the tile glyph is displayed in ANSI inverted video (`\033[7m{glyph}\033[0m`).
- Stepping onto any tile containing an entity (fixture or actor) automatically activates the **Proximity Interaction Menu** in Zone 5.

### 5.2 Contextual Proximity Interaction Menu

When the cursor rests on an entity tile, Zone 5 presents an enumerated action list. Single-key presses trigger actions directly:

```text
ZONE 5 (Proximity Menu):
 Kael: T talk · B trade
```

The menu is drawn from state by the renderer (`core/menu.py`); it is never stored in the message buffer. It is one line: the entity's name, then only the actions possible right now. Inspect (`I`) and close (`X`) always work and are listed in Zone 6 instead.

**Options:**
- `F search` / `F pry open (<source>)`: containers that are not yet `SPENT`.
- `R read`: `log` fixtures. Needs no item.
- `U <verb> (<source>)`: the verb follows the effect (`open`, `repair`, `harvest`, `bypass`, `refill <item>`, `smelt <item>`). The source names what will satisfy it: a skill (`Cargo Handler training`), a companion (`Radek`) or a carried item. Free sources always win so no item wears needlessly.
- `G go to <exit> (<hazards>)`: open exits. Hazards come from the destination's vitals: `no air` / `thin air`, `freezing` / `cold`, `high radiation` / `radiation`.
- `T talk`, `B trade`: actors; `B` only when they would accept something you carry. Off an actor, `T` opens the team panel.

**Hint line.** When an expected action is unavailable the menu says why, in plain words: `Needs a pipe fitting or a spanner.`, `Sealed. Needs a pry-bar or a strong lifter.`, `Already searched.`

`s` always moves south; searching uses `f`.

### 5.3 Command Grammar & Slash Command System

Arbitrary non-slash keystrokes are silently consumed by the input loop to prevent accidental input pollution. Typing a leading slash `/` initiates full command entry in Zone 6:

| Action / Verb | Syntax | Execution Details | Advances Tick? |
| :--- | :--- | :--- | :--- |
| `w`/`a`/`s`/`d` | *(single key)* | Moves cursor 1 tile; opens the proximity menu on entity tiles. | Yes |
| `i` / `e` | *(single key / menu)* | Inspects entity under player cursor. | No |
| `u` | *(menu)* | Operates the fixture under the cursor with the best matching source. | Yes |
| `f` | *(menu)* | Searches the container under the cursor. | Yes |
| `r` | *(menu)* | Reads the log fixture under the cursor. | Yes |
| `g` | *(single key / menu)* | Traverses open hatch or umbilical under cursor. | Yes |
| `t` | *(menu)* | Talks with the actor under the cursor. | Yes |
| `b` | *(menu)* | Accepts the actor's trade. Outside the menu, `b` returns from the map. | Yes |
| `x` | *(menu)* | Clears proximity menu and restores standard message buffer. | No |
| `/look` | `/look` | Describes the room and lists exits with their hazards. | No |
| `/inspect` | `/inspect <target>` | Examines a fixture, actor, carried item or exit by name or ID. | No |
| `/use` | `/use [item] <fixture>` | Operates a fixture in the current room, preferring the named item. | Yes |
| `/search` | `/search <fixture>` | Searches a container in the current room. | Yes |
| `/read` | `/read <fixture>` | Reads a terminal or notice board. | Yes |
| `/talk` | `/talk <actor>` | Engages dialogue with specified actor. | Yes |
| `/barter` | `/barter [actor] [item]` | Accepts an actor's trade, optionally offering a specific item. | Yes |
| `/consume` | `/consume [item]` (`/eat`, `/drink`) | Eats or drinks sustenance: `hydration` T-1.5, `nutrition` all tracks -1.0, `biomass` R-2.0 more with `bio_filter` in the party. | Yes |
| `/leave` | `/leave <exit>` | Walks to the exit's hatch and crosses it; costs one cycle per tile walked. | Yes |
| `/wait` | `/wait` | Pauses for 1 cycle; processes exposure and environmental decay. | Yes |
| `/map` | `/map` | Opens dedicated ASCII cluster and node topology view. | No |
| `/back` | `/back` | Exits map topology view and returns to compartment view. | No |
| `p` / `/pack` | *(single key)* / `/pack` | Shows the pack in Zone 5: stacked items and uses left. | No |
| `c` / `/character`| *(single key)* / `/character` | Shows background, keepsake, and each work skill's level, experience, perks and next perk. | No |
| `t` / `/team` | *(single key)* / `/team` (`/party`) | Lists team members and what they count as. `t` talks instead when standing on an actor. | No |
| `j` / `/jobs` | *(single key)* / `/jobs` | Lists today's jobs, progress and pay. | No |
| `/sleep` | `/sleep` (or `U` on a bunk) | Sleeps in a room with a bunk after 20+ turns awake; starts a new day (§8.4). | Night |
| `/log` | `/log` | Prints the 10 most recent chronological action entries (moves are not logged). | No |
| `/flavor` | `/flavor [on\|off]` | Toggles room descriptions on first arrival. | No |
| `/color` | `/color [on\|off]` | Toggles text styles and the orange accent. | No |
| `/help` | `/help [survival\|trade\|commands]` | Short help by topic. | No |
| `/quit` | `/quit` | Deterministically saves state to disk and exits engine. | No |

### 5.4 Multi-Stage NPC Interaction & Dynamic Barter Protocol

NPCs are persistent actors with distinct motivations, dialogue reactivity, and roleplay utility:

1. **Contextual & Background Awareness:**
   - Actors carry `dialogue_variants`, evaluated in order: `past_work:<routine>`, `visited:<node>`, `party:<companion>`, `has_cap:<capability>`. The first match replaces the idle line until the trade is done.
2. **Explicit, Flexible Barter:**
   - `[T]` / `/talk` states the offer. `[B]` / `/barter` executes it. Nothing is traded by talking.
   - Actors accept any carried item carrying one of their `trade_required_tags`.
   - Handing over: credentials are shown and kept; items that wear lose 1 integrity (consumed at 0); anything else (materials, dice, scrip) changes hands entirely.
   - The actor's offered item is added, `trade_completed = True`, and dialogue updates.
3. **Companion Recruitment:**
   - Actors with `companion_unlock` join the team on trade and leave their room's grid. Companions contribute their capability tags (`two_person_lift`, `signal_boost`, `bio_filter`) to the whole party.

### 5.5 Expanded Fixture Functionality & Environmental Systems

Fixtures represent the physical affordances of each compartment:

| Effect Key | Description & Mechanical Behavior |
| :--- | :--- |
| `"unlock"` | `SEALED`/`LOCKED` -> `OPEN`. Grants passage through the associated edge. With `reseal_on_pass`, the gate returns to `SEALED` after the player crosses. |
| `"refill"` | Restores a carried `refillable` item's integrity to `max_integrity`. |
| `"repair"` | `DISABLED` -> `ACTIVE`. Applies `on_repair_vitals` to the room. Refuses once already `ACTIVE`, so tools are not worn twice. |
| `"scavenge"` | Searched with `[F]`. Sealed containers are pried open first. Transfers `yields` to the pack and sets `SPENT`. Containers with `restock` (bins, skids, sleds, caches, the ore face) refill each morning; personal and one-off finds do not. |
| `"harvest"` | Collects `yields` (default algae paste). Tools used are not worn. Spots with `restock` are spent until the next morning. |
| `"smelt"` | Salvage casts a Pipe Fitting. Ore forges a Pry-Bar with `scrap_fabrication`, otherwise melts to scrap. |
| `"override"` | One-time bypass: opens `opens_fixture`, grants `grants_capability`, then sets `SPENT`. |
| `"sleep"` | Bunks (`▭`). Sleeping starts a new day (§8.4). |
| `"log"` | Read with `[R]`, no item needed. Shows `log_text`; `log_text_locked` needs `signal_analysis`, `signal_boost` or `lore`. |

**Wear rules.** Only the carried item that satisfied a requirement wears, and only if no skill, clearance or companion already satisfied it. `conduit_mastery` keeps tools (`force_lever`, `wrench`) from wearing on unlock, repair and pry-open work.

### 5.6 Tick Processor Pipeline (`core/tick.py`)

Every tick-advancing action triggers a 7-step pure state reduction:
1. `cycle += 1`
2. **Exposure Accumulation:** Calculate pressure, radiation, and temperature deltas. Apply reductions from perks and the team.
3. **Exposure Recovery:** In Depth 0 Pressurized nodes, reduce all exposure tracks by 2.0 (minimum 0.0).
4. **Exposure Consequences:** Evaluate Stressed, Critical and Incapacitated limits (+5.0 each with `trench_hardened`). Warnings fire on level changes.
5. **Sustenance & Log:** Every 10 cycles (20 with `wayfarer`), decrement integrity of sustenance items by 1. Update action log history (max 20 entries).
6. **Experience & Jobs:** Apply experience from the action (passed by the reducer) plus Survival for a hostile turn; perks are granted on level-up. Advance today's jobs and pay for any completed.
7. **Fatigue:** Warn when tired; at 90 turns awake the player falls asleep (in place if the room is safe, otherwise the medics carry them back). Incapacitation revives the player the same way.

Hands-on actions at Critical exposure or while tired run the pipeline twice.

---

## 6. UI Viewport & Terminal Constraints

### 6.1 Viewport Constraints

* Minimum terminal size: 40 columns by 20 rows. Walking into a wall does nothing at all: no message, no time, and the menu for the current tile stays usable. When the terminal is shorter than the frame, the Zone 4 legend is dropped first.
* Rendered via ANSI terminal clearing and sequential string construction.
* Zone 2 minimap displays up to a 10×10 grid. Entity glyphs with player cursor overlap are rendered in inverted video (`\033[7m`).
* Box-drawing characters (`┌ ─ ┐ │ └ ┘ ├ ┤ ┬ ┴ ┼`) and unicode symbols (`= ⌸ ⎅ ≡ ⚲ ⊞ ◆ ■ ▭ ~ ·`) are permitted; entity glyphs follow §6.4. Emojis are prohibited.
* **Styles and palette** (`ui/style.py`): bold, dim and inverse, plus one accent colour, orange (`\033[38;5;208m`). No other colours.
  - Orange is reserved for danger: warning messages, the `Strained` status, rising exposure tracks and the hazard words in Zone 1. `DANGER` status is orange inverse.
  - Bold: room name, gains (`+ Skill`, `+ Got`, `+ Crew`), the menu title, the Pack heading.
  - Inverse: the player's tile and the key letters in the menu.
  - Dim: dialogue, room descriptions, the legend, Zone 6 hints and menu hints.
  - `/color off` renders plain text (the cursor keeps its inverse). The setting is saved.

### 6.2 The 6-Zone Layout Specification

Rendered at 40 columns (styles removed):

```
┌──────────────────────────────────────┐
│ Berth 04                   Station A │
│ 101.3 kPa · 18°C · 0.2 mSv  safe air │
├──────────────────────────────────────┤
│┌───────────────────┐│ Day 1 · Evening│
││ ░ ░ ░ ░ ◆ ░ ░ ░ ░ ││ Strained /15   │
││ ░ · · = · · · · ░ ││ Air   0.0      │
││ ░ · · · · · · · ░ ││ Rad   0.0      │
││ ░ · · ⊞ · K · ⌸ ░ ││ Cold  5.1 -2   │
││ ◆ · · · · · · · = ││ Awake 41/90    │
││ ░ · · · · · · ⊞ ░ ││ Team: Radek    │
││ ░ · · · · · · · ░ ││                │
││ ░ · · · ⎅ · · · ░ ││                │
││ ░ ░ ░ ░ ░ ░ ░ ░ ░ ││                │
│└───────────────────┘│                │
├──────────────────────────────────────┤
│ ◆ Bunkroom N · Hab Ring W            │
│ ⊞ Freight Skid · Scrap Bin           │
│ K Kael                               │
│ = Shuttle E (sealed) · Stowaway to   │
│   Shuttle (sealed)                   │
│ ⎅ Sub-Deck (locked)                  │
│ ⌸ Docking Collar                     │
├──────────────────────────────────────┤
│ ! Cold 5.1 of 15. Head back soon.    │
│ Kael: T talk · B trade               │
├──────────────────────────────────────┤
│ I inspect  X close  WASD move        │
│ M map  P pack  C char  J jobs        │
└──────────────────────────────────────┘
```

* **Zone 1:** room name and area (`Station A`, `Station B`, `In transit`, `Moon`), then readings and, outside safe havens, hazard words in orange. If both do not fit, the hazard words win.
* **Zone 2:** the room grid, up to 10×10.
* **Zone 3:** day and shift (`Day 1 · Evening`); status `OK`, or `Strained · max 15` / `DANGER · max 15` (the blackout limit shows only when it matters); the three exposure tracks `Air` (low pressure), `Rad`, `Cold` with their per-turn trend (`+3.5`, or `-2` while recovering); turns awake (`Awake 41/90`, orange when tired); the team, shortened to `Radek +2` when long. The pack is not shown here; press `P`.
* **Zone 4:** legend, one line per glyph (§6.4). Exits are named by destination plus the wall they sit on (`N`, `S`, `E`, `W`), so doors sharing a glyph stay distinguishable. Notable states follow in brackets (`sealed`, `locked`, `broken`, `used`). No IDs.
* **Zone 5:** messages sorted by kind, then the proximity menu (§5.2). Panels opened with `P`, `C`, `T` appear here. See §6.3.
* **Zone 6:** two lines of key hints. Normally `WASD move  / command  Q quit` and `M map  P pack  C char  T team  J jobs`; with the menu open, `I inspect  X close  WASD move` and the panel keys (without `T` when standing on an actor).

### 6.3 Messages and Wording

Reducers tag each message with a kind (`core/text.py`); the renderer sorts and styles them:

| Kind | Prefix in state | Shown as | Used for |
| :--- | :--- | :--- | :--- |
| danger | `!! ` | `! ` in orange, first | Exposure level changes, blackout, arriving somewhere hostile, shaking hands |
| gain | `+ ` | `+ ` in bold, second | `Skill:`, `Crew:`, `Got:`, `Found:` |
| plain | none | normal | The result of the action |
| quiet | `~ ` (hidden) | dim, last | Dialogue, room descriptions |

* **Warnings fire on change.** Exposure warnings appear when the level changes (OK → Strained → DANGER, or back to OK: "You're breathing easier."). Zone 3 carries the ongoing state.
* **Room descriptions** appear on the first visit only (and with `/look`).
* **Plain names.** Player text never shows internal IDs or tags. Requirement tags read as nouns via `TAG_NAMES` (`seal_fitting` → "a pipe fitting", `heavy_lift` → "a strong lifter"). Fixture states read as `sealed`, `locked`, `broken`, `used`, `open`, `working`.
* **Tone.** Short, direct sentences in second person. Units stay (kPa, °C, mSv), jargon goes.

### 6.4 Map Glyphs

One glyph per kind of thing, so the map reads at a glance; the legend names each one.

| Glyph | Kind | Rule |
| :--- | :--- | :--- |
| `◆` | Door | Exit to a room on the same level |
| `⎅` | Lift or ladder | Exit that changes level, or any lift/ladder |
| `≡` | Vent | Crawlway exits |
| `=` | Shuttle boarding | Exits to or from the shuttle |
| `⊞` | Container | Anything searched with `F` |
| `⌸` | Screen or panel | Readable logs and bypass panels |
| `⚲` | Supply | Water taps and food vats |
| `■` | Machine | Things to repair or smelt |
| `▭` | Bunk | Where you sleep |
| `A`–`Z` | Person | First letter of their name |

Walls and floors keep their per-room glyphs. `tests/test_ui_flow.py` checks every fixture against these rules.

---

## 7. Character Creation Sequence

### 7.1 Creation-to-State Mapping

Character creation establishes personal background, starting equipment, and an authentic roleplay identity:

| Step | Selection | In-Game Mechanical Effect |
| :--- | :--- | :--- |
| **Step 1: Callsign** | Free text input | Stored in `character.name`. |
| **Step 2: Personal Anchor** | 1. Pipe Fitting (`fitting_copper`) | Utility item; provides `seal_fitting`, `conductive`. |
| | 2. Work Pass (`pass_work`) | Credential; provides `dock_clearance`, `id_verified`. |
| | 3. Steel Dice (`dice_steel`) | Record item; provides `morale`, `barter_token`. |
| | 4. Chalk Slate (`slate_tally`) | Record item; provides `record`, `marking`, `lore`. |
| **Step 3: Past Routine** | 1. Seam Scraper (`seam_scraper`) | `unlocked_capabilities += {"seal_fitting"}`; starts at Engineering 2. Can inspect weld integrity, bypass stuck seals, and craft basic fittings. |
| | 2. Algae Tender (`algae_tender`) | `unlocked_capabilities += {"bio_filter"}`; starts at Survival 2. Can harvest biomass, service scrubbers, and identify potable fluids. |
| | 3. Cargo Handler (`cargo_handler`) | `unlocked_capabilities += {"heavy_lift"}`; starts at Logistics 2. Can brute-force seized levers, lift heavy bulkheads, and handle dense freight. |

*Initial Spawn:* Player begins in `stn_a_bunkroom` at grid center `(node.size // 2, node.size // 2)`, with `cycle = 0`, `day = 1`, zero exposure, and day 1's jobs posted.

---

## 8. Progression, Capabilities & Team Mechanics

### 8.1 Work Skills and Levels

Three work skills level from 1 to 5. Experience comes from doing the work; each level grants one perk (a capability tag the rules already understand). Your past routine starts you at level 2 in its skill.

| Skill | Earned by |
| :--- | :--- |
| Engineering | Opening (+15), repairing (+20), bypassing (+15), smelting (+10), prying containers open (+10) |
| Survival | Each turn where exposure builds up (+2, or +3 while Strained or worse) |
| Logistics | Searching (+8), trading (+20), harvesting (+5), job deliveries |

Jobs pay extra experience in their skill (§8.4).

| Skill | Level | XP | Grants | Perk |
| :--- | :--- | :--- | :--- | :--- |
| Engineering | 2 | 30 | `seam_discipline` | Inspecting shows whether you can fix it, and with what. |
| Engineering | 3 | 90 | `scrap_fabrication` | Forge pry-bars from ore at the smelter. |
| Engineering | 4 | 180 | `bulkhead_ear` | Hear the air behind a door before you open it. |
| Engineering | 5 | 300 | `conduit_mastery` | Tools don't wear on pipe and valve work. |
| Survival | 2 | 30 | `cold_bypass` | Cold builds up half as fast. |
| Survival | 3 | 90 | `vacuum_walk` | Low pressure builds up half as fast. |
| Survival | 4 | 180 | `deep_well` | Radiation builds up half as fast. |
| Survival | 5 | 300 | `trench_hardened` | You can take 5 more of everything before blacking out. |
| Logistics | 2 | 30 | `scavenger_instinct` | Find extra scrap when searching. |
| Logistics | 3 | 90 | `crew_coordination` | Your team shields you: every track builds up 0.2 slower. |
| Logistics | 4 | 180 | `signal_analysis` | Read the scrambled parts of logs and boards. |
| Logistics | 5 | 300 | `wayfarer` | Food lasts twice as long and shuttle rides are free. |

### 8.2 Inventory Assets Reference

| ID | Name | Category | Tags | Max Integrity | Operational Utility |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `fitting_copper` | Pipe Fitting | utility | `seal_fitting`, `conductive` | 1 | Seals fluid/gas leaks; bypasses low-voltage relays. |
| `pass_work` | Work Pass | credential | `dock_clearance`, `id_verified` | 0 | Authorizes cargo hoist operation and standard shuttle boarding. |
| `dice_steel` | Steel Dice | record | `morale`, `barter_token` | 0 | Milled steel cubes; accepted by dockers and miners as trade collateral. |
| `slate_tally` | Chalk Slate | record | `record`, `marking`, `lore` | 0 | Displays scratched station manifests, codes, and historical tallies. |
| `chit_transit` | Shuttle Token | credential | `transit_clearance` | 1 | Stamped token granting single-hop shuttle boarding. |
| `tool_prybar` | Pry-Bar | utility | `force_lever`, `heavy_duty` | 4 | Heavy lever for jammed valves, sealed hatches, and stubborn crates. |
| `tool_spanner` | Spanner | utility | `bio_filter`, `wrench` | 3 | Sized for biological filtration couplings and mechanical bolts. |
| `flask_water` | Canteen | sustenance | `hydration`, `refillable` | 3 | Drinking flask; refillable at active water taps. Decays over cycles. |
| `ration_dry` | Ration Bar | sustenance | `nutrition` | 3 | Calorie bar; satisfies metabolic requirements. Decays over cycles. |
| `algae_paste` | Algae Paste | sustenance | `nutrition`, `biomass` | 2 | Nutrient slurry harvested from active hydroponic tanks. |
| `wire_spool` | Copper Wire | utility | `conductive`, `electrical` | 2 | Used for rewiring damaged consoles and electrical overrides. |
| `seal_patch` | Seal Patch | utility | `vacuum_seal`, `adhesive` | 2 | Seals the Lava Tube breach, restoring partial pressure there. |
| `scrap_metal` | Scrap Metal | material | `salvage`, `conductive` | 0 | Salvaged plates; used as raw stock in the smelter crucible. |
| `ore_sample` | Lunar Ore | material | `mineral` | 0 | Heavy basalt core extracted from deep mining veins. |
| `scrip_shift` | Shift Scrip | record | `barter_token` | 1 | Ration-office scrip; found in the Bunkroom locker and the Fuel Spur cabinet. Buys Tarek's help. |

### 8.3 Companion Roster & Team Synergy

Companions represent fellow crew members recruited across the stations. They travel with the player and contribute specialized capabilities:

| ID | Name | Title | Cluster Source | Capability Tag | Function & Synergy |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `comp_radek` | Radek | Cargo Rigger | Station Alpha (Sub-Deck) | `two_person_lift` | Operates heavy industrial lifts, assists in prying sealed doors, and hauls freight. |
| `comp_tarek` | Tarek | Array Specialist | Station Beta (Dock / Array) | `signal_boost` | Decodes encrypted station data, intercepts distress traffic, and hacks consoles. |
| `comp_mira` | Mira | Hab Botanist | Station Alpha (Hab Ring) | `bio_filter` | Optimizes life support scrubbers, harvests algae rations, and purges exposure toxins. |

---

### 8.4 Daily Routine

* **Shifts.** A day is three shifts of 30 turns awake: Morning, Evening, Night.
* **Fatigue.** At 60 turns awake you are tired: hands-on work takes twice as long. At 90 you fall asleep where you stand. In a safe room you wake there next morning; anywhere else the medics carry you to the Bunkroom and use one ration.
* **Sleep.** Bunks are in the Bunkroom and the Habitat Dome. Sleeping needs 20+ turns awake. The night passes (30 cycles), exposure clears, and a new day starts.
* **Each morning:** restocking containers refill, harvest spots regrow, and three jobs are posted from `jobs.json` on a fixed rotation (day *d* posts templates 3(*d*−1) … 3(*d*−1)+2, wrapping around). No randomness.
* **Jobs** are done by playing: `use` a fixture, `deliver` items to a room (taken on arrival), or `stay` a number of turns in a room. Completion pays experience and items (tokens, patches, rations, scrip), so routine work funds expeditions.

---

## 9. Preset Reference Dataset (`core/data/default-1.0/`)

The blocks below are generated from the canonical JSON files and checked by `tests/test_gdd_sync.py`.

### 9.1 Items (`items.json`)

```json
[
  {
    "id": "fitting_copper",
    "name": "Pipe Fitting",
    "category": "utility",
    "tags": [
      "seal_fitting",
      "conductive"
    ],
    "integrity": 1,
    "max_integrity": 1,
    "description": "Standard threaded pipe collar with a clean silicone ring."
  },
  {
    "id": "pass_work",
    "name": "Work Pass",
    "category": "credential",
    "tags": [
      "dock_clearance",
      "id_verified"
    ],
    "integrity": 0,
    "max_integrity": 0,
    "description": "Laminated shift card signed by the transit stevedore office."
  },
  {
    "id": "dice_steel",
    "name": "Steel Dice",
    "category": "record",
    "tags": [
      "morale",
      "barter_token"
    ],
    "integrity": 0,
    "max_integrity": 0,
    "description": "Two milled steel cubes, pips worn flat from rolling on deck plate."
  },
  {
    "id": "slate_tally",
    "name": "Chalk Slate",
    "category": "record",
    "tags": [
      "record",
      "marking",
      "lore"
    ],
    "integrity": 0,
    "max_integrity": 0,
    "description": "Flat slate slab showing scratched shift quotas and valve coordinates."
  },
  {
    "id": "chit_transit",
    "name": "Shuttle Token",
    "category": "credential",
    "tags": [
      "transit_clearance"
    ],
    "integrity": 1,
    "max_integrity": 1,
    "description": "Stamped metal token granting single-hop shuttle boarding."
  },
  {
    "id": "tool_prybar",
    "name": "Pry-Bar",
    "category": "utility",
    "tags": [
      "force_lever",
      "heavy_duty"
    ],
    "integrity": 4,
    "max_integrity": 4,
    "description": "Flat-nosed iron lever rated for stuck latches and warped plates."
  },
  {
    "id": "tool_spanner",
    "name": "Spanner",
    "category": "utility",
    "tags": [
      "bio_filter",
      "wrench"
    ],
    "integrity": 3,
    "max_integrity": 3,
    "description": "Offset ring spanner sized for standard filtration cartridge bolts."
  },
  {
    "id": "flask_water",
    "name": "Canteen",
    "category": "sustenance",
    "tags": [
      "hydration",
      "refillable"
    ],
    "integrity": 3,
    "max_integrity": 3,
    "description": "Metal drinking flask fitted with a screw seal."
  },
  {
    "id": "ration_dry",
    "name": "Ration Bar",
    "category": "sustenance",
    "tags": [
      "nutrition"
    ],
    "integrity": 3,
    "max_integrity": 3,
    "description": "Dense calorie block in foil wrap. Tastes like salted chalk."
  },
  {
    "id": "algae_paste",
    "name": "Algae Paste",
    "category": "sustenance",
    "tags": [
      "nutrition",
      "biomass"
    ],
    "integrity": 2,
    "max_integrity": 2,
    "description": "High-protein spirulina slurry harvested from station hydroponics."
  },
  {
    "id": "wire_spool",
    "name": "Copper Wire",
    "category": "utility",
    "tags": [
      "conductive",
      "electrical"
    ],
    "integrity": 2,
    "max_integrity": 2,
    "description": "Flexible coil of copper wiring suitable for circuit overrides."
  },
  {
    "id": "seal_patch",
    "name": "Seal Patch",
    "category": "utility",
    "tags": [
      "vacuum_seal",
      "adhesive"
    ],
    "integrity": 2,
    "max_integrity": 2,
    "description": "Self-curing elastomer patch rated for sudden pressure drops."
  },
  {
    "id": "scrap_metal",
    "name": "Scrap Metal",
    "category": "material",
    "tags": [
      "salvage",
      "conductive"
    ],
    "integrity": 0,
    "max_integrity": 0,
    "description": "Twisted structural alloy plates suitable for smelting."
  },
  {
    "id": "ore_sample",
    "name": "Lunar Ore",
    "category": "material",
    "tags": [
      "mineral"
    ],
    "integrity": 0,
    "max_integrity": 0,
    "description": "Heavy core of titanium-rich lunar basalt extracted from the deep shaft."
  },
  {
    "id": "scrip_shift",
    "name": "Shift Scrip",
    "category": "record",
    "tags": [
      "barter_token"
    ],
    "integrity": 1,
    "max_integrity": 1,
    "description": "Punched ration-office scrip good for one favor between shift crews."
  }
]
```

### 9.2 Complete 14-Node World Preset (`nodes.json`)

```json
[
  {
    "id": "stn_a_bunkroom",
    "name": "Bunkroom",
    "cluster": "station_alpha",
    "size": 6,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {
      "pressure_kpa": 101.3,
      "radiation_msv": 0.1,
      "temperature_c": 20
    },
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hatch_berth": {
        "id": "hatch_berth",
        "glyph": "◆",
        "name": "Berth Hatch",
        "state": "open",
        "grants_edge": "to_berth",
        "on_use_effect": null,
        "description": "Oval pressure seal leading to the primary transfer platform.",
        "required_tags": []
      },
      "spigot_01": {
        "id": "spigot_01",
        "glyph": "⚲",
        "name": "Water Tap",
        "state": "active",
        "grants_edge": null,
        "on_use_effect": "refill",
        "description": "Push-valve tap metering gray-line recycled potable water.",
        "required_tags": [
          "refillable"
        ]
      },
      "personal_locker": {
        "id": "personal_locker",
        "glyph": "⊞",
        "name": "Crew Locker",
        "state": "active",
        "grants_edge": null,
        "on_use_effect": "scavenge",
        "description": "Metal footlocker tucked under a cot. Contains discarded shift notes and copper wire.",
        "required_tags": [],
        "yields": [
          "wire_spool",
          "scrip_shift"
        ]
      },
      "vent_duct": {
        "id": "vent_duct",
        "glyph": "≡",
        "name": "Vent Crawlway",
        "state": "sealed",
        "grants_edge": "to_sub_vent",
        "on_use_effect": "unlock",
        "description": "Narrow maintenance duct descending behind conduit lines straight to the sub-deck.",
        "required_tags": [
          "seal_fitting",
          "wrench"
        ]
      },
      "crew_bunk": {
        "id": "crew_bunk",
        "glyph": "▭",
        "name": "Crew Bunk",
        "state": "active",
        "required_tags": [],
        "grants_edge": null,
        "on_use_effect": "sleep",
        "description": "Fold-down bunk with a thin mattress. Sleep here to start a new day."
      }
    },
    "actors": {},
    "placements": [
      {
        "entity_id": "hatch_berth",
        "row": 0,
        "col": 2
      },
      {
        "entity_id": "spigot_01",
        "row": 4,
        "col": 1
      },
      {
        "entity_id": "personal_locker",
        "row": 1,
        "col": 4
      },
      {
        "entity_id": "vent_duct",
        "row": 5,
        "col": 2
      },
      {
        "entity_id": "crew_bunk",
        "row": 1,
        "col": 1
      }
    ],
    "edges": {
      "to_berth": {
        "id": "to_berth",
        "target_node_id": "stn_a_berth",
        "label": "Berth 04",
        "gated_by_fixture": null,
        "requires_capability": null
      },
      "to_sub_vent": {
        "id": "to_sub_vent",
        "target_node_id": "stn_a_sub",
        "label": "Sub-Deck (vent)",
        "gated_by_fixture": "vent_duct",
        "requires_capability": null
      }
    },
    "description": "Narrow sleeping bay lined with fold-down bunks. Recycled air smells faintly of cleaning solvent."
  },
  {
    "id": "stn_a_berth",
    "name": "Berth 04",
    "cluster": "station_alpha",
    "size": 9,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {
      "pressure_kpa": 101.3,
      "radiation_msv": 0.2,
      "temperature_c": 18
    },
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hatch_bunks": {
        "id": "hatch_bunks",
        "glyph": "◆",
        "name": "Bunkroom Hatch",
        "state": "open",
        "grants_edge": "to_bunks",
        "on_use_effect": null,
        "description": "Hatch back to the shared sleeping quarters.",
        "required_tags": []
      },
      "cargo_hoist": {
        "id": "cargo_hoist",
        "glyph": "⎅",
        "name": "Cargo Hoist",
        "state": "locked",
        "grants_edge": "to_subdeck",
        "on_use_effect": "unlock",
        "description": "Chain-driven freight platform descending into the sub-deck conduit well.",
        "required_tags": [
          "dock_clearance",
          "force_lever",
          "heavy_lift",
          "two_person_lift"
        ]
      },
      "shuttle_gate": {
        "id": "shuttle_gate",
        "glyph": "=",
        "name": "Shuttle Gate",
        "state": "sealed",
        "grants_edge": "to_shuttle",
        "on_use_effect": "unlock",
        "description": "Flexible boarding seal clamped to the shuttle. Takes one transit token per boarding, then reseals.",
        "required_tags": [
          "transit_clearance"
        ],
        "reseal_on_pass": true
      },
      "freight_skid": {
        "id": "freight_skid",
        "glyph": "⊞",
        "name": "Freight Skid",
        "state": "active",
        "grants_edge": null,
        "on_use_effect": "scavenge",
        "description": "Heavy industrial pallet lashed down with tension clamps. Loose packing holds spare salvage.",
        "required_tags": [],
        "yields": [
          "scrap_metal"
        ],
        "restock": true
      },
      "salvage_bin": {
        "id": "salvage_bin",
        "glyph": "⊞",
        "name": "Scrap Bin",
        "state": "active",
        "grants_edge": null,
        "on_use_effect": "scavenge",
        "description": "Welded steel bin holding discarded copper pipe fittings and scrap brackets.",
        "required_tags": [],
        "yields": [
          "fitting_copper"
        ],
        "restock": true
      },
      "hab_hatch": {
        "id": "hab_hatch",
        "glyph": "◆",
        "name": "Hab Ring Hatch",
        "state": "open",
        "grants_edge": "to_hab",
        "on_use_effect": null,
        "description": "Wide corridor hatch leading up to the hab ring common gallery.",
        "required_tags": []
      },
      "umbilical_collar": {
        "id": "umbilical_collar",
        "glyph": "⌸",
        "name": "Docking Collar",
        "state": "active",
        "required_tags": [
          "wrench",
          "seal_fitting"
        ],
        "grants_edge": null,
        "on_use_effect": "override",
        "opens_fixture": "shuttle_gate",
        "description": "Access panel for the shuttle docking collar. Re-seating the collar by hand fools the gate into cycling open once."
      },
      "freight_clamps": {
        "id": "freight_clamps",
        "glyph": "=",
        "name": "Cargo Clamps",
        "state": "sealed",
        "required_tags": [
          "force_lever",
          "heavy_lift",
          "two_person_lift"
        ],
        "grants_edge": "to_shuttle_skid",
        "on_use_effect": "unlock",
        "reseal_on_pass": true,
        "description": "Ratchet clamps holding a freight skid bound for the shuttle hold. Released, there is room to ride along unseen."
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
        "trade_completed": false,
        "dialogue_idle": "Shuttle to the Moon is warming up. If you've got spare pipe collars or salvage, I can endorse a work pass for the freight deck.",
        "dialogue_post_trade": "Collar's seated. Pass endorsed. Take care on the sub-deck; Radek's down there cursing at a frozen valve.",
        "companion_unlock": null,
        "trade_required_tags": [
          "seal_fitting"
        ],
        "dialogue_variants": [
          [
            "past_work:cargo_handler",
            "You lash skids like a Berth hand. Bring me a pipe collar and I'll stamp you a pass; the hoist knows your kind of shoulders anyway."
          ]
        ]
      }
    },
    "placements": [
      {
        "entity_id": "hatch_bunks",
        "row": 0,
        "col": 4
      },
      {
        "entity_id": "freight_skid",
        "row": 3,
        "col": 3
      },
      {
        "entity_id": "npc_kael",
        "row": 3,
        "col": 5
      },
      {
        "entity_id": "salvage_bin",
        "row": 5,
        "col": 7
      },
      {
        "entity_id": "hab_hatch",
        "row": 4,
        "col": 0
      },
      {
        "entity_id": "shuttle_gate",
        "row": 4,
        "col": 8
      },
      {
        "entity_id": "cargo_hoist",
        "row": 7,
        "col": 4
      },
      {
        "entity_id": "umbilical_collar",
        "row": 3,
        "col": 7
      },
      {
        "entity_id": "freight_clamps",
        "row": 1,
        "col": 3
      }
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
        "label": "Shuttle",
        "gated_by_fixture": "shuttle_gate",
        "requires_capability": null
      },
      "to_subdeck": {
        "id": "to_subdeck",
        "target_node_id": "stn_a_sub",
        "label": "Sub-Deck",
        "gated_by_fixture": "cargo_hoist",
        "requires_capability": null
      },
      "to_shuttle_skid": {
        "id": "to_shuttle_skid",
        "target_node_id": "shuttle_ab",
        "label": "Stowaway to Shuttle",
        "gated_by_fixture": "freight_clamps",
        "requires_capability": null
      }
    },
    "description": "Open transfer bay smelling of hydraulic fluid and ozone. Cargo skids line the deck under industrial lighting."
  },
  {
    "id": "stn_a_sub",
    "name": "Sub-Deck",
    "cluster": "station_alpha",
    "size": 8,
    "depth": 1,
    "environment": "depressurizing",
    "base_vitals": {
      "pressure_kpa": 65.0,
      "radiation_msv": 2.0,
      "temperature_c": -25
    },
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hoist_up": {
        "id": "hoist_up",
        "glyph": "⎅",
        "name": "Hoist Up",
        "state": "open",
        "grants_edge": "to_berth",
        "on_use_effect": null,
        "description": "Chain platform ascending back to Berth 04.",
        "required_tags": []
      },
      "vent_to_bunk": {
        "id": "vent_to_bunk",
        "glyph": "≡",
        "name": "Vent Up",
        "state": "open",
        "grants_edge": "to_bunk_vent",
        "on_use_effect": null,
        "description": "Climbing rungs inside the ventilation riser back to the bunkroom.",
        "required_tags": []
      },
      "jammed_valve": {
        "id": "jammed_valve",
        "glyph": "■",
        "name": "Frozen Valve",
        "state": "disabled",
        "grants_edge": null,
        "on_use_effect": "repair",
        "description": "Thermal bypass valve seized shut by line ice. Freeing it restores pressure and heat to the conduits.",
        "required_tags": [
          "force_lever",
          "wrench"
        ],
        "on_repair_vitals": {
          "pressure_kpa": 92.0,
          "radiation_msv": 2.0,
          "temperature_c": -5
        }
      },
      "tool_rack": {
        "id": "tool_rack",
        "glyph": "⊞",
        "name": "Tool Rack",
        "state": "active",
        "grants_edge": null,
        "on_use_effect": "scavenge",
        "description": "Industrial tool board mounted on the conduit wall. Holds a thermal pry-bar.",
        "required_tags": [],
        "yields": [
          "tool_prybar"
        ]
      }
    },
    "actors": {
      "npc_radek": {
        "id": "npc_radek",
        "glyph": "R",
        "name": "Radek",
        "title": "Cargo Rigger",
        "status": "Shivering over frozen conduit junction",
        "trade_offered_id": "chit_transit",
        "trade_completed": false,
        "dialogue_idle": "Valve's iced solid. Can't get the air back without a pry-bar. Got one? I've got an extra shuttle token if you help crack it.",
        "dialogue_post_trade": "Valve's turning. Heat's coming back. I'm ready to roll if you need a hand hauling freight.",
        "companion_unlock": "comp_radek",
        "trade_required_tags": [
          "force_lever"
        ],
        "dialogue_variants": [
          [
            "past_work:cargo_handler",
            "Another lifter. Good. Crack this valve with me and I'll ride along wherever you're hauling."
          ]
        ]
      }
    },
    "placements": [
      {
        "entity_id": "hoist_up",
        "row": 0,
        "col": 4
      },
      {
        "entity_id": "vent_to_bunk",
        "row": 7,
        "col": 1
      },
      {
        "entity_id": "jammed_valve",
        "row": 4,
        "col": 1
      },
      {
        "entity_id": "tool_rack",
        "row": 3,
        "col": 6
      },
      {
        "entity_id": "npc_radek",
        "row": 4,
        "col": 6
      }
    ],
    "edges": {
      "to_berth": {
        "id": "to_berth",
        "target_node_id": "stn_a_berth",
        "label": "Berth 04 (up)",
        "gated_by_fixture": null,
        "requires_capability": null
      },
      "to_bunk_vent": {
        "id": "to_bunk_vent",
        "target_node_id": "stn_a_bunkroom",
        "label": "Bunkroom (vent)",
        "gated_by_fixture": null,
        "requires_capability": null
      }
    },
    "description": "Low-ceilinged conduit passage. Frost crusts the pipe manifolds. The air is thin and bites cold."
  },
  {
    "id": "stn_a_hab",
    "name": "Hab Ring",
    "cluster": "station_alpha",
    "size": 8,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {
      "pressure_kpa": 101.3,
      "radiation_msv": 0.1,
      "temperature_c": 21
    },
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hatch_to_berth": {
        "id": "hatch_to_berth",
        "glyph": "◆",
        "name": "Berth Hatch",
        "state": "open",
        "grants_edge": "to_berth",
        "on_use_effect": null,
        "description": "Wide corridor hatch leading down to the transfer berths.",
        "required_tags": []
      },
      "notice_board": {
        "id": "notice_board",
        "glyph": "⌸",
        "name": "Notice Board",
        "state": "active",
        "grants_edge": null,
        "on_use_effect": "log",
        "description": "Postings: shift rosters, fuel quotas on Station Beta, and reports of seismic tremors in the lunar mines.",
        "required_tags": [],
        "log_text": "Shift roster: Berth 04 hoist crew short two riggers. Fuel quota on Station Beta raised 8%. Lunar mine reports tremors on the lower gallery.",
        "log_text_locked": "Maintenance memo, scratched over: 'Shuttle docking collar can be re-seated by hand with a spanner or a pipe collar. The gate trusts the collar.'"
      },
      "algae_basin": {
        "id": "algae_basin",
        "glyph": "⚲",
        "name": "Algae Vat",
        "state": "active",
        "grants_edge": null,
        "on_use_effect": "harvest",
        "description": "Green spirulina culture bubbling behind acrylic. Can yield fresh nutrient paste.",
        "required_tags": [
          "bio_filter"
        ],
        "restock": true
      }
    },
    "actors": {
      "npc_mira": {
        "id": "npc_mira",
        "glyph": "M",
        "name": "Mira",
        "title": "Hab Botanist",
        "status": "Checking nutrient flow in algae basin",
        "trade_offered_id": "flask_water",
        "trade_completed": false,
        "dialogue_idle": "Recycler pumps are surging. If you have clean wire or copper fittings to ground this sensor, I can spare a clean canteen.",
        "dialogue_post_trade": "Sensor's grounded. Water's running sweet. If you're heading out to the outer rings, I can monitor your bio-filters.",
        "companion_unlock": "comp_mira",
        "trade_required_tags": [
          "conductive"
        ],
        "dialogue_variants": [
          [
            "past_work:algae_tender",
            "You've rinsed filters before, I can tell. Ground this sensor with wire or copper and I'll trade you a canteen."
          ]
        ]
      }
    },
    "placements": [
      {
        "entity_id": "hatch_to_berth",
        "row": 7,
        "col": 4
      },
      {
        "entity_id": "notice_board",
        "row": 3,
        "col": 1
      },
      {
        "entity_id": "algae_basin",
        "row": 3,
        "col": 6
      },
      {
        "entity_id": "npc_mira",
        "row": 4,
        "col": 6
      }
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
    "name": "Shuttle",
    "cluster": "transit",
    "size": 6,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {
      "pressure_kpa": 98.0,
      "radiation_msv": 1.5,
      "temperature_c": 16
    },
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "gate_alpha": {
        "id": "gate_alpha",
        "glyph": "=",
        "name": "Door to Station A",
        "state": "open",
        "grants_edge": "to_stn_a",
        "on_use_effect": null,
        "description": "Docking collar sealed to Station Alpha's Berth 04.",
        "required_tags": []
      },
      "gate_beta": {
        "id": "gate_beta",
        "glyph": "=",
        "name": "Door to Station B",
        "state": "open",
        "grants_edge": "to_stn_b",
        "on_use_effect": null,
        "description": "Docking collar clamped to Station Beta's Dock Ring.",
        "required_tags": []
      },
      "gate_luna": {
        "id": "gate_luna",
        "glyph": "=",
        "name": "Door to Moon",
        "state": "open",
        "grants_edge": "to_luna",
        "on_use_effect": null,
        "description": "Reinforced exterior airlock leading directly down to the lunar surface apron.",
        "required_tags": []
      },
      "flight_console": {
        "id": "flight_console",
        "glyph": "⌸",
        "name": "Flight Screen",
        "state": "active",
        "grants_edge": null,
        "on_use_effect": "log",
        "description": "Automated guidance screen displaying orbital ephemeris, lunar pad coordinates, and radiation forecasts.",
        "required_tags": [],
        "log_text": "Ephemeris: lunar pad window open. Surface forecast 25 mSv, -80 C. Pad-to-dome airlock is 3 tiles south of the lander hatch. Do not linger.",
        "log_text_locked": "Cargo manifest, restricted: freight skids at Berth 04 ride the shuttle hold unsealed. Clamp tension is the only check."
      }
    },
    "actors": {},
    "placements": [
      {
        "entity_id": "gate_alpha",
        "row": 0,
        "col": 1
      },
      {
        "entity_id": "gate_beta",
        "row": 0,
        "col": 4
      },
      {
        "entity_id": "gate_luna",
        "row": 5,
        "col": 2
      },
      {
        "entity_id": "flight_console",
        "row": 2,
        "col": 2
      }
    ],
    "edges": {
      "to_stn_a": {
        "id": "to_stn_a",
        "target_node_id": "stn_a_berth",
        "label": "Station A",
        "gated_by_fixture": null,
        "requires_capability": null
      },
      "to_stn_b": {
        "id": "to_stn_b",
        "target_node_id": "stn_b_dock",
        "label": "Station B",
        "gated_by_fixture": null,
        "requires_capability": null
      },
      "to_luna": {
        "id": "to_luna",
        "target_node_id": "luna_pad",
        "label": "Landing Pad",
        "gated_by_fixture": null,
        "requires_capability": null
      }
    },
    "description": "Functional shuttle shuttle cabin with four acceleration couches. Reinforced viewports overlook the lunar rim."
  },
  {
    "id": "stn_b_dock",
    "name": "Dock Ring",
    "cluster": "station_beta",
    "size": 8,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {
      "pressure_kpa": 100.5,
      "radiation_msv": 0.3,
      "temperature_c": 19
    },
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "shuttle_return": {
        "id": "shuttle_return",
        "glyph": "=",
        "name": "Shuttle Door",
        "state": "open",
        "grants_edge": "to_shuttle",
        "on_use_effect": null,
        "description": "Umbilical back to the inter-station shuttle shuttle.",
        "required_tags": []
      },
      "hatch_array": {
        "id": "hatch_array",
        "glyph": "◆",
        "name": "Comms Hub Hatch",
        "state": "open",
        "grants_edge": "to_array",
        "on_use_effect": null,
        "description": "Pressure hatch leading to the communications array center.",
        "required_tags": []
      },
      "hatch_fuel": {
        "id": "hatch_fuel",
        "glyph": "◆",
        "name": "Fuel Spur Hatch",
        "state": "open",
        "grants_edge": "to_fuel",
        "on_use_effect": null,
        "description": "Blast door to the fuel processing and propellant manifold.",
        "required_tags": []
      },
      "freight_crate": {
        "id": "freight_crate",
        "glyph": "⊞",
        "name": "Cargo Crate",
        "state": "sealed",
        "grants_edge": null,
        "on_use_effect": "scavenge",
        "description": "Steel shipping crate bound with nylon bands. Can be levered open with a pry-bar.",
        "required_tags": [
          "force_lever",
          "heavy_lift"
        ],
        "yields": [
          "chit_transit"
        ]
      }
    },
    "actors": {
      "npc_tarek": {
        "id": "npc_tarek",
        "glyph": "T",
        "name": "Tarek",
        "title": "Array Specialist",
        "status": "Monitoring signal telemetry on hand slate",
        "trade_offered_id": "wire_spool",
        "trade_completed": false,
        "dialogue_idle": "Comms array on Beta is picking up anomalous seismic echoes from the lunar crater. Got steel dice or trade tokens? I have copper wire coils.",
        "dialogue_post_trade": "Deal. If you ever need remote terminals bypassed or signals boosted, signal me.",
        "companion_unlock": "comp_tarek",
        "trade_required_tags": [
          "barter_token"
        ],
        "dialogue_variants": [
          [
            "has_cap:signal_analysis",
            "You read the array bursts too? Then you know the tube is leaking. Trade tokens still buy my wire and my time."
          ]
        ]
      }
    },
    "placements": [
      {
        "entity_id": "shuttle_return",
        "row": 0,
        "col": 4
      },
      {
        "entity_id": "hatch_array",
        "row": 4,
        "col": 0
      },
      {
        "entity_id": "hatch_fuel",
        "row": 4,
        "col": 7
      },
      {
        "entity_id": "freight_crate",
        "row": 6,
        "col": 6
      },
      {
        "entity_id": "npc_tarek",
        "row": 3,
        "col": 3
      }
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
        "label": "Comms Hub",
        "gated_by_fixture": null,
        "requires_capability": null
      },
      "to_fuel": {
        "id": "to_fuel",
        "target_node_id": "stn_b_fuel",
        "label": "Fuel Spur",
        "gated_by_fixture": null,
        "requires_capability": null
      }
    },
    "description": "Wide docking bay with magnetic clamp rails. The air smells of fuel volatiles and industrial lubricant."
  },
  {
    "id": "stn_b_array",
    "name": "Comms Hub",
    "cluster": "station_beta",
    "size": 6,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {
      "pressure_kpa": 101.0,
      "radiation_msv": 0.2,
      "temperature_c": 20
    },
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hatch_dock": {
        "id": "hatch_dock",
        "glyph": "◆",
        "name": "Dock Hatch",
        "state": "open",
        "grants_edge": "to_dock",
        "on_use_effect": null,
        "description": "Corridor hatch leading back to Dock Ring Bay 7.",
        "required_tags": []
      },
      "comms_rack": {
        "id": "comms_rack",
        "glyph": "⌸",
        "name": "Radio Rack",
        "state": "active",
        "grants_edge": null,
        "on_use_effect": "log",
        "description": "Signal array intercepting transmissions across the orbit. Mentions high-grade ore found in the Lunar Lava Tube.",
        "required_tags": [],
        "log_text": "Intercepts across the orbit. Routine traffic between Beta dock and the lunar dome.",
        "log_text_locked": "Decoded burst from a surveyor beacon: breach in the lava tube wall, east of the ladder. Elastomer patch would hold it. Tube pressure recovers if sealed."
      },
      "crypto_terminal": {
        "id": "crypto_terminal",
        "glyph": "⌸",
        "name": "Relay Terminal",
        "state": "active",
        "grants_edge": null,
        "on_use_effect": "override",
        "description": "Encrypted relay terminal with exposed wiring. Bridging its relay with electrical wire prints a forged shift clearance.",
        "required_tags": [
          "electrical"
        ],
        "grants_capability": "dock_clearance"
      }
    },
    "actors": {},
    "placements": [
      {
        "entity_id": "hatch_dock",
        "row": 5,
        "col": 2
      },
      {
        "entity_id": "comms_rack",
        "row": 1,
        "col": 2
      },
      {
        "entity_id": "crypto_terminal",
        "row": 2,
        "col": 4
      }
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
    "description": "Hexagonal chamber packed with computing racks. Green status LEDs blink in rhythmic patterns."
  },
  {
    "id": "stn_b_fuel",
    "name": "Fuel Spur",
    "cluster": "station_beta",
    "size": 6,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {
      "pressure_kpa": 99.0,
      "radiation_msv": 1.0,
      "temperature_c": 22
    },
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hatch_dock_fuel": {
        "id": "hatch_dock_fuel",
        "glyph": "◆",
        "name": "Dock Hatch",
        "state": "open",
        "grants_edge": "to_dock",
        "on_use_effect": null,
        "description": "Blast door back to Dock Ring.",
        "required_tags": []
      },
      "fuel_manifold": {
        "id": "fuel_manifold",
        "glyph": "⌸",
        "name": "Fuel Gauges",
        "state": "active",
        "grants_edge": null,
        "on_use_effect": "log",
        "description": "High-pressure fuel injection lines running floor to ceiling.",
        "required_tags": [],
        "log_text": "Line pressures nominal. Placard: propellant crews eat on shift; bring your own rations.",
        "log_text_locked": "Refinery ledger: Kovac trades patches for food. Vance on the smelter floor pays in tools for raw ore."
      },
      "spares_cabinet": {
        "id": "spares_cabinet",
        "glyph": "⊞",
        "name": "Spares Cabinet",
        "state": "active",
        "grants_edge": null,
        "on_use_effect": "scavenge",
        "description": "Steel wall cabinet storing silicone seal patches.",
        "required_tags": [],
        "yields": [
          "seal_patch",
          "scrip_shift"
        ]
      }
    },
    "actors": {
      "npc_kovac": {
        "id": "npc_kovac",
        "glyph": "K",
        "name": "Kovac",
        "title": "Refinery Tech",
        "status": "Checking pressure gauges on propellant lines",
        "trade_offered_id": "seal_patch",
        "trade_completed": false,
        "dialogue_idle": "Shift's gone four hours past relief. Got a ration block? I can trade seal patches.",
        "dialogue_post_trade": "Much obliged. These patches will hold against pure vacuum if you blow a seal down on the pad.",
        "companion_unlock": null,
        "trade_required_tags": [
          "nutrition"
        ],
        "dialogue_variants": [
          [
            "party:comp_mira",
            "Is that Mira? Tell her the fuel spur air is fine. Rations still buy patches."
          ]
        ]
      }
    },
    "placements": [
      {
        "entity_id": "hatch_dock_fuel",
        "row": 5,
        "col": 2
      },
      {
        "entity_id": "fuel_manifold",
        "row": 1,
        "col": 2
      },
      {
        "entity_id": "spares_cabinet",
        "row": 2,
        "col": 1
      },
      {
        "entity_id": "npc_kovac",
        "row": 2,
        "col": 4
      }
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
    "description": "Processing bay filled with heavy fuel lines and hazard placards. Smell of solvent hangs in the air."
  },
  {
    "id": "luna_pad",
    "name": "Landing Pad",
    "cluster": "lunar_base",
    "size": 7,
    "depth": 0,
    "environment": "vacuum",
    "base_vitals": {
      "pressure_kpa": 0.0,
      "radiation_msv": 25.0,
      "temperature_c": -80
    },
    "grid_floor": "~",
    "grid_wall": "░",
    "fixtures": {
      "lander_hatch": {
        "id": "lander_hatch",
        "glyph": "=",
        "name": "Shuttle Hatch",
        "state": "open",
        "grants_edge": "to_shuttle",
        "on_use_effect": null,
        "description": "Ascent module hatch back to the shuttle shuttle.",
        "required_tags": []
      },
      "dome_airlock": {
        "id": "dome_airlock",
        "glyph": "◆",
        "name": "Dome Airlock",
        "state": "open",
        "grants_edge": "to_dome",
        "on_use_effect": null,
        "description": "Reinforced airlock cylinder leading into the pressurized habitat dome.",
        "required_tags": []
      },
      "regolith_sled": {
        "id": "regolith_sled",
        "glyph": "⊞",
        "name": "Old Survey Sled",
        "state": "active",
        "grants_edge": null,
        "on_use_effect": "scavenge",
        "description": "Unmanned lunar utility sled abandoned on the regolith. Contains basalt scrap.",
        "required_tags": [],
        "yields": [
          "scrap_metal"
        ],
        "restock": true
      }
    },
    "actors": {},
    "placements": [
      {
        "entity_id": "lander_hatch",
        "row": 0,
        "col": 3
      },
      {
        "entity_id": "dome_airlock",
        "row": 6,
        "col": 3
      },
      {
        "entity_id": "regolith_sled",
        "row": 3,
        "col": 4
      }
    ],
    "edges": {
      "to_shuttle": {
        "id": "to_shuttle",
        "target_node_id": "shuttle_ab",
        "label": "Shuttle",
        "gated_by_fixture": null,
        "requires_capability": null
      },
      "to_dome": {
        "id": "to_dome",
        "target_node_id": "luna_dome",
        "label": "Habitat Dome",
        "gated_by_fixture": null,
        "requires_capability": null
      }
    },
    "description": "Flat regolith landing apron under unfiltered stars. Gray dust covers the deck. Total vacuum silence."
  },
  {
    "id": "luna_dome",
    "name": "Habitat Dome",
    "cluster": "lunar_base",
    "size": 10,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {
      "pressure_kpa": 95.0,
      "radiation_msv": 3.0,
      "temperature_c": 17
    },
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "airlock_pad": {
        "id": "airlock_pad",
        "glyph": "◆",
        "name": "Pad Airlock",
        "state": "open",
        "grants_edge": "to_pad",
        "on_use_effect": null,
        "description": "Airlock back to the exposed lunar surface pad.",
        "required_tags": []
      },
      "hatch_smelter": {
        "id": "hatch_smelter",
        "glyph": "◆",
        "name": "Smelter Hatch",
        "state": "open",
        "grants_edge": "to_smelter",
        "on_use_effect": null,
        "description": "Reinforced hatch leading to the smelting floor.",
        "required_tags": []
      },
      "hatch_crater": {
        "id": "hatch_crater",
        "glyph": "◆",
        "name": "Crater Hatch",
        "state": "open",
        "grants_edge": "to_crater",
        "on_use_effect": null,
        "description": "Exterior airlock leading out to the crater observation rim.",
        "required_tags": []
      },
      "seismic_station": {
        "id": "seismic_station",
        "glyph": "⌸",
        "name": "Quake Monitor",
        "state": "active",
        "grants_edge": null,
        "on_use_effect": "log",
        "description": "Readouts confirm cavernous basalt structures beneath the crater floor.",
        "required_tags": [],
        "log_text": "Readouts confirm cavernous basalt structures beneath the crater floor.",
        "log_text_locked": "Seismic survey note: the mine cage takes two operators or one trained lifter. Mine air is thin and hot with radiation. Budget your exposure."
      },
      "dome_locker": {
        "id": "dome_locker",
        "required_tags": [],
        "grants_edge": null,
        "glyph": "⊞",
        "name": "Dome Locker",
        "state": "active",
        "on_use_effect": "scavenge",
        "yields": [
          "ration_dry"
        ],
        "description": "Shared crew locker by the airlock. Someone left a ration behind.",
        "restock": true
      },
      "seed_crate": {
        "id": "seed_crate",
        "required_tags": [],
        "grants_edge": null,
        "glyph": "⊞",
        "name": "Seed Crate",
        "state": "active",
        "on_use_effect": "scavenge",
        "yields": [
          "algae_paste"
        ],
        "description": "Cold-packed crate of starter cultures for the trays.",
        "restock": true
      },
      "dome_board": {
        "id": "dome_board",
        "required_tags": [],
        "grants_edge": null,
        "glyph": "⌸",
        "name": "Dome Board",
        "state": "active",
        "on_use_effect": "log",
        "log_text": "Dome roster: surface walks in pairs. Pad-to-airlock is the shortest run on this moon.",
        "log_text_locked": "Maintenance note: the lava tube breach vents into the crater. Seal it and the tube holds air.",
        "description": "Wall screen with crew rosters and surface forecasts."
      },
      "hydro_tray": {
        "id": "hydro_tray",
        "required_tags": [
          "bio_filter"
        ],
        "grants_edge": null,
        "glyph": "⚲",
        "name": "Hydroponic Tray",
        "state": "active",
        "on_use_effect": "harvest",
        "yields": [
          "algae_paste"
        ],
        "description": "Shallow tray of algae under daylight panels. Filter work needs a trained hand or a spanner.",
        "restock": true
      },
      "dome_tap": {
        "id": "dome_tap",
        "required_tags": [
          "refillable"
        ],
        "grants_edge": null,
        "glyph": "⚲",
        "name": "Dome Water Tap",
        "state": "active",
        "on_use_effect": "refill",
        "description": "Recycled water tap. Fills any canteen."
      },
      "dome_bunk": {
        "id": "dome_bunk",
        "glyph": "▭",
        "name": "Dome Bunk",
        "state": "active",
        "required_tags": [],
        "grants_edge": null,
        "on_use_effect": "sleep",
        "description": "Spare bunk behind a privacy curtain. Sleep here to start a new day."
      }
    },
    "actors": {
      "npc_chen": {
        "id": "npc_chen",
        "glyph": "O",
        "name": "Olena Chen",
        "title": "Field Geologist",
        "status": "Analyzing core samples from deep mine",
        "trade_offered_id": "tool_spanner",
        "trade_completed": false,
        "dialogue_idle": "The volcanic tube below the crater is rich with ancient minerals. Bring me scrap from the surface sled and I will trade specialized tools.",
        "dialogue_post_trade": "Excellent material. If you descend into the crater or lava tube, watch your pressure gauge; the cold contracts valve seals rapidly.",
        "companion_unlock": null,
        "trade_required_tags": [
          "salvage"
        ],
        "dialogue_variants": [
          [
            "visited:luna_tube",
            "You've been in the tube. Did you see the east wall? That seam is venting. Scrap buys you a spanner."
          ]
        ]
      }
    },
    "placements": [
      {
        "entity_id": "airlock_pad",
        "row": 0,
        "col": 5
      },
      {
        "entity_id": "hatch_smelter",
        "row": 5,
        "col": 0
      },
      {
        "entity_id": "hatch_crater",
        "row": 5,
        "col": 9
      },
      {
        "entity_id": "seismic_station",
        "row": 2,
        "col": 6
      },
      {
        "entity_id": "npc_chen",
        "row": 3,
        "col": 3
      },
      {
        "entity_id": "dome_locker",
        "row": 8,
        "col": 1
      },
      {
        "entity_id": "seed_crate",
        "row": 8,
        "col": 2
      },
      {
        "entity_id": "dome_board",
        "row": 2,
        "col": 7
      },
      {
        "entity_id": "hydro_tray",
        "row": 7,
        "col": 7
      },
      {
        "entity_id": "dome_tap",
        "row": 7,
        "col": 8
      },
      {
        "entity_id": "dome_bunk",
        "row": 8,
        "col": 8
      }
    ],
    "edges": {
      "to_pad": {
        "id": "to_pad",
        "target_node_id": "luna_pad",
        "label": "Landing Pad",
        "gated_by_fixture": null,
        "requires_capability": null
      },
      "to_smelter": {
        "id": "to_smelter",
        "target_node_id": "luna_smelter",
        "label": "Smelter",
        "gated_by_fixture": null,
        "requires_capability": null
      },
      "to_crater": {
        "id": "to_crater",
        "target_node_id": "luna_crater",
        "label": "Crater Rim",
        "gated_by_fixture": null,
        "requires_capability": null
      }
    },
    "description": "Geodesic dome with hydroponic trays and artificial daylight panels. Safe haven from vacuum."
  },
  {
    "id": "luna_smelter",
    "name": "Smelter",
    "cluster": "lunar_base",
    "size": 8,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {
      "pressure_kpa": 93.0,
      "radiation_msv": 5.0,
      "temperature_c": 35
    },
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hatch_dome_smelter": {
        "id": "hatch_dome_smelter",
        "glyph": "◆",
        "name": "Dome Hatch",
        "state": "open",
        "grants_edge": "to_dome",
        "on_use_effect": null,
        "description": "Corridor back to the habitat dome.",
        "required_tags": []
      },
      "mine_shaft": {
        "id": "mine_shaft",
        "glyph": "⎅",
        "name": "Mine Lift",
        "state": "locked",
        "grants_edge": "to_mine",
        "on_use_effect": "unlock",
        "description": "Heavy industrial lift descending into the deep mining shaft. Requires two operators.",
        "required_tags": [
          "two_person_lift",
          "heavy_lift"
        ]
      },
      "smelting_crucible": {
        "id": "smelting_crucible",
        "glyph": "■",
        "name": "Crucible",
        "state": "active",
        "grants_edge": null,
        "on_use_effect": "smelt",
        "description": "Induction furnace capable of refining raw basalt ore into structural fittings and tools.",
        "required_tags": []
      }
    },
    "actors": {
      "npc_vance": {
        "id": "npc_vance",
        "glyph": "V",
        "name": "Vance",
        "title": "Smelter Veteran",
        "status": "Stoking the induction coils",
        "trade_offered_id": "tool_prybar",
        "trade_completed": false,
        "dialogue_idle": "Deep mine has plenty of raw basalt ore, but the lift needs nerve to ride. Bring me an ore sample and I'll forge you a heavy pry-bar.",
        "dialogue_post_trade": "Clean melt. Here's your iron bar. Treat it right and it'll crack open any sealed hatch on this moon.",
        "companion_unlock": null,
        "trade_required_tags": [
          "mineral"
        ],
        "dialogue_variants": [
          [
            "visited:luna_mine",
            "You rode the cage and came back. Hand me a core of that ore and I'll forge you a bar."
          ]
        ]
      }
    },
    "placements": [
      {
        "entity_id": "hatch_dome_smelter",
        "row": 0,
        "col": 4
      },
      {
        "entity_id": "mine_shaft",
        "row": 7,
        "col": 4
      },
      {
        "entity_id": "smelting_crucible",
        "row": 4,
        "col": 1
      },
      {
        "entity_id": "npc_vance",
        "row": 4,
        "col": 6
      }
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
    "description": "Industrial floor vibrating with furnace hum. Fine ore dust settles on every surface. Dry heat."
  },
  {
    "id": "luna_crater",
    "name": "Crater Rim",
    "cluster": "lunar_base",
    "size": 6,
    "depth": 0,
    "environment": "vacuum",
    "base_vitals": {
      "pressure_kpa": 0.0,
      "radiation_msv": 30.0,
      "temperature_c": -120
    },
    "grid_floor": "~",
    "grid_wall": "░",
    "fixtures": {
      "hatch_dome_crater": {
        "id": "hatch_dome_crater",
        "glyph": "◆",
        "name": "Dome Hatch",
        "state": "open",
        "grants_edge": "to_dome",
        "on_use_effect": null,
        "description": "Airlock back to the pressurized habitat dome.",
        "required_tags": []
      },
      "tube_entrance": {
        "id": "tube_entrance",
        "glyph": "⎅",
        "name": "Ladder Down",
        "state": "open",
        "grants_edge": "to_tube",
        "on_use_effect": null,
        "description": "Ladder and winch system descending into a vast subsurface volcanic tube.",
        "required_tags": []
      },
      "surveyor_cache": {
        "id": "surveyor_cache",
        "glyph": "⊞",
        "name": "Survey Cache",
        "state": "active",
        "grants_edge": null,
        "on_use_effect": "scavenge",
        "description": "Pressurized container bolted to the crater rim containing emergency rations.",
        "required_tags": [],
        "yields": [
          "ration_dry"
        ],
        "restock": true
      }
    },
    "actors": {},
    "placements": [
      {
        "entity_id": "hatch_dome_crater",
        "row": 0,
        "col": 3
      },
      {
        "entity_id": "tube_entrance",
        "row": 5,
        "col": 3
      },
      {
        "entity_id": "surveyor_cache",
        "row": 2,
        "col": 2
      }
    ],
    "edges": {
      "to_dome": {
        "id": "to_dome",
        "target_node_id": "luna_dome",
        "label": "Habitat Dome",
        "gated_by_fixture": null,
        "requires_capability": null
      },
      "to_tube": {
        "id": "to_tube",
        "target_node_id": "luna_tube",
        "label": "Lava Tube",
        "gated_by_fixture": null,
        "requires_capability": null
      }
    },
    "description": "Narrow pathway carved along the rim of an ancient impact crater. Earth hangs silent in the black sky."
  },
  {
    "id": "luna_mine",
    "name": "Deep Mine",
    "cluster": "lunar_base",
    "size": 6,
    "depth": 1,
    "environment": "depressurizing",
    "base_vitals": {
      "pressure_kpa": 50.0,
      "radiation_msv": 15.0,
      "temperature_c": -30
    },
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "cage_up": {
        "id": "cage_up",
        "glyph": "⎅",
        "name": "Mine Lift Up",
        "state": "open",
        "grants_edge": "to_smelter",
        "on_use_effect": null,
        "description": "Cage lift ascending back to Smelter Flat.",
        "required_tags": []
      },
      "ore_face": {
        "id": "ore_face",
        "glyph": "⊞",
        "name": "Ore Face",
        "state": "active",
        "grants_edge": null,
        "on_use_effect": "scavenge",
        "description": "Dark basalt vein rich in metallic deposits. Yields high-grade lunar ore.",
        "required_tags": [],
        "yields": [
          "ore_sample"
        ],
        "restock": true
      }
    },
    "actors": {},
    "placements": [
      {
        "entity_id": "cage_up",
        "row": 0,
        "col": 2
      },
      {
        "entity_id": "ore_face",
        "row": 4,
        "col": 2
      }
    ],
    "edges": {
      "to_smelter": {
        "id": "to_smelter",
        "target_node_id": "luna_smelter",
        "label": "Smelter (up)",
        "gated_by_fixture": null,
        "requires_capability": null
      }
    },
    "description": "Subterranean gallery hacked into basalt rock. Cold creeps from the dark excavation walls."
  },
  {
    "id": "luna_tube",
    "name": "Lava Tube",
    "cluster": "lunar_base",
    "size": 8,
    "depth": 1,
    "environment": "low_temp",
    "base_vitals": {
      "pressure_kpa": 40.0,
      "radiation_msv": 8.0,
      "temperature_c": -45
    },
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "ascent_ladder": {
        "id": "ascent_ladder",
        "glyph": "⎅",
        "name": "Ladder Up",
        "state": "open",
        "grants_edge": "to_crater",
        "on_use_effect": null,
        "description": "Steel ladder ascending back up to the crater observation rim.",
        "required_tags": []
      },
      "subsurface_cache": {
        "id": "subsurface_cache",
        "glyph": "⊞",
        "name": "Buried Cache",
        "state": "active",
        "grants_edge": null,
        "on_use_effect": "scavenge",
        "description": "Canister containing historic tally slates and emergency supplies left by early prospectors.",
        "required_tags": [],
        "yields": [
          "slate_tally"
        ]
      },
      "hull_breach": {
        "id": "hull_breach",
        "glyph": "■",
        "name": "Cracked Wall",
        "state": "disabled",
        "required_tags": [
          "vacuum_seal"
        ],
        "grants_edge": null,
        "on_use_effect": "repair",
        "on_repair_vitals": {
          "pressure_kpa": 78.0,
          "radiation_msv": 8.0,
          "temperature_c": -20
        },
        "description": "A crack in the tube wall hissing air out into the crater. An elastomer patch would hold it."
      }
    },
    "actors": {},
    "placements": [
      {
        "entity_id": "ascent_ladder",
        "row": 0,
        "col": 4
      },
      {
        "entity_id": "subsurface_cache",
        "row": 4,
        "col": 3
      },
      {
        "entity_id": "hull_breach",
        "row": 6,
        "col": 6
      }
    ],
    "edges": {
      "to_crater": {
        "id": "to_crater",
        "target_node_id": "luna_crater",
        "label": "Crater Rim (up)",
        "gated_by_fixture": null,
        "requires_capability": null
      }
    },
    "description": "Vast natural cavern formed by ancient lava flows. Smooth curved basalt walls vanish into cold darkness."
  }
]
```

### 9.3 Companions Reference (`companions.json`)

```json
[
  {
    "id": "comp_radek",
    "name": "Radek",
    "title": "Cargo Rigger",
    "status": "Ready to work",
    "capability_tag": "two_person_lift"
  },
  {
    "id": "comp_tarek",
    "name": "Tarek",
    "title": "Array Specialist",
    "status": "Scanning telemetry",
    "capability_tag": "signal_boost"
  },
  {
    "id": "comp_mira",
    "name": "Mira",
    "title": "Hab Botanist",
    "status": "Monitoring filters",
    "capability_tag": "bio_filter"
  }
]
```

### 9.4 Work Skills Reference (`skills.json`)

```json
[
  {
    "id": "engineering",
    "name": "Engineering",
    "earned_by": "Opening, repairing, bypassing and smelting.",
    "perks": [
      {
        "level": 2,
        "xp": 30,
        "grants": "seam_discipline",
        "text": "Inspecting shows whether you can fix it, and with what."
      },
      {
        "level": 3,
        "xp": 90,
        "grants": "scrap_fabrication",
        "text": "Forge pry-bars from ore at the smelter."
      },
      {
        "level": 4,
        "xp": 180,
        "grants": "bulkhead_ear",
        "text": "Hear the air behind a door before you open it."
      },
      {
        "level": 5,
        "xp": 300,
        "grants": "conduit_mastery",
        "text": "Tools don't wear on pipe and valve work."
      }
    ]
  },
  {
    "id": "survival",
    "name": "Survival",
    "earned_by": "Time spent in cold, thin air or radiation.",
    "perks": [
      {
        "level": 2,
        "xp": 30,
        "grants": "cold_bypass",
        "text": "Cold builds up half as fast."
      },
      {
        "level": 3,
        "xp": 90,
        "grants": "vacuum_walk",
        "text": "Low pressure builds up half as fast."
      },
      {
        "level": 4,
        "xp": 180,
        "grants": "deep_well",
        "text": "Radiation builds up half as fast."
      },
      {
        "level": 5,
        "xp": 300,
        "grants": "trench_hardened",
        "text": "You can take 5 more of everything before blacking out."
      }
    ]
  },
  {
    "id": "logistics",
    "name": "Logistics",
    "earned_by": "Searching, trading, harvesting and deliveries.",
    "perks": [
      {
        "level": 2,
        "xp": 30,
        "grants": "scavenger_instinct",
        "text": "Find extra scrap when searching."
      },
      {
        "level": 3,
        "xp": 90,
        "grants": "crew_coordination",
        "text": "Your team shields you: every track builds up 0.2 slower."
      },
      {
        "level": 4,
        "xp": 180,
        "grants": "signal_analysis",
        "text": "Read the scrambled parts of logs and boards."
      },
      {
        "level": 5,
        "xp": 300,
        "grants": "wayfarer",
        "text": "Food lasts twice as long and shuttle rides are free."
      }
    ]
  }
]
```

### 9.5 Daily Jobs Reference (`jobs.json`)

```json
[
  {
    "id": "job_scrap_bin",
    "title": "Empty the Berth 04 scrap bin",
    "kind": "use",
    "target": "salvage_bin",
    "skill": "logistics",
    "xp": 15,
    "reward_items": [
      "scrip_shift"
    ]
  },
  {
    "id": "job_algae_vat",
    "title": "Harvest the Hab Ring algae vat",
    "kind": "use",
    "target": "algae_basin",
    "skill": "logistics",
    "xp": 15,
    "reward_items": [
      "ration_dry"
    ]
  },
  {
    "id": "job_sub_patrol",
    "title": "Walk a 6-turn patrol in the Sub-Deck",
    "kind": "stay",
    "target": "stn_a_sub",
    "count": 6,
    "skill": "engineering",
    "xp": 25,
    "reward_items": [
      "seal_patch"
    ]
  },
  {
    "id": "job_scrap_smelter",
    "title": "Deliver 2 Scrap Metal to the Smelter",
    "kind": "deliver",
    "target": "luna_smelter",
    "item": "scrap_metal",
    "count": 2,
    "skill": "logistics",
    "xp": 40,
    "reward_items": [
      "chit_transit"
    ]
  },
  {
    "id": "job_paste_fuel",
    "title": "Bring Algae Paste to the Fuel Spur",
    "kind": "deliver",
    "target": "stn_b_fuel",
    "item": "algae_paste",
    "count": 1,
    "skill": "logistics",
    "xp": 25,
    "reward_items": [
      "ration_dry"
    ]
  },
  {
    "id": "job_ore_core",
    "title": "Cut a core at the Deep Mine ore face",
    "kind": "use",
    "target": "ore_face",
    "skill": "survival",
    "xp": 30,
    "reward_items": [
      "chit_transit"
    ]
  },
  {
    "id": "job_quake_check",
    "title": "Log the Habitat Dome quake monitor",
    "kind": "use",
    "target": "seismic_station",
    "skill": "engineering",
    "xp": 10,
    "reward_items": [
      "scrip_shift"
    ]
  },
  {
    "id": "job_sled_salvage",
    "title": "Strip the old survey sled on the Landing Pad",
    "kind": "use",
    "target": "regolith_sled",
    "skill": "survival",
    "xp": 20,
    "reward_items": [
      "seal_patch"
    ]
  },
  {
    "id": "job_tray_harvest",
    "title": "Harvest the Habitat Dome tray",
    "kind": "use",
    "target": "hydro_tray",
    "skill": "logistics",
    "xp": 15,
    "reward_items": [
      "scrip_shift"
    ]
  }
]
```

---

## 10. Grid Rendering Algorithm

The renderer constructs the N×N grid dynamically from node definitions and entity placements rather than storing static string matrices:

```python
def build_grid(node: Node, player_row: int, player_col: int) -> Tuple[str, ...]:
    """Construct N×N grid rows from node walls, floor, and entity placements."""
    n = node.size
    grid = [[node.grid_floor] * n for _ in range(n)]

    # Border walls
    for r in range(n):
        grid[r][0] = node.grid_wall
        grid[r][n - 1] = node.grid_wall
    for c in range(n):
        grid[0][c] = node.grid_wall
        grid[n - 1][c] = node.grid_wall

    # Place entities
    for placement in node.placements:
        entity_id = placement.entity_id
        glyph = "?"
        if entity_id in node.fixtures:
            glyph = node.fixtures[entity_id].glyph
        elif entity_id in node.actors:
            glyph = node.actors[entity_id].glyph
        grid[placement.row][placement.col] = glyph

    # Overlay player cursor with ANSI invert on overlap
    r, c = player_row, player_col
    if 0 <= r < n and 0 <= c < n:
        underlying = grid[r][c]
        if underlying == node.grid_floor:
            grid[r][c] = "@"
        else:
            grid[r][c] = f"\033[7m{underlying}\033[0m"

    return tuple(" ".join(row) for row in grid)
```

---
