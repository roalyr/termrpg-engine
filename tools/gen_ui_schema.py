"""
Generates schemas/ui.schema.json, the UI pack schema. Edit this file, not the schema:

    python3 tools/gen_ui_schema.py

tests/test_ui_pack.py checks that the committed schema is what this file generates.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))     # run as a script from anywhere
from lib.text import DEFAULT_COLOURS  # noqa: E402

C = "common.schema.json#/$defs/"
D = "#/$defs/"
def c(name, **extra): d = {"$ref": C + name}; d.update(extra); return d
def obj(desc, props, required=(), **extra):
    d = {"type": "object", "description": desc, "properties": props, "additionalProperties": False}
    if required: d["required"] = list(required)
    d.update(extra); return d
def arr(item, desc, **extra):
    d = {"type": "array", "description": desc, "items": item}; d.update(extra); return d
def intval(default, lo, hi, desc): return {"type": "integer", "minimum": lo, "maximum": hi, "default": default, "description": desc}
def char(default, desc, maxlen=3): return {"type": "string", "minLength": 0 if default == "" else 1, "maxLength": maxlen, "default": default, "description": desc}
def flag(default, desc): return {"type": "boolean", "default": default, "description": desc}
SCHEMA_REF = {"type": "string", "description": "Path to this file's schema, for editors. Ignored by the engine."}
OUT = Path(__file__).resolve().parent.parent / "schemas" / "ui.schema.json"

PALETTE = list(DEFAULT_COLOURS)          # the style roles' colours: the names every pack's palette has
SCREENS = {"world": "Walking around.", "encounter": "A fight.", "debrief": "The after-action screen at the end of a fight.",
           "gear": "The gear screen: what's equipped by slot, spare gear and designs, and building.",
           "character": "The character screen: who you are, skills, stats, conditions, party and standing.",
           "talk": "A conversation: the speaker, what was said, and your responses.",
           "map": "The map of a region: the places you've been and where their exits lead.",
           "start": "The start screen: the game's name, Continue, New game, Load, Help, Quit.",
           "slots": "The save slots, to load a game or to start a new one in.",
           "help": "The help screen: the keys, and how it works.",
           "quit": "Quit to the start screen? Asked when Q is pressed in the game."}
ACTIONS = {
 "move_north": ("w", "Step up; scrolls an open sub-window up."), "move_west": ("a", "Step left."),
 "move_south": ("s", "Step down; scrolls an open sub-window down."),
 "move_east": ("d", "Step right."), "wait": (".", "Let a turn pass."),
 "pack": ("p", "Open or close the pack: what you carry, and storage within reach."),
 "gear": ("f", "Open the gear screen. It may share its key with Equip, which only works on that screen."),
 "character": ("c", "Open or close the character screen."),
 "map": ("m", "Open or close the map. It may share its key with the gear screen's modifications, which only work there."),
 "history": ("l", "Open or close the message history."), "close": ("x", "Close the menu, panel or target choice."),
 "quit": ("q", "Save and quit."), "next_page": ("]", "Next page of the pack panel, or the next region on the map."),
}
CONTEXTS = {
 "walk": "Walking with nothing in focus.", "menu": "A menu is open.", "choice": "A choice waits for an answer.",
 "pack": "The pack panel is open.", "sheet": "The character screen is open.", "encounter": "Picking an action tile.",
 "target": "Picking a target for an action.", "debrief": "The after-action screen.",
 "panel": "The shared panel is open (what Inspect shows).",
 "item": "An item's details are open.",
 "gear": "The gear screen, picking from its list.",
 "modify": "The gear screen's list of modifications for the picked item.",
 "talk": "A conversation, waiting for a response.",
 "map": "The map: the cursor moves between places, the next-page key shows the next region.",
 "card": "An event's card without a question: any key continues.",
 "history": "The message history is open.",
 "picked": "An action tile is picked: its details show, the same number uses it.",
 "start": "The start screen.", "slots": "The save slots.", "help": "The help screen.",
 "quit": "The quit question: Y quits to the start screen, N goes back.",
}
ROLES = {
 "title": ("white", True, False, "Screen titles: the location, the encounter, the result."),
 "heading": ("white", True, False, "Headings inside zones: 'Fitted:', 'Round 1:'."),
 "danger": ("orange", False, False, "Warnings, hazards, harm, intents, low pools."),
 "gain": ("white", True, False, "Gains: items, levels, wins."),
 "quiet": ("grey", False, True, "Dialogue and descriptions."),
 "unavailable": ("grey", False, True, "Options that can't be used now, with their hint."),
 "hint": ("grey", False, True, "Key hints and the legend."),
 "key": ("white", False, False, "Key letters in menus (drawn inverse)."),
 "map_player": ("white", True, False, "The player on the map (drawn inverse)."),
 "map_person": ("white", True, False, "People on the map whose view of the player is 0 or more."),
 "map_hostile": ("red", False, False, "People on the map whose view of the player is below 0."),
 "map_object": ("yellow", False, False, "Objects on the map."),
 "map_exit": ("cyan", False, False, "Doors and other exits on the map."),
 "map_wall": ("grey", False, False, "Wall glyphs on the map."),
 "map_floor": ("grey", False, True, "Floor glyphs on the map."),
}
WIDGETS = {
 "title": (list(SCREENS), "The screen's title line: the location and region with hazards, the encounter and its round, or the fight's result.", {}),
 "grid": (["world"], "The room: tiles, objects, characters and the player.", {}),
 "status": (["world"], "Day and phase, pool bars, statuses and party.", {
     "pools": {"description": "Which pool stats show as bars: 'all', or a list of groups in order: 'health', the other 'draining' pools (mana), the 'filling' pools (heat).",
               "default": "all", "oneOf": [{"const": "all"},
                   arr({"enum": ["health", "draining", "filling"]}, "Groups of pools.", minItems=1, uniqueItems=True)]},
     "day": flag(True, "Show the day and phase."), "statuses": flag(True, "List the player's statuses."),
     "party": flag(True, "List who travels with the player.")}),
 "legend": (["world"], "What each glyph on the grid is.", {}),
 "log": (list(SCREENS), "Messages, in the order they happened.", {
     "round_heading": flag(True, "In fights, head the log with the round it describes.")}),
 "menu": (["world"], "What can be done with the thing in focus.", {
     "hints": flag(True, "Show why unavailable options can't be used.")}),
 "choice": (["world", "encounter"], "A choice waiting for an answer.", {
     "hints": flag(True, "Show why unavailable options can't be picked.")}),
 "board": (["world"], "The pack panel: cargo, items by where they are, the picked item's options.", {
     "budgets": flag(True, "Show the cargo line.")}),
 "tiles": (["encounter"], "The player's action tiles: the number in the top border, the name inside (the action's short name when it's longer than the tile), costs as symbols; the picked tile drawn with the heavy border.", {
     "per_row": intval(0, 0, 9, "Tiles per row; 0 fits as many as the width allows.")}),
 "fighters": (["encounter"], "Both sides with health bars, their statuses with rounds left, and the enemies' intents; while picking a target, the possible targets marked with the cursor glyph and numbered.", {
     "intent": flag(True, "Show each enemy's intent.")}),
 "art": (["encounter"], "The picture of the enemy in front, in half-block pixels in the art zone, centred; without one, its glyph in the middle.", {
     "frame": flag(True, "Draw a frame around it.")}),
 "panel": (["world", "gear"], "The shared panel for details: what Inspect shows, an item's details, the message history, or an event's card (a question, or a text longer than card_min_lines); questions always open as a card. A title, a subtitle and a text. It takes the place of the other widgets in its zone while open; up and down scroll it.", {
     "slider": flag(True, "Draw a slider at the right edge when the content is longer than the panel.")}),
 "portrait": (["character", "talk"], "The player's picture on the character screen, the speaker's in a conversation: pixels drawn with half-block characters, two per text cell, in the art zone. Without one, an empty frame of the same size keeps the place.", {
     "frame": flag(True, "Draw a frame around it.")}),
 "identity": (["character", "talk"], "Name, title, faction and rank, and the pool bars; in a conversation, the speaker's name, title, faction and trust.", {}),
 "conversation": (["talk"], "The conversation: the last exchanges, the speaker's current line, and your numbered responses (trades show what you give and get), Leave last. It keeps its newest lines in view; up and down look back.", {
     "trades": flag(True, "Show what a trade gives and takes, read from its take_item and give_item effects.")}),
 "skills": (["character"], "Each skill with its level, progress to the next, and what the next level brings.", {}),
 "stats": (["character"], "The derived stats, and conditions (statuses) with the turns they have left.", {}),
 "people": (["character"], "Who travels with you, with their health, and how the factions regard you.", {}),
 "region_map": (["map"], "A region's map: the places you've been, the places their exits lead to that you haven't been yet, and the ways between neighbouring places; you and the cursor marked. Locations without a place on their region's map aren't drawn.", {}),
 "map_place": (["map"], "The place under the map's cursor: its name, whether you've been there, where its exits lead; then what the map's glyphs mean.", {
     "legend": flag(True, "Show what the map's glyphs mean.")}),
 "budgets": (["gear"], "Each budget, each filling pool's constant load, and cargo as bars: used of what the loadout provides.", {}),
 "loadout": (["gear"], "The gear screen's list: what's equipped by slot (empty slots too; slots that gear adds under it), spare gear, designs. Up and down move the pick; the list scrolls to keep it in view.", {}),
 "pick": (["gear"], "The picked entry: what it is, what its action would change, and its action keys; or the modifications that apply to it.", {}),
 "action": (["encounter"], "The picked action's details, in place of the log: its costs and what it does in words, and why it can't be used when it can't.", {}),
 "start_menu": (["start"], "The start screen's choices, numbered; Continue shows the slot, place and day it would resume.", {}),
 "description": (["start"], "The game pack's description.", {}),
 "slots": (["slots"], "The save slots: where and when each was saved, or empty.", {}),
 "help": (["help"], "The keys, generated from the bindings, then how it works: the interface (the UI pack's words) and the game's own help (the game pack's 'help').", {}),
 "question": (["quit"], "The quit question.", {}),
 "keys": (list(SCREENS), "The key hints for the current context, built from the key bindings.", {}),
}

widget_defs = {}
for name, (screens, desc, opts) in WIDGETS.items():
    props = {"widget": {"const": name}}
    props.update(opts)
    widget_defs[f"widget_{name}"] = obj(desc + " Allowed on: " + ", ".join(screens) + ".", props, ("widget",),
                                        **{"x-screens": screens})

layout = {"description": "What a zone holds: one widget, two side by side, or several one after another.",
          "x-discriminator": "widget",
          "oneOf": [obj("Two layouts side by side, divided by a line.", {
                         "row": arr({"$ref": D + "layout"}, "Left, then right.", minItems=2, maxItems=2),
                         "fixed": {"enum": ["left", "right"], "default": "left",
                                   "description": "The side that keeps its natural width; the other takes the rest."}}, ("row",)),
                    obj("Layouts one after another in the same zone; empty ones take no space.", {
                         "stack": arr({"$ref": D + "layout"}, "Top to bottom.", minItems=1)}, ("stack",))]
                   + [{"$ref": D + f"widget_{n}"} for n in WIDGETS]}

zone = obj("One bordered band of a screen.", {
   "content": {"$ref": D + "layout"},
   "priority": intval(0, 0, 9, "When the screen doesn't fit the terminal, zones with the highest priority are dropped first; 0 is never dropped."),
   "hide_when_empty": flag(True, "Draw nothing, not even the border, when the zone has nothing to show."),
   "scroll": flag(False, "When the screen still doesn't fit after dropping zones, show only this zone's last lines (at least one), so the newest messages and the menu stay in view."),
   "notes": c("notes")}, ("content",))

size = obj("Sizes, in terminal cells.", {
   "min_columns": intval(48, 30, 200, "The narrowest terminal the screens must fit."),
   "min_rows": intval(24, 10, 100, "The shortest terminal the screens must fit."),
   "cell_width": intval(2, 1, 3, "Columns per grid tile (the glyph plus spacing)."),
   "tile_width": intval(10, 6, 16, "Width of an action tile, borders included."),
   "bar_length": intval(8, 3, 16, "Length of a pool bar in the status panel."),
   "fighter_bar_length": intval(6, 3, 16, "Length of a health bar in the fighters panel."),
   "side_min_width": intval(14, 8, 60, "The narrowest the panel beside the grid or the art may get."),
   "page_size": intval(9, 1, 9, "Entries per page of the pack panel (picked with 1-9)."),
   "art_width": intval(24, 4, 32, "Width of the art zone (a character's picture: portrait and fight), in pixels (one text column each)."),
   "art_height": intval(24, 4, 32, "Height of the art zone, in pixels (two per line of text)."),
   "save_slots": intval(3, 1, 9, "How many numbered save slots the start screen offers."),
   "card_min_lines": intval(3, 0, 20, "An event text longer than this many lines on the narrowest screen opens as a card; shorter ones stay in the message log; 0 opens every event text as a card. Questions always open as a card.")}, default={})
border = obj("The box-drawing set.", {k: char(v, f"The {k.replace('_', ' ')} piece.", 1) for k, v in (
   ("horizontal", "─"), ("vertical", "│"), ("top_left", "┌"), ("top_right", "┐"), ("bottom_left", "└"),
   ("bottom_right", "┘"), ("join_left", "├"), ("join_right", "┤"))}, default={})
glyphs = obj("Characters the widgets draw with.", {
   "border": border,
   "bar_full": char("█", "A filled step of a bar.", 1), "bar_empty": char("░", "An empty step of a bar.", 1),
   "player": char("@", "The player on the grid when nothing else is on their tile.", 1),
   "intent": char("⚠", "Before an enemy's intent.", 2), "cost": char("▲", "Before an action tile's pool cost.", 1),
   "mark_danger": char("! ", "Before warning messages.", 3), "mark_gain": char("+ ", "Before gain messages.", 3),
   "separator": char(" · ", "Between entries on one line (the legend).", 3),
   "cursor": char("▸", "Marks the picked line of a list, so the pick shows without colour too.", 1),
   "place": char("■", "A place you've been to, on the map.", 1),
   "unexplored": char("?", "A place an exit leads to that you haven't been to, on the map.", 1),
   "border_picked": obj("The box-drawing set for a picked action tile.", {k: char(v, f"The {k.replace('_', ' ')} piece.", 1) for k, v in (
       ("horizontal", "━"), ("vertical", "┃"), ("top_left", "┏"), ("top_right", "┓"), ("bottom_left", "┗"),
       ("bottom_right", "┛"))}, default={}),
   "cooldown": char("⟳", "Before an action tile's cooldown.", 1),
   "charges": char("×", "Before an action tile's uses left this fight.", 1),
   "slider_track": char("│", "The slider's track, beside a scrolling panel.", 1),
   "slider_thumb": char("█", "The slider's thumb: where the visible part is.", 1),
   "arrows": obj("The arrow keys as shown in key hints.", {
        "north": char("↑", "Up.", 1), "south": char("↓", "Down.", 1),
        "west": char("←", "Left.", 1), "east": char("→", "Right.", 1)}, default={})}, default={})
style = obj("How text in one role looks.", {
   "colour": {"enum": PALETTE, "description": "Colour from the engine's palette."},
   "bold": flag(False, "Bold."), "dim": flag(False, "Dimmed.")})
styles = obj("Text style by role. Roles are fixed by the engine. A game pack's own colour for an object, a person or a room's floor and walls overrides the map roles.",
   {role: {**style, "default": {"colour": col, "bold": bold, "dim": dim}, "description": desc}
    for role, (col, bold, dim, desc) in ROLES.items()}, default={})
tokens = obj("Layout variables: every size, glyph and style the widgets use.", {
   "$schema": SCHEMA_REF, "size": size, "padding": intval(1, 0, 2, "Spaces between a zone's border and its text."),
   "glyphs": glyphs, "styles": styles, "notes": c("notes")})

hint = obj("One key hint: the keys of some actions (or 1-9), then a label.", {
   "actions": arr({"enum": list(ACTIONS)}, "Actions whose keys are shown, joined, e.g. WASD.", uniqueItems=True),
   "digits": flag(False, "Show '1-9' (the number keys) instead of action keys."),
   "arrows": flag(False, "Show the arrow keys (↑↓←→) for move actions instead of their letters; the arrow keys always work."),
   "picked": flag(False, "Show the picked action tile's number, then the label ('3 again: use')."),
   "label": {"$ref": C + "id", "x-ref": "word", "description": "Id of a text in the words file."}}, ("label",))
keys = obj("Key bindings and the hints each context shows. Number keys 1-9 always pick numbered entries and can't be bound.", {
   "$schema": SCHEMA_REF,
   "bindings": obj("The key for each input action.", {
        a: {"type": "string", "pattern": r"^[^0-9A-Z\s/]$", "default": k, "description": d + " One key: not a digit, a space, '/' (the command line) or an upper-case letter (keys match either case)."} for a, (k, d) in ACTIONS.items()}, default={}),
   "hints": obj("The hints shown in each context, in order.", {
        ctx: {**arr(hint, d), "default": []} for ctx, d in CONTEXTS.items()}, default={}),
   "notes": c("notes")})

WORDS = {
 "go_to": ("Menu label for an exit without a label of its own.", ["destination"]),
 "talk": ("Menu label for talking to someone.", []), "inspect": ("Menu label for looking closely.", []),
 "workshop": ("Menu label on a workshop (a bench, a forge): opens the gear screen with the gear key.", []),
 "equip": ("Board: equip a piece of gear.", []), "remove": ("Board: take off equipped gear.", []),
 "store": ("Board: put an item into storage within reach.", []), "take": ("Board: take a stored item.", []),
 "dismantle": ("Board: dismantle an item at a workshop.", []), "repair": ("Board: repair a worn item.", []),
 "make": ("Board: make a copy of a known design.", []), "modify": ("Board: apply a modification.", ["modification"]),
 "pack_equipped": ("Board heading: equipped gear.", []), "pack_carried": ("Board heading: carried items.", []),
 "pack_stored": ("Board heading: storage within reach.", ["container"]),
 "pack_designs": ("Board heading: known designs, near a workshop that makes things.", []),
 "pack_more": ("Board: more pages.", ["page", "pages"]),
 "character_title": ("Character screen title.", ["name"]),
 "map_title": ("Map screen title.", ["region"]),
 "map_regions": ("Map screen: which of the regions you've been to is shown, beside the title.", ["number", "count"]),
 "map_here": ("Map: under the place you're in.", []), "map_visited": ("Map: under a place you've been to.", []),
 "map_known": ("Map: under a place you haven't been to.", []),
 "map_leads": ("Map: where a place's exits lead.", ["places"]),
 "map_elsewhere": ("Map: places in other regions that exits on this map lead to.", ["places"]),
 "map_nowhere": ("Map: when the place you're in has no place on its region's map.", []),
 "map_legend_here": ("Map legend: you.", []), "map_legend_visited": ("Map legend: a place you've been to.", []),
 "map_legend_known": ("Map legend: a place you haven't been to.", []),
 "skills_heading": ("Character screen heading: skills.", []),
 "skill_next": ("Character screen: what the next level of a skill brings.", ["level", "text"]),
 "skill_top": ("Character screen: a skill at its top level.", []),
 "skills_none": ("Character screen: no skills yet.", []),
 "stats_heading": ("Character screen heading: stats.", []),
 "conditions_heading": ("Character screen heading: conditions (statuses).", []),
 "conditions_none": ("Character screen: no conditions.", []),
 "condition_turns": ("Character screen: turns a condition has left.", ["turns"]),
 "party_heading": ("Character screen heading: the party.", []),
 "party_alone": ("Character screen: travelling alone.", []),
 "party_down": ("Character screen: a companion who is down.", []),
 "standing_heading": ("Character screen heading: standing.", []),
 "standing_rank": ("Character screen: your rank.", ["rank"]),
 "standing_view": ("Character screen: how a faction regards you.", ["faction", "level", "value"]),
 "cost_pool": ("Action details: what it costs of a pool (mana spent, heat added).", ["stat", "amount"]),
 "cost_cooldown": ("Action details: rounds before it can be used again.", ["rounds"]),
 "cost_charges": ("Action details: uses left this fight.", ["left", "total"]),
 "cost_consumes": ("Action details: items used up.", ["items"]),
 "cost_free": ("Action details: no cost.", []),
 "turns_one": ("A count of one turn, used in other words.", []),
 "turns_many": ("A count of turns, used in other words.", ["count"]),
 "rounds_one": ("A count of one round, used in other words.", []),
 "rounds_many": ("A count of rounds, used in other words.", ["count"]),
 "act_early": ("Action details: acts before initiative.", []),
 "act_late": ("Action details: acts after initiative.", []),
 "act_damage": ("Action details: damage.", ["amount", "type", "target"]),
 "act_status": ("Action details: a status put on someone.", ["status", "rounds", "target"]),
 "act_stat": ("Action details: a stat changed for some rounds.", ["stat", "amount", "rounds", "target"]),
 "act_stat_lasting": ("Action details: a stat changed for good.", ["stat", "amount", "target"]),
 "act_restore": ("Action details: a pool restored.", ["stat", "amount", "target"]),
 "act_end_status": ("Action details: a status ended.", ["status", "target"]),
 "act_escape": ("Action details: the fight ends with you getting away.", []),
 "act_end": ("Action details: the fight ends.", []),
 "act_chance": ("Action details: something that happens by chance.", ["percent", "then"]),
 "target_enemy": ("Action details: one enemy.", []), "target_all_enemies": ("Action details: every enemy.", []),
 "target_ally": ("Action details: one ally.", []), "target_all_allies": ("Action details: your whole side.", []),
 "target_self": ("Action details: the user.", []),
 "action_unusable": ("Action details: why it can't be used now.", ["why"]),
 "start_continue": ("Start screen: resume the last game.", []), "start_new": ("Start screen: a new game.", []),
 "start_load": ("Start screen: pick a saved game.", []), "start_help": ("Start screen: the help screen.", []),
 "start_quit": ("Start screen: leave the program.", []),
 "slot_name": ("A save slot's name.", ["number"]), "slot_empty": ("An empty save slot.", []),
 "slot_where": ("Where a saved game is.", ["place", "day", "phase"]),
 "slot_saved": ("When a slot was saved.", ["when"]), "slot_unreadable": ("A save that can't be read.", []),
 "slots_load_title": ("Slots screen title, loading.", []), "slots_new_title": ("Slots screen title, for a new game.", []),
 "slots_new_note": ("Slots screen, for a new game: a used slot is overwritten.", []),
 "help_title": ("Help screen title.", []), "help_keys": ("Help heading: the keys.", []),
 "help_how": ("Help heading: how it works.", []),
 "help_interface": ("Help: how the interface works, for every game.", []),
 "key_move": ("Help: what the move keys do.", []), "key_wait": ("Help: what the wait key does.", []),
 "key_pack": ("Help: what the pack key does.", []), "key_gear": ("Help: what the gear key does.", []),
 "key_character": ("Help: what the character key does.", []), "key_map": ("Help: what the map key does.", []), "key_history": ("Help: what the history key does.", []),
 "key_close": ("Help: what the close key does.", []), "key_quit": ("Help: what the quit key does.", []),
 "key_next_page": ("Help: what the next-page key does.", []), "key_digits": ("Help: what the number keys do.", []),
 "key_arrows": ("Help: how the arrow keys are named.", []), "key_escape": ("Help: how the Esc key is named.", []),
 "quit_question": ("The quit question.", []), "quit_saved": ("Under the quit question.", []),
 "history_title": ("Message history heading.", []),
 "history_empty": ("Message history: nothing yet.", []),
 "talk_title": ("Conversation title.", ["name"]),
 "talk_trust": ("Conversation: how the speaker regards you.", ["level", "value"]),
 "talk_says": ("Conversation: the speaker's line.", ["name", "text"]),
 "talk_you": ("Conversation history: the response you gave.", ["response"]),
 "talk_leave": ("Conversation: the response that ends it.", []),
 "talk_give": ("Conversation: what a trade takes from you.", []),
 "talk_get": ("Conversation: what a trade gives you.", []),
 "day_phase": ("Status: the day and part of the day.", ["day", "phase"]),
 "party": ("Status: who travels with the player.", ["names"]),
 "encounter_round": ("Encounter title with the round about to be played.", ["encounter", "round"]),
 "round_log": ("Log heading: the round just played.", ["round"]),
 "round_end": ("Log line before what the end of a round brings.", []),
 "terminal_too_small": ("Shown instead of the game when the terminal is too small.", ["columns", "rows"]),
 "save_older_than_pack": ("Log line when a loaded save was made before the pack changed: what was added since is missing from it.", []),
 "details": ("Board: open the picked item's details.", []),
 "kind_gear": ("Item details: what gear is called.", []), "kind_material": ("Item details: what a material is called.", []),
 "kind_consumable": ("Item details: what a consumable is called.", []), "kind_misc": ("Item details: any other item.", []),
 "slot_named": ("Item details: the slot an item fits.", ["slot"]),
 "item_condition": ("Item details: its condition.", ["now", "top"]),
 "item_broken": ("Item details: a broken item's condition.", []),
 "item_uses": ("Item details label: budgets and pools it uses while equipped.", []),
 "item_gives": ("Item details label: stats it adds.", []),
 "item_slots": ("Item details label: the slots it adds.", []),
 "item_worn_size": ("Item details label: the size its wearer becomes.", []),
 "item_tags": ("Item details label: what it counts as.", []),
 "item_actions": ("Item details label: actions it gives.", []),
 "item_mods": ("Item details label: its mod slots.", []),
 "item_mods_free": ("Item details: free mod slots.", ["free", "total"]),
 "item_size": ("Item details label: its size.", []),
 "item_stack": ("Item details label: how many fit in one stack.", []),
 "item_stack_count": ("Item details: the stack limit.", ["count"]),
 "item_needs": ("Item details label: what equipping it needs.", []),
 "item_dismantle": ("Item details label: what taking it apart gives.", []),
 "item_make": ("Item details label: what making one costs.", []),
 "item_repair": ("Item details label: what a repair costs.", []),
 "item_repair_amount": ("Item details: what a repair restores.", ["items", "amount"]),
 "design_known": ("Item details: you know how to make it.", []),
 "design_unknown": ("Item details: you don't know how to make it yet.", []),
 "gear_title": ("Gear screen title.", []),
 "gear_at": ("Gear screen: the workshop within reach.", ["place"]),
 "gear_planning": ("Gear screen: no workshop within reach.", []),
 "gear_worn": ("Gear list heading: equipped.", []), "gear_spare": ("Gear list heading: spare gear.", []),
 "gear_designs": ("Gear list heading: known designs.", []), "gear_empty": ("Gear list: an empty slot.", []),
 "gear_carried": ("Gear list: where a spare item is.", []),
 "gear_in": ("Gear list: a stored spare item's place.", ["container"]),
 "gear_equipped": ("Picked entry: it's equipped.", []), "gear_design": ("Picked entry: a design.", []),
 "gear_change": ("Picked entry: what an action would change.", ["action", "changes"]),
 "modify_menu": ("Picked entry: open the modifications list.", []),
 "modify_title": ("Modifications list heading.", ["item"]),
 "modify_none": ("Modifications list: none apply.", []),
 "mod_condition": ("Modifications list: what one adds to the maximum condition.", ["amount"]),
 "mod_uses": ("Modifications list: how one changes what an item uses.", ["stat", "amount"]),
}
words = obj("The UI's own words: labels, headings and hint labels. The game's voice (what happens, hints, dialogue) stays in the game pack's strings.", {
   "$schema": SCHEMA_REF,
   "engine": obj("Words the widgets use. Placeholders in braces are filled in; each word may use only its own. A missing word shows as its key.",
        {k: {"type": "string", "minLength": 1, "description": d + (f" Placeholders: {', '.join('{' + p + '}' for p in ph)}." if ph else " No placeholders."),
             "x-placeholders": ph} for k, (d, ph) in WORDS.items()}, default={}),
   "entries": {**arr(obj("A label for key hints.", {"id": c("id"), "text": c("label"), "notes": c("notes")}, ("id", "text")),
                  "Hint labels, referred to by id from keys.json."), "default": []},
   "notes": c("notes")})

screens = obj("Each screen as a list of zones, top to bottom.", dict(
   {"$schema": SCHEMA_REF, "notes": c("notes")},
   **{name: arr({"$ref": D + "zone"}, desc, minItems=1) for name, desc in SCREENS.items()}), tuple(SCREENS))

KINDS = ["tokens", "keys", "screens", "words"]
path = {"type": "string", "pattern": r"^(?!/)(?!.*\.\.)[A-Za-z0-9_\-/]+\.json$", "description": "Path relative to the UI pack."}
manifest = obj("A UI pack's manifest (ui.json). A UI pack is shared by game packs; it owns the look, layout, keys and the UI's words.", {
   "$schema": SCHEMA_REF, "id": c("id"), "name": c("label"),
   "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$", "description": "The UI pack's own version."},
   "schema_version": {"const": 4, "description": "Schema version the UI pack was written for."},
   "description": c("text"), "authors": arr({"type": "string", "minLength": 1}, "Credits."),
   "files": obj("Data files by kind; files of one kind are merged.", {k: arr(path, f"{k} files.", minItems=1, uniqueItems=True) for k in KINDS},
                ("tokens", "keys", "screens", "words")),
   "notes": c("notes")}, ("id", "name", "version", "schema_version", "files"))

schema = {
 "$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "ui.schema.json",
 "title": "UI packs",
 "description": "A UI pack standardises the terminal UI: tokens (sizes, glyphs, styles), a fixed catalogue of widgets arranged into screens, key bindings with their hints, and the UI's own words. Every field defaults to the standard look, so a UI pack only writes what it changes. The engine owns the catalogue: screens, widgets and where each may appear, input actions, hint contexts and style roles.",
 "x-schema-version": 4, "$ref": "#/$defs/manifest",
 "$defs": dict({"manifest": manifest, "tokens_file": tokens, "keys_file": keys, "screens_file": screens, "words_file": words,
                "zone": zone, "layout": layout, "hint": hint, "style": style}, **widget_defs),
}


def text() -> str:
    """The schema file's contents."""
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    OUT.write_text(text(), encoding="utf-8")
    print(len(WIDGETS), "widgets,", len(ACTIONS), "actions,", len(CONTEXTS), "contexts,", len(WORDS), "words")
