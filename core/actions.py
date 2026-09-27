from typing import Tuple
from core.types import GameState
from core.reducers import (
    reduce_move, reduce_interact_go, reduce_interact_inspect,
    reduce_interact_use, reduce_interact_talk, reduce_interact_cancel,
    reduce_interact_scavenge, reduce_interact_read, reduce_interact_barter,
    reduce_scavenge, reduce_read, reduce_barter, reduce_consume,
    reduce_inspect, reduce_talk, reduce_use, reduce_leave,
    reduce_wait, reduce_map, reduce_back, reduce_pack,
    reduce_character, reduce_party, reduce_log, reduce_flavor,
    reduce_help, _entity_under_cursor,
)

# Single keys that act on the entity under the cursor while the proximity menu is open.
MENU_KEYS = ("i", "u", "g", "t", "f", "r", "b", "x")


def tokenize_command(raw_input: str) -> Tuple[str, ...]:
    """Tokenizes and normalizes user input into lowercased terms, supporting leading slash."""
    cleaned = raw_input.strip().lstrip("/")
    if not cleaned:
        return ()
    return tuple(cleaned.lower().split())


def _quit(state: GameState) -> GameState:
    return state._replace(is_running=False, message_buffer=("Saving snapshot and exiting.",))


def dispatch_action(state: GameState, raw_input: str) -> GameState:
    """Dispatches normalized user command to the appropriate pure state reducer."""
    tokens = tokenize_command(raw_input)
    if not tokens:
        return state

    verb = tokens[0]
    args = tokens[1:]
    rest = " ".join(args)

    if state.active_view == "map_topology":
        if verb in ("back", "b", "map", "m"):
            return reduce_back(state)
        if verb in ("leave", "go", "move") and args:
            return reduce_leave(state, args[0])
        if verb in ("quit", "q", "exit"):
            return _quit(state)
        return state._replace(message_buffer=("In Map view. Type 'back' to return to compartment.",))

    if state.proximity_menu_active and not args:
        if verb in ("i", "inspect"):
            return reduce_interact_inspect(state)
        if verb in ("u", "use"):
            return reduce_interact_use(state)
        if verb in ("g", "go"):
            return reduce_interact_go(state)
        if verb in ("t", "talk"):
            return reduce_interact_talk(state)
        if verb in ("f", "search", "scavenge"):
            return reduce_interact_scavenge(state)
        if verb in ("r", "read"):
            return reduce_interact_read(state)
        if verb in ("b", "barter", "trade") and _entity_under_cursor(state)[1]:
            return reduce_interact_barter(state)
        if verb in ("x", "cancel"):
            return reduce_interact_cancel(state)

    if verb in ("w", "a", "s", "d"):
        return reduce_move(state, verb)
    if verb == "e":
        return reduce_interact_inspect(state)
    if verb == "g" and not args:
        return reduce_interact_go(state)

    if verb in ("inspect", "look", "examine"):
        return reduce_inspect(state, rest)
    if verb in ("talk", "speak", "chat"):
        return reduce_talk(state, rest) if rest else reduce_interact_talk(state)
    if verb in ("barter", "trade"):
        return reduce_barter(state, args[0] if args else "", " ".join(args[1:]))
    if verb == "use":
        if len(args) >= 2:
            return reduce_use(state, args[0], args[1])
        if args:
            return reduce_use(state, "", args[0])
        return reduce_interact_use(state)
    if verb in ("search", "scavenge", "take", "f"):
        return reduce_scavenge(state, rest or None)
    if verb in ("read", "r"):
        return reduce_read(state, rest) if rest else reduce_interact_read(state)
    if verb in ("consume", "eat", "drink"):
        return reduce_consume(state, rest)
    if verb in ("wait", "rest"):
        return reduce_wait(state)
    if verb in ("leave", "go", "move"):
        return reduce_leave(state, args[0]) if args else reduce_interact_go(state)
    if verb in ("map", "m"):
        return reduce_map(state)
    if verb in ("back", "b"):
        return reduce_back(state)
    if verb in ("pack", "inv", "inventory"):
        return reduce_pack(state)
    if verb in ("character", "char"):
        return reduce_character(state)
    if verb == "party":
        return reduce_party(state)
    if verb == "log":
        return reduce_log(state)
    if verb in ("flavor", "flavor_text"):
        return reduce_flavor(state, rest)
    if verb in ("help", "?"):
        return reduce_help(state)
    if verb in ("quit", "q", "exit"):
        return _quit(state)
    return state._replace(message_buffer=("Unknown command. Type '/help' for available actions.",))
