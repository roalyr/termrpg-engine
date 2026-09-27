"""Player-facing wording: message kinds, plain names for tags, hazard words.

Messages carry their kind as a short prefix so the renderer can sort and style
them without the reducers knowing about the terminal:
  "!! " danger   - shown first, highlighted
  "+ "  gain     - new skill, crew member or item
  "~ "  quiet    - dialogue and room descriptions, dimmed (prefix is hidden)
  anything else  - the plain result of the player's action
"""
from typing import Iterable, Tuple

from core.types import NodeVitals

DANGER = "!! "
GAIN = "+ "
QUIET = "~ "

TRACK_NAMES = ("Air", "Rad", "Cold")
STATUS_NAMES = {"NOMINAL": "OK", "STRESSED": "Strained", "CRITICAL": "DANGER"}
STATE_WORDS = {"sealed": "sealed", "locked": "locked", "disabled": "broken", "spent": "used",
               "open": "open", "active": "working"}

# How each tag reads in "Needs ..." hints. Unlisted tags fall back to their words.
TAG_NAMES = {
    "seal_fitting": "a pipe fitting",
    "wrench": "a spanner",
    "force_lever": "a pry-bar",
    "heavy_lift": "a strong lifter",
    "two_person_lift": "a second lifter",
    "dock_clearance": "a work pass",
    "transit_clearance": "a shuttle token",
    "vacuum_seal": "a seal patch",
    "electrical": "copper wire",
    "conductive": "copper or wire",
    "bio_filter": "filter skills or a spanner",
    "refillable": "a canteen",
    "barter_token": "dice or scrip",
    "salvage": "scrap metal",
    "mineral": "lunar ore",
    "nutrition": "food",
    "signal_boost": "a signal specialist",
}


def danger(text: str) -> str:
    return DANGER + text


def gain(text: str) -> str:
    return GAIN + text


def quiet(text: str) -> str:
    return QUIET + text


def speech(name: str, line: str) -> str:
    return quiet(f'{name}: "{line}"')


def message_kind(message: str) -> str:
    if message.startswith(DANGER):
        return "danger"
    if message.startswith(GAIN):
        return "gain"
    if message.startswith(QUIET):
        return "quiet"
    return "plain"


def strip_kind(message: str) -> str:
    """Removes the hidden quiet prefix; danger and gain markers stay visible."""
    return message[len(QUIET):] if message.startswith(QUIET) else message


def tag_name(tag: str) -> str:
    return TAG_NAMES.get(tag, tag.replace("_", " "))


def needs(tags: Iterable[str]) -> str:
    """'a pipe fitting or a spanner' for a requirement list."""
    names = [tag_name(t) for t in tags]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " or " + names[-1]


def hazard_words(vitals: NodeVitals) -> str:
    """Short plain description of what a room will do to the player; empty when safe."""
    words = []
    if vitals.pressure_kpa < 10:
        words.append("no air")
    elif vitals.pressure_kpa < 90:
        words.append("thin air")
    if vitals.temperature_c < -60:
        words.append("freezing")
    elif vitals.temperature_c < -10:
        words.append("cold")
    if vitals.radiation_msv > 15:
        words.append("high radiation")
    elif vitals.radiation_msv > 5:
        words.append("radiation")
    return ", ".join(words)


def worst_track(values: Tuple[float, float, float]) -> Tuple[str, float]:
    """(track name, value) for the highest of the three exposure tracks."""
    idx = max(range(3), key=lambda i: values[i])
    return TRACK_NAMES[idx], values[idx]
