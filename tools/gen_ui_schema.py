"""
Generates schemas/ui.schema.json, the UI pack schema. Edit this file, not the schema:

    python3 tools/gen_ui_schema.py

tests/test_ui_pack.py checks that the committed schema is what this file generates.
"""
import json
from pathlib import Path

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

PALETTE = ["grey", "white", "green", "cyan", "blue", "violet", "yellow", "orange", "red"]
SCREENS = {"world": "Walking around.", "encounter": "A fight.", "debrief": "The after-action screen at the end of a fight.",
           "fitting": "The fitting screen: the loadout, spare gear and designs, and building.",
           "character": "The character screen: who you are, skills, stats, conditions, party and standing.",
           "talk": "A conversation: the speaker, what was said, and your responses."}
ACTIONS = {
 "move_north": ("w", "Step up; scrolls an open sub-window up."), "move_west": ("a", "Step left."),
 "move_south": ("s", "Step down; scrolls an open sub-window down."),
 "move_east": ("d", "Step right."), "wait": (".", "Let a turn pass."),
 "pack": ("p", "Open or close the pack: what you carry, and storage within reach."),
 "fitting": ("f", "Open the fitting screen. It may share its key with Fit, which only works on that screen."),
 "character": ("c", "Open or close the character screen."),
 "history": ("l", "Open or close the message history."), "close": ("x", "Close the menu, panel or target choice."),
 "quit": ("q", "Save and quit."), "next_page": ("]", "Next page of the fitting board."),
}
CONTEXTS = {
 "walk": "Walking with nothing in focus.", "menu": "A menu is open.", "choice": "A choice waits for an answer.",
 "pack": "The pack panel is open.", "sheet": "The character screen is open.", "encounter": "Picking an action tile.",
 "target": "Picking a target for an action.", "debrief": "The after-action screen.",
 "panel": "The shared panel is open (what Inspect shows).",
 "item": "An item's details are open.",
 "fitting": "The fitting screen, picking from its list.",
 "modify": "The fitting screen's list of modifications for the picked item.",
 "talk": "A conversation, waiting for a response.",
 "card": "An event's card without a question: any key continues.",
 "history": "The message history is open.",
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
}
WIDGETS = {
 "title": (list(SCREENS), "The screen's title line: the location and region with hazards, the encounter and its round, or the fight's result.", {}),
 "grid": (["world"], "The room: tiles, objects, characters and the player.", {}),
 "status": (["world"], "Day and phase, pool bars, statuses and party.", {
     "pools": {"description": "Which pool stats show as bars: 'all', or a list of stat roles in order.",
               "default": "all", "oneOf": [{"const": "all"},
                   arr({"enum": ["health", "heat", "power", "mass", "initiative", "cargo"]}, "Stat roles.", minItems=1, uniqueItems=True)]},
     "day": flag(True, "Show the day and phase."), "statuses": flag(True, "List the player's statuses."),
     "party": flag(True, "List who travels with the player.")}),
 "legend": (["world"], "What each glyph on the grid is.", {}),
 "log": (list(SCREENS), "Messages, in the order they happened.", {
     "round_heading": flag(True, "In fights, head the log with the round it describes.")}),
 "menu": (["world"], "What can be done with the thing in focus.", {
     "hints": flag(True, "Show why unavailable options can't be used.")}),
 "choice": (["world", "encounter"], "A choice waiting for an answer.", {
     "hints": flag(True, "Show why unavailable options can't be picked.")}),
 "board": (["world"], "The fitting board: budgets, items by where they are, the picked item's options.", {
     "budgets": flag(True, "Show the power, mass and cargo line.")}),
 "tiles": (["encounter"], "The player's action tiles.", {
     "per_row": intval(0, 0, 9, "Tiles per row; 0 fits as many as the width allows.")}),
 "fighters": (["encounter"], "Both sides with health bars, and the enemies' intents.", {
     "intent": flag(True, "Show each enemy's intent.")}),
 "art": (["encounter"], "The picture of the enemy in front.", {
     "frame": flag(True, "Draw a frame around it.")}),
 "panel": (["world", "fitting"], "The shared panel for details: what Inspect shows, an item's details, the message history, or an event's card (a question, or a text longer than card_min_lines); questions always open as a card. A title, a subtitle and a text. It takes the place of the other widgets in its zone while open; up and down scroll it.", {
     "slider": flag(True, "Draw a slider at the right edge when the content is longer than the panel.")}),
 "portrait": (["character", "talk"], "The player's portrait on the character screen, the speaker's in a conversation: pixels drawn with half-block characters, two per text cell. Without one, an empty frame of the same size keeps the place.", {
     "frame": flag(True, "Draw a frame around it.")}),
 "identity": (["character", "talk"], "Name, title, faction and rank, and the pool bars; in a conversation, the speaker's name, title, faction and trust.", {}),
 "conversation": (["talk"], "The conversation: the last exchanges, the speaker's current line, and your numbered responses (trades show what you give and get), Leave last. It keeps its newest lines in view; up and down look back.", {
     "trades": flag(True, "Show what a trade gives and takes, read from its take_item and give_item effects.")}),
 "skills": (["character"], "Each skill with its level, progress to the next, and what the next level brings.", {}),
 "stats": (["character"], "The derived stats, and conditions (statuses) with the turns they have left.", {}),
 "people": (["character"], "Who travels with you, with their health, and how the factions regard you.", {}),
 "budgets": (["fitting"], "Power, mass, heat and cargo as bars: used of what the loadout provides.", {}),
 "loadout": (["fitting"], "The fitting screen's list: what's worn by slot (empty slots too), spare gear, designs. Up and down move the pick; the list scrolls to keep it in view.", {}),
 "pick": (["fitting"], "The picked entry: what it is, what its action would change, and its action keys; or the modifications that apply to it.", {}),
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
   "min_columns": intval(40, 30, 200, "The narrowest terminal the screens must fit."),
   "min_rows": intval(20, 10, 100, "The shortest terminal the screens must fit."),
   "cell_width": intval(2, 1, 3, "Columns per grid tile (the glyph plus spacing)."),
   "tile_width": intval(10, 6, 16, "Width of an action tile, borders included."),
   "bar_length": intval(8, 3, 16, "Length of a pool bar in the status panel."),
   "fighter_bar_length": intval(6, 3, 16, "Length of a health bar in the fighters panel."),
   "side_min_width": intval(14, 8, 60, "The narrowest the panel beside the grid or the art may get."),
   "page_size": intval(9, 1, 9, "Entries per page of the pack panel (picked with 1-9)."),
   "portrait_width": intval(12, 4, 24, "Width of the portrait zone, in pixels (one text column each)."),
   "portrait_height": intval(12, 4, 24, "Height of the portrait zone, in pixels (two per line of text)."),
   "card_min_lines": intval(3, 0, 20, "An event text longer than this many lines on the narrowest screen opens as a card; shorter ones stay in the message log; 0 opens every event text as a card. Questions always open as a card.")}, default={})
