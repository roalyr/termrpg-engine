# Agent guide

Instructions for AI agents (and people) working on this project. Read this file
before making any change. It tells you what you may edit, which tools to use, how
to check your work, and the rules of the data that are easy to get wrong.

## The rules that matter most

1. **Run the checker after every edit:** `python3 -m core.packtool check <pack>`.
   A task isn't done until it reports `0 error(s)`.
2. **Edit only what your task needs.** The permissions table below says what you may
   touch. When in doubt, ask the user.
3. **Never edit a schema, the validator or a test to make an error go away.** Fix
   the data. If the data can't express what's needed, stop and explain it to the
   user (see [When the schema can't express something](#when-the-schema-cant-express-something)).
4. **Never invent fields, checks, ops or ids.** Look them up with
   `python3 -m core.packtool explain …` and `… ids …`.
5. **Before renaming or deleting anything, run `refs`** and update every use.
6. **Run the tests before finishing:** `python3 -B -m unittest discover -s tests`.
7. **Report what you changed,** what the checker said, and anything you were unsure
   about.

## Documents, in order of authority

| Document | What it is |
|---|---|
| [VISION.md](VISION.md) | What the game is. Overrides everything else |
| [AGENTS.md](AGENTS.md) | How to work on the project (this file) |
| [README.md](README.md) | Reference for every schema, check, effect and term (glossary) |
| [ROADMAP.md](ROADMAP.md) | Milestones and what is done |
| `System Architecture & Game Design Document.md` | The old engine only. Being removed; don't use it for new work |

## What kind of work you'll do

- **Until version 1.0** the engine is being rebuilt (see ROADMAP.md). Engine and
  schema work is done by the lead developer. Don't start engine work on your own.
- **After version 1.0** most work is **writing content packs** under the user's
  guidance: rooms, objects, items, characters, encounters, events, text. Engine
  changes are small, incremental, requested by the user, and follow the procedure in
  [Changing the engine or schemas](#changing-the-engine-or-schemas).

## What you may edit

| Path | Content work | Notes |
|---|---|---|
| `packs/game/**` (and other game packs) | **Yes** | Your normal workspace |
| `packs/test/**` | Ask first | Only changes when the engine or schemas change; its ids are used by tests |
| `packs/ui/**` | **Yes, when asked** | The look, layout, keys and the UI's words. Check with `packtool check packs/ui/<id>` |
| `schemas/**` | Ask first | The contract with the engine. See [Changing the engine or schemas](#changing-the-engine-or-schemas) |
| `core/schema.py`, `core/pack.py`, `core/packtool.py` | Ask first | The validator and tools |
| `engine/**` | Ask first | Small, tested changes only |
| `tools/**` | Ask first | Standalone editors for packs; see `tools/README.md` |
| `tests/**` | Add, don't weaken | Add tests for new code. Never delete or loosen a test to make it pass |
| `README.md` | When schemas change | Keep the schema section and glossary in sync |
| `ROADMAP.md` | When a milestone is done | Tick it off |
| `VISION.md` | **Never**, unless the user says so | |
| `AGENTS.md` | Only when asked | |
| Old engine: `core/` (other files), `ui/`, `main.py` | **No** | Being replaced |
| `saves/`, `presets/` | **Never commit** | Local runtime data |

## Tools

All commands run from the project root.

| Command | Use it to |
|---|---|
| `python3 -m core.packtool check packs/game` | Validate a pack. Prints every error and warning with its file and path |
| `python3 -m core.packtool ids packs/game` | See which namespaces exist and how many ids each has |
| `python3 -m core.packtool ids packs/game item` | List every id in a namespace and where it's declared |
| `python3 -m core.packtool refs packs/game frame_scout` | See where an id is declared and every place it's used |
| `python3 -m core.packtool explain` | List the topics you can look up |
| `python3 -m core.packtool explain ops` / `explain checks` | List every effect or check with a one-line description |
| `python3 -m core.packtool explain op damage` | Show one effect's fields, which are required, defaults and limits |
| `python3 -m core.packtool explain check relation` | The same for a check |
| `python3 -m core.packtool explain item frame` | The fields of an item kind |
| `python3 -m core.packtool explain location` | Any schema definition: `placement`, `exit`, `character`, `event`, `encounter`, `modification`… |
| `python3 -m core.packtool explain vocab stats` | A vocabulary section |
| `python3 -m core.packtool check packs/ui/default` | Validate a UI pack |
| `python3 -m core.packtool explain widget status` / `explain ui tokens` | A UI widget's options, or a UI pack file's fields |
| `python3 play.py --pack packs/game --new` | Play the pack in the terminal to see your work: `--new` goes straight into a new game (slot 1, or `--slot name`); without flags the start screen opens |
| `python3 -B -m unittest discover -s tests` | Run all tests. Use `-B` on phone storage |
| `python3 -B tests/run.py` | The same tests in parallel, about twice as fast. `tests/run.py pack` runs only test files with `pack` in the name |

**The working loop:** look up (`explain`, `ids`) → edit → `check` → fix → `check` →
tests.

## Doing a content task

1. **Understand the request.** Ask the user if the design is unclear. Don't guess
   story or balance decisions; offer options instead.
2. **Look up what exists:** `ids` for the namespaces you'll touch, and `explain` for
   every definition you'll write.
3. **Find a recipe** below that is close to the task, and copy its shape.
4. **Edit the pack's JSON files.** Add entries to the right file; the pack's
   `pack.json` lists the files by kind. New files must be added to `pack.json`.
5. **Run `check`** and fix every error. Read warnings and mention them in your report.
6. **Run the tests.**
7. **Bump the pack's version** in `pack.json` (see [Pack versions](#pack-versions)).
8. **Report:** what you added or changed (by id), the final checker output, open
   questions.

A task is done when `check` reports 0 errors, the tests pass, and the user has
your report.

## Rules of the data

These are the mistakes the checker catches most often, and a few it can't catch.

**Files and ids**

- JSON only: no comments, no trailing commas. 2-space indentation, UTF-8, no emoji.
  Use `notes` fields for comments.
- Unknown fields are errors. Every field you write must appear in `explain`.
- Leave out fields whose default you want: `explain` shows each default, and the
  engine fills it in. Write a field only to change it.
- Ids are `lower_snake_case`. They must be unique within their namespace across the
  whole pack. **Placement ids are unique across all locations.**
- Every referenced id must exist: tags, stats, statuses, slot types, grades,
  factions, flags and object states are declared in `vocab.json`.
- **Saves refer to ids.** Renaming or deleting an id breaks existing saves. Do it
  only when asked, use `refs` to update every use, and bump the major version.

**Grammar**

- Bounds in checks are `min` and `max` (inclusive). Give at least one.
- `damage` and `apply_status` hit `target` by default. In places where there is no
  target (a location's `on_turn`, a status's `on_turn`), write `"subject": "self"`.
- `"this"` means the placed object, and only works inside objects, placements and
  exits.
- `{"role": "name"}` only works inside events, and only for roles in the cast. A
  cast condition may only use roles listed before it.
- Effects run in order. Put `set_state` before effects that depend on the new state.
- `chance` checks and `{min, max}` amounts are rolled from the game's seed. Don't
  expect them to vary within one replay.
- The README table "what self, target and this mean" tells you who `self` is in each
  place, and "How the engine applies the grammar" explains groups, pools, broken
  items, relations and defeat.
- A check on `party` passes if anyone in the party passes; an effect on `party` hits
  everyone.

**World**

- Grid positions are `[row, column]`, counted from the top-left `[0, 0]`. Without
  `rows`, row 0, the last row, column 0 and the last column are walls.
- Doors and other exits sit on wall tiles; everything else on floor tiles. One
  placement per tile; characters need a free floor tile.
- An exit only goes one way. **Two rooms need a door placement in each**, each with
  its own `exit` pointing at the other door's placement id.
- A door's state belongs to its placement. Two door placements don't share a state.
- Every `size` and `holds_size` value must be named in the vocabulary's `sizes`.
- `holds_size` left out means no limit on locations and objects, but holds nothing
  on items.
- A tag marked `hazard` only shows a warning. The harm itself must be written in the
  location's `on_turn`, which only runs while the player is there (for everyone in
  the room).
- Solid objects (`"solid": true`) are used from the next tile; the player bumps into
  them. Don't make a room's only way through solid. An `entry` on a solid object puts
  arrivals on the nearest free floor tile.
- Interaction keys `w a s d . p f c x q ]` (the UI pack's bindings), `g t i` and the
  digits are taken by the game; pick another letter for `key`, or the engine picks one.
- Players can change frames, modules and implants only next to a workshop offering
  `refit`. Put one where players should be able to refit, and make sure the room's
  `holds_size` fits the frames meant to be worn there.
- A frame's size is its wearer's size: a size-5 suit can't pass a door or enter a
  room whose `holds_size` is smaller. Plan where heavy suits can go.
- Starting items in lockers and bays go in `contents`; they must fit the object's
  `storage` (stacks) and `holds_size`.

**Items and characters**

- `has_item` checks carried items unless its `source` says `fitted` or `any`; that is
  what `take_item` can take, so a "requires it, then takes it" trade can't be cheated.
- An item's `kind` decides its fields. Only frames, modules and implants take
  `slot_type`, `slots`, `mod_slots` and `fit_requires`. Only modules take `uses`.
- Modules go into `frame` slot types, implants into `body` slot types.
- Items that stack (`stack` above 1) can't have a `condition`. Only items with a
  `condition` can have `repair`.
- A character's loadout must fit: free slots for every module and implant, power and
  mass `uses` within what the body, frame, modules and implants provide, constant
  heat below maximum heat, inventory stacks within cargo. The checker shows the
  numbers when it doesn't fit.
- `template: true` characters (enemies spawned in numbers) have no `location`. In
  encounters, only templates take a `count`.

**Encounters**

- Damage written as `{"stat": …, "times": …}` scales with the **user's** stat. An
  enemy without that stat in its body hits for only the `plus` part: give enemies the
  stats their actions read.
- Check that enemies can actually hurt the player and the player can hurt them:
  damage minus the target's resisting stat must be above 0.
- AI never uses actions that end the encounter (like Retreat). Give enemies
  `ai.flee_below` if they should run when hurt.
- A character's `actions`, their items' actions, skill-level actions and `innate`
  actions are all they can do. Allies with no actions of their own do nothing.
- The player's `on_defeat` decides what losing means (carried home, robbed, rescued).
  It runs after the encounter ends. Without it the player is left with 1 health.
- Give long action names a `short` (at most 8 characters) for the tile; `intent` is
  the word shown over an enemy.
- Don't put `choose` in an action's effects.

**Crafting**

- Crafting happens only next to a workshop offering the service (`dismantle`,
  `fabricate`, `modify`, `repair`), on items up to its `max_grade`. Place workshops
  with the services and grade a place should have: a field bench, a proper shop.
- Designs are learned by dismantling (when `salvage.learn_requires` holds) or by the
  `learn_design` effect. An item without `salvage` can never be learned that way.
- Make every input obtainable: `fabricate.inputs`, `repair.inputs` and a
  modification's `material` must come from somewhere the player can reach (loot,
  storage, salvage, trades).
- A modification fills one of the item's `mod_slots`; items without `mod_slots`
  can't be modified. `applies_to.kinds` is required; `tags` and `slot_types` narrow
  it further.
- What crafting produces must fit in the player's cargo, or the action is refused.

**Events**

- Routine upkeep is an event too: a crate that refills each morning is a `day_start`
  event with `notify: false` that sets its state back. The engine never heals on its
  own: a night's rest is a `day_start` event with `restore` on `"subject": "party"`,
  which also gets downed companions back up.
- A cast drawn `from` `anyone` can include the player and characters with no
  location. Write conditions that rule out who shouldn't play the role.
- Relations in cast conditions fall back through factions: a character with no view
  of someone uses their faction's view. Test with `play.py` that the right people get
  cast.
- An event's `name` is the title of its card. Events that ask a question, or whose
  `text` runs past about three lines on a 48-column screen, open as a card the
  player has to read; keep everyday events to a line or two so they stay in the log.
- `notify: false` events shouldn't use `choose`: the player would get a question about
  something they can't see.
- Requested events (`trigger_event`) ignore `chance` and `cooldown` but still need a
  cast and `when`. `on_defeat` usually requests a rescue event this way.
- Off-screen characters never act on their own. Only events move them or change
  their views and ranks, so rivals need events to have lives.

**Text**

- Labels (`name`, `label`) are at most 32 characters. An action's `short` is at
  most 8.
- **Pictures live in the art file** (`art` kind, ids `art_…`) and are used by id: a
  character's `art` is shown on the character screen, in conversations and in fights.
  One picture can serve many characters (every guard, every drone).
- A picture is pixel letters plus a palette: every row the same length, every letter
  in the palette, a space or `.` for see-through; up to 32 by 32 pixels. The default
  UI pack shows 24 by 24 (12 lines), centred, and cuts what's larger: draw for 24 by
  24. Draw for the shape first: without colour only the silhouette shows.
- A text that is exactly `@` plus an id shows that entry from `strings.json`.
- Engine messages in `strings.json` may only use their own placeholders:
  `explain engine` lists them. Write all of them: a missing one shows as its key.
- The screen's labels, headings and key hints are not in `strings.json`: they belong
  to the UI pack (`packs/ui/<id>/words.json`), shared by every game. Change them only
  when the user asks.

## Editing a UI pack

A UI pack (`packs/ui/<id>/`) holds the look and layout shared by game packs:
`tokens.json` (sizes, glyphs, styles), `screens.json` (which widgets each screen
shows, in what order), `keys.json` (key bindings and the hints they produce) and
`words.json` (labels, headings and hint labels). README.md, "UI packs", explains
each part.

- Change values; leave out what should stay standard (every field has a default).
- Use only the widgets in the catalogue (`explain widget …`) on the screens that allow
  them. Behaviour (what appears when, how a widget draws) is engine code.
- Keep the world screen within `min_columns`: the checker shows the numbers when the
  grid and side panel don't fit.
- Keys: one action per key, in lower case; digits are reserved for picking numbered
  entries. Game
  packs' interaction keys must not use the bound keys either.
- The game's voice stays in the game pack's `strings.json`; only labels, headings and
  hints go in the UI pack's `words.json`.
- Check with `python3 -m core.packtool check packs/ui/<id>`, then run the tests.

## Naming ids in game packs

Prefixes make ids easy to read and search. Use them in game packs:

| Namespace | Prefix | Example |
|---|---|---|
| Region | `reg_` | `reg_station_a` |
| Location | `loc_` | `loc_bunkroom` |
| Placement | the location's name without `loc_`, then what it is | `bunkroom_hatch_berth` |
| Object | `obj_` | `obj_hatch` |
| Frame | `frame_` | `frame_vacuum_suit` |
| Module (tools, weapons, systems) | `module_` | `module_cutter` |
| Implant | `implant_` | `implant_eye` |
| Material | `material_` | `material_scrap` |
| Consumable | `consumable_` | `consumable_ration` |
| Misc item | `misc_` | `misc_work_pass` |
| Action | `action_` | `action_cut` |
| Skill | `skill_` | `skill_cutting` |
| Character | `char_` | `char_kael`, `char_loader_drone` |
| Encounter | `enc_` | `enc_loader_ambush` |
| Loot table | `loot_` | `loot_scrap_bin` |
| Event | `event_` | `event_grudge` |
| Modification | `mod_` (not to be confused with `module_`) | `mod_reinforced` |
| Tag, stat, status | `tag_`, `stat_`, `status_` | `tag_sealed`, `stat_armor`, `status_burning` |
| Damage type, slot type, grade | `dmg_`, `slot_`, `grade_` | `dmg_kinetic`, `slot_hand`, `grade_exotic` |
| Object state, phase, faction, flag | `state_`, `phase_`, `faction_`, `flag_` | `state_open`, `phase_night` |
| Custom string | `str_` | `str_kael_greeting` |
| Art (pictures) | `art_` | `art_kael`, `art_sentry` |

The test pack follows these prefixes too, with plain names (a workshop, a storage room,
a cutter, scrap), so its ids can be copied as examples.

## Recipes

Each recipe shows entries grouped by the kind of file they go into: `"items": […]`
means "add these to the `entries` of your items file". `"placements:loc_workshop": […]`
means "add these to the `placements` of location `loc_workshop`". The ids come from the
test pack; replace them with your pack's.

Every recipe here is validated against the test pack by
`tests/test_agent_docs.py`, so it's known to be correct.

### Add a room and connect it both ways

Each side of a connection is a door placement with an `exit` pointing at the other
door. Both are placed on wall tiles.

<!-- recipe -->
```json
{
  "locations": [
    { "id": "loc_corridor", "name": "Corridor", "region": "reg_lower_deck",
      "description": "A narrow corridor.",
      "grid": { "width": 5, "height": 5, "floor": "·", "wall": "░" },
      "placements": [
        { "id": "corridor_door", "object": "obj_door", "at": [2, 0], "state": "state_open",
          "exit": { "location": "loc_workshop", "entry": "workshop_door_corridor",
                    "requires": { "check": "object_state", "object": "this", "state": "state_open" },
                    "hint": "The door is closed." } }
      ] }
  ],
  "placements:loc_workshop": [
    { "id": "workshop_door_corridor", "object": "obj_door", "at": [3, 5], "state": "state_open",
      "exit": { "location": "loc_corridor", "entry": "corridor_door",
                "requires": { "check": "object_state", "object": "this", "state": "state_open" },
                "hint": "The door is closed." } }
  ]
}
```

### Make a room hazardous

The `hazard` tag shows the warning; `on_turn` does the harm. Note `"subject": "self"`.

<!-- recipe -->
```json
{
  "locations": [
    { "id": "loc_vent_room", "name": "Vent room", "region": "reg_lower_deck", "tags": ["tag_gas_leak"],
      "grid": { "width": 5, "height": 5, "floor": "·", "wall": "░" },
      "on_turn": [
        { "op": "if",
          "if": { "not": { "check": "has_tag", "tag": "tag_filter", "source": "fitted" } },
          "then": [ { "op": "damage", "amount": 1, "damage_type": "dmg_toxic", "subject": "self" } ] }
      ] }
  ]
}
```

### Add a person who talks, trades and can join the party

Dialogue lines are tried in order; put the most specific first and a line without
`when` last. **In dialogue lines `self` is the speaker and `target` the listener; in a
character's interactions it's the other way round:** `self` is whoever interacts and
`target` is this character. So "the speaker travels with the player" is
`{ "check": "in_party" }`, but in an interaction it's
`{ "check": "in_party", "subject": "target" }`.

<!-- recipe -->
```json
{
  "characters": [
    { "id": "char_trader", "name": "Trader", "title": "Scrap dealer",
      "location": "loc_workshop", "at": [2, 1], "faction": "faction_crew",
      "body": { "size": 3, "stats": { "stat_health": 10, "stat_cargo": 4 } },
      "inventory": [ { "item": "consumable_medkit", "count": 4 } ],
      "wants": ["tag_tool"],
      "talk": [
        { "when": { "check": "in_party" }, "text": "Where to?" },
        { "when": { "check": "has_item", "item": "misc_keycard", "subject": "target" }, "text": "That key. I'd trade for it." },
        { "text": "Looking to trade?" }
      ],
      "interactions": [
        { "id": "trade", "label": "Trade key for supplies", "key": "b", "repeat": "once",
          "requires": { "check": "has_item", "item": "misc_keycard" },
          "hint": "Wants a key.",
          "effects": [
            { "op": "take_item", "item": "misc_keycard" },
            { "op": "give_item", "item": "consumable_medkit", "count": 2 },
            { "op": "change_relation", "of": "target", "toward": "self", "amount": 20 }
          ] },
        { "id": "recruit", "label": "Ask to join", "key": "t",
          "shown_if": { "not": { "check": "in_party", "subject": "target" } },
          "requires": { "check": "relation", "of": "target", "toward": "self", "min": 20 },
          "hint": "Doesn't know you well enough.",
          "effects": [ { "op": "join_party", "subject": "target", "leader": "self" } ] }
      ] }
  ]
}
```

### Add a suit, a tool, and someone wearing them

The frame's stats provide the budgets; the module's `uses` spends them. Check the
numbers: power 2 of 8, mass 3 of 12, heat 0 of 10, cargo 1 stack of 3 + 2.

<!-- recipe -->
```json
{
  "items": [
    { "id": "frame_work", "kind": "frame", "name": "Work suit", "size": 3, "grade": "grade_common",
      "description": "A light work suit.",
      "stats": { "stat_health": 25, "stat_power": 8, "stat_mass": 12, "stat_heat": 10, "stat_cargo": 3 },
      "slots": [ { "slot_type": "slot_hand", "count": 2 } ],
      "mod_slots": 1, "condition": 10,
      "repair": { "inputs": [ { "item": "material_scrap", "count": 2 } ] } },
    { "id": "module_drill", "kind": "module", "name": "Drill", "size": 1, "grade": "grade_common",
      "tags": ["tag_tool"], "slot_type": "slot_hand",
      "uses": { "power": 2, "mass": 3 },
      "actions": ["action_strike"], "condition": 5,
      "salvage": { "yields": [ { "item": "material_scrap", "count": 2 } ],
                   "learn_requires": { "check": "skill", "skill": "skill_salvage", "min": 2 } },
      "fabricate": { "inputs": [ { "item": "material_scrap", "count": 4 } ] } }
  ],
  "characters": [
    { "id": "char_worker", "name": "Worker",
      "body": { "size": 3, "stats": { "stat_health": 10, "stat_cargo": 2 } },
      "frame": "frame_work", "fitted": ["module_drill"],
      "inventory": [ { "item": "material_scrap", "count": 5 } ],
      "skills": { "skill_salvage": 2 } }
  ]
}
```

### Add an enemy, its picture, its loot, an encounter, and something that starts it

Enemies spawned in numbers are templates: no location, and a `count` in the
encounter. Their picture is an `art` entry, shown in the fight. Here an alarm panel
in the storage room starts the encounter.

<!-- recipe -->
```json
{
  "art": [
    { "id": "art_sentry", "notes": "A squat sentry: a dome with red eyes on four legs.",
      "rows": [
      "......aaaa......",
      "....aaaaaaaa....",
      "...aaeaaaaeaa...",
      "...aaaaaaaaaa...",
      "....aammmmaa....",
      "..bbbbbbbbbbbb..",
      "..bb..bbbb..bb..",
      "..bb..bb..bb.bb."
      ],
      "palette": { "a": "grey", "e": "red", "m": 238, "b": 244 } }
  ],
  "loot_tables": [
    { "id": "loot_sentry", "rolls": 1, "nothing": 1,
      "always": [ { "item": "material_scrap", "count": 1 } ],
      "entries": [ { "item": "material_odd_metal", "weight": 1 }, { "item": "consumable_medkit", "weight": 3 } ] }
  ],
  "characters": [
    { "id": "char_sentry", "name": "Sentry", "template": true, "glyph": "s", "art": "art_sentry",
      "body": { "size": 3, "stats": { "stat_health": 12, "stat_initiative": 1, "stat_armor": 1 } },
      "actions": ["action_strike", "action_guard"],
      "ai": { "flee_below": 0.2 },
      "loot": "loot_sentry" }
  ],
  "encounters": [
    { "id": "enc_sentries", "name": "Sentries", "intro": "Two shapes unfold from the wall.",
      "enemies": [ { "character": "char_sentry", "count": 2 } ],
      "on_win": [ { "op": "set_flag", "flag": "flag_power", "add": 1 } ] }
  ],
  "objects": [
    { "id": "obj_alarm", "name": "Alarm panel", "glyph": "!", "solid": true,
      "states": ["state_closed", "state_used"],
      "interactions": [
        { "id": "press", "label": "Press it", "key": "u",
          "requires": { "check": "object_state", "object": "this", "state": "state_closed" },
          "hint": "It's dead now.",
          "effects": [
            { "op": "set_state", "object": "this", "state": "state_used" },
            { "op": "start_encounter", "encounter": "enc_sentries" }
          ] }
      ] }
  ],
  "placements:loc_storage": [
    { "id": "storage_alarm", "object": "obj_alarm", "at": [1, 1] }
  ]
}
```

### Add a living-world event

The cast finds its people by conditions, so the event plays out between different
characters each time. `notify: false` keeps off-screen events quiet.

<!-- recipe -->
```json
{
  "events": [
    { "id": "event_rivals_clash", "name": "Rivals clash", "trigger": "day_start",
      "chance": 0.2, "cooldown": 5, "notify": false,
      "cast": [
        { "role": "first", "when": { "check": "rank", "min": 1 } },
        { "role": "second",
          "when": { "all": [ { "check": "rank", "min": 1 },
                             { "check": "relation", "of": "self", "toward": { "role": "first" }, "max": -10 } ] } }
      ],
      "effects": [
        { "op": "change_relation", "of": { "role": "first" }, "toward": { "role": "second" }, "amount": -10, "mutual": true },
        { "op": "if", "if": { "check": "chance", "p": 0.5 },
          "then": [ { "op": "change_rank", "amount": 1, "subject": { "role": "first" } } ],
          "else": [ { "op": "change_rank", "amount": 1, "subject": { "role": "second" } } ] }
      ] }
  ]
}
```

### Add a modification

The material decides what's added, always the same way. It fills one mod slot for
good.

<!-- recipe -->
```json
{
  "modifications": [
    { "id": "mod_lightened", "name": "Lightened", "material": "material_odd_metal", "count": 1,
      "description": "Strange metal, lighter than it should be.",
      "applies_to": { "kinds": ["module"], "slot_types": ["slot_hand"] },
      "requires": { "check": "skill", "skill": "skill_salvage", "min": 2 },
      "adds": { "uses": { "mass": -1 }, "tags": ["tag_filter"] } }
  ]
}
```

## Fixing checker errors

| The checker says | What to do |
|---|---|
| `unknown field 'x'` | The field doesn't exist there. Check `explain` for the right name, or use `notes` |
| `missing required field 'x'` | Add it; `explain` marks required fields with `*` |
| `unknown op 'x'. Known: …` / `unknown check 'x'` | A typo or an invented effect; pick one from the list |
| `unknown tag 'x'` (or stat, item, placement…) | Declare it, or fix the id. `ids <pack> <namespace>` lists what exists |
| `duplicate placement 'x'` | Placement ids are unique across the pack. Prefix them with the location |
| `use only one of: a, b` / `needs exactly one of` | Give exactly one of those fields |
| `needs 'check', or one of: all, any, not` | A condition must be a check or a combination |
| `unknown size class 'n'` | Name that size in `vocab.json` → `sizes` |
| `position [r, c] is outside the grid` / `already taken` / `not a floor tile` | Pick another tile. Rows first, then columns |
| `fitted gear needs N power, the loadout provides M` | Remove a module, lower its `uses`, or use a stronger frame |
| `inventory needs N cargo stacks, the loadout carries M` | Carry less, or add cargo |
| `no free 'slot' slot in the frame` | The frame lacks that slot type or it's full |
| `role 'x' is not in the event's cast` | Add the role to `cast`, or fix the name |
| `unknown placeholder {x}` | Use only the placeholders `explain engine` lists for that message |
| `unknown string '@x'` | Add the entry to `strings.json`, or fix the id |
| warning: `uses a reserved feature` | Only use reserved features when the user asks; the engine ignores them |

## Writing game text

- **Tone:** grounded, dry, direct. Everyday life on the frontier; technology that
  feels real. Strangeness comes slowly, through materials nobody can explain but
  everyone can use.
- **Second person, short sentences, plain words.** Units are fine (kPa, °C); jargon
  and technobabble are not.
- **No emoji.** Map glyphs are single characters.
- **Hints say what's needed,** in plain words: "Needs a cutter or a heavier frame."
- **Write trades as top-level `take_item` and `give_item` effects** of an interaction
  (not inside an `if`): the conversation screen reads them to show "You give" and
  "You get". `self` is the player, `target` the person.
- **Write the pack's `help`** in `pack.json`: the game's premise and a few tips, a short
  paragraph. The help screen shows it under the interface's own help.
- **Give every object, person and item a `description`.** Inspect and the item details
  show it. Say what the thing is and what it's for; the numbers are shown already.
- Keep names short enough for a 48-column screen.

## When the schema can't express something

Don't bend existing fields to mean something else, and don't add fields. Stop and
tell the user:

1. what the content needs to do;
2. why no existing check, effect or field can do it (name what you looked at with
   `explain`);
3. the smallest schema change that would allow it.

Changing the schema is an engine task and follows the next section.

## Changing the engine or schemas

Only when the user asks. Every change follows the schema-first order:

1. **Schema.** Extend the schema. Mark planned-but-unsupported parts
   `"x-status": "reserved"`. A change that breaks existing packs raises the schema
   version everywhere (every schema's `x-schema-version` and `pack.schema.json`'s
   `schema_version`).
2. **Test pack.** Add small generic data that uses the new part.
3. **Engine and validator.** Implement it, with tests. Add validator rules for
   anything a schema can't check.
4. **Game pack.** Write the real content.

Then update `README.md` (schema section and glossary), this file if the rules or
recipes change, and `ROADMAP.md`. All tests must pass, including the recipe test.

## Pack versions

A pack's `version` in `pack.json` is `major.minor.patch`:

- **patch:** text and balance fixes;
- **minor:** new content;
- **major:** renamed or removed ids, or changed meaning. Breaks saves.

## Git

- Commit only when the user asks. Work on a branch, not directly on `main`.
- One topic per commit. The subject line says what changed (`feat(pack): add the
  Berth 04 traders`); the body says why.
- Never rewrite history or force-push. Never commit `saves/` or `presets/`.
