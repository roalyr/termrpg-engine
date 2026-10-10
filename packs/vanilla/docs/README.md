# Vanilla pack: design documents

The design of `vanilla`, the first game pack. These documents are the source the pack
is built from: people and agents write and refine them here, and an agent later
derives the pack's JSON from them.

## Workflow

```
 1. DESIGN      people and agents write these documents, one topic at a time,
                until every open question is settled
 2. ENGINE      engine-requirements.md lists what the pack needs that the engine
                or UI can't do yet; each item goes through the schema-first
                order in AGENTS.md (schema → test pack → engine → game pack)
 3. CONTENT     an agent derives the pack's JSON from the documents, following
                AGENTS.md, and checks it with packtool
 4. PLAYTEST    findings go back into the documents first, then into the JSON
```

The documents win over the JSON: if they disagree, fix the JSON, or change the
document first and then the JSON. VISION.md wins over these documents.

## Documents

| Document | Covers | Status |
|---|---|---|
| [01-scope.md](01-scope.md) | Purpose, length, focus, what "done" means | Decided |
| [02-setting.md](02-setting.md) | Era, who runs what, history, the exotic material, tone | In progress |
| [03-world.md](03-world.md) | Regions, the surface grid, bases, routes, points of interest | In progress |
| [04-player.md](04-player.md) | The start, the player's climb | Not started |
| [05-build.md](05-build.md) | Frames, modules, implants, skills, stats; counts | Not started |
| [06-challenge.md](06-challenge.md) | Hazards, enemies, encounters, defeat | Not started |
| [07-crafting.md](07-crafting.md) | Materials, workshops, designs, modifications | Not started |
| [08-people.md](08-people.md) | Factions, characters, companions, rivals, events | Not started |
| [09-economy-and-time.md](09-economy-and-time.md) | Trade, currency, time, routines, suit endurance | Not started |
| [10-text.md](10-text.md) | Writing style, names, art, presentation | Not started |
| [engine-requirements.md](engine-requirements.md) | What the pack needs from the engine and UI | Collecting |

## Conventions

- **Decided** items are agreed with the user. Change them only when the user says so.
- **Proposed** items are drafts waiting for the user's answer. Never build from them.
- **Open** questions are listed at the end of each document, with their question id
  (`B6`, `C3`…) so answers can be traced.
- Plain English, short sentences, as in the project's other docs.
- Name things by their future id where one is settled (`loc_hub_dock`), so the
  content step can map documents to JSON directly.
- Anything the engine can't express goes into `engine-requirements.md`, never into a
  workaround in the design.
