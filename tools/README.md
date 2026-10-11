# Tools

Terminal tools for working on content packs. They edit a pack's JSON files in place;
the checker (`core.packtool check`) still has the last word.

**Start here:** `python3 editor.py` opens one menu for every tool, laid out like the
game's start screen. With more than one pack in `packs/` it asks which to open first;
`--pack packs/test` opens one directly, `--no-colour` draws plain text.

| Tool | What it does | On its own |
|---|---|---|
| Map | The world by region: where locations lie, how they connect, what needs fixing | `python3 -m tools.map <pack>` |
| Room | One location's layout: tiles, size, objects, entry point, doors, open edges | `python3 -m tools.room <pack>` |
| Entries | Any entry by kind (objects, items, characters, actions, events…), field by field | `python3 -m tools.entries <pack>` |
| Loadout | A character's frame, modules, implants and inventory, against their budgets | `python3 -m tools.loadout <pack>` |
| Overview | The pack's files, entry counts by kind, the checker's report | `python3 -m tools.overview <pack>` |
| Art | The pack's pictures in pixels: paint, mirror, undo, colours | `python3 -m tools.art <pack>` |

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
- **Fits 48 by 24.** Every screen works at the UI pack's minimum size (the game's
  phone-sized screen) and uses more room when there is more.

### 2. Intuitive

- **The game's keys.** Keys mean what they mean in the game, from the UI pack's
  bindings: arrows or WASD move and pick, Enter or a digit chooses, X or Esc goes back
  one step, Q leaves the tool. A tool's own letters never take the keys that move, go
  back or quit (WASD, X, Q in the default UI pack); the game's screen keys (P pack,
  L log…) mean nothing in a tool and are free.
- **Enter shows what you can do.** On a thing (a tile, an entry) Enter lists every
  action that works on it right now, each with its letter; the letters are shortcuts
  for when you know them. The hint line stays short: move, Enter actions, back.
- **Lists filter as you type.** In a list (objects, locations) letters type a filter
  and only the arrows move; Enter picks, Esc goes back. Long lists scroll and keep the
  pick in view.
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

- **Nothing is written until you say so.** A `*` in the title shows unsaved changes.
  Leaving with changes asks: Y save, N discard, X stay. Save is also in the actions
  list.
- **Saving checks.** Saving writes only the changed files, in the packs' format, then
  runs the checker and shows its verdict. Git is the undo.
- **Never overwrites someone else's save.** If a file about to be written was changed
  on disk since the tool read it (another tool, an editor, a person), saving asks:
  O overwrite, N don't save. Not saving keeps your changes open; leave without saving
  and open the pack again to see the other changes.
- **Never breaks a reference.** Removing something still used elsewhere is refused,
  with the files that use it. Two sides of a door or an edge are removed together.
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
  the tools with keys against a copy of the test pack, at 48 by 24 and wider.

`tools/overview.py` is the smallest tool and the template for new ones.

## The editors

Decided so far (2026-10-10). Each editor is designed in detail before it's built.

### Room: one location (ready)

Pick a location, move the cursor over its grid; Enter lists what works on the tile:

| Letter | Action | When |
|---|---|---|
| P | Place an object (the id is made from the room and object: `workshop_crate`, `workshop_crate_2`) | Empty floor or wall |
| M | Move it (Enter puts it down) | On a placement, not part of an open edge |
| R | Remove it, and the other side of a door or edge | On a placement nothing else uses |
| G | Go to the other side | On a door or edge tile |
| E | Arrivals appear here / back to the centre (`entry`) | On a placement |
| L | Door to another location: pick the object, the location, then the tile there (a free wall tile facing this one is suggested) | Empty wall tile on a side |
| O | Open the side to another location: an open edge | A side with nothing on it |
| T | Wall and floor swap; "Make it nothing" is in the list | Anywhere (people stand on floor) |
| C | Colour: this placement or every one of its object, the person standing here, or the room's walls or floor. A named colour, a terminal colour (0-255) from the grid, or Default (the UI pack's colour) | Anywhere |
| Z | Room size, `width x height`: 3 to 12 across, 3 to 10 down (a custom shape keeps its top-left part) | Anywhere |

