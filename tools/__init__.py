"""
Standalone tools for working on content packs. Start them from the editor's menu
(python3 editor.py) or on their own (python3 -m tools.<name> <pack>).

Every tool is a class with 'name' and 'about', built from (PackFiles, Look), with
render(columns, rows) and handle(key) -> False to leave.
"""


def tools() -> list:
    """The finished tools, in menu order. Planned ones aren't listed until they work."""
    from tools.art import Art
    from tools.entries import Entries
    from tools.loadout import Loadout
    from tools.map import Map
    from tools.overview import Overview
    from tools.room import Room
    return [Map, Room, Entries, Loadout, Art, Overview]
