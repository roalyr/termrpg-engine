# Vision

This page is the top-level reference for what the game is. Where it disagrees with
`System Architecture & Game Design Document.md`, this page wins. That document
still describes how the current engine works until each system is redesigned.

## In one sentence

A salvager on the frontier of space gets stronger by recovering and fitting strange
technology, takes on ever more dangerous places, and grows alongside the people they
meet, while a world that runs on its own rules creates the story around them.

## How it should feel

Like reading a web novel you're living in. You climb step by step, get stronger in
ways you can see, pick up companions, suffer setbacks that become turning points, and
always sense that the world is bigger than where you are now. The game is open-ended.

## Pillars

1. **Build.** Your character, suits and later your ship are made of pieces you choose
   and combine. This is where most of the player's thinking goes.
2. **Challenge.** Dangerous places, encounters and fights test the build.
3. **Craft and salvage.** What you win becomes material, and material becomes new
   pieces for the build. The world starts seeded with predefined items; modding and
   reinforcing them come later.
4. **Frontier.** A hand-made world with some areas that regenerate. Stranger
   materials lie farther out, which pulls the player outward.
5. **A living world.** People, factions, rivals and events follow their own rules and
   react to the player. Stories come out of those rules, not from scripts. This
   pillar supports the others; it is not the core.

## Loops

```
 ENCOUNTER    choose actions from your fit and skills against a threat
 EXPEDITION   hub → refit → enter a zone → encounters → return with spoils
 JOURNEY      better build → rank and reputation → farther, stranger regions
              → the world changes around what you did
```

Everything runs through the build: challenges test it, salvage feeds it, companions
add to it, setbacks change it.

## The build

- **The suit is your stats. You are your skills.** Characters have no body
  attributes.
- **Suits** are frames with slots for gear and modules, limited by **power, mass and
  heat**. They range from rugged unpowered vacuum suits to exoskeletons, semi-mech
  machines and suit-ship hybrids. The goal is versatility and mobility, hence limbs.
  A suit's frame decides where it can go.
- **Implants** are slots in the body, unlocked through play and empty at the start.
  They stay with you when you change suits.
- **Skills** are one short list (for example Piloting, Cutting, Rigging, Gunnery,
  Systems, EVA), each at level 1 to 5. Using a skill raises it. Each level adds one
  clear thing: a frame you can pilot, a module you use well, or a new action.
- **Refitting** happens only in hubs, dedicated bays and ship hangars. Heavy suits
  can't enter living areas. You may own several suits, limited by parking space.

## Encounters

- In an encounter, **actions** appear as tiles in Zone 4. They come from what you
  have fitted plus your skills. This is not a deck-builder: nothing is drawn or
  shuffled, and the fitting board stays the real model.
- Combat is part of the core, alongside hazards and obstacles.
- Encounters should read at a glance: bars, what the enemy is about to do, pictures,
  and colour. Plain text alone is not enough.

## World

- **Ships and shuttles are locations that move.** They have rooms and hangars and
  dock at different places. Personal suits and small crewed vessels are how you leave
  them to reach surfaces, derelicts and tunnels.
- **Strangeness** is a slow reveal of **exotic materials**: things nobody can explain
  but everyone can use. Each new tier shows up first as a tool, later as a question.
  Soft sci-fi that feels like hard sci-fi.
- **Scope of the simulation: detailed nearby, abstract far away.** Rivals and factions
  away from the player are short records moved forward once a day by one roll, with
  one tunable progress rate and a fixed number of records. When one meets the player,
  it becomes a full character.

## The player

- Starts as a nobody, with an optional backstory chosen at character creation that
  shapes the start, not a quest.
- Losing is tragic and dramatic, never an outright game over, and ideally a turning
  point: new paths, grudges, knowledge.

## Design rules

- Few, simple systems. Merge layers instead of adding them.
- Settle the big picture before designing any system in detail.
- Stories come from mechanics and how they interact, not from hand-written plots.
- **Hand-made core, controlled procedural generation.** Randomness is seeded, so runs
  differ but stay reproducible and testable.

## Engine and content

The engine and the game content are separate products, with a strict schema as the
only contract between them.

- **The engine never names content.** No room, item, person, tag or text is hardcoded
  in code. Everything the engine needs (starting location, what a tag means, names
  shown to the player) comes from the content pack.
- **A content pack is a folder of data** validated against a versioned schema. The
  engine refuses to load a pack that doesn't match, and says where it failed.
- **Two kinds of pack:**
  - a **test pack** with small, generic content (`room_a`, `item_1`, `enemy_basic`),
    used for engine development and automated tests;
  - the **game pack** with the real world, names and writing, where content work
    happens.
- **Either side can change safely.** Engine work runs against the test pack. Content
  work only touches the game pack and is checked by the schema validator plus a pack
  test (for example: every zone is reachable).
- Modding and new content follow the same path: a new or edited pack, no code.

## Schema-first development

The schemas in `schemas/` are the source of truth for what the game can contain and
do. The condition and effect types they define are the engine's feature list: if an
interaction can't be expressed in the schema, the engine can't do it yet.

Every feature goes through the same order:

1. **Schema.** Extend or add the schema, and describe the new fields and types.
2. **Test pack.** Add small generic data that uses the new part of the schema.
3. **Engine.** Implement it against the test pack, with tests.
4. **Game pack.** Write the real content.

Rules:

- A schema change that breaks existing packs raises `schema_version`. Packs state the
  version they were written for.
- Schemas may reserve fields for features the engine doesn't implement yet, as long
  as they're marked as reserved. This keeps planned features from forcing a redesign
  later.
- Vocabulary (tags, stats, damage types and the like) is declared by each pack, not
  listed in the schema. The schema fixes structure, not content.

## Kept from the current game

The room grid and walking, the six-zone screen, saving and loading, the two stations
and the Moon as the starting region, and the grounded, dry tone.
