# Design: a genre-agnostic engine (milestone 8)

Status: **Proposed.** Big picture only; nothing here is built until the user agrees.

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
slot of its type. The frame becomes an optional worn layer that adds slots, stats and
a size. Modules and implants then differ only in their slot types, so they could
become one kind.

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
seen by pack authors, not players. The changes above break packs anyway, so this is
the cheapest moment to rename them to neutral words, for example `outfit`, `gear`,
`change`. The alternative is to keep them and document them as neutral terms.

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

## Open questions

- **Q1.** Merge modules and implants into one kind?
- **Q2.** Rename the author-facing words now, or keep them?
- **Q3.** Should the frame stay a special item at all, or become just gear in a "worn"
  slot that adds slots and size?
- **Q4.** Does the fantasy pack's shape above cover what you want proven, or should it
  test something else (for example a party of several heroes)?
