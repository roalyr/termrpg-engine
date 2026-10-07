# Playtest: the test pack

A checklist of every feature the engine has so far (milestones 0–6 and the UI pack),
played by hand in the terminal. Each point says what to try and what should happen;
how you get there is up to you. Tick the box when it works; note anything that
doesn't. Things that depend on chance are marked **(chance)**.

```sh
python3 play.py --new                 # a fresh game of the test pack
python3 play.py                       # resume the saved game
python3 play.py --no-colour           # plain text
python3 play.py --slot two --new      # a separate save
python3 play.py --ui packs/ui/<id>    # another UI pack
```

The key hints at the bottom of the screen always show the keys that work right now.

## Where things are

- **Workshop** (the start): a door to the storage room, a crate, a locker, a workbench,
  a training sim, Juno (a scrap trader), and a tunnel hatch that isn't active yet.
- **Storage** (a gas leak): a door back, a med station, a suit bay holding a heavy
  suit and an eye implant, a terminal, and a floor hatch that starts a fight with
  drones. Without an air filter, everyone there loses health every turn.
- The **training sim** and **med station** are test-only shortcuts, so later
  features can be reached by hand.

---

## 1. The screen

- [ ] The world screen shows the location and region, the room grid with you on it,
  the day and phase, health and heat bars, a legend of every glyph, messages, and key
  hints.
- [ ] Every line is the terminal's width; nothing spills past the right border.
- [ ] On a short terminal the legend disappears first and the newest messages and
  menu stay in view; a crowded fight switches its tiles to a compact list. Below
  40×20 the game asks for a bigger terminal.

## 2. Walking and looking

- [ ] Walking into a wall does nothing: no message, no time.
- [ ] Bumping a solid object or a person puts it in focus without moving, and shows
  its menu with the right keys. Close it with the close key.
- [ ] Unavailable options are greyed out with a hint saying what's needed; pressing
  them shows the hint and takes no time.
- [ ] Inspect opens a panel explaining what a thing does and what it needs (try the
  workbench, the terminal, the suit bay and Juno); a door shows whether it's open.
- [ ] While the panel is open, up and down (arrows or W/S) scroll it instead of
  moving; on a short terminal a slider shows where you are, and "↑↓ scroll" appears
  only when there's more to see. Left and right do nothing. X closes it and returns
  to the menu; then up and down move again.
- [ ] The same holds for the character screen (C closes it) and the pack panel, where
  up and down turn pages when there's more than one.

## 3. Interactions

- [ ] A daily interaction (searching the crate) takes time, gives loot **(chance)**,
  changes the object's state in the legend, and can't be repeated the same day.
- [ ] A once-only interaction can't be used twice.
- [ ] An interaction's key never clashes with the UI's keys or with Go, Talk and
  Inspect: a clash gets a spare letter.

## 4. People

- [ ] Talk opens the conversation screen (one turn passes): Juno's portrait, name,
  title, faction and trust as words, a number and a bar; Juno's line; numbered
  responses with Leave last. 1-3 answer, X leaves back to the menu.
- [ ] Trade shows "You give Keycard" and "You get Medkit x2" before you answer. After
  it, the history shows "You: Trade" and what changed hands, trust rises, and
  Recruit stops being greyed out.
- [ ] Talking shows the most fitting dialogue line; it changes when they travel with
  you ("Lead on." after recruiting, and the conversation goes on).
- [ ] On a short terminal the portrait row gives way; up and down look back through
  a long conversation.
- [ ] A recruited companion leaves the map, follows you between rooms, shows in the
  status panel, and fights on your side.

## 5. The pack, the fitting screen and the character screen

- [ ] The pack panel (P) shows cargo, then what you carry and, next to storage, what's
  stored, numbered; picking a number shows take, store and use. No fitting there.
- [ ] Using a consumable spends one from the stack.
- [ ] The fitting screen (F) shows the worn suit and where you are ("At: Workbench",
  or "Planning only"), the budgets as bars, then Worn by slot (empty slots as
  "· empty"), Spare and Designs. Up and down move the pick, skipping empty slots, and
  the list scrolls to keep it in view; digits jump. The pick shows with colour off too.
- [ ] The picked entry says what its action would change ("Remove: PWR 4→3/6").
  Something that would go over a budget shows the number in the warning colour and is
  greyed out with the reason; something blocked for another reason shows no preview.
- [ ] Away from a workshop every action is greyed out with "Needs a refit workshop."
- [ ] At the suit bay, the heavy suit and the eye implant are listed as spare "in Suit
  bay" and fit straight from there.
- [ ] M lists the modifications that apply, with cost, what each adds and why not; a
  digit applies one. I opens the details; X goes back a level each time.
