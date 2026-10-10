# Playtest: the test pack

A checklist of everything the engine and interface do so far (milestones 0–7), played
by hand in the terminal. Each point says what to try and what should happen; how you
get there is up to you. Tick the box when it works; note anything that doesn't.
Things that depend on chance are marked **(chance)**.

Part A checks the interface screen by screen; part B checks the game's features.
Run part A at least twice: once at the smallest size (40×20) and once with
`--no-colour`.

```sh
python3 play.py                       # the start screen
python3 play.py --new                 # straight into a fresh game (slot 1)
python3 play.py --no-colour           # plain text
python3 play.py --slot two --new      # straight into a save named 'two'
python3 play.py --ui packs/ui/<id>    # another UI pack
```

Default keys: W A S D move, `.` waits, P pack, F fitting, C character, L message
log, X closes, Q quits, `]` next page, digits pick.

## Where things are

- **Workshop** (the start): a door to the storage room, a crate, a locker, a workbench,
  a training sim, Juno (a scrap trader), and a tunnel hatch that isn't active yet.
- **Storage** (a gas leak): a door back, a med station, a suit bay holding a heavy
  suit and an eye implant, a terminal, and a floor hatch that starts a fight with
  drones. Without an air filter, everyone there loses health every turn.
- The **training sim** and **med station** are test-only shortcuts, so later
  features can be reached by hand.
- **Fine-grade items** (coloured cyan): the heavy suit, the shield, odd metal.
  Everything else is common (grey).

---

# Part A: the interface

## A1. On every screen

- [ ] Every line is exactly the terminal's width; nothing spills past the right
  border, and borders join cleanly between zones.
- [ ] At 40×20 every screen still works: less important zones (the legend first)
  give way, then widgets switch to compact forms, and the thing you're looking at or
  choosing always keeps at least 3 lines. Below 40×20 the game asks for a bigger
  terminal, and comes back when you resize.
- [ ] One clear focus at a time: the picked entry stands out, the rest steps back.
- [ ] The key hints at the bottom show only keys that work right now, and change
  with what's open (moving, scrolling, picking, a question).
- [ ] Up and down are contextual: they move you on the map; scroll an open
  sub-window until it's closed; move the pick in a list.
- [ ] Anything longer than its space shows a slider at its right edge; the thumb
  moves as you scroll and reaches the bottom at the end. "↑↓ scroll" appears only
  when there's more to see.
- [ ] X always goes back exactly one level (details → item → list → map).
- [ ] Wrapped text never cuts a word; wrapped options and choices hang indented under
  their first line, not under their number.
- [ ] Colour means something: warning (danger, over budget, a loss), gain, greyed out
  (unavailable), and item grade. Item names show their grade colour wherever items
  are listed: the pack, the fitting screen, item details.
- [ ] With `--no-colour` everything is still readable: picks show with a cursor or a
  heavy border, unavailable options keep their hint, the portrait is a silhouette.
- [ ] Wording is consistent: "Message log", "1 turn" / "3 turns", "Keys above act".

## A2. Start, save slots, help, quit

- [ ] Without flags the game opens on the start screen: the pack's name and version,
  New game, Help and Quit; once there's a save, Continue (with its slot, place and
  day) and Load too. Up and down plus Enter, or a number, choose.
- [ ] New game takes an empty slot; with all three used it asks which to replace.
  Load lists the slots with where and when each was saved.
- [ ] Help lists every key (rebind one in a UI pack and it changes), how the interface
  works, and the test pack's own tips; up and down scroll it with a slider.
- [ ] Q in the game asks "Quit to the start screen?" from anywhere, a fight too: N or X
  goes back exactly where you were, Y saves and returns to the start screen.
  Continue resumes exactly, even mid-fight or with a choice waiting.
- [ ] `--new` and `--slot` go straight into a game.

## A3. The world screen

- [ ] It shows the location and region, the room grid with you on it, the day and
  phase, health and heat bars, a legend of every glyph, messages, and key hints.
- [ ] Bumping a solid object or a person puts it in focus without moving, and shows
  its menu with the right keys. X closes it.
- [ ] Unavailable options are greyed out with a hint saying what's needed; pressing
  them shows the hint and takes no time.
- [ ] Inspect opens a panel explaining what a thing does and what it needs (the
  workbench, the terminal, the suit bay, Juno); a door shows whether it's open.
  Up and down scroll it, left and right do nothing, X returns to the menu; then up
  and down move you again.

## A4. The pack panel

- [ ] P shows cargo, then what you carry and, next to storage, what's stored,
  numbered; no fitting here. The message log stays visible beside it.
- [ ] Picking a number highlights the entry and lists its options (take, store, use,
  I Details) indented right under it; the pick stays in view at 40×20.
