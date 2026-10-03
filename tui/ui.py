"""
The UI pack, loaded for the renderer: tokens, key bindings and hints, screens and words,
validated and with every default filled in.
"""
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, NamedTuple, Optional

from core import uipack
from core.pack import Report

ROOT_DIR = Path(__file__).resolve().parent.parent
UI_DIR = ROOT_DIR / "packs" / "ui"


class UIPackError(Exception):
    def __init__(self, ui_dir: Path, report: Report):
        self.report = report
        lines = "\n".join(f"  {e}" for e in report.errors)
        super().__init__(f"The UI pack in {ui_dir} has {len(report.errors)} error(s):\n{lines}")


class UI(NamedTuple):
    tokens: Mapping[str, Any]
    bindings: Mapping[str, str]                 # action -> key
    hints: Mapping[str, List[Mapping]]          # context -> hint entries
    screens: Mapping[str, List[Mapping]]        # screen -> zones
    words: Mapping[str, str]                    # engine word -> template
    labels: Mapping[str, str]                   # hint label id -> text

    def word(self, key: str, **fields: Any) -> str:
        """A UI word with its placeholders filled in; a missing word shows as its key."""
        template = self.words.get(key)
        return template.format(**fields) if template is not None else key

    def action_of(self, key: str) -> Optional[str]:
        """The input action bound to a key, if any."""
        for action, bound in self.bindings.items():
            if bound == key:
                return action
        return None

    @property
    def bound_keys(self) -> frozenset:
        return frozenset(self.bindings.values())


def load_ui(ui_dir: Path) -> UI:
    """Validates and loads a UI pack. Raises UIPackError on errors."""
    report, merged = uipack.load_merged(ui_dir)
    if report.errors:
        raise UIPackError(ui_dir, report)
    keys, words = merged["keys"], merged["words"]
    return UI(tokens=merged["tokens"], bindings=dict(keys["bindings"]), hints=dict(keys["hints"]),
              screens={k: v for k, v in merged["screens"].items() if k not in ("$schema", "notes")},
              words=dict(words.get("engine", {})), labels={e["id"]: e["text"] for e in words.get("entries", [])})


def ui_dir_for(ui_id: str) -> Path:
    return UI_DIR / ui_id


@lru_cache(maxsize=None)
def default_ui() -> UI:
    """The default UI pack, loaded once."""
    return load_ui(ui_dir_for("default"))
