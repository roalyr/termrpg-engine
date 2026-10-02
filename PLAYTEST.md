# Playtest: the test pack

A step-by-step check of every feature the engine has so far (milestones 0–6), played
by hand in the terminal. Each step says what to press and what you should see. Tick
the box when it matches; note anything that doesn't.

Every route and message here was checked against the game with the default seed
(`--new`, seed 1). Things that depend on chance are marked **(chance)**.

## Before you start

```sh
python3 play.py --new            # a fresh game of the test pack (seed 1)
python3 play.py                  # resume the saved game
python3 play.py --no-colour      # plain text
python3 play.py --slot two --new # a separate save
```

- Keys act immediately; no Enter. **Q** saves and quits at any time.
- Positions are `(row, column)` from the top-left corner.
- **On the fitting board (P), numbers change** whenever something is taken, stored,
  fitted, removed or made, because items are grouped by where they are. Always read
  the number off the screen. Where these steps give numbers, they're what you'll see
  if you followed every step before exactly.
- The **training console** and **med station** are test-only shortcuts, so the
  later features can be reached by hand.

### Room A (where you start)

```
         col 0 1 2 3 4 5
   row 0     ░ ░ ◆ ░ ░ ░     ◆ (0,2) door to Room B, closed
   row 1     ░ § · · ⊞ ░     § (1,1) training console   ⊞ (1,4) crate
   row 2     ░ · · · @ ░     @ (2,4) you
   row 3     ░ · · N · ░     N (3,3) Npc
   row 4     ░ ▯ · · ■ ░     ▯ (4,1) locker   ■ (4,4) bench (workshop)
   row 5     ░ ░ ◆ ░ ░ ░     ◆ (5,2) zone passage (not active yet)
```

### Room B (through the door)

```
         col 0 1 2 3 4 5 6
   row 0     ░ ░ ░ ◇ ░ ░ ░   ◇ (0,3) door back to Room A
   row 1     ░ ~ + ~ ~ ~ ░   + (1,2) med station
   row 2     ░ ▣ ~ ~ ~ ⌸ ░   ▣ (2,1) suit bay   ⌸ (2,5) terminal
   row 3     ░ ░ ~ ⊙ ~ ░ ░   ⊙ (3,3) hatch (starts a fight)
   row 4       ░ ░ ░ ░ ░
```

Room B is hazardous: everyone without a suit carrying tag B loses 1 health per turn
there, the player and companions included.

---

## 1. The screen

- [ ] Six zones: header "Room A · Region A1"; the grid with you as `@`; the status
  panel "Day 1 · Phase A", `HP 30/30`, `HT 2/8`; the legend; an empty message area;
  key hints at the bottom.
- [ ] The legend lists the door, crate, locker, bench, training console and `N Npc`.
- [ ] Shrink the terminal below 40×20: "Make the terminal at least 40x20." Restore it.

## 2. Walking and looking

- [ ] **D** (into the east wall): nothing at all. No message, no time passes.
- [ ] **W** (into the crate): you don't move; the menu shows `Crate`, `F Search`,
  `I Inspect`, and the hints read "Keys shown above  X close  WASD move".
- [ ] **I**: "Crate". **X**: the menu closes.

## 3. The crate (a daily search)

- [ ] **W** then **F**: two turns pass. **(chance)** "Empty.", or "+ Found: …" and
  "You find something."
- [ ] The legend shows `Crate (used)`. **F** again: "Already searched."

## 4. The NPC: talk, trade, recruit (optional)

From the start tile: **A**, then **S** (bump the NPC).

- [ ] Menu `Npc`: `B Trade`, `U Recruit - Doesn't trust you enough.` (greyed out),
  `T Talk`, `I Inspect`. Recruit got **U** because T belongs to Talk.
- [ ] **T**: "Npc: Hello." **I**: "Npc - Test NPC".
- [ ] **B**: "Lost: Key A." and "+ Got: Consumable A x2."
- [ ] **U** (Recruit, now available): "+ Npc joins Player." **T**: "Npc: Lead on."
- [ ] The status panel shows "With: Npc"; the `N` leaves the map and follows you.

If you recruit them, they come into Room B without a suit and get hurt there; step 12
heals them. If you trade the key away, skip storing it in step 10.

## 5. The fitting board and using an item

- [ ] **P**: `PWR 4/6  MAS 5/10  CRG …/6`, then `Fitted:` 1 Frame A, 2 Tool A 4/4,
  3 System A, and `Carried:` with Consumable A and Material A in two stacks (10 and 2).
- [ ] Pick the consumable, **U**: "Used Consumable A." and the stack drops by one.
- [ ] Pick Frame A: `R Remove - Needs a refit workshop.`
- [ ] **P** closes the board. **C** opens the character panel: `Skill A 1 (0/30)`,
  `PWR 6, MAS 10, INI 0, ARM 2, CRG 6`. **C** closes it.

## 6. The door

Walk to the door at (0,2) (from the start: **A A W W**, or around the NPC).