- [ ] With more than nine entries it shows "Page 1/2"; up and down (or `]`) turn pages,
  and numbers start at 1 again on each page.
- [ ] I Details shows the item's kind, slot, grade, condition, description, and rows
  for what it uses and gives, mounts, tags, actions, mod slots, size, stack, needs,
  taking apart, making and repairing. Try the cutter, the light suit, a medkit, and
  the heavy suit in the suit bay. X goes back with the item still picked; P closes
  everything.
- [ ] After an action the same item stays picked at its new number (store an item,
  then take it back without picking it again); it's unpicked when the item is gone.

## A5. Message log and cards

- [ ] L opens the message log: grouped under day and shift headings, newest at the
  bottom; up looks back with the slider, X closes. It's still there after quitting
  and resuming.
- [ ] A fight's result and loot are in the log afterwards.
- [ ] Short event texts ("Machines hum somewhere below.") stay in the log; long ones
  (the rescue after losing) open as a card titled with the event's name: any key
  continues, up and down scroll it.
- [ ] Every question opens as a card (the terminal's is titled "Terminal"); its first
  choice is in view even at 40×20, and up and down scroll the rest.

## A6. The conversation screen

- [ ] Talk opens it (one turn passes): Juno's portrait, name, title, faction and trust
  as words, a number and a bar; Juno's line; numbered responses with Leave last.
  1-3 answer, X leaves back to the menu.
- [ ] Trade shows "You give Keycard" and "You get Medkit x2" before you answer. After
  it, the history shows "You: Trade" and what changed hands.
- [ ] On a short terminal the portrait row gives way; up and down look back through
  a long conversation.

## A7. The fitting screen

- [ ] F shows the worn suit and where you are ("At: Workbench", or "Planning only"),
  the budgets as bars, then Worn by slot (empty slots as "· empty"), Spare and
  Designs.
- [ ] Up and down move the pick, skipping empty slots, and the list scrolls to keep it
  in view; digits jump. The pick shows with colour off too.
- [ ] The picked entry says what its action would change ("Remove: PWR 4→3/6").
  Something that would go over a budget shows the number in the warning colour and is
  greyed out with the reason; something blocked for another reason shows no preview.
- [ ] Away from a workshop every action is greyed out with "Needs a refit workshop."
- [ ] M lists the modifications that apply, with cost, what each adds and why not; a
  digit applies one. I opens the details; X goes back a level each time.

## A8. The character screen

- [ ] C shows your portrait in half-block pixels beside your name, rank and health
  and heat bars; then skills with a progress bar and what the next level brings,
  stats in columns, conditions with turns left, the party with health (or "down"),
  your rank and how the station crew regards you.
- [ ] Up and down scroll it on a short terminal; C or X closes it.

## A9. The fight and after-action screens

- [ ] The encounter screen shows the round, the enemy's picture in pixels, both sides with
  health bars (and your heat), each enemy's intent, and the action tiles: the number
  in the top border, the whole name inside ("Retreat"), costs as symbols (▲ heat,
  ⟳ cooldown, × uses left). A crowded fight switches its tiles to a compact list.
- [ ] A digit picks a tile (heavy border) and shows its details in place of the log:
  costs and what it does in words, or why it can't be used. The same digit uses it,
  another picks another, X lets go. It still fits 40×20.
- [ ] An action with several possible targets marks them ▸ in the fighters column; a
  digit picks one, X goes back to the tile. The names don't move.
- [ ] Each fighter shows their statuses with rounds left (Burning 3).
- [ ] Each round's log is headed "Round N:", and anything the end of a round brings
  comes after an "End of round:" line.
- [ ] The after-action screen shows the result, the last round and the loot; "Lost."
  is in the warning colour. Any key returns to the map.

## A10. UI packs

- [ ] Copy `packs/ui/default`, change a key binding, a glyph (a slider glyph, a
  border) and a word, and play with `--ui`: the hints, help, input and screen follow.
- [ ] A broken UI pack (two actions on one key, or the engine's G key) is refused at
  start with the checker's message.

---

# Part B: the game

## B1. Walking and interactions

- [ ] Walking into a wall does nothing: no message, no time.
- [ ] A daily interaction (searching the crate) takes time, gives loot **(chance)**,
  changes the object's state in the legend, and can't be repeated the same day.
- [ ] A once-only interaction can't be used twice.
- [ ] An interaction's key never clashes with the UI's keys or with Go, Talk and
  Inspect: a clash gets a spare letter.

## B2. People

- [ ] After trading, Juno's trust rises and Recruit stops being greyed out.
- [ ] Talking shows the most fitting dialogue line; it changes when they travel with
  you ("Lead on." after recruiting, and the conversation goes on).
- [ ] A recruited companion leaves the map, follows you between rooms, shows in the
  status panel, and fights on your side.

## B3. Items and storage

- [ ] Using a consumable spends one from the stack.
- [ ] Next to a locker or bay, its contents appear in the pack; take and store move
  whole stacks.
- [ ] A locker or bay refuses more than it holds.

## B4. Doors and exits

- [ ] A closed door blocks its exit with a hint; opening it changes its glyph and
  legend entry.
- [ ] Using a tool to open it wears the tool down.
- [ ] Going through puts you at the matching door on the other side and passes time.
- [ ] A suit too big for a door or room is refused ("doesn't fit").

## B5. Suits, modules and implants

All of this happens on the fitting screen.

- [ ] At the suit bay (a refit workshop) the heavy suit and the eye implant are listed
  as spare "in Suit bay" and fit straight from there.
- [ ] Taking off the worn frame needs its modules removed first; a new frame needs the
  old one off first.
- [ ] Health, budgets and cargo follow the loadout: they drop when a suit comes off
  and rise when a heavier one goes on.
- [ ] Fitting is refused when it would go over a budget or has no free slot, and
  removing or fitting away from a refit workshop is refused with a hint.
- [ ] Fitting an implant changes its stat (initiative).

## B6. Skills

- [ ] Training raises experience; reaching a level is announced with what it unlocks
  (a new action, or a stat bonus visible on the character screen).

## B7. Crafting at a workshop

All of these happen on the fitting screen, next to the workbench.

- [ ] **Repair** restores a worn item's condition for materials; an undamaged item says
  so.
- [ ] **Dismantle** gives materials and, with enough skill, teaches the design (a
  Designs section appears); without the skill it says the item is beyond you.
- [ ] **Fabricate** makes the item from a learned design, spends materials and time,
  and is refused when the result won't fit in cargo.
- [ ] **Modify** fills a mod slot for good and shows in the item's name; it's refused
  when no slot is free, when the material is missing, or when the item's grade is
  above the workshop's.
- [ ] The odd metal's modification changes the item in a fixed way (here it adds the
  Burn action, heat, and an air filter, which protects you in the storage room).

## B8. Hazards and on-arrival events

- [ ] Entering the storage room shows the arrival message and an arrival event's
  text ("Machines hum somewhere below."); the gas leak is named in the warning colour.
- [ ] Without protection, health drops every turn there, for you and for companions
  with you; with an air filter it doesn't.

## B9. Choices

- [ ] Using the terminal asks a question with numbered options; the hint shows the
  real range (1-2). Moving does nothing while it waits.
- [ ] An option whose condition fails is greyed out with its hint and can't be picked.

## B10. Healing

- [ ] The med station heals the whole party and brings a downed companion back.
- [ ] Each morning the party gets 10 health back, and a downed companion gets up again.

## B11. Fighting

- [ ] The fight opens with its intro.
- [ ] Quicker fighters act first; priority actions (Guard) go before everyone.
- [ ] Armor reduces damage; heat rises with actions and cools after the fight.
- [ ] Cooldowns ("Ready in N") and one-charge actions ("Used up.") work; an action that
  consumes materials takes them.
- [ ] Statuses (damage over time) tick and end; the hazard hits at the end of a round.
- [ ] Retreat **(chance)** ends on an "Escaped." screen, or fails and the fight goes
  on.

## B12. Losing

- [ ] When your health runs out you lose the fight; after the after-action screen you
  are back on the map, rescued and alive. Losing is never a game over.

## B13. Time and the living world

- [ ] Waiting passes time: the phase changes mid-day, and a new day is announced.
- [ ] The crate restocks quietly each morning.
- [ ] **(chance)** A grudge event casts one of the rivals who resent you and asks what
  to do, on a card titled "Grudge" with its text and choices; the rest of the morning
  waits for your answer.

## B14. Saving

- [ ] The game saves after every turn: quit at any moment and Continue resumes exactly
  there, the message log included.

---

## Still impractical by hand

These work (the automated tests cover them) but are hard to reach on purpose:

- **Overheating:** heat cools after each fight; reaching the maximum takes a long
  fight with several heat-heavy actions.
- **An enemy fleeing:** it needs an enemy below its flee threshold at the start of a
  round.
- **`events_per_trigger`:** the test pack doesn't set a limit.

## Settled for now (the simplest choices)

1. **Healing over time and downed companions:** a quiet morning event restores 10
   health to the party, which also gets downed companions up. Packs choose the amount.
2. **Shifting item numbers:** the pack keeps the acted-on item picked at its new
   number.