- [ ] A picked item offers I Details: the panel shows its kind, slot, grade,
  condition, description, and rows for what it uses and gives, mounts, tags, actions,
  mod slots, size, stack, needs, taking apart, making and repairing. Try the cutter,
  the light suit, a medkit, and the heavy suit in the suit bay. X goes back with the
  item still picked; P closes everything.
- [ ] After an action the same item stays picked at its new number (store an item, then
  take it back without picking it again); it's unpicked when the item is gone.
- [ ] Removing or fitting gear away from a refit workshop is refused with a hint.
- [ ] The character screen (C) shows your portrait in half-block pixels beside your
  name, rank and health and heat bars; then skills with a progress bar and what the
  next level brings, stats in columns, conditions with turns left, the party with
  health (or "down"), your rank and how the station crew regards you. Up and down
  scroll it on a short terminal; C or X closes it. With colour off the portrait is a
  silhouette.

## 6. Doors and exits

- [ ] A closed door blocks its exit with a hint; opening it changes its glyph and
  legend entry.
- [ ] Using a tool to open it wears the tool down.
- [ ] Going through puts you at the matching door on the other side and passes time.
- [ ] A suit too big for a door or room is refused ("doesn't fit").

## 7. Skills

- [ ] Training raises experience; reaching a level is announced with what it unlocks
  (a new action, or a stat bonus visible in the sheet).

## 8. Crafting at a workshop

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

## 9. Lockers and bays

- [ ] Next to a locker or bay, its contents appear on the board; take and store move
  whole stacks.
- [ ] A locker or bay refuses more than it holds.

## 10. Hazards and on-arrival events

- [ ] Entering the storage room shows the arrival message and an arrival event's
  text ("Machines hum somewhere below."); the gas leak is named in the warning colour.
- [ ] Without protection, health drops every turn there, for you and for companions
  with you; with an air filter it doesn't.

## 11. Choices

- [ ] Using the terminal asks a question with numbered options; the hint shows the
  real range (1-2). Moving does nothing while it waits.
- [ ] An option whose condition fails is greyed out with its hint and can't be picked.

## 12. Healing

- [ ] The med station heals the whole party and brings a downed companion back.
- [ ] Each morning the party gets 10 health back, and a downed companion gets up again.

## 13. Suits, modules and implants

- [ ] At the bay (a refit workshop): taking off the worn frame needs its modules
  removed first; a new frame needs the old one off first.
- [ ] All of this happens on the fitting screen.
- [ ] Health, budgets and cargo follow the loadout: they drop when a suit comes off
  and rise when a heavier one goes on.
- [ ] Fitting is refused when it would go over a budget or has no free slot.
- [ ] Fitting an implant changes its stat (initiative).

## 14. Fighting

- [ ] The fight opens with its intro; the encounter screen shows the round, the enemy's
  picture, both sides with health bars (and your heat), each enemy's intent, and the
  action tiles with their costs.
- [ ] An action with several possible targets asks for one; the close key backs out.
- [ ] Each round's log is headed "Round N:" and lists what happened in order:
  quicker fighters first, priority actions (Guard) before everyone.
- [ ] Armor reduces damage; heat rises with actions and cools after the fight.
- [ ] Anything the end of a round brings (statuses ticking, the hazard) comes after an
  "End of round:" line.
- [ ] Cooldowns ("Ready in N") and one-charge actions ("Used up.") work; an action that
  consumes materials takes them.
- [ ] Statuses (damage over time) tick and end.
- [ ] Winning ends on an after-action screen: the result, the last round, the loot.
  Any key returns to the map.
- [ ] Retreat **(chance)** ends on an "Escaped." screen, or fails and the fight goes
  on.

## 15. Losing

- [ ] When your health runs out, the after-action screen says "Lost." in the warning
  colour; any key brings you back to the map, rescued and alive. Losing is never a
  game over.

## 16. Paging

- [ ] With more than nine entries, the pack panel shows "Page 1/2" and up and down (or
  the next-page key) turn pages; numbers start at 1 again on each page.

## 17. Time and the living world

- [ ] Waiting passes time: the phase changes mid-day, and a new day is announced.
- [ ] The crate restocks quietly each morning.
- [ ] **(chance)** A grudge event casts one of the rivals who resent you and asks what
  to do; the rest of the morning waits for your answer.

## 18. Saving

- [ ] Quitting saves; starting again resumes exactly, even mid-fight or with a choice
  waiting.
- [ ] `--new` starts over; `--slot` keeps games apart.

## 19. The UI pack

- [ ] Copy `packs/ui/default`, change a key binding, a glyph and a word, and play with
  `--ui`: the hints, input and screen follow.
- [ ] A broken UI pack (two actions on one key, or the engine's G key) is refused at
  start with the checker's message.

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
2. **Shifting board numbers:** the board keeps the acted-on item picked at its new
   number.
