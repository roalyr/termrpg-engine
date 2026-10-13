"""
Starts: other ways to begin a game. A start is the pack's usual new game, then the
start's effects, run by the player, and whatever they set off (a fight, an event, owed
time) settled as after any action.
"""
from engine import events
from engine.content import Content
from engine.effects import run
from engine.state import Ctx, GameState, new_game


def begin(content: Content, seed: int, start_id: str) -> GameState:
    """A new game from a start. Raises KeyError for an unknown start."""
    start = content.get("start", start_id)
    state = new_game(content, seed)
    state = run(content, state, Ctx(self_id=state.player), start["effects"])
    return events.settle(content, state)
