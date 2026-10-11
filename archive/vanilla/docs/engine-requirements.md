# Engine requirements

What the pack needs from the engine and the UI. Each entry says what the design
needs, whether the current engine can already do it, and if not, the smallest change
that would. Engine changes follow the schema-first order in AGENTS.md and need the
user's go-ahead.

Status: **Works** (content can do it today), **Check** (probably works, to confirm
with a small test), **Needed** (engine or schema change), **Deferred** (wanted, not
for 1.0).

| # | Need | Status | Notes |
|---|---|---|---|
| 1 | Surface as a 6×6 grid of locations | Works | Each cell a location; edge exits are path placements on wall tiles, one in each cell of a pair. Many placements to write, but nothing new |
| 2 | An overview map of the surface | Works | The map screen (M) draws a region's locations at their `map` x/y: places you've been and where their exits lead. Give each surface cell a `map` position |
| 3 | Shuttle on a schedule | Check | An exit or interaction with a `time` check on day or phase. Confirm how phases map to a schedule the player can read |
| 4 | Expanding the player's workshop or room with bought parts | Needed? | A workshop's `services` and `max_grade` are fixed per object and don't change with state. Options: pre-placed workshops unlocked by a state or a door, or an engine change letting services depend on state |
| 5 | Solar storms on the open surface | Check | A `day_start` event sets a flag; each surface cell's `on_turn` checks it. Works, but repeated in 36 cells |
| 6 | Suit endurance outside habitats | Check | A pool stat drained by `on_turn` in exposed locations, restored in habitats. Depends on J2 |
