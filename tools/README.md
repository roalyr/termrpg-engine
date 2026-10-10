# Tools

Standalone terminal tools for working on content packs. They edit a pack's JSON
files in place; the checker (`core.packtool check`) still has the last word.

Run them from the project root:

| Command | What it does | Status |
|---|---|---|
| `python3 -m tools` | Lists the tools | Ready |
| `python3 -m tools.overview <pack>` | A pack at a glance: files, entry counts by kind, the checker's report | Ready |
| `python3 -m tools.map <pack>` | The world graph | Planned |
| `python3 -m tools.room <pack> <location>` | One location's layout | Planned |
| `python3 -m tools.art <pack> <character>` | Portraits and encounter art | Planned |
| `python3 tools/gen_ui_schema.py` | Regenerates `schemas/ui.schema.json` (see README.md, "UI packs") | Ready |

## How the tools work

- **Pack files in place.** A tool opens a pack with `tools.lib.packfiles.PackFiles`,
  edits entries as plain dicts (as written, no defaults filled in) and writes only the
  files it changed, in the packs' own format: 2-space indentation, UTF-8, a newline at
  the end. A file written back unchanged is byte for byte the same. Git is the undo.
- **Check after saving.** Saving runs the validator and shows its report. A tool never
  writes anything the schemas don't allow on purpose, but the report is what counts.
- **Like the game.** A tool is a class with `render(columns, rows)` (the screen as
  text) and `handle(key)` (False to quit), run by `tools.lib.term.run`. Raw keys,
  widths and styles come from the game's `tui.text`. Keys arrive as names: a
  character, or `up`, `down`, `left`, `right`, `enter`, `esc`, `backspace`, `tab`.
  When stdin isn't a terminal, keys are read from it, so a tool can be scripted.
- **Tested.** `render` and `handle` touch no terminal, so `tests/test_tools.py` drives
  the tools with keys against a copy of the test pack.
- **Content-free.** Like the engine, tools never name a pack's ids. Anything a tool
  needs to know (the door object to use, say) is asked for or read from the pack.

`tools/overview.py` is the smallest tool and the template for new ones.

## Planned editors

Decided so far (2026-10-10). Each editor is designed in detail before it's built.

### Map: the world graph

- Locations drawn as nodes at their `map` x/y, grouped by region; exits drawn as
  links between them. Locations without `map` are listed aside to be placed.
- Move a node to change its `map` position.
- **Linking two locations creates both doors:** pick the object to use (a door, a
  path) and a wall tile on each side; the tool writes a placement in each location,
  each with an `exit` pointing at the other. Unlinking removes both, after checking
  with `refs` that nothing else uses those placement ids.
- Opens the room editor on a location.

### Room: one location

- Layout and exits only: grid size and shape (`rows`), wall and floor tiles,
  placing, moving and deleting placements by object, the `entry` point, and door
  pairing.
- Everything else on a placement (state, contents, interactions, names) stays in
  JSON, written by hand or by an agent.
- Shows the rules the checker enforces as you go: doors on wall tiles, everything
  else on floor, one placement per tile, placement ids unique across the pack.

### Art: portraits and encounter art

- Portraits: pixel rows plus a palette, drawn with half blocks as the character
  screen draws them, at most 24 by 24. Without colour only the silhouette shows,
  so the editor can show both.
- Encounter `art`: at most 10 lines of 21 characters.
