# Tools

Terminal tools for working on content packs. They edit a pack's JSON files in place;
the checker (`core.packtool check`) still has the last word.

**Start here:** `python3 editor.py` opens one menu for every tool, laid out like the
game's start screen. With more than one pack in `packs/` it asks which to open first;
`--pack packs/test` opens one directly, `--no-colour` draws plain text.

| Tool | What it does | On its own |
|---|---|---|
| Overview | The pack's files, entry counts by kind, the checker's report | `python3 -m tools.overview <pack>` |
| Map | The world graph (planned) | |
| Room | One location's layout (planned) | |
| Art | Portraits and encounter art (planned) | |

`python3 tools/gen_ui_schema.py` is a script, not an editor: it regenerates
`schemas/ui.schema.json` (see README.md, "UI packs").

## Guidelines for every tool

These hold for every tool. A new tool, or a change to one, follows them.

### 1. Least clutter

- **One screen, one job.** Show what the current step needs and nothing more. Details
  come on demand (a key, a pick), not all at once.
- **No dead entries.** The menu lists only tools that work. A key hint is shown only
  when its key does something right now.
- **Few words.** Labels are short and plain. No ids where a name will do; show the id
  only where the user has to type or choose it.
- **Fits 40 by 20.** Every screen works at the UI pack's minimum size (the game's
  phone-sized screen) and uses more room when there is more.

### 2. Intuitive

- **The game's keys.** Keys mean what they mean in the game, from the UI pack's
  bindings: arrows or WASD move and pick, Enter or a digit chooses, X or Esc goes back
  one step, Q leaves the tool. A tool's own keys are letters named after what they do
  (R check, S save), and are always in the hint line.
- **Always a way back.** X or Esc leaves every screen, and at the editor's menu it
  quits. Nothing is a dead end.
- **Show, don't ask.** Pick from lists (objects, locations, tiles) instead of typing
  ids. Typing is for names and new ids, and a tool suggests the id from the pack's
  prefixes (see AGENTS.md, "Naming ids").
- **Say what's wrong where it's wrong.** A rule broken by an edit (a door off the
  wall, two things on one tile) shows on the spot, in the game's danger colour, in
  plain words.

### 3. The game's look

- Bordered bands drawn with the UI pack's glyphs, padding and styles
  (`tools.lib.screen`): a **title** band (the tool's name on the left, the pack on the
  right), the **body**, an optional **description** of the pick, and the **hints**.
- Numbered menus with the game's cursor (`screen.menu`), quiet text for explanations,
  the danger colour for problems.
- Without colour (`--no-colour`) a tool still works: picks are marked by the cursor,
  not only by colour.

### 4. Safe with the pack

- **Nothing is written until you save.** The title shows when there are unsaved
  changes; leaving with unsaved changes asks first.
- **Saving checks.** Saving writes only the changed files, in the packs' format, then
  runs the checker and shows its report. Git is the undo.
- **Content-free.** Like the engine, a tool never names a pack's ids. What it needs (the
  door object to use, say) it asks for or reads from the pack.

## How a tool is built

- A class with `name` and `about` (shown in the editor's menu), built from
  `(PackFiles, Look)`, with `render(columns, rows)` returning the screen as text and
  `handle(key)` returning False to leave. `tools.tools()` lists the finished tools in
  menu order; add a tool there when it works.
- `if __name__ == "__main__": sys.exit(term.run_tool(MyTool, sys.argv[1:]))` lets it
  run on its own.
- **Pack files** (`tools.lib.packfiles.PackFiles`): entries are edited as plain dicts
  (as written, no defaults filled in); `touch(file)` marks a change, `save()` writes
  only changed files, each atomically, and a file written back unchanged is byte for
  byte the same.
- **Keys** (`tools.lib.term`, `Look.action`): keys arrive as names (a character, or
  `up`, `down`, `left`, `right`, `enter`, `esc`, `backspace`, `tab`); `look.action(key)`
  turns the game's bindings into `up`, `down`, `left`, `right`, `back`, `quit`. When
  stdin isn't a terminal, keys are read from it, so a tool can be scripted.
- **Tested.** `render` and `handle` touch no terminal, so `tests/test_tools.py` drives
  the tools with keys against a copy of the test pack, at 40 by 20 and wider.

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