border = obj("The box-drawing set.", {k: char(v, f"The {k.replace('_', ' ')} piece.", 1) for k, v in (
   ("horizontal", "─"), ("vertical", "│"), ("top_left", "┌"), ("top_right", "┐"), ("bottom_left", "└"),
   ("bottom_right", "┘"), ("join_left", "├"), ("join_right", "┤"))}, default={})
glyphs = obj("Characters the widgets draw with.", {
   "border": border,
   "bar_full": char("█", "A filled step of a bar.", 1), "bar_empty": char("░", "An empty step of a bar.", 1),
   "player": char("@", "The player on the grid when nothing else is on their tile.", 1),
   "intent": char("⚠", "Before an enemy's intent.", 2), "cost": char("▲", "Before an action tile's heat cost.", 1),
   "mark_danger": char("! ", "Before warning messages.", 3), "mark_gain": char("+ ", "Before gain messages.", 3),
   "separator": char(" · ", "Between entries on one line (the legend).", 3),
   "cursor": char("▸", "Marks the picked line of a list, so the pick shows without colour too.", 1),
   "slider_track": char("│", "The slider's track, beside a scrolling panel.", 1),
   "slider_thumb": char("█", "The slider's thumb: where the visible part is.", 1),
   "arrows": obj("The arrow keys as shown in key hints.", {
        "north": char("↑", "Up.", 1), "south": char("↓", "Down.", 1),
        "west": char("←", "Left.", 1), "east": char("→", "Right.", 1)}, default={})}, default={})