The side panel lists each kind of thing in the room once, with where exits lead.
The room is drawn as the game draws it: joined walls, glyphs in their map colours.
Everything else on a placement (state, contents, interactions, names) stays in JSON.

**Two ways between locations:**

- **A door** (or any passage): one placement on a wall tile in each location, each
  with an `exit` to the other.
- **An open edge,** for neighbouring areas of the same size such as surface cells:
  every tile of one side (corners excepted) is a placement whose exit leads to the
  matching tile on the other location's opposite side (`field_east_1` ↔
  `plain_west_1`). Stepping on one offers to go. Both sides must be the same length.
  Pick an object that looks like ground for its tiles (the test pack's
  `obj_ground`, `·`, between the Crater rim and the Dust flat). The game lists the
  edge once in its legend; arrivals land on the matching edge tile.

### Map: the world by region (ready)

**Each region is its own map:** its own coordinate system, filled with its rooms at
their `map` x/y. Regions aren't drawn inside one another. You switch regions from the
**region list** (X from a map), or by **following an exit** into the region it leads
to, the way the player would travel. A region's `parent` only indents it under its
parent in the list; regions' own `map` positions aren't used.

On a map each location is `■`; exits between neighbouring cells are drawn as lines.
The map shows only as far as rooms are placed, plus one cell to grow into. The detail
band names the location, its status, its first problem and its exits, with the region
of any exit that leads elsewhere ("Exits: Tunnel one in Tunnels").

| Letter | Action | When |
|---|---|---|
| E | Edit the room (the room editor, in place; X comes back to the map) | On a location |
| G | Follow an exit: the map of the region it leads into, the cursor on where it arrives | On a location with exits |
| L | Link to a neighbour: a door (auto-placed on the facing walls, as near the middle as a free tile allows) or an open edge (offered when the sides match) | On a location with a neighbour |
| M | Move it (Enter puts it down) | On a location |
| N | New location here: a name, then an id suggested from it; the size, floor and wall are the region's most common | On an empty cell |
| P | Place one here: a location of this region without a `map` | On an empty cell |

X goes back along the exits you followed, then to the region list. The list shows
each region's location count and, in colour, its most important status; its last
entry makes a **new region** (a name, then an id). Esc on the list leaves the map,
asking to save if anything changed.

Exits can lead from any location to any other, in any region. Link non-neighbours
and other regions from the room editor (L on a wall tile).

**Colour schemes.** A scheme sorts locations into statuses, each with a colour, a
mark used without colour, and words for the legend. The legend shows only the
statuses on screen. A region in the list shows the most important status among its
locations.
Schemes live in `tools/lib/maps.py` (`SCHEMES`); with more than one, a C action
switches between them.

**Validity** (the first scheme), most important first:

| Status | Colour | Mark | Meaning |
|---|---|---|---|
| problem | orange | `!` | A placement's problem (a one-way or broken exit, nothing to stand on), an exit with nothing leading back, or a checker error about the location (as of the last save) |
| cut off | grey | `?` | No chain of exits leads here from the start location (`requires` aren't evaluated) |
| hazard | yellow | `^` | It has a tag marked `hazard` in the vocabulary |
| start | green | `@` | The game starts here |

Later schemes could colour by kind of place, by region, or by who lives there.

### Art: pictures (ready)

Every picture in the game is an entry in the pack's art file (pixel rows and a
palette, up to 32 by 32); characters use them by id (`art`) on the character screen,
in conversations and in fights.

The editor opens on the list of pictures: each with its size and who uses it, filtered
as you type, and **New picture…** last (an id, then a blank 24 by 24 with one colour).
The canvas draws the picture as the game does, two pixels per text cell; the cursor
is one pixel, shown in magenta (without colour, its cell is inverted and the detail
band gives the row and column). Beside it the palette, the current colour marked.

