from typing import Tuple, List
from core.types import GameState
from core.reducers import (
    reduce_inspect, reduce_talk, reduce_use, reduce_leave,
    reduce_wait, reduce_map, reduce_back, reduce_pack,
    reduce_character, reduce_party, reduce_log, reduce_flavor,
    reduce_help
)


def tokenize_command(raw_input: str) -> Tuple[str, ...]:
    """Tokenizes and normalizes user input into lowercased terms."""
    cleaned = raw_input.strip()
    if not cleaned:
        return ()
    return tuple(cleaned.lower().split())


def dispatch_action(state: GameState, raw_input: str) -> GameState:
    """Dispatches normalized user command to the appropriate pure state reducer."""
    tokens = tokenize_command(raw_input)
    if not tokens:
        return state

    verb = tokens[0]
    args = tokens[1:]

    # In map view, allow 'back' or 'leave <node_id>'
    if state.active_view == "map_topology":
        if verb in ("back", "b"):
            return reduce_back(state)
        elif verb in ("leave", "go", "move") and args:
            return reduce_leave(state, args[0])
        elif verb in ("quit", "q", "exit"):
            return state._replace(is_running=False, message_buffer=("Session terminated.",))
        elif verb == "map":
            return reduce_back(state)
        else:
            return state._replace(
                message_buffer=("In Map view. Type 'back' to return to compartment, or 'leave <edge_id>'.",)
            )

    if verb in ("inspect", "look", "examine"):
        target = " ".join(args) if args else ""
        return reduce_inspect(state, target)

    elif verb in ("talk", "speak", "chat"):
        actor = " ".join(args) if args else ""
        return reduce_talk(state, actor)

    elif verb == "use":
        if len(args) < 2:
            return state._replace(
                message_buffer=("Usage: use <item_id> <target_fixture_id>",)
            )
        return reduce_use(state, args[0], args[1])

    elif verb in ("wait", "rest"):
        return reduce_wait(state)

    elif verb in ("leave", "go", "move"):
        if not args:
            return state._replace(
                message_buffer=("Usage: leave <exit_id>",)
            )
        return reduce_leave(state, args[0])

    elif verb == "map":
        return reduce_map(state)

    elif verb in ("pack", "inv", "inventory"):
        return reduce_pack(state)

    elif verb in ("character", "char"):
        return reduce_character(state)

    elif verb == "party":
        return reduce_party(state)

    elif verb == "log":
        return reduce_log(state)

    elif verb in ("flavor", "flavor_text"):
        toggle = args[0] if args else ""
        return reduce_flavor(state, toggle)

    elif verb in ("help", "?"):
        return reduce_help(state)

    elif verb in ("quit", "q", "exit"):
        return state._replace(is_running=False, message_buffer=("Saving snapshot and exiting.",))

    else:
        return state._replace(
            message_buffer=("Unknown command. Type 'help' for available actions.",)
        )