style = obj("How text in one role looks.", {
   "colour": {"enum": PALETTE, "description": "Colour from the engine's palette."},
   "bold": flag(False, "Bold."), "dim": flag(False, "Dimmed.")})
styles = obj("Text style by role. Roles are fixed by the engine.",
   {role: {**style, "default": {"colour": col, "bold": bold, "dim": dim}, "description": desc}
    for role, (col, bold, dim, desc) in ROLES.items()}, default={})
tokens = obj("Layout variables: every size, glyph and style the widgets use.", {
   "$schema": SCHEMA_REF, "size": size, "padding": intval(1, 0, 2, "Spaces between a zone's border and its text."),
   "glyphs": glyphs, "styles": styles, "notes": c("notes")})

hint = obj("One key hint: the keys of some actions (or 1-9), then a label.", {
   "actions": arr({"enum": list(ACTIONS)}, "Actions whose keys are shown, joined, e.g. WASD.", uniqueItems=True),
   "digits": flag(False, "Show '1-9' (the number keys) instead of action keys."),
   "arrows": flag(False, "Show the arrow keys (↑↓←→) for move actions instead of their letters; the arrow keys always work."),
   "label": {"$ref": C + "id", "x-ref": "word", "description": "Id of a text in the words file."}}, ("label",))
keys = obj("Key bindings and the hints each context shows. Number keys 1-9 always pick numbered entries and can't be bound.", {
   "$schema": SCHEMA_REF,
   "bindings": obj("The key for each input action.", {
        a: {"type": "string", "pattern": r"^[^0-9A-Z\s]$", "default": k, "description": d + " One key: not a digit, a space or an upper-case letter (keys match either case)."} for a, (k, d) in ACTIONS.items()}, default={}),
   "hints": obj("The hints shown in each context, in order.", {
        ctx: {**arr(hint, d), "default": []} for ctx, d in CONTEXTS.items()}, default={}),
   "notes": c("notes")})

