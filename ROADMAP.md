# Roadmap

The plan for rebuilding the engine on content packs. [VISION.md](VISION.md) says what
the game is; [README.md](README.md) documents the schemas; [AGENTS.md](AGENTS.md)
says how to work on the project.

## Where things stand

- [x] Vision agreed and recorded
- [x] Complete schema set, validator (`core/pack.py`) and tools (`core/packtool.py`)
- [x] Generic test pack (`packs/test`) that uses every part of the schemas
- [x] Milestone 0: foundations
- [x] Milestone 1: state and grammar
- [ ] Engine rebuild: milestones 2–7 below
- [ ] **Version 1.0**: the first clean version of the game, after milestone 7

## Principles

- **A new `engine/` package alongside the old `core/`.** The old game keeps working
  until the new one can do more; then it is deleted. No half-converted modules.
- **Nothing but packs.** The engine loads a pack through the validator and refuses
  an invalid one. Engine work runs against `packs/test`.
- **Pure functions and immutable state.** Action + state → new state; the renderer
  is a pure function of state. Every rule is testable and every game replayable.
- **Randomness lives in the state** (the seed plus a counter), so the same save and
  inputs always give the same result.
- **Saves store only what changed**, plus the pack's id and version. Content is never
  copied into a save.
- **Parts of the old UI worth keeping:** raw key input, text width and wrapping, the
  six-zone frame, styles (extended to the grade palette), atomic saving.

## Milestones

Every milestone ends with something that runs and is tested, and with two chores:

- **Update the docs:** mark the milestone done here, and update README.md and
  AGENTS.md wherever what they describe changed.
- **Prune the old design document:** remove the parts of
  `System Architecture & Game Design Document.md` that the milestone made obsolete.
  Keep what still describes the running old engine. Its section 9 is checked by
  `tests/test_gdd_sync.py`; remove the matching test when a section is removed.

### 0. Foundations ✓

- `engine/` package layout.
- Read a validated pack into typed, read-only `Content`; id lookups.
- Seeded randomness.
- Done when: the test pack loads into `Content`, and an invalid pack is refused
  with the validator's messages.
- Delivered: `engine/content.py` (`load_pack`, `Content`, `PackError`; every schema
  default filled in at load by `core.schema.apply_defaults`; placements merged with
  their templates), `engine/rng.py`, `engine/frozen.py`. A test keeps any pack id out
  of engine code.

### 1. State and grammar ✓

- `GameState`: characters (the player is one), placement states, flags, relations,
  parties, time, randomness, messages.
- Derived stats: body + frame + modules + implants + skills.
- Condition evaluator for every check; effect interpreter for every effect outside
  encounters.
- Messages through the pack's strings.
- Done when: every check and every non-encounter effect has a test against the test
  pack.
- Delivered: `engine/state.py` (`GameState`, `CharState`, `ItemInst`, `new_game`,
  time), `engine/stats.py` (derived stats, tags, size, budgets, cargo, item views
  with modifications), `engine/context.py` (subjects, agents, relations with faction
  fallback, item picks, amounts), `engine/conditions.py` (all 19 checks),
  `engine/effects.py` (all effects; `choose` pauses and resumes; `start_encounter`
  and `trigger_event` leave requests for milestones 4 and 6). The rules decided here
  are in README.md, "How the engine applies the grammar".
- Carried into milestone 2: an arrival on a solid object's tile (the test pack starts
  the player on the crate) should be placed next to it; `spend_time` should run the
  per-turn processing.

### 2. Walkable world

- Grid movement, solid objects, the menu built from interactions (`shown_if`,
  `requires`, hints, keys), exits, `on_enter` / `on_turn`, time and phases.
- The six-zone screen, the input loop, saving and loading.
- Done when: the test pack is playable. Walk room A → room B, open doors, search the
  crate, take hazard damage, talk to the NPC and recruit them.

### 3. Build

- Inventory and cargo, the fitting board, fitting and removing within budgets,
  refitting only at `refit` workshops, frame size against `holds_size`.
- Skills and experience.
- Done when: modules and frames can be swapped, and the budget and size rules behave
  as the validator predicts.

### 4. Encounters

- Encounter state, turn order (initiative and priority), action tiles in Zone 4.
- Costs (heat, cooldown, charges, consumed items), statuses, overheating.
- AI choice and intent, art in Zone 2, retreat, win / lose / escape, loot,
  `on_defeat`.
- Done when: the test pack's drone encounter can be played to each of its three
  outcomes.

### 5. Crafting

- Workshops: dismantle and learn designs, fabricate, modify, repair.
- Done when: the test tool can be dismantled, learned, fabricated, reinforced and
  repaired.

### 6. Living world

- The event engine: triggers, cast, chance, weight, cooldown, notify.
- Off-screen characters moved only by events.
- Done when: the grudge and off-screen rivalry events fire with different casts
  under different seeds.

### 7. First game pack → version 1.0

- Write Station A, the shuttle and the Moon as `packs/game`, in the new format and
  to the new design.
- Delete the old engine (`core/` modules the new engine replaced, `ui/`, the old
  `main.py`) and the old design document.
- Tag the result as **version 1.0**.

## After 1.0

- Content work happens mostly in game packs, under the user's guidance, following
  [AGENTS.md](AGENTS.md).
- Engine changes are small and incremental, and follow the schema-first workflow:
  schema → test pack → engine with tests → game pack.
- Reserved features wait for their own design: procedural zones, ships as moving
  regions, mods (`extends`).
