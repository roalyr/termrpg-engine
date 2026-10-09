"""
Around the game: the start screen, the save slots and the help screen, before a game
is loaded. Reading the slots touches the disk; deciding what a key does doesn't.
"""
import time
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

from engine import save
from engine.content import Content
from engine.state import day_of, phase_of


class SlotInfo(NamedTuple):
    """One numbered save slot: where and when its game was saved, if it has one."""
    number: int
    path: Path
    used: bool = False
    readable: bool = True
    place: Optional[str] = None
    day: Optional[int] = None
    phase: Optional[str] = None
    saved: Optional[str] = None      # when, in words
    mtime: float = 0.0


class Shell(NamedTuple):
    """What the shell shows: 'start', 'slots' (to 'load' or start a 'new' game in) or 'help'."""
    screen: str = "start"
    selected: int = 0
    scroll: int = 0
    mode: str = "load"


class ShellData(NamedTuple):
    """What the shell's widgets draw from."""
    entries: Tuple[str, ...]
    slots: Tuple[SlotInfo, ...]
    mode: str


def slot_path(saves_dir: Path, number: int) -> Path:
    return saves_dir / f"slot{number}.json"


def read_slots(content: Content, saves_dir: Path, count: int) -> Tuple[SlotInfo, ...]:
    """The numbered slots and what's in each."""
    slots = []
    for number in range(1, count + 1):
        path = slot_path(saves_dir, number)
        if not path.exists():
            slots.append(SlotInfo(number, path))
            continue
        mtime = path.stat().st_mtime
        when = time.strftime("%d %b %H:%M", time.localtime(mtime))
        try:
            state = save.load(content, path)
        except (save.SaveError, ValueError, KeyError, TypeError):
            slots.append(SlotInfo(number, path, used=True, readable=False, saved=when, mtime=mtime))
            continue
        me = state.characters[state.player]
        place = content.get("location", me.location)["name"] if me.location else ""
        phase = content.get("phase", phase_of(content, state.turn))["name"]
        slots.append(SlotInfo(number, path, True, True, place, day_of(content, state.turn), phase, when, mtime))
    return tuple(slots)


def last_played(slots: Tuple[SlotInfo, ...]) -> Optional[SlotInfo]:
    """The slot saved most recently, which Continue resumes."""
    used = [s for s in slots if s.used and s.readable]
    return max(used, key=lambda s: s.mtime) if used else None


def entries(slots: Tuple[SlotInfo, ...]) -> Tuple[str, ...]:
    """The start screen's choices: Continue and Load only when there's a game to resume."""
    resumable = last_played(slots) is not None
    return tuple(e for e in ("continue", "new", "load", "help", "quit") if resumable or e not in ("continue", "load"))


def handle(shell: Shell, action: Optional[str], key: str, slots: Tuple[SlotInfo, ...]):
    """
    One key on the shell: returns the new Shell and an outcome: None, ('play', path, fresh)
    or 'exit'. Up and down move the pick, a digit or Enter chooses, close goes back.
    """
    choices = entries(slots)
    count = {"start": len(choices), "slots": len(slots)}.get(shell.screen, 0)
    if shell.screen == "help":
        if action in ("close", "quit"):
            return Shell(), None
        if action == "move_north":
            return shell._replace(scroll=max(0, shell.scroll - 1)), None
        if action == "move_south":
            return shell._replace(scroll=shell.scroll + 1), None
        return shell, None
    if action == "move_north":
        return shell._replace(selected=max(0, shell.selected - 1)), None
    if action == "move_south":
        return shell._replace(selected=min(count - 1, shell.selected + 1)), None
    pick = int(key) - 1 if len(key) == 1 and key.isdigit() and key != "0" else None
    if key in ("\n", "\r", " ") or action == "confirm":
        pick = shell.selected
    if shell.screen == "start":
        if action == "quit" and pick is None:
            return shell, "exit"
        if pick is None or pick >= len(choices):
            return shell, None
        return _start_choice(choices[pick], slots)
    if action == "close":                                     # the slots screen: back
        return Shell(selected=choices.index("load") if "load" in choices and shell.mode == "load" else 0), None
    if pick is None or pick >= len(slots):
        return shell._replace(selected=pick if pick is not None and pick < len(slots) else shell.selected), None
    slot = slots[pick]
    if shell.mode == "new":
        return shell, ("play", slot.path, True)
    if slot.used and slot.readable:
        return shell, ("play", slot.path, False)
    return shell._replace(selected=pick), None


def _start_choice(choice: str, slots: Tuple[SlotInfo, ...]):
    if choice == "continue":
        return Shell(), ("play", last_played(slots).path, False)
    if choice == "new":
        empty = next((s for s in slots if not s.used), None)
        if empty is not None:
            return Shell(), ("play", empty.path, True)
        return Shell("slots", mode="new"), None                # every slot used: pick one to replace
    if choice == "load":
        return Shell("slots", selected=max(0, last_played(slots).number - 1)), None
    if choice == "help":
        return Shell("help"), None
    return Shell(), "exit"
