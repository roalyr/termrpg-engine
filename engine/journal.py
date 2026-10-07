"""
The journal: the message history kept with the game, so it survives saving.

record() runs after every key the player presses: it adds the messages that key brought
(and a fight's after-action screen when one appears), stamped with the turn, keeping the
last JOURNAL_SIZE lines.
"""
from typing import List

from engine.state import Entry, GameState

JOURNAL_SIZE = 200


def record(before: GameState, after: GameState) -> GameState:
    """'after' with what the step from 'before' said added to its journal."""
    entries: List[Entry] = []
    old = before.messages
    new = after.messages[len(old):] if after.messages[:len(old)] == old else after.messages
    entries += [Entry(after.turn, m.kind, m.text) for m in new]
    if after.debrief is not None and after.debrief != before.debrief:
        debrief = after.debrief
        entries.append(Entry(after.turn, "danger" if debrief.result == "lost" else "gain", debrief.title))
        entries += [Entry(after.turn, m.kind, m.text) for m in debrief.messages]
    if not entries:
        return after
    return after._replace(journal=(after.journal + tuple(entries))[-JOURNAL_SIZE:])
