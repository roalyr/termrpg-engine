# Design: a genre-agnostic engine (milestone 8)

Status: **Decided** (2026-10-11): the big picture (Q1–Q3) and the details below.


## Goal

The same engine plays a sci-fi RPG and a classical fantasy RPG equally well. Proof:
two test packs, `packs/test_scifi` and `packs/test_fantasy`, each using every part of
the schemas, with the engine tests run against both.

## The fantasy test pack

The same shape as the sci-fi pack, so each feature has a twin in the other genre.

| Feature | Sci-fi (today) | Fantasy |
|---|---|---|
| Two rooms joined by a door | Workshop, storage | Smithy, cellar |
| A hazard and the gear that stops it | Gas leak, air filter | Damp cold, a fur cloak |
| Something worn that sets where you go | Work suit, heavy frame | Leather armour, plate (too big for the cellar stairs) |
| Gear in slots | Cutter, drill in hand slots | Sword, shield in hand slots, without armour too |
| Something in the body | Implant | A blessing or a tattoo |
| What limits a loadout | Power, mass | Weight (and nothing else) |
| What actions cost | Heat that builds up | Mana that is spent, stamina that builds up |
| A workshop | Workbench: repair, take apart, make, modify | Forge and an altar (the altar adds runes) |
| Where gear changes | Suits only at the bay | Weapons anywhere, armour anywhere, blessings only at the altar |
| A person who trades and joins | Juno | A hedge witch |
| Enemies, loot, defeat, rescue | Drones | Rats or a skeleton |
| Events and rest | Morning restock, rest | The same |

## What changes in the engine

Four changes, each removing an assumption that only suits make true. Each one merges
or loosens what exists rather than adding a layer.

**1. Gear without a frame.** Today modules fit only into a frame's slots, and implants
only into the body's. Proposal: a slot is a slot, wherever it comes from. The body
and the worn frame both provide slots of any slot type, and any slotted item fits a
slot of its type. The frame becomes gear in a worn slot that adds slots, stats and a
size. Modules and implants then differ only in their slot types, so they become one
kind.

**2. Budgets the pack declares.** Today the vocabulary must name exactly one stat each
for power, mass and heat, and an item's `uses` knows only power and mass. Proposal: a
stat can be marked as a budget (any number of them, or none); gear `uses` any budget
stat; the loadout must stay within each. Health, initiative and cargo keep their
roles: every genre has them.