| Key | Action |
|---|---|
| Space | Paint the pixel with the current colour (both sides with mirror on) |
| Tab | The next colour in the palette, then see-through |
| K | Pick the colour under the cursor |
| M | Mirror on or off: painting does the left and right at once |
| U | Undo (back through every change since the picture was opened) |
| N | New colour: the next free letter, a named colour or one from the 256-colour grid |
| C | Change the current colour (every pixel of it changes) |
| Z | Size, `width x height` from 2 to 32 (the top-left part is kept; 24 by 24 fills the default art zone) |

Enter lists these and the rest: removing the current colour (its pixels become
see-through), deleting a picture nothing uses, saving. X goes back to the list,
asking to save if anything changed; Esc on the list leaves.

### Entries: any entry, field by field (ready)

One editor for every kind of entry: objects, items, characters, actions, skills,
encounters, loot tables, events, modifications, strings, regions, locations, zones
and art. Its fields come from the pack schemas, so a field added to a schema shows up
here by itself. (The vocabulary isn't an entry list and stays in JSON for now.)

Pick a kind (with how many entries it has), then an entry (filtered as you type), or
**New…** last: an id, prefilled with the kind's prefix (`obj_`, `char_`…); for items
first the item's kind, which then sets its fields. A new entry opens with what it's
missing listed in red.

The entry shows one line per field: its value, or quietly its default; a required
field not filled in says so. Below are the picked field's description and what the
schema finds wrong with the entry. Reserved fields only show when the entry uses them.

Up and down pick a field; Enter edits it, with the input that suits it:

| Field | Edited with |
|---|---|
| Names, ids in a line, glyphs | A line of text, checked against the schema's limits |
| Numbers | A line, checked as a number in its range |
| Yes or no | Enter switches it |
| One of a few words, a size, an id of another entry | A list to pick from (ids with their names, sizes with theirs) |
| A list of ids (tags, actions, fitted modules…) | The list: Enter on one takes it out, **Add…** picks one more, Esc is done |
| Colours | The colour picker, with Default first |
| Descriptions and notes | The text editor, as plain text |
| Anything bigger (effects, conditions, dialogue, interactions, stats, a grid) | The text editor, as JSON. A mistake isn't lost: edit again, or drop the change |

Leaving a field empty (or picking Default, `(none)`) takes it out of the file, so its
default applies: the file keeps only what differs.

**The text editor** is `$VISUAL` or `$EDITOR`, else `nano`. It gets the whole
terminal; save and close it to come back.

E lists what works on the whole entry:

| Action | What it does |
|---|---|
| Edit it all as JSON | The whole entry in the text editor; its id must stay (use Rename) |
| Rename the id… | Every use in the pack changes with it, `pack.json` included. Old saves won't know the new id: raise the pack's major version |
| Duplicate… | A copy under a new id (the next free `_2`, `_3` is suggested) |
| Delete | Only when nothing uses it; otherwise the files that still do |
| Save changes | When there are any |

X goes back to the entry list, Esc to the kinds; Esc on the kinds leaves, asking to
save if anything changed.

### Loadout: what a character wears and carries (ready)

Pick a character (templates included). The top shows who they are: title, size, where
they stand (the player: the pack's start), then **power, mass, heat and cargo** as bars
of what the loadout uses against what it provides, and their other stats added up
(body, frame, modules, implants, skill levels). With the room to spare (about 40 rows
at 48 columns) their picture sits beside it; V hides or shows it.

Below, one line per thing:

| Line | Enter | R |
|---|---|---|
| The frame | Another frame, or none | Takes it off (fitted modules then have nowhere to go) |
| A frame or body slot, filled or `(empty)` | The modules (implants) of that slot type, each with what it uses and gives | Takes it out |
| A fitted item with no slot, in red | Another item | Takes it out |
| A carried stack, with its cargo stacks | Its count; 0 takes it out | Takes it out |
| Carry another item… | An item, then how many (added to a stack it already has) | |

The bars and the problems below the list follow every change before anything is
saved. They count the way the checker counts (slots, power, mass, constant heat below
maximum heat, cargo stacks), so a loadout with no problems here passes the check;
`tests/test_tools.py` holds the two to the same verdicts.

G opens the character's room in the room editor, the cursor on them; X there comes
back. X goes back to the characters; Esc there leaves, asking to save.
