# Vision

This page is the foundation: what the engine is for and the rules every game built on
it follows. Every other document follows from it, and where one disagrees, this page
wins. Each game's own vision lives with that game.

## In one sentence

An engine and toolkit for terminal RPGs in which characters are built from pieces,
tested by dangerous places, improved through crafting, and live in a world that runs
on its own rules, so the story comes from play.

## What its games are made of

- **Build.** A character is made of pieces they choose and combine: what they wear,
  what they hold and carry in slots, what is part of their body, and their skills.
  Budgets the game defines limit what fits, and what a character wears decides where
  they can go. This is where most of the player's thinking goes.
- **Challenge.** Places, hazards, obstacles and encounters test the build.
- **Craft.** What you win becomes material, and material becomes new pieces:
  - **Modify:** apply a material to an item; the material decides what it adds,
    always the same way. Items have a few mod slots, and modifications are permanent.
  - **Dismantle:** break an item down into materials and, with enough skill, learn
    its design.
  - **Fabricate** copies of known designs, and **repair** worn items, at workshops.
  - Results are predictable: no random rolls in crafting.
- **A living world.** People, factions, rivals and events follow their own rules and
  react to the player.

## Encounters

- **Actions** appear as tiles. They come from what a character has fitted plus their
  skills. This is not a deck-builder: nothing is drawn or shuffled, and the fitting
  board stays the real model.
- Encounters should read at a glance: bars, what the enemy is about to do, pictures,
  and colour. Plain text alone is not enough.
- **Losing is never a game over.** What defeat means is the game's to write.

## Design rules

- **Player-NPC parity.** The player is a character like any other. Every rule, stat,
  check and effect works the same for every character, and any character can be
  controlled by the player or by the AI. There are no player-only mechanics: NPCs
  change gear, gain skills, travel in parties, hold views of each other and rank up by
  the same rules.
- Few, simple systems. Merge layers instead of adding them.
- Settle the big picture before designing any system in detail.
- Stories come from mechanics and how they interact, not from hand-written plots.
- **Detailed nearby, abstract far away.** People and factions away from the player
  move forward in simple, cheap steps. When one meets the player, they are a full
  character.
- **Hand-made core, controlled procedural generation.** Randomness is seeded, so runs
  differ but stay reproducible and testable.

## Engine and content

The engine and the game content are separate products, with data as the only
contract between them.

- **The engine knows no genre.** A powered suit and a suit of armour, a plasma cutter
  and a sword, a reactor's heat and a mage's mana are the same mechanics under
  different names. Test packs in more than one genre keep this true.
- **The engine never names content.** No room, item, person, tag or text is written
  into the engine. Every place, name and meaning a game uses comes from a content
  pack.
- **What the engine can do is what the data can say.** A feature exists when content
  can describe it; it is designed in the data first, then built.
- **Either side can change safely.** The engine is built against small test packs; a
  game is written as data, checked before it is played.
- **Games are designed in words first.** A game pack is derived from human-readable
  design documents; the documents are the source, the data follows them.
- Modding and new content follow the same path: a new or edited pack, no code.
