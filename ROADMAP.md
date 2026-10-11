# Roadmap

What's done and what's next. [VISION.md](VISION.md) says what the engine is for;
[README.md](README.md) documents the schemas; [AGENTS.md](AGENTS.md) says how to work
on the project. What each finished milestone delivered is in the git history.

## Where things stand

- [x] Vision agreed and recorded
- [x] Schemas, validator (`core/pack.py`) and tools (`core/packtool.py`)
- [x] Generic test pack (now `packs/test_scifi`) that uses every part of the schemas
- [x] Milestone 0: foundations (packs load into typed content, seeded randomness)
- [x] Milestone 1: state and grammar (every check and effect)
- [x] Milestone 2: walkable world, saving and loading
- [x] Milestone 3: build (fitting, budgets, refitting at workshops)
- [x] Milestone 4: encounters
- [x] Milestone 5: crafting
- [x] Milestone 6: living world (events and casts)
- [x] UI packs: the look, layout, keys and the UI's words as data
- [x] Hardening: random play, a code review and its fixes, plain names in the test pack
- [x] Milestone 7: UI overhaul (every screen, sub-window and menu)
- [x] Pack editors (`python3 editor.py`), the map screen, pictures in the art file,
  shared code in `lib/`
- [ ] Milestone 8: a genre-agnostic engine, with sci-fi and fantasy test packs
- [ ] **Version 1.0**: the first clean version of the engine and tools, after milestone 8

## Principles

- **Nothing but packs.** The engine loads a pack through the validator and refuses
  an invalid one. Engine work runs against the test packs.
- **Pure functions and immutable state.** Action + state → new state; the renderer
  is a pure function of state. Every rule is testable and every game replayable.
- **Randomness lives in the state** (the seed plus a counter), so the same save and
  inputs always give the same result.
- **Saves store only what changed**, plus the pack's id and version. Content is never
  copied into a save.
- **Every milestone ends with something that runs and is tested,** and with the docs
  updated: tick it off here, and update README.md and AGENTS.md wherever what they
  describe changed.

## 8. A genre-agnostic engine → version 1.0

The engine should build a sci-fi RPG and a classical fantasy RPG equally well.
Games, starting with `vanilla` (now in `archive/`), move to their own repositories.

1. **Design, big picture first** ([docs/design/genre-agnostic.md](docs/design/genre-agnostic.md)):
   a fantasy test pack, and the generalizations agreed against both genres:
   - gear without a frame: the body provides equipment slots, and the frame (suit,
     armour) becomes an optional worn layer;
   - budgets the pack declares, instead of fixed power, mass and heat;
   - action costs on any pool stat, either building up to a limit (heat, fatigue) or
     spent down (mana, ammunition);
   - where gear can be changed: per slot type or item kind, not only at workshops.
2. **Build it schema first,** one change at a time. The changes break existing packs:
   one major schema version for all of them.
3. **Two test packs,** each using every part of the schemas: sci-fi
   (`packs/test_scifi`) and fantasy (`packs/test_fantasy`). Engine tests run against both.
4. **Delete the old engine** (the `core/` modules the new engine replaced, `ui/`, the
   old `main.py`), the old design document and `tests/test_gdd_sync.py`.
5. Tag the result as **version 1.0**.

## After 1.0

- **Tools and features for makers:** grow, step by step, a set of tools that is
  versatile and intuitive for any genre. Each feature is proven in both test packs.
- Engine changes are small and incremental, and follow the schema-first workflow:
  schema → test pack → engine with tests → game pack.
- **Layouts for wide terminals** (lists and details side by side) are a milestone of
  their own, since every screen and window would need them. Until then there is one
  stacked layout for every terminal.
- **Known gap:** a `choose` inside an action's effects doesn't pause the round.
- Reserved features wait for their own design: procedural zones, moving regions
  (ships, caravans), mods (`extends`).