WORDS = {
 "go_to": ("Menu label for an exit without a label of its own.", ["destination"]),
 "talk": ("Menu label for talking to someone.", []), "inspect": ("Menu label for looking closely.", []),
 "fit": ("Board: fit a frame, module or implant.", []), "remove": ("Board: remove a worn or fitted item.", []),
 "store": ("Board: put an item into storage within reach.", []), "take": ("Board: take a stored item.", []),
 "dismantle": ("Board: dismantle an item at a workshop.", []), "repair": ("Board: repair a worn item.", []),
 "fabricate": ("Board: make a copy of a known design.", []), "modify": ("Board: apply a modification.", ["modification"]),
 "pack_fitted": ("Board heading: worn and fitted items.", []), "pack_carried": ("Board heading: carried items.", []),
 "pack_stored": ("Board heading: storage within reach.", ["container"]),
 "pack_designs": ("Board heading: known designs, near a fabricating workshop.", []),
 "pack_more": ("Board: more pages.", ["page", "pages"]),
 "character_title": ("Character screen title.", ["name"]),
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
 "details": ("Board: open the picked item's details.", []),
 "kind_frame": ("Item details: what a frame is called.", []), "kind_module": ("Item details: what a module is called.", []),
 "kind_implant": ("Item details: what an implant is called.", []), "kind_material": ("Item details: what a material is called.", []),
 "kind_consumable": ("Item details: what a consumable is called.", []), "kind_misc": ("Item details: any other item.", []),
 "slot_named": ("Item details: the slot an item fits.", ["slot"]),
 "item_condition": ("Item details: its condition.", ["now", "top"]),
 "item_broken": ("Item details: a broken item's condition.", []),
 "item_uses": ("Item details label: power, mass and heat it spends.", []),
 "item_gives": ("Item details label: stats it adds.", []),
 "item_mounts": ("Item details label: a frame's slots.", []),
 "item_tags": ("Item details label: what it counts as.", []),
 "item_actions": ("Item details label: actions it gives.", []),
 "item_mods": ("Item details label: its mod slots.", []),
 "item_mods_free": ("Item details: free mod slots.", ["free", "total"]),
 "item_size": ("Item details label: its size.", []),
 "item_stack": ("Item details label: how many fit in one stack.", []),
 "item_stack_count": ("Item details: the stack limit.", ["count"]),
 "item_needs": ("Item details label: what wearing or fitting it needs.", []),
 "item_salvage": ("Item details label: what taking it apart gives.", []),
 "item_fabricate": ("Item details label: what making one costs.", []),
 "item_repair": ("Item details label: what a repair costs.", []),
 "item_repair_amount": ("Item details: what a repair restores.", ["items", "amount"]),
 "design_known": ("Item details: you know how to make it.", []),
 "design_unknown": ("Item details: you don't know how to make it yet.", []),
 "fitting_title": ("Fitting screen title.", ["frame"]),
 "fitting_no_frame": ("Fitting screen title without a frame worn.", []),
 "fitting_at": ("Fitting screen: the workshop within reach.", ["place"]),
 "fitting_planning": ("Fitting screen: no workshop within reach.", []),
 "fitting_worn": ("Fitting list heading: worn and fitted.", []), "fitting_spare": ("Fitting list heading: spare gear.", []),
 "fitting_designs": ("Fitting list heading: known designs.", []), "fitting_empty": ("Fitting list: an empty slot.", []),
 "fitting_frame_slot": ("Fitting list: the frame's own line when none is worn.", []),
 "fitting_carried": ("Fitting list: where a spare item is.", []),
 "fitting_in": ("Fitting list: a stored spare item's place.", ["container"]),
 "fitting_fitted": ("Picked entry: it's worn or fitted.", []), "fitting_design": ("Picked entry: a design.", []),
 "fitting_change": ("Picked entry: what an action would change.", ["action", "changes"]),
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
   "schema_version": {"const": 1, "description": "Schema version the UI pack was written for."},
   "description": c("text"), "authors": arr({"type": "string", "minLength": 1}, "Credits."),
   "files": obj("Data files by kind; files of one kind are merged.", {k: arr(path, f"{k} files.", minItems=1, uniqueItems=True) for k in KINDS},
                ("tokens", "keys", "screens", "words")),
   "notes": c("notes")}, ("id", "name", "version", "schema_version", "files"))

schema = {
 "$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "ui.schema.json",
 "title": "UI packs",
 "description": "A UI pack standardises the terminal UI: tokens (sizes, glyphs, styles), a fixed catalogue of widgets arranged into screens, key bindings with their hints, and the UI's own words. Every field defaults to the standard look, so a UI pack only writes what it changes. The engine owns the catalogue: screens, widgets and where each may appear, input actions, hint contexts and style roles.",
 "x-schema-version": 1, "$ref": "#/$defs/manifest",
 "$defs": dict({"manifest": manifest, "tokens_file": tokens, "keys_file": keys, "screens_file": screens, "words_file": words,
                "zone": zone, "layout": layout, "hint": hint, "style": style}, **widget_defs),
}


def text() -> str:
    """The schema file's contents."""
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    OUT.write_text(text(), encoding="utf-8")
    print(len(WIDGETS), "widgets,", len(ACTIONS), "actions,", len(CONTEXTS), "contexts,", len(WORDS), "words")
