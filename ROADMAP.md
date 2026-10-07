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
- [x] Milestone 2: walkable world (`python3 play.py`)
- [x] Milestone 3: build
- [x] Milestone 4: encounters
- [x] Milestone 5: crafting
- [x] Milestone 6: living world
- [x] UI packs: the look, layout, keys and the UI's words as data
- [x] Hardening: random play, a code review and its fixes, plain names in the test pack
- [ ] Milestone 7: UI overhaul
- [ ] Milestone 8: first game pack
- [ ] **Version 1.0**: the first clean version of the game, after milestone 8

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

### 2. Walkable world ✓

- Grid movement, solid objects, the menu built from interactions (`shown_if`,
  `requires`, hints, keys), exits, `on_enter` / `on_turn`, time and phases.
- The six-zone screen, the input loop, saving and loading.
- Done when: the test pack is playable. Walk room A → room B, open doors, search the
  crate, take hazard damage, talk to the NPC and recruit them.
- Delivered: `engine/world.py` (tiles, movement, focus, the menu, interactions, exits,
  talk, inspect), `engine/turns.py` (per-turn processing and owed time),
  `engine/save.py` (JSON saves tied to the pack's id and major version), the terminal
  UI in `tui/` and `play.py`. New engine message keys for the UI's words.
  `tests/test_engine_world.py` plays the test pack through.
- Carried forward: using items from the pack (consumables) comes with the fitting
  board in milestone 3; the crate never restocks until day-start events exist
  (milestone 6); `start_encounter` requests wait for milestone 4.

### 3. Build ✓

- Inventory and cargo, the fitting board, fitting and removing within budgets,
  refitting only at `refit` workshops, frame size against `holds_size`.
- Skills and experience.
- Done when: modules and frames can be swapped, and the budget and size rules behave
  as the validator predicts.
- Delivered: `engine/build.py` (fit and remove within slots, `fit_requires` and
  budgets, only at `refit` workshops; pools follow the loadout; storage with
  starting `contents`; using items, a consumable spending one), size checks at exits,
  the pack panel as the fitting board, experience progress in the character panel.
  Schema: object and placement `contents`, new UI message keys.
  `tests/test_engine_build.py` swaps a full suit at the test pack's bay.
- Carried forward: skills gain experience from actions' `trains` in milestone 4; a
  workshop's `max_grade` applies to crafting (milestone 5), not to refitting.

### 4. Encounters ✓

- Encounter state, turn order (initiative and priority), action tiles in Zone 4.
- Costs (heat, cooldown, charges, consumed items), statuses, overheating.
- AI choice and intent, art in Zone 2, retreat, win / lose / escape, loot,
  `on_defeat`.
- Done when: the test pack's drone encounter can be played to each of its three
  outcomes.
- Delivered: `engine/encounter.py` (spawning, sides, AI choices with intent and
  fleeing, rounds ordered by priority then initiative, costs with overheating,
  cooldowns, charges and consumed items, blocking statuses, skill experience from
  `trains`, the end with loot, deferred `on_defeat` and no game over), the
  encounter screen (art, both sides with intents, action tiles) and keys. The test
  pack gains a drone hatch in room B. `tests/test_engine_encounter.py` wins, loses
  and escapes the drone encounter.
- Carried forward: `trigger_event` requests (such as the test player's rescue) wait
  for milestone 6; a `choose` inside an action's effects doesn't pause the round.

### 5. Crafting ✓

- Workshops: dismantle and learn designs, fabricate, modify, repair.
- Done when: the test tool can be dismantled, learned, fabricated, reinforced and
  repaired.
- Delivered: `engine/craft.py` (the four services within reach of a workshop offering
  them, up to its `max_grade`; dismantling teaches designs when `learn_requires`
  holds; modifications on carried or fitted items with the loadout re-checked;
  results must fit in cargo), crafting options and a designs section on the fitting
  board, and paging for packs with more than nine entries. The test player now
  starts without the tool's design. `tests/test_engine_craft.py` takes the tool
  through its whole life.

### 6. Living world ✓

- The event engine: triggers, cast, chance, weight, cooldown, notify.
- Off-screen characters moved only by events.
- Done when: the grudge and off-screen rivalry events fire with different casts
  under different seeds.
- Delivered: `engine/events.py` (settling after each action: requested encounters,
  requested events, trigger moments, owed time; casting from seeded candidate pools;
  repeat, cooldown, chance and the optional `events_per_trigger` limit; notify).
  Turns, day changes and arrivals queue trigger moments. Schema: the
  `events_per_trigger` setting, clearer `trigger` and `weight` wording. The test pack
  gains three off-screen rivals, a morning restock of the crate, an arrival event
  and a one-time event. `tests/test_engine_events.py` covers casting, firing,
  triggers, limits and saves.

### 7. UI overhaul

Polish every screen, menu and sub-window before writing a real game pack, so engine
work and content work are cleanly separated: after this milestone, the game pack
should need content only. The test pack grows as each step needs it (item
descriptions, statuses on enemies, an ally, a long event text, richer dialogue).

**The guiding principle is visual clarity.** Every step is checked against it:
- one clear focus at a time: what you're looking at or choosing stands out, the rest
  steps back;
- a plain hierarchy: a title, then sections with headings, then entries; aligned
  columns for numbers;
- no cut-off words: text wraps or the layout adapts; long names get short forms;
- colour means something (danger, gain, unavailable, grade), never decoration, and
  everything still reads without colour;
- the keys that work right now are always shown.

Decided:
- **One shared panel** for sub-windows (inspect, item details, dialogue, help, message
  history): it takes over the lower area, the map stays visible above.
- **Up and down are contextual.** They move the player while no sub-window is open;
  while one is open they scroll it, until it is closed. On list screens (fitting,
  and later others) they move the pick instead. Left and right do nothing
  there, and moving never closes a sub-window: only the close key does.
- **Long pages get a vertical slider** at their right edge, showing where you are; up
  and down move it.
- **Character and fitting are full screens of their own**, with their own zones: the
  tactical screens where planning and building happen. The fitting screen holds the
  loadout and budgets, spare gear and designs, the picked item's details, and every
  building action: fit, remove, and the workshop's repair, take apart, make and
  modify. It opens anywhere for planning; its actions work only next to a workshop
  offering them, and are greyed out with a hint elsewhere.
- **The pack panel keeps the everyday inventory work** as it is now: what you carry,
  storage within reach, taking, storing and using items.
- **Start, help and quit screens** are part of the milestone.
- **Trading stays pack-written interactions**; the UI only shows them more clearly.
  No trade screen or prices.

Steps, each one playable and tested:

1. ✓ **Sub-windows:** the shared panel (scrolling, slider, keys from the UI pack), and
   Inspect for places and people in it.
2. ✓ **Items:** an item detail view (description, stats, power and mass use, tags, mods,
   grade, condition), shown from the pack panel and the fitting screen.
3. ✓ **Fitting screen:** a full screen with the loadout and budgets, spare gear and
   designs, the picked item's details and what it would change, and every building
   action (fit, remove, repair, take apart, make, modify, with what designs need and
   what modifications add). The pack panel loses its fitting and crafting options.
   Agreed layout, stacked on every terminal:
   - title: "Fitting · <frame>" and where you are ("At: Workbench", or "Planning
     only" away from a workshop, with the actions greyed out and a hint);
   - budgets as bars (power, mass, heat, cargo);
   - the list: Worn (the frame, then each of its slots and the body's implant slots,
     empty ones shown as "· empty" and not numbered), Spare (gear carried or in
     storage within reach, labelled where it is), Designs (when known, with costs);
   - the picked entry: a short summary, what its action would change ("Fit: PWR
     4→5/6", over-budget numbers in the warning colour and the action greyed out with
     the reason), and its action keys; I opens the full item details in the panel;
   - modify lists the modifications that apply, each with what it adds and needs,
     before one is applied;
   - up and down move the pick through the list (empty slots skipped); digits jump
     to an entry; the list pages past nine entries.
4. ✓ **Character screen:** a full screen with skills and their next levels, stats,
   statuses, party and standing, and a portrait zone: characters may have a pixel
   `portrait`, drawn with half-block characters (an empty frame keeps the place
   without one).
5. **People:** a dialogue window; trades showing what you give and get. Agreed
   layout:
   - a full conversation screen, opened by Talk from the person's menu (the menu
     stays as it is for objects and people; Talk still takes a turn);
   - on top, the speaker's portrait beside their name, title, faction and how they
     regard you (the level's name, the number and a bar);
   - below, the conversation: the last few exchanges (your response, their reply,
     what changed hands), scrolling with the slider, reset when it ends; then their
     current line;
   - your responses: their interactions, numbered (digits answer), unavailable ones
     greyed out with the pack's hint, and Leave last; a trade shows "You give" and
     "You get", read from its own take_item and give_item effects;
   - X leaves.
6. **Fights:** action details before use, fighters' statuses, the chosen target
   highlighted, tile names that fit.
7. **Messages:** message history, and long event texts in the panel.
8. **Around the game:** a start screen (new game, continue, save slots), a help and
   keys screen, quit confirmation.
9. **Polish pass:** item names coloured by grade, small-screen behaviour, consistent
   wording, UI pack docs, the playtest.

### 8. First game pack → version 1.0

- Write Station A, the shuttle and the Moon as `packs/game`, in the new format and
  to the new design.
- Delete the old engine (`core/` modules the new engine replaced, `ui/`, the old
  `main.py`) and the old design document.
- Tag the result as **version 1.0**.

## UI packs (done)

Standard widgets and layout variables in a separate UI pack, shared by game packs.

- [x] `ui.schema.json`: tokens, a fixed widget catalogue arranged into screens, key
  bindings with generated hints, the UI's own words. Every field defaults to the
  standard look.
- [x] `packs/ui/default`: the standard look as data; `core/uipack.py` validates UI
  packs; `packtool` checks and explains them.
- [x] Rebuild `tui/` as the widget catalogue plus a layout engine reading the UI pack;
  move the UI's words out of game packs' `strings.json`; key hints generated from the
  bindings; tests rendering every screen at the minimum size and wider.

## After 1.0

- Content work happens mostly in game packs, under the user's guidance, following
  [AGENTS.md](AGENTS.md).
- Engine changes are small and incremental, and follow the schema-first workflow:
  schema → test pack → engine with tests → game pack.
- **Layouts for wide terminals** (lists and details side by side) are a milestone of
  their own, since every screen and window would need them. Until then there is one
  stacked layout for every terminal.
- Reserved features wait for their own design: procedural zones, ships as moving
  regions, mods (`extends`).
