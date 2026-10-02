# CLI Space RPG

A text RPG for the terminal, built with the Python 3 standard library only. You are a
salvager on the frontier of space. You get stronger by recovering, fitting and
improving strange technology, take on ever more dangerous places, and grow alongside
the people you meet, while a world that runs on its own rules creates the story
around you.

- **What the game is meant to be:** [VISION.md](VISION.md). It takes precedence over
  every other document.
- **How to work on the project** (for people and AI agents): [AGENTS.md](AGENTS.md).
- **The rebuild plan:** [ROADMAP.md](ROADMAP.md).
- **How the old engine works:** `System Architecture & Game Design Document.md`. It is
  being pruned as the new engine replaces it.

## Contents

1. [Status](#status)
2. [Quick start](#quick-start)
3. [Repository layout](#repository-layout)
4. [How development works](#how-development-works)
5. [Schemas](#schemas)
6. [Glossary](#glossary)

## Status

The project is between two engines.

- **The old engine** (`core/`, `ui/`, `main.py`) is playable, but its content is
  partly hardcoded and its design (chores, survival meters) was rejected.
- **The new data layer is complete.** The schemas in `schemas/` describe all game
  content; a validator checks packs against them; a generic test pack in
  `packs/test/` uses every part of them.
- **The new engine** (`engine/`) reads packs and nothing else. Milestones 0–3 are
  done: the test pack is playable in the terminal with `python3 play.py`, including
  refitting suits. See [ROADMAP.md](ROADMAP.md).

## Quick start

```sh
python3 play.py                                # play the test pack on the new engine
python3 play.py --pack packs/test --slot two --new   # a fresh game in another save slot
python3 main.py                                # play the old engine
python3 -m core.packtool check packs/test      # validate a content pack
python3 -m core.packtool ids packs/test item   # list the ids of a kind
python3 -m core.packtool refs packs/test pl_a_door_b   # where an id is declared and used
python3 -m core.packtool explain op damage     # document any part of the schemas
python3 -B -m unittest discover -s tests       # run all tests
```

Use `-B` when running tests on shared phone storage: the file system's coarse
timestamps can make Python run stale cached bytecode.

## Repository layout

| Path | What it holds |
|---|---|
| `VISION.md` | The game's direction and design rules |
| `schemas/` | JSON Schemas: the contract between engine and content |
| `packs/test/` | Generic test pack for engine development and tests |
| `core/schema.py` | Checker for the JSON Schema subset the schemas use |
| `core/pack.py` | Pack validator: files, references and game rules |
| `core/packtool.py` | Command-line tools: `check`, `ids`, `refs`, `explain` |
| `AGENTS.md`, `GEMINI.md` | Instructions for AI agents |
| `ROADMAP.md` | The engine rebuild plan |
| `engine/` | The new engine: `content.py` loads packs, `state.py` the game state, `stats.py` derived stats, `conditions.py` and `effects.py` the grammar, `context.py` references, `rng.py` seeded randomness |
| `tui/`, `play.py` | The terminal UI for the new engine, and how to start it |
| `core/`, `ui/`, `main.py` | The old engine (being replaced) |
| `core/data/default-1.0/` | The old engine's content (to be rewritten as a game pack) |
| `tests/` | Unit tests; `tests/test_pack_validation.py` covers the validator |

## How development works

**The engine and the content are separate.** The engine never names a room, item,
person or tag, and prints no text of its own. Everything comes from a **pack**: a
folder of JSON data checked against the schemas.

- **Test pack** (`purpose: "test"`): small, generic content (`room_a`, `item_1`) for
  engine work and automated tests.
- **Game pack** (`purpose: "game"`): the real world, names and writing.

**Development is schema-first.** The schemas define what the game can contain and
do. Every feature goes through the same four steps:

1. **Schema:** extend or add the schema.
2. **Test pack:** add small generic data that uses it.
3. **Engine:** implement it against the test pack, with tests.
4. **Game pack:** write the real content.

---

## Schemas

### How a pack is put together

A pack is a folder with a manifest, `pack.json`, which lists the data files to load,
grouped by **kind**. Files of the same kind are merged. Each kind is checked against
its schema:

| Kind (in `pack.json` → `files`) | Schema | Reference namespace | Holds |
|---|---|---|---|
| `vocab` | `vocab.schema.json` | several (see [Vocabulary](#vocabulary-vocabjson)) | Tags, stats, statuses and other words |
| `regions` | `world.schema.json` | `region` | Groups of locations |
| `locations` | `world.schema.json` | `location`, `placement` | Rooms and their placed objects |
| `zones` | `world.schema.json` | `zone` | Procedural areas (reserved) |
| `objects` | `object.schema.json` | `object` | Object templates |
| `items` | `item.schema.json` | `item` | Everything carried, fitted or implanted |
| `actions` | `action.schema.json` | `action` | Encounter actions |
| `skills` | `skill.schema.json` | `skill` | Skills and their levels |
| `characters` | `character.schema.json` | `character` | Everyone, the player included |
| `encounters` | `encounter.schema.json` | `encounter` | Fights and confrontations |
| `loot_tables` | `loot.schema.json` | `loot_table` | Weighted loot |
| `events` | `event.schema.json` | `event` | Living-world events |
| `strings` | `strings.schema.json` | `string` | Engine messages and reusable text |
| `modifications` | `modification.schema.json` | `modification` | Crafting modifications |

`common.schema.json` holds the shared grammar that all of these use, and
`pack.schema.json` describes the manifest.

Every file except `pack.json`, `vocab.json` and `strings.json` has the same shape:

```json
{ "$schema": "../../schemas/item.schema.json", "entries": [ { "id": "…" }, … ] }
```

`$schema` is optional. It lets editors such as VS Code autocomplete and check the
file as you type. The engine ignores it.

### Conventions

- **Ids** are `lower_snake_case`, at most 48 characters, and unique within their
  namespace across the whole pack. Placement ids are unique across all locations.
- **References.** A field that names another thing holds its id. The validator
  checks that every reference points at something that exists.
- **Labels** are short names (at most 32 characters) that must fit a 40-column
  screen. **Text** is longer player-facing prose (at most 600 characters).
- **`@` texts.** A text field whose value is exactly `@` plus an id (for example
  `"@greeting"`) shows that entry from the strings file.
- **Glyphs** are one or two characters drawn on the map. No emoji.
- **`notes`** fields are for authors; the engine ignores them.
- **Defaults.** Fields with a default can be left out. The engine fills in every
  default the schemas declare when it loads a pack (`explain` shows them), so the
  engine itself never assumes a value.
- **Reserved** fields and definitions are designed but not supported by the engine
  yet. Using them produces a warning, not an error.
- **Versioning.** Every schema carries `x-schema-version`, and a pack states the
  `schema_version` it was written for. A change that breaks existing packs raises
  the version, and the engine refuses packs written for another one.

The schemas use a few keywords of their own on top of JSON Schema:

| Keyword | Meaning |
|---|---|
| `x-ref` | The value is a reference into the named namespace |
| `x-ref-keys` | The object's keys are references (for maps like `{"stat_armor": 2}`) |
| `x-discriminator` | The field (`check`, `op`, `kind`) that picks which form an object takes |
| `x-status: "reserved"` | Designed, not supported yet |
| `x-placeholders` | The placeholders an engine message may use |
| `x-schema-version` | The schema version |

### The grammar (`common.schema.json`)

Everything that can happen in the game is written with the same pieces: conditions
that are true or false, and effects that change the world. The full list of checks
and effects is the engine's feature list: if something can't be expressed with
them, the engine can't do it yet.

#### Subjects and agents

A **subject** says who or what a check or effect applies to:

| Value | Meaning |
|---|---|
| `"self"` (default) | Whoever acts: the player when the player interacts, an NPC when an NPC acts |
| `"target"` | What the action is aimed at |
| `"player"` | The player's character |
| `"party"` | The acting character and everyone travelling with them |
| `{"character": "id"}` | A specific character |
| `{"role": "name"}` | A role from the running event's cast (events only) |

An **agent** is anyone who can hold a view of others, used by relations. It's
`"self"`, `"target"`, `"player"`, `{"character": …}`, `{"faction": …}` or
`{"role": …}`.

**Player-NPC parity:** every check and effect works the same for every character.
Nothing is player-only.

What `self`, `target` and `this` mean depends on where a condition or effect is
written:

| Where | `self` | `target` | `this` |
|---|---|---|---|
| Object or placement interaction | The character interacting | — | The placed object |
| Exit `requires` | The traveller | — | The exit's placement |
| Character interaction | The character interacting | The character interacted with | — |
| Dialogue line `when` | The speaker | Who they talk to | — |
| Item interaction | The item's holder | — | (item pick `{"used": true}` is the item) |
| Action effects and `requires` | The user | Each chosen target | — |
| Action `ai.when` | The user | — | — |
| Location `on_enter`, `on_turn` | The character in the location | — | — |
| Status `on_apply`, `on_turn`, `on_expire` | The character with the status | — | — |
| Character `on_defeat` | The defeated character | — | — |
| Encounter effects | The player | — | — |
| Event `when` and effects | The player (cast members are `{"role": …}`) | — | — |
| Event cast `when` | The candidate for the role | — | — |
| `fit_requires`, modification `requires`, `salvage.learn_requires` | The character fitting or crafting | — | — |
| Loot entry `when` | Who receives the loot | — | — |

#### Amounts

An **amount** is one of three forms:

```text
3                                             fixed
{ "min": 1, "max": 3 }                        rolled from the game seed (integers roll integers)
{ "stat": "stat_power", "times": 0.5, "plus": 2 }   scaled from the subject's stat, rounded down
{ "skill": "skill_a", "times": 2 }                  … or from a skill level
```

The scaled form takes `stat` or `skill` (not both), an optional `subject` (default
`self`), `times` (default 1) and `plus` (default 0).

Randomness is always seeded, so a game can be replayed exactly.

#### Object references and item picks

An **object reference** is `"this"` (the placed object whose interaction or template
is running) or a placement id.

An **item pick** says which of the subject's items is meant:

| Form | Picks |
|---|---|
| `{"item": "id"}` | That item |
| `{"tag": "id"}` | The first carried or fitted item with that tag |
| `{"slot_type": "id"}` | The item fitted in a slot of that type |
| `{"used": true}` | The item that satisfied the requirement of the interaction or action being performed |

#### Conditions

A condition is a small tree. `{"all": […]}`, `{"any": […]}` and `{"not": …}` combine
other conditions; the leaves are checks, picked by the `check` field.

| Check | Fields | True when |
|---|---|---|
| `has_tag` | `tag`, `subject`, `source` | The subject has the tag. `source` narrows where it may come from: `any` (default), `fitted` (suit gear), `carried`, `body` (implants and skills), `party` (companions) |
| `has_item` | `item`, `count` (1), `subject` | The subject carries at least `count` of the item |
| `skill` | `skill`, `min`, `subject` | The skill is at least level `min` |
| `stat` | `stat`, `min`, `max`, `subject` | The stat's current value is within bounds |
| `item_condition` | `pick`, `min`, `max`, `subject` | A picked item's condition is within bounds (items that don't wear always pass) |
| `knows_design` | `item`, `subject` | The subject can fabricate the item |
| `status` | `status`, `subject` | The subject has the status |
| `flag` | `flag`, `min`, `max` | A world flag is within bounds (unset flags are 0) |
| `location` | `location`, `subject` | The subject is in the location |
| `region` | `region`, `subject` | The subject is in the region |
| `visited` | `location`, `subject` | The subject has been there |
| `object_state` | `object`, `state` | A placed object is in the state |
| `size` | `min`, `max`, `subject` | The subject's size class is within bounds |
| `fits` | `subject` or `item`; `into_object`, `into_item` or `into_location` | The thing's size is at most the container's `holds_size` |
| `in_party` | `subject`, `leader` (default `player`) | The subject travels in the leader's party |
| `relation` | `of`, `toward` (default `player`), `min`, `max` | How `of` regards `toward` is within bounds |
| `rank` | `min`, `max`, `subject` | The subject's rank is within bounds |
| `time` | `phase`, `day_min`, `day_max` | The day and part of the day match |
| `chance` | `p` (between 0 and 1) | A seeded roll passes |

Bounds (`min`, `max`) are inclusive, and at least one must be given.

Example: "has a pry-bar, or wears a frame of size 5 or more".

```json
{ "any": [ { "check": "has_tag", "tag": "force_lever" },
           { "check": "size", "min": 5 } ] }
```

#### Effects

An effect is one thing that happens, picked by the `op` field. Effects in a list run
in order.

| Group | Op | Fields | Does |
|---|---|---|---|
| Items | `give_item` | `item`, `count`, `subject` | Adds items to the inventory |
| | `take_item` | `item` or `tag`, `count`, `subject` | Removes items |
| | `roll_loot` | `table`, `rolls` (1), `subject` | Rolls a loot table for the subject |
| | `wear` | `pick`, `amount`, `subject` | Lowers an item's condition (negative repairs). At 0 the item is broken |
| | `modify_item` | `pick`, `add_tags`, `remove_tags`, `stats`, `max_condition`, `name_suffix` | Permanently changes one item into a unique variant |
| | `learn_design` | `item`, `subject` | The subject can now fabricate the item |
| Stats | `damage` | `amount`, `damage_type`, `subject` (default `target`) | Deals damage; the damage type's resisting stat reduces it |
| | `restore` | `stat`, `amount`, `subject` | Raises a pool toward its maximum (heal, repair, cool) |
| | `modify_stat` | `stat`, `amount`, `subject`, `duration` | Adds to a stat; temporary with a duration, otherwise permanent |
| | `apply_status` | `status`, `subject` (default `target`), `duration`, `stacks` | Puts a status on the subject |
| | `remove_status` | `status`, `subject` | Removes a status |
| World | `set_flag` | `flag`, `value` or `add` | Sets or changes a world flag |
| | `set_state` | `object`, `state` | Changes a placed object's state |
| | `move_to` | `location`, `entry`, `subject` | Moves the subject and their party |
| | `spend_time` | `turns` | Lets time pass |
| | `trigger_event` | `event` | Runs an event now |
| | `start_encounter` | `encounter` | Starts an encounter |
| | `end_encounter` | `result` (`escaped`, `won`, `lost`) | Ends the current encounter |
| People | `grant_xp` | `skill`, `amount`, `subject` | Gives skill experience |
| | `join_party` | `subject`, `leader` (default `player`) | The subject joins the leader's party |
| | `leave_party` | `subject` | The subject leaves their party |
| | `change_relation` | `of`, `toward` (default `player`), `amount`, `mutual` | Changes how `of` regards `toward`; `mutual` changes both views |
| | `change_rank` | `amount`, `subject` | Raises or lowers rank |
| | `unlock_slot` | `slot_type`, `count`, `subject` | Opens implant slots in the body |
| Flow | `message` | `text`, `kind` | Shows a line; `kind` is `plain`, `gain` (bold), `danger` (warning colour) or `quiet` (dimmed) |
| | `if` | `if`, `then`, `else` | Runs `then` when the condition holds, otherwise `else` |
| | `choose` | `prompt`, `options` (1–4) | The player picks one option; each has `label`, `condition`, `hint`, `effects` |

Example: search a crate once, with an even chance of finding something.

```json
[ { "op": "set_state", "object": "this", "state": "state_used" },
  { "op": "if", "if": { "check": "chance", "p": 0.5 },
    "then": [ { "op": "roll_loot", "table": "loot_crate" } ],
    "else": [ { "op": "message", "text": "Empty." } ] } ]
```

#### How the engine applies the grammar

Rules the engine follows that the schemas alone don't spell out:

- **Groups.** A check on several characters (subject `party`) passes when **any** of
  them passes: the party can open a door if anyone has the tool. An effect on a group
  applies to **each** member. A subject that names nobody (no target, a role not
  cast, a character not in play) makes a check fail and an effect do nothing.
- **Derived stats.** A character's stat is the sum of their body, worn frame, fitted
  modules, implants, reached skill levels and active stat changes, kept within the
  stat's `min` and `max`. For a pool this sum is the maximum.
- **Pools** start full, except the heat pool, which starts at the loadout's constant
  heat load. Lowering a maximum lowers the current value with it; raising it doesn't.
- **Broken items** (condition 0) count for nothing: no stats, tags or actions until
  repaired.
- **Size.** A character's size is their frame's, or their body's without one.
  `holds_size` left out means *no limit* on locations and objects, and *holds
  nothing* on items.
- **Items.** Plain items stack up to their `stack`; items with a condition,
  modifications or changes are unique. Carrying is limited to the `cargo` stat in
  stacks; what doesn't fit isn't given. `modify_item` on a stack takes one item off
  it. `take_item` takes from the inventory only.
- **Relations** are one-way. Without a direct view, factions stand in, in this order:
  the viewer's faction toward the other, the viewer toward the other's faction,
  faction toward faction; then the pack's `relation_default`.
- **Defeat.** When health reaches 0 the character is down and their `on_defeat` runs
  next, with `self` the defeated character and `target` whoever caused it. Restoring
  health above 0 brings them back.
- **Skills.** `grant_xp` raises a skill to every level whose `xp` is reached, up to
  `skill_max_level`, and each new level is announced.
- **Order.** Effects run in order. `if` runs its branch before the effects after it;
  `on_defeat`, `on_enter` and a status's `on_apply` run right after the effect that
  caused them. `choose` stops and waits for the player; the remaining effects run
  after the choice.
- **Messages** are shown for the player's own character and for characters in the
  player's location. Each action starts with an empty message list.
- **Walking.** A step costs one turn. Floor tiles and non-solid placements (doors on
  wall tiles) can be stood on. Walking onto a placement puts it in focus; bumping into
  a solid object or another character puts them in focus without moving. Walls do
  nothing at all. Party members move with the player. An arrival on a solid object
  lands on the nearest free floor tile.
- **The menu** shows the focused thing while it is on the player's tile or next to
  it: its interactions (`shown_if` hides, `requires` greys out with the hint), "go"
  for exits, "talk" for characters with dialogue, and "inspect". Keys come from each
  interaction's `key`; `w a s d i x q p c g t` and `1`–`4` are reserved, so a clash
  gets a spare letter.
- **Repeats.** `once` interactions are used up for good, `daily` ones until the next
  day; the count is per placement or character.
- **Time.** Interactions take their `time`; exits their `time`; talking one turn.
  `spend_time` adds to the turns owed, which are processed after the action. Each turn,
  every character in a location gets the location's `on_turn`; statuses run their
  `on_turn` once per stack, count down and end with `on_expire`; timed stat changes
  count down. A choice waiting for the player pauses time.
- **Not yet active** (later milestones): `start_encounter` and `trigger_event` are
  recorded and handled by encounters (milestone 4) and the event engine
  (milestone 6); `end_encounter` does nothing outside an encounter.
- **Saves** go to `saves/<pack folder>/<slot>.json` and hold only the state. A save
  only loads with the same pack and the same major pack version.
- **Refitting.** Frames, modules and implants are fitted or removed only within reach
  (the player's tile or next to it) of a workshop offering `refit`. A fit needs a free
  slot, the item's `fit_requires`, power and mass within what the loadout provides,
  constant heat below maximum heat, and for a frame, a size that fits the current
  location. A frame comes off only after its modules. Removed items go to the
  inventory, which must still fit in cargo afterwards (a frame often provides cargo).
  When a pool's maximum changes, its current value moves with it, never below 1, so
  putting on a suit adds its health.
- **Size at exits.** Going through an exit needs the traveller's size to fit the exit
  placement's `holds_size` and the destination's.
- **Storage.** Objects with `storage` within reach take and give items one at a time;
  items must fit their `holds_size`. That's where suits are parked.
- **Using items.** An item's interactions are used from the pack; for a consumable,
  each use spends one before the effects run. In item interactions the item pick
  `{"used": true}` is the item itself.

#### Interactions

An **interaction** is something a character can do with an object, another
character or an item. Anything in the world is "when this holds, doing this has
these effects":

| Field | Meaning |
|---|---|
| `id` | Unique within its owner; placements override template interactions by id |
| `label` | Shown in the menu |
| `key` | Suggested single key in the menu; the engine may reassign it |
| `shown_if` | Hidden unless this holds |
| `requires` | Shown but unavailable unless this holds |
| `hint` | Shown when `requires` fails, e.g. "Needs a cutter or a heavier frame." |
| `time` | Turns it takes (default 1) |
| `repeat` | `always` (default), `once`, or `daily` (available again each new day) |
| `effects` | What happens |

### Pack manifest (`pack.json`)

| Field | Meaning |
|---|---|
| `id`, `name`, `description`, `authors` | Identity |
| `version` | The pack's own version, `major.minor.patch` |
| `schema_version` | The schema version it targets (currently `1`) |
| `purpose` | `game` (default) or `test` |
| `start` | `location`, optional `entry` placement, `player` character, `day` (1), `phase` (the first one) |
| `settings` | `skill_max_level` (5), `relation_min` (-100), `relation_max` (100), `relation_default` (0) |
| `files` | Data files by kind; paths relative to the pack, no `..` |
| `extends` | Packs this one modifies. Reserved, for mods |

### Vocabulary (`vocab.json`)

The vocabulary declares the words the rest of the pack refers to. The schemas fix
the structure; the vocabulary fixes the words. `stats`, `sizes` and `phases` are
required.

| Section | Declares | Fields |
|---|---|---|
| `tags` | Tags things carry | `id`, `name` (a noun phrase used in hints, e.g. "a pry-bar"), `description`, `hazard` (shown as a danger on locations) |
| `stats` | Numbers | `id`, `name`, `short` (≤4 chars), `kind` (`value`, or `pool` with a current and a maximum), `role`, `min`, `max` |
| `damage_types` | Kinds of harm | `id`, `name`, `resisted_by` (a stat that reduces it point for point) |
| `statuses` | Temporary conditions | `id`, `name`, `glyph`, `harmful`, `stacking` (`refresh`, `stack`, `ignore`), `max_stacks`, `blocks_actions`, `on_apply`, `on_turn`, `on_expire` |
| `slot_types` | Slots | `id`, `name`, `host` (`frame` for suits, `body` for implants) |
| `grades` | Item tiers | `id`, `name`, `colour`, `order` |
| `sizes` | Size class names | `size` (0–9), `name` |
| `ranks` | Rank names | `rank`, `name` |
| `relation_levels` | Relation bands | `min`, `name` (a value takes the band with the highest `min` not above it) |
| `object_states` | Object states | `id`, `name` (the word shown, e.g. "locked") |
| `phases` | Parts of the day, in order | `id`, `name`, `turns`; a day is the sum of their turns |
| `factions` | Groups | `id`, `name`, `description` |
| `flags` | Named world numbers | `id`, `description`, `default` |

**Stat roles.** The engine needs to know a few stats by meaning rather than by name.
Each role must be given to exactly one stat:

| Role | Meaning | Kind |
|---|---|---|
| `health` | A character is down at 0 | pool |
| `heat` | Builds up with actions; at its maximum the frame overheats | pool |
| `power` | Fitting budget: provided by the loadout, used by modules | value |
| `mass` | Fitting budget: provided by the loadout, used by modules | value |
| `initiative` | Who acts first in an encounter | value |
| `cargo` | How many item stacks a character can carry | value |

**Grade colours** come from the engine's palette: `grey`, `white`, `green`, `cyan`,
`blue`, `violet`, `yellow`, `orange`, `red`.

### World (`world.schema.json`)

**Regions** group locations and can nest: a station holds a ring that holds rooms.

| Field | Meaning |
|---|---|
| `parent` | The region this one belongs to |
| `map` | `{x, y}` on the parent's map view |
| `tags` | Tags on the region |
| `mobile` | Reserved: the region is a ship. `airlock` (its placement that docks) and `docked_at` (the dock port it starts at) |

**Locations** are rooms or open areas the player walks around in.

| Field | Meaning |
|---|---|
| `region` | Required |
| `grid` | `width` and `height` (3–10), `floor` and `wall` glyphs, optional `rows` |
| `size`, `holds_size` | How big the space is, and the largest size class that can be inside (living areas keep heavy suits out) |
| `tags` | Tags marked as hazards are shown as dangers |
| `entry` | Where arrivals appear; defaults to the grid centre |
| `placements` | Objects in the room |
| `on_enter`, `on_turn` | Effects when a character arrives, and every turn for each character here. Hazards live in `on_turn` |
| `map` | `{x, y}` on the region's map view |
| `template` | A room shape for procedural zones, not part of the fixed world |

`rows` draws shapes other than a rectangle: one string per row, `#` for wall, `.`
for floor and a space for nothing. Without `rows` the edge is wall and the inside is
floor. Grid positions are `[row, column]` from the top-left corner.

```json
"grid": { "width": 7, "height": 5, "floor": "~", "wall": "░",
          "rows": ["###.###", "#.....#", "#.....#", "##...##", " ##### "] }
```

A **placement** puts an object template at a grid position:

| Field | Meaning |
|---|---|
| `id` | Unique across the pack; checks and effects refer to it |
| `object` | The template |
| `at` | `[row, column]` on a wall or floor tile, one placement per tile |
| `name`, `description`, `glyph`, `state`, `contents` | Override the template's |
| `tags` | Added to the template's |
| `interactions` | Merged with the template's by id: the same id replaces, a new id adds |
| `exit` | Makes it a way to somewhere else |
| `dock_port` | Reserved: ships can dock here |

An **exit** leads to a `location` (or, reserved, a `zone`). It may name an `entry`
placement in the destination, a `label` (default "Go to …"), a `requires` condition
with a `hint`, and a `time`. The engine offers the "go" interaction by itself.

```json
{ "id": "pl_a_door_b", "object": "obj_door", "at": [0, 2],
  "exit": { "location": "room_b", "entry": "pl_b_door_a",
            "requires": { "check": "object_state", "object": "this", "state": "state_open" },
            "hint": "The door is closed." } }
```

**Zones** (reserved) are procedural areas built from template rooms: `rooms` (an
amount), `room_pool` (template locations with `weight` and `max`), `object_pool`
(objects with `weight` and `per_room`), `encounters` with `weight`,
`encounter_chance`, `regenerate` (`never`, `daily`, `on_leave`) and the `exit`
placement that leads back.

### Objects (`object.schema.json`)

Object templates are the things locations place: doors, crates, terminals,
machines, bunks.

| Field | Meaning |
|---|---|
| `name`, `glyph`, `description`, `tags` | Required: `name`, `glyph` |
| `size`, `holds_size` | Its size, and the largest thing that fits in, through or onto it |
| `solid` | Blocks walking onto its tile; used from a neighbouring tile |
| `states` | The states it can be in; the first is the initial one unless `state` says otherwise |
| `state_glyphs` | A different glyph per state, e.g. an open hatch |
| `storage` | It holds this many item stacks (a locker, a suit bay) |
| `contents` | What it holds at the start: items with counts. A placement's `contents` replace the template's |
| `workshop` | It is a workshop: `services` (`refit`, `dismantle`, `fabricate`, `modify`, `repair`) and an optional `max_grade`. Frames, modules and implants can only be changed where `refit` is offered |
| `interactions` | What characters can do with it; `this` is the placed object |

### Items (`item.schema.json`)

Every item has a `kind` that decides which extra fields it takes.

**Fields every item has:**

| Field | Meaning |
|---|---|
| `id`, `kind`, `name`, `size` | Required |
| `description`, `grade`, `tags` | Tags count for `has_tag` while carried, fitted or implanted |
| `holds_size` | For items that hold things (a bag, a cargo module): the largest size that fits. Without it nothing fits |
| `stats` | Added to the holder while the item is active (worn, fitted, implanted) |
| `actions` | Encounter actions it gives while active |
| `interactions` | What the holder can do with it from the pack |
| `value` | Rough trade value |
| `stack` | How many fit in one cargo stack (default 1) |
| `condition` | Maximum condition. Items with one wear down and break at 0; items without one never wear. Stacking items can't have one |
| `salvage` | Dismantling: `yields` (items and counts), `learn` (whether it teaches the design, default yes), `learn_requires` |
| `fabricate` | Making a copy: `inputs`, `requires`, `time` |
| `repair` | Restoring condition: `inputs`, `amount` (full repair if left out). Only for items with a condition |

**Kinds and their extra fields:**

| Kind | What it is | Extra fields |
|---|---|---|
| `frame` | A suit or piloted machine. Its size is the wearer's size | `slots` (slot types with counts), `mod_slots`, `fit_requires` |
| `module` | Anything fitted into a frame slot. **Gear** is a module in a limb or hand slot | `slot_type`, `uses`, `mod_slots`, `fit_requires` |
| `implant` | Fitted into a body slot; stays when changing suits | `slot_type`, `mod_slots`, `fit_requires` |
| `material` | Scrap, ore, exotic matter | none |
| `consumable` | Each use of one of its interactions spends one | none |
| `misc` | Keys, passes, data, keepsakes, trade goods | none |

**How fitting works.** The stats of the body, frame, modules and implants together
*provide* the budgets: the stat with the `power` role gives power, and so on. Each
module's `uses` takes `power` and `mass` from those budgets, and both must fit.
`heat` in `uses` is a constant load that lowers how much heat can build up before
overheating, and it must stay below maximum heat. Carried items must fit in cargo,
counted in stacks. Frame traits such as sealing, limbs or thrusters are tags.

```json
{ "id": "module_system", "kind": "module", "name": "System A", "size": 2,
  "slot_type": "slot_frame_a", "uses": { "power": 3, "mass": 3, "heat": 2 },
  "stats": { "stat_armor": 2 }, "mod_slots": 2 }
```

### Actions (`action.schema.json`)

Actions are what characters do in encounters, shown as tiles. They are not cards:
nothing is drawn or shuffled. A character's actions come from fitted items, skill
levels, their own `actions` list, and innate actions.

| Field | Meaning |
|---|---|
| `name`, `short` | `short` (≤8 chars) is the tile's label |
| `description`, `glyph`, `tags` | Tags say what kind of action it is (attack, defence…) |
| `target` | `self`, `enemy` (default), `ally`, `all_enemies`, `all_allies` |
| `cost` | `heat` (an amount), `cooldown` (rounds), `charges` (per encounter), `consumes` (`item` or `tag`, `count`) |
| `requires`, `hint` | Usable only when the condition holds; otherwise the tile is greyed out with the hint |
| `priority` | -3 to 3: acts earlier or later in the round than initiative alone would put it |
| `effects` | Required. Damage defaults to the target |
| `trains` | Skill experience gained per use: `{"skill_a": 3}` |
| `innate` | Every character has it (retreat, wait) |
| `intent` | Word shown over an AI-controlled character about to use it, e.g. "CRUSH" |
| `ai` | `when` it is considered and its `weight`, for AI-controlled characters |

### Skills (`skill.schema.json`)

The suit is your stats; you are your skills. Skills rise with use.

| Field | Meaning |
|---|---|
| `name`, `short`, `description` | Identity |
| `earned_by` | How it grows, in plain words |
| `levels` | Listed once each, lowest first: `level`, `xp` (total needed; level 1 needs 0), `text` (what it adds, in plain words), and what it grants: `actions`, `tags`, `stats` |

Everything a level grants is kept at higher levels. No level may exceed the pack's
`skill_max_level`.

### Characters (`character.schema.json`)

One record serves the player's character, NPCs, companions and enemies.

| Field | Meaning |
|---|---|
| `name`, `title`, `description`, `glyph` | The glyph defaults to the first letter of the name |
| `art` | A picture of up to 10 lines of 21 characters, shown during encounters |
| `tags`, `faction`, `rank` | |
| `template` | Generic character that encounters and zones spawn copies of; has no location |
| `location`, `at` | Where a unique character starts; `at` must be a free floor tile |
| `leader` | Starts in this character's party |
| `body` | Required: `size`, `stats` (base health, cargo…), `slots` (implant slots unlocked at the start) |
| `frame`, `fitted`, `implants` | Worn suit, modules in its slots, implants in the body |
| `inventory` | Carried items with counts |
| `designs` | Items they can fabricate at the start |
| `skills` | Starting levels: `{"skill_a": 2}` |
| `actions` | Actions of their own, e.g. a drone's claws |
| `views` | Starting relations: `toward` (an agent) and `value` |
| `wants` | Tags of things they value, for trades and the world simulation |
| `talk` | Dialogue lines: `when`, `text`, `effects`. The first line whose condition holds is used |
| `interactions` | What others can do with them. Trading and recruiting are ordinary effects |
| `ai` | `flee_below`: try to escape below this share of maximum health |
| `loot` | Loot table rolled for whoever defeats them |
| `on_defeat` | Effects when they go down. For the player's character, this decides what losing means |

### Encounters (`encounter.schema.json`)

An encounter happens where it starts. The player's party is always on the player's
side.

| Field | Meaning |
|---|---|
| `name`, `description`, `intro` | `intro` is shown when it starts |
| `enemies`, `allies` | Side entries: `character`, and a `count` (an amount) for templates only |
| `escape` | Whether retreat actions can end it (default yes) |
| `loot` | Rolled for the winners, besides each defeated character's own loot |
| `on_start`, `on_win`, `on_lose`, `on_escape` | Effects. On a loss, the player character's `on_defeat` runs too |

### Loot tables (`loot.schema.json`)

| Field | Meaning |
|---|---|
| `rolls` | How many times to draw (an amount, default 1) |
| `entries` | Each is an `item` with a `count`, or another `table`; with `weight` and an optional `when` condition |
| `nothing` | Weight of drawing nothing |
| `always` | Items given every time, before the rolls |

A table may roll other tables, but never itself, directly or through others.

### Events (`event.schema.json`)

Events are how stories come out of the rules. An event doesn't name its characters.
It finds a **cast** by conditions, so the same event can play out between different
people each time, including NPCs far from the player.

| Field | Meaning |
|---|---|
| `trigger` | When the engine considers it: `day_start` (default), `turn`, `enter_location`, or `manual` (only through `trigger_event`) |
| `cast` | Roles filled in order. Each has `role` (its name), `character` (always this one) or `from` (`anyone`, `here`, `party`), a `when` condition with `self` as the candidate, and `optional` |
| `when` | Must hold once the cast is filled |
| `chance` | Chance to fire each time it's considered |
| `weight` | Relative likelihood when several events could fire at once |
| `cooldown` | Days before it can fire again |
| `repeat` | Whether it can fire more than once |
| `notify` | Whether the player sees its messages; off-screen events between NPCs usually don't |
| `text`, `effects` | Shown and run when it fires. Use `choose` for a decision |

A role is used as `{"role": "name"}` wherever a subject or agent goes. A cast
condition may only use roles filled before it, and roles exist only inside events.

```json
{ "id": "event_grudge", "trigger": "day_start", "chance": 0.3, "cooldown": 3,
  "cast": [ { "role": "sore", "when": { "check": "relation", "of": "self", "toward": "player", "max": -20 } } ],
  "effects": [ { "op": "choose", "prompt": "What do you do?", "options": [
      { "label": "Apologise", "effects": [ { "op": "change_relation", "of": { "role": "sore" }, "amount": 10 } ] },
      { "label": "Ignore it", "effects": [] } ] } ] }
```

### Strings (`strings.schema.json`)

All text the engine prints comes from the pack.

- **`engine`** maps each engine message key to the pack's wording. Placeholders in
  braces are filled in by the engine, and each message may use only its own:
  `"enter_location": "You enter {location}."`. A missing message is shown as its key,
  and the validator warns about it.
- **`entries`** are reusable texts (`id`, `text`) that any text field can show with
  `@id`.

| Key | Placeholders |
|---|---|
| `enter_location` | `{location}`, `{character}` |
| `exit_blocked` | `{object}`, `{state}` |
| `needs` | `{needs}` (tag names joined with `list_or`) |
| `list_or`, `list_and` | none |
| `nothing_here`, `unknown_command` | none |
| `items_found`, `items_gained`, `items_lost` | `{items}` |
| `item_broken`, `cargo_full` | `{item}` |
| `cannot_fit` | `{thing}`, `{container}` |
| `skill_up` | `{skill}`, `{level}`, `{text}` |
| `party_join` | `{character}`, `{leader}` |
| `party_leave`, `character_down`, `overheated` | `{character}` |
| `encounter_start`, `encounter_won`, `encounter_lost`, `encounter_escaped` | `{encounter}` |
| `status_applied`, `status_ended` | `{character}`, `{status}` |
| `day_start` | `{day}` |
| `phase_start` | `{phase}`, `{day}` |
| `go_to` | `{destination}` |
| `talk`, `inspect`, `already_used`, `unavailable` | none |
| `keys_walk`, `keys_menu`, `keys_choice` | none (the key hints at the bottom) |
| `day_phase` | `{day}`, `{phase}` |
| `party` | `{names}` |
| `pack_fitted`, `pack_carried`, `game_saved` | none |
| `character_title` | `{name}` |
| `terminal_too_small` | `{columns}`, `{rows}` |
| `fit`, `remove`, `store`, `take` | none (pack panel labels) |
| `refit_needed`, `frame_worn`, `frame_needed`, `remove_modules_first`, `keys_pack` | none |
| `no_free_slot`, `cannot_use`, `item_fitted`, `item_removed` | `{item}` |
| `over_budget` | `{stat}`, `{need}`, `{have}` |
| `storage_full`, `pack_stored` | `{container}` |
| `item_stored`, `item_taken` | `{item}`, `{container}` |

### Modifications (`modification.schema.json`)

Crafting is mostly about improving found items, and the results are predictable.
Dismantling, fabricating and repairing are described on the items themselves.
Modifications are the only separate crafting data.

A modification applies a material to a matching item and always adds the same
thing. It takes one of the item's mod slots, permanently.

| Field | Meaning |
|---|---|
| `name` | Added to the item's name, e.g. "Reinforced" |
| `material`, `count` | The material used (must be a `material`) and how many |
| `applies_to` | `kinds` (required: `frame`, `module`, `implant`), and optionally `tags` (any of) and `slot_types`. An item must match every field given |
| `requires` | Needed to apply it, e.g. a skill level |
| `adds` | At least one of `stats`, `tags`, `actions`, `max_condition`, `uses` (a change to a module's power, mass or heat use; negative lowers it) |
| `once` | Can be applied to the same item only once (default yes) |

Refitting and crafting happen at **workshops** (objects with a `workshop` block).
**Refit** lets characters change frames, modules and implants; parking a suit is
storing it in an object whose `holds_size` fits it. The four crafting services:

- **Dismantle** destroys an item, gives its `salvage.yields`, and teaches its design
  if `salvage.learn_requires` holds.
- **Fabricate** makes a copy of a known design from `fabricate.inputs`.
- **Modify** applies a modification.
- **Repair** restores condition from `repair.inputs`.

### The validator

```sh
python3 -m core.packtool check packs/test     # or: python3 -m core.pack packs/test
```

It prints every error and warning with the file and the path inside it, and exits
with 1 if there are errors:

```
vocab.json: statuses[0].on_turn[0].op: unknown op 'dmg'. Known: apply_status, change_rank, …
locations.json: entries[0].placements[1]: position [9, 9] is outside the grid
```

**Errors** make a pack unusable:

- **Files:** missing files, invalid JSON (with line and column), kinds without a
  schema.
- **Schema:** every file against its schema: types, required and unknown fields,
  id patterns, lengths and ranges, and one form per `check`, `op` and `kind`.
- **Ids and references:** duplicate ids in a namespace (across files too); references
  to ids that don't exist; sizes that the vocabulary doesn't name; `@id` texts that
  don't exist.
- **Vocabulary:** each stat role held by exactly one stat; `health` and `heat` are
  pools; ranks and relation bands don't repeat; relation settings make sense.
- **World:**
  - placements inside the grid, one per tile;
  - `rows` matching the grid size;
  - entry points and exit arrivals in the right location;
  - no exits into template rooms, and no start in one;
  - no region inside itself;
  - object states that belong to the object;
  - zone room pools made of templates.
- **Items and crafting:**
  - frames and modules use frame slots, implants use body slots;
  - stacking items don't wear;
  - repair costs only on items that wear;
  - dismantling never returns the item itself;
  - modifications use materials.
- **Skills:** levels listed once each, lowest first; experience rising; level 1 at 0
  experience; no level above `skill_max_level`.
- **Characters:**
  - the worn frame is a frame, fitted items are modules, implants are implants;
  - no slot over-filled;
  - power and mass within the budgets;
  - constant heat below maximum heat;
  - inventory within cargo;
  - skill levels within the maximum;
  - templates without a location, standing characters on free floor tiles;
  - no leader loops;
  - the start character isn't a template and isn't placed elsewhere.
- **Encounters, loot and events:**
  - only templates take a count;
  - no loot table rolls itself;
  - event roles cast before use, once each, and only inside events.
- **Strings:** engine messages use only their placeholders and valid braces.

**Warnings** don't stop a pack:

- reserved features in use;
- references to kinds the pack doesn't load;
- engine messages not written yet;
- `max_stacks` on a status that doesn't stack.

---

## Glossary

**Action.** Something a character can do in an encounter, shown as a tile. Comes
from fitted items, skill levels, the character's own list, or is innate.

**Agent.** Anyone who can hold a view of others: a character, a faction, or a
subject word. Used by relations.

**Amount.** A number in data: fixed, a seeded `{min, max}` range, or scaled from a
stat or skill.

**Art.** A small picture made of characters, shown during encounters.

**Body.** A character without a suit: size, base stats and implant slots.

**Budget.** The power and mass a loadout provides and its modules use, and the heat
limit that constant heat load eats into.

**Cargo.** How many item stacks a character can carry. A stat role.

**Cast.** The roles an event fills by conditions before it fires.

**Character.** Anyone: the player's character, NPCs, companions, enemies. All follow
the same rules.

**Check.** A leaf of a condition, picked by its `check` field (`has_tag`, `skill`…).

**Condition.** (1) A true-or-false tree of checks combined with `all`, `any` and
`not`. (2) An item's wear level; items with a condition break at 0. The two meanings
are distinguished by context: `requires` and `when` fields hold the first,
`condition` on an item and the `item_condition` check refer to the second.

**Content.** Everything in a pack: the world, items, people, text. Opposite of the
engine.

**Design.** Knowing how to fabricate an item. Learned by dismantling one (skill
permitting) or through `learn_design`.

**Dismantle.** Destroying an item at a workshop for materials, and possibly its
design.

**Effect.** One thing that happens, picked by its `op` field.

**Encounter.** A fight or confrontation, played with actions.

**Engine.** The code. It reads packs and names no content.

**Entry.** (1) One record in a data file's `entries` list. (2) The placement where
arrivals appear in a location.

**Event.** A living-world rule that finds its own cast and changes the world.

**Exit.** A placement block that leads to another location or zone.

**Fabricate.** Making a copy of a known design from materials at a workshop.

**Faction.** A group characters belong to and hold views of.

**Fitting.** Putting modules into a frame's slots within its budgets.

**Flag.** A named world number (0 when unset) that checks read and effects change.

**Frame.** A suit or piloted machine, from a rugged vacuum suit to a suit-ship hybrid.
Its size becomes the wearer's size.

**Game pack.** A pack with the real game content.

**Gear.** A module fitted in a limb or hand slot: tools and weapons.

**Glyph.** The character drawn for something on the map.

**Grade.** An item's tier, drawn in its grade's colour.

**Grammar.** The shared building blocks in `common.schema.json`: subjects,
amounts, conditions, effects, interactions.

**Hazard.** A tag shown as a danger on locations. The harm itself comes from the
location's `on_turn` effects.

**`holds_size`.** The largest size class that fits in, through or onto something.

**Implant.** An item fitted into a body slot. Stays across suit changes.

**Innate.** An action every character has.

**Intent.** The word shown over an AI-controlled character about to act.

**Interaction.** Something a character can do with an object, character or item:
conditions, a hint and effects.

**Item pick.** A way to say which item an effect means: by id, by tag, by slot type,
or the one just used.

**Kind.** (1) The type of an item (`frame`, `module`…). (2) The type of a data file
in the manifest (`items`, `locations`…).

**Label.** A short name that fits a narrow screen.

**Loadout.** A character's frame, fitted modules and implants together.

**Location.** A room or area on a grid.

**Loot table.** A weighted list of items and other tables.

**Material.** An item used for crafting and trade.

**Mod slot.** Room on an item for one modification.

**Modification.** A material applied to an item that always adds the same thing.
Permanent.

**Module.** An item fitted into a frame slot.

**Namespace.** The set of ids of one kind (`item`, `placement`, `tag`…) that
references point into.

**Object.** A template for a thing placed in locations.

**Object state.** A state an object can be in, such as open or locked.

**On-screen / off-screen.** Near the player, simulated in full; far away, kept as
short records moved by events.

**Op.** The field that picks an effect.

**Pack.** A folder of content data with a manifest.

**Parity.** The rule that the player follows the same rules as every other
character.

**Party.** A leader and the characters travelling with them.

**Phase.** A part of the day, such as morning.

**Placement.** An object template put at a grid position, with a pack-unique id.

**Pool.** A stat with a current value and a maximum, such as health.

**Rank.** A character's standing in the Registry.

**Reference.** A field holding the id of something else.

**Region.** A group of locations, such as a station or a ship. Can nest.

**Relation.** How one agent regards another. One-way.

**Repair.** Restoring an item's condition from materials at a workshop.

**Reserved.** Designed but not supported by the engine yet.

**Role.** (1) A named part in an event's cast. (2) A stat role (below).

**Salvage.** What dismantling an item gives.

**Schema.** A JSON Schema file describing one kind of content.

**Schema version.** The version of the schemas a pack targets.

**Size.** A size class from 0 to 9 for anything: items, objects, characters, frames,
locations. A shorthand for volume.

**Skill.** Know-how that rises with use. Each level adds one clear thing.

**Slot type.** A kind of slot, on a frame or in the body.

**Stack.** A group of identical items in one cargo space.

**Stat.** A number on characters, items and objects.

**Stat role.** The built-in meaning the engine gives one stat: health, power, mass,
heat, initiative or cargo.

**Status.** A temporary condition on a character, such as burning.

**Strings.** The pack's wording for engine messages, plus reusable texts.

**Subject.** Who or what a check or effect applies to.

**Tag.** A word things carry, which checks can look for.

**Template.** (1) A generic character spawned by encounters. (2) A room shape for
zones. (3) An object definition that placements use.

**Test pack.** A pack with small generic content for engine work and tests.

**`this`.** The placed object whose interaction or template is running.

**Trigger.** When the engine considers an event.

**Validator.** `core/pack.py`: checks a pack against the schemas and the game's
rules.

**View.** A character's starting relation toward someone.

**Vocabulary.** The pack's declared words: tags, stats, statuses and so on.

**Workshop.** An object where crafting happens.

**Zone.** A procedural area built from template rooms. Reserved.