**3. Costs on any pool.** Today an action's only resource cost is heat, which builds up
and overheats. Proposal: a pool stat says how it behaves: it **fills** (heat,
fatigue: at its maximum the character loses a turn, as now) or it **drains** (mana,
ammunition: an action that can't pay is refused). An action's cost names the pool
and the amount; gear can still put a constant load on a filling pool.

**4. Where gear can change.** Today any change of frame, module or implant needs a
workshop offering `refit`. Proposal: each slot type (and the frame) says whether it
changes anywhere or only at a workshop offering a given service.

## Naming

Field and kind names (`frame`, `module`, `implant`, `refit`, `salvage`, `fitting`) are
seen by pack authors. The changes above break packs anyway, so they are renamed to
neutral words now (Q2; see "The new words").

## Not in this milestone

Currency and shops, spell schools, mounts, travel between regions, wide-terminal
layouts. They are genre-neutral gaps, not genre assumptions, and come later as maker
features proven in both packs.

## Order of work

1. Agree this page, then each change in a little more detail.
2. Schema changes for all four, as one major schema version; the sci-fi pack updated
   to match.
3. The fantasy test pack, written against the new schemas.
4. Engine, validator, tools and UI, with the tests run against both packs.
5. README, AGENTS.md (recipes) and the playtest updated.

## Decided

- **Q1.** Modules and implants merge into one kind.
- **Q2.** Author-facing words are renamed now, in the same schema version.
- **Q3.** The frame is not a special item: it is gear in a "worn" slot that adds slots
  and sets its wearer's size.
- **Q4.** Open: the fantasy pack's shape above is a working draft, to revisit while
  writing it.

## Details

### The new words

| Today | Proposed | Why |
|---|---|---|
| item kinds `frame`, `module`, `implant` | one kind, `gear` | Q1 and Q3: anything that goes into a slot |
| character `frame`, `fitted`, `implants` | one list, `equipped` | Every slot is alike; where an item sits follows from its slot type |
| `fit_requires` | `equip_requires` | |
| `has_item` source `fitted` | `equipped` | |
| workshop service `refit` | `equip` | Changing gear, where a slot type needs a workshop |
| workshop service `fabricate`, item field `fabricate` | `make` | Neutral: forging, sewing, printing |
| item field `salvage` | `dismantle` | Matches the service of the same name |
| effect `unlock_slot` (implant slots) | `unlock_slot` (any body slot) | Same name, wider meaning |
| stat roles `power`, `mass`, `heat` | removed: budgets and pools are declared (below) | |
| action `cost.heat` | `cost.pools` | |
| UI words "Suit", "Fitting", "Module", "Implant" | "Gear", "Equipment" | Default UI pack only; a game pack's UI pack can say "Suit" again |

Code keeps its internal names where renaming would only churn (`build.py`, variable
names); what authors and players read changes.

### 1. Slots and gear

- **Slot types lose `host`.** A slot type is just a type: `slot_worn`, `slot_hand`,
  `slot_neural`.
- **Slots come from the body and from equipped gear.** `body.slots` lists any slot types
  (today: only implant slots). Gear may have `slots` too: a suit adds hand slots, a belt
  adds pouch slots.
- **Gear fits a free slot of its `slot_type`,** wherever the slot comes from. Gear that
  provides slots can't be taken off while something is in them (as with frames today).
- **`worn_size`** on gear: while it is equipped, its wearer counts as that size class
  (doors, rooms, the `size` check). Without any, the body's size counts; with several,
  the largest.
- In the sci-fi pack, the body has one worn slot and its implant slots; the suit adds
  the hand slots, so tools still need a suit. In the fantasy pack, the body has hands,
  a worn slot and a neck slot.

### 2. Budgets

- **A stat can be a budget** (`"budget": true`). Gear `uses` any budget stats
  (`"uses": {"stat_weight": 3}`). What the body, gear and skill levels add to a budget
  stat is what's available; what equipped gear uses must stay within it.
- Any number of budget stats, or none. The fantasy pack has one (weight); the sci-fi
  pack keeps power and mass.
- `health`, `initiative` and `cargo` keep their roles: every genre has them.

### 3. Pools and costs

- **A pool either drains or fills** (`"fills": true` for the second):
  - *draining* (health, mana, ammunition): costs and damage lower it; an action whose
    cost it can't pay is refused; at 0 a health pool downs its character;
  - *filling* (heat, fatigue): costs raise it; at its maximum the character loses
    their next action and the pool falls back to its resting value (today's
    overheating).
- **`uses` on a filling pool is a constant load:** its resting value, as gear's heat is
  today.
- **`per_round`** (optional): how far the pool moves back toward rest each round
  (heat cools, mana returns). After an encounter, filling pools rest; draining pools
  only return through effects (rest events, potions), as health does today.
- **An action's cost names its pools:** `"cost": {"pools": {"stat_mana": 4}}`. Cooldown,
  charges and consumed items stay as they are.

### 4. Where gear changes

- **A slot type may need a workshop:** `"equip_at_workshop": true`. Gear in such a slot
  is equipped or taken off only within reach of a workshop offering `equip`;
  everything else changes anywhere.
- A workshop's `equip` can be limited to some slot types (`"equip_slot_types"`), so a
  suit bay changes suits but not implants, and an altar gives blessings but not
  armour.

### What else moves with it

- The sci-fi test pack is migrated to the new words, with the same behaviour.
- The validator's loadout check (`lib/budgets.py`), the gear screen (today's fitting
  screen), the loadout and entries editors, README, AGENTS.md's recipes and the
  playtest follow.
- One schema version for all of it (3), and a major version of the sci-fi pack.