- [ ] Menu `Door`: `U Open`, `G Go to Room B - The door is closed.` (greyed out).
- [ ] **G** while closed: "The door is closed."
- [ ] **U**: the door opens (legend `Room B (open)`, glyph `◇`). On the board, Tool A
  is now 3/4: the tool that opened it wore down. **Don't go through yet.**

## 7. Training (test-only shortcut)

From the door: **S**, then **A** (bump the console at (1,1)).

- [ ] Menu `Training console`, `U Train skill A`.
- [ ] **U**: "+ Skill A 2! Unlocks Burst." **U** again: nothing announced (60 of 90).
  **U** again: "+ Skill A 3! Tougher." In **C**: `Skill A 3`, and HP max is now 35.

## 8. The bench: repair, dismantle, learn, fabricate, modify

From (1,2): **S D D S S**. You end at (3,4), bumping the bench. **P**.

- [ ] Pick Tool A (3/4): `R Remove`, `E Repair`, `U Modify: Reinforced`,
  `H Modify: Strange - Needs Exotic A x1.`
- [ ] **E**: "+ Repaired Tool A." (4/4). Its repair option now says "Tool A is in good
  shape."
- [ ] Pick System A: `Modify: Reinforced - System A is beyond this workshop.` (its
  grade is above the bench's).
- [ ] Pick Tool A, **R**: "Removed Tool A." It moves to `Carried:`.
- [ ] Pick it, **V** (Dismantle): "+ Took apart Tool A: Material A x2." and
  "+ You understand how Tool A is made." A `Designs:` section appears with Tool A.
  (At skill A 1 you'd only get "Tool A is beyond you for now.")
- [ ] Pick the design, **B** (Fabricate): "+ Made Tool A." Two turns pass; Material A
  drops by 3.
- [ ] Pick the new Tool A (4/4), **F**: "Fitted Tool A."
- [ ] Pick Frame A, **U**: "+ Frame A is now Reinforced." It shows as
  `Frame A (Reinforced)`.

## 9. The exotic material and the Strange modification

From the bench: **W A A A S** to (3,1), next to the locker. **P**.

- [ ] An `In Locker:` section shows `Exotic A`. Pick it, **K**: "Took Exotic A from
  Locker."
- [ ] Back to the bench: **W D D D S S**. **P**, pick Tool A, **H**: "+ Tool A is now
  Strange." It's `Tool A (Strange)`; the heat bar's constant load rises by 1, and
  Strange added the Burst action and **tag B** to the tool. Tag B is what Room B's
  hazard checks for, so from now on the hazard can't hurt you while the tool is
  fitted. (The material decided the property, and it happens to protect you.)
- [ ] Pick Tool A again: `Modify: Reinforced - Tool A (Strange) has no free mod
  slot.` (it has one).

## 10. Packing for the suit swap

The heavy suit can only be put on in Room B, and taking the light one off leaves you
carrying only 2 stacks. So empty the pack here, except the small Material A stack
(Burst uses 2 of them).

From the bench: **W A A A S** to the locker. **P**.

- [ ] Store the consumables (**O**): "Stored Consumable A in Locker." The whole stack
  goes; the numbers shift.
- [ ] Store the big Material A stack, then Key A (if you still have it). Keep the small
  Material A stack.
- [ ] `Carried:` now holds only Material A. **P** closes the board.

## 11. Room B: arrival, hazard, the terminal

From the locker: **W D W W** to the door, then **G**.

- [ ] "You enter Room B." and "Machines hum somewhere below." (the arrival event). The
  header shows `a hazard` in the warning colour. Thanks to the Strange tool your
  health doesn't drop here. (Without it, it drops by 1 every turn, as it does for a
  recruited NPC without a suit.)
- [ ] **S S** to (2,3), **D**, then **D** (bump the terminal). **R** (Use): "Pick one.",
  `1 Option A`, `2 Option B`, hints "1-4 choose". Movement keys do nothing while it
  waits.
- [ ] **2**: Option B (it needs flag A ≥ 1, which the arrival event set). It sets the
  flag back to 0.
- [ ] **R** again: now `2 Option B - Needs flag A.` is greyed out. **2**: "Needs flag
  A." and the choice stays. **1** closes it.

## 12. The med station

From the terminal: **A A** to (2,2), then **W** (bump the med station at (1,2)).

- [ ] **U** (Heal the party): "+ Everyone is patched up." Health and the party's health
  back to full.
- [ ] If the recruited NPC went down ("! Npc goes down." after about ten turns here),
  this brings them back too.

## 13. The suit swap

Heal first (step 12): taking off the light suit costs its 20 health, and once the
Strange tool is off, the hazard ticks again until Frame B (which carries tag B) is on. Stand at (2,2), between the bay and the med station. **P**: the board
shows `In Bay:` Frame B and Implant A.

These numbers assume steps 8–10 exactly:

- [ ] **3 R**: "Removed Tool A (Strange)." **4 O**: stored in the bay.
- [ ] **2 R**: "Removed System A." **3 O**: stored.
- [ ] **1 R**: "Removed Frame A (Reinforced)." Health drops by 20; `PWR 0/0`,
  `CRG 2/2`. **2 O**: stored.
- [ ] **2 K**: "Took Frame B from Bay." **2 F**: "Fitted Frame B." Health jumps (about
  +45) and stops dropping: Frame B carries tag B.
- [ ] Take the tool and the system back from the bay and fit them (**K**, then **F**,
  reading the numbers off the screen): `PWR 4/12  MAS 5/25`.
- [ ] Before fitting, Frame A gave `F Fit - Take off the worn frame first.` and
  `R Remove - Remove its modules first.`. Try these out of order to see the refusals.
- [ ] Optional: take Implant A and fit it: "Fitted Implant A."; `INI` becomes 1.

## 14. Fighting

From (2,2): **D** to (2,3), then **S** (bump the hatch). **U** (Open).

- [ ] "! Drones!", "Drones close in.". The encounter screen: "Drones · round 1", the
  drone's picture, health bars (and your heat), each drone with its intent
  (`⚠ STRIKE Player`) in the warning colour, and the tiles `1 Strike ▲1`,
  `2 Burst ▲3-4`, `3 Guard ▲1`, `4 Retreat`. If the NPC exists and isn't with you,
  they fight on your side.
- [ ] **(chance)** With two drones, **1** asks for a target ("1-9 target  X back"):
  press its number. **X** backs out.
- [ ] **1** (Strike): the drones act first ("Drone uses Strike."; they're quicker),
  then you. Heat rises by 1. In the heavy suit their hits don't get through your
  armor.
- [ ] **3** (Guard) in a later round: "Player uses Guard." comes **first** (priority).
  Guard then shows "Ready in 1.".
- [ ] Win: "! Drone goes down.", "+ Won.", then "+ Found: …" lines (the encounter's and
  each drone's loot). Heat cools to the constant load.
- [ ] Open the hatch again. **2** (Burst): "Player uses Burst of damage.",
  "Lost: Material A x2.", and every drone gets "Damage over time". **(chance)** Usually
  both go down that round. If the fight goes on, Burst shows "Used up." (one charge per
  fight).
- [ ] Open it once more and press **4** (Retreat): **(chance, 60%)** "+ Escaped.", or
  "You can't get away." and the round goes on.

## 15. The door in a heavy suit

- [ ] From (2,3): **W W** to the door, **G**: "Frame B doesn't fit Door." Heavy suits
  can't enter Room A (it holds size 3). To go back, swap to Frame A at the bay (step 13
  in reverse).

## 16. Paging

- [ ] Once the board has more than nine entries (loot from a few fights does it), the
  last line reads "Page 1/2  ] next". **]** shows the next page; numbers start at 1
  again on each page.

## 17. Time and the living world

Press **.** (wait) repeatedly. A day is 60 turns; Phase B starts at turn 30.

- [ ] "Phase B." then, at the next day, "Day 2.".
- [ ] The crate in Room A is `(closed)` again and can be searched (the quiet morning
  restock).
- [ ] **(chance, 30% each morning)** "Someone holds a grudge." with `1 Apologise`,
  `2 Ignore it`: one of the two rivals who resent you was cast. While it waits, the
  rest of that morning waits too.
- [ ] Off-screen rivals change their views of each other quietly; that can't be seen
  on screen yet.

## 18. Saving

- [ ] **Q**: "Saved." Run `python3 play.py` again: exactly where you left off, even
  mid-fight or with a choice waiting.
- [ ] `python3 play.py --new` starts over.

## 19. Losing (a separate game)

The heavy suit makes you nearly untouchable, so test losing in a fresh game.

```sh
python3 play.py --slot lose --new
```

- [ ] Open the door with the tool (**A A W W U**), go through (**G**), walk to the hatch
  (**S S**, then **S** to bump it) and open it (**U**).
- [ ] Keep striking; between fights stay in Room B (the hazard hurts without the
  Strange tool). When your health runs out: "! Player goes down.", "! Lost.",
  "! You go down.", "You enter Room A." and "! Someone drags you out." You wake in Room A with 5 health: losing is never a game
  over.

---

## Still impractical by hand

These work (the automated tests cover them) but are hard to reach on purpose:

- **Overheating:** heat cools after each fight; reaching the maximum takes a long
  fight with several Bursts.
- **A drone fleeing:** it needs a drone below a quarter of its health at the start of
  a round, which the damage numbers rarely leave.
- **`events_per_trigger`:** the test pack doesn't set a limit.

## Open design gaps

1. **Downed companions don't recover on their own.** Only an effect that restores
   health brings them back (the test-only med station does).
2. **There is no healing over time.** Health returns only through consumables,
   restoring effects and the rescue after losing.
3. **Fitting-board numbers shift** after every take, store, fit, remove or make.
