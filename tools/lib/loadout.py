"""
A character's loadout, worked out from the pack as it is in memory (saved or not): the
slots of the body and of equipped gear and what fills them, what the loadout provides
and uses of each budget, filling pool and cargo, its other stats, and what doesn't fit.
The numbers are the checker's (lib.budgets counts for both), so a loadout this calls
fine passes the check.
"""
from typing import Dict, List, NamedTuple, Optional

from lib.budgets import Problem, Slot, budget_stats, over
from lib.budgets import loadout as count_loadout
from tools.lib.packfiles import PackFiles


class Budget(NamedTuple):
    stat: str
    name: str
    short: str
    used: float
    provided: float
    fills: bool = False

    @property
    def over(self) -> bool:
        return over(self.fills, self.used, self.provided)


class Sheet(NamedTuple):
    size: Optional[int]       # the wearer's size: the largest worn_size, else the body's
    slots: List[Slot]
    extra: List[Slot]         # equipped items with no free slot (or that aren't gear)
    budgets: List[Budget]
    stats: Dict[str, float]   # the other stats, totalled
    problems: List[str]


class Vocab(NamedTuple):
    stats: Dict[str, dict]
    roles: Dict[str, str]     # role -> stat id
    slot_types: Dict[str, dict]


def vocab(pack: PackFiles) -> Vocab:
    merged: Dict[str, list] = {}
    for rel in pack.kinds.get("vocab", []):
        for key, value in pack.data[rel].items():
            if isinstance(value, list):
                merged.setdefault(key, []).extend(value)
    stats = {s["id"]: s for s in merged.get("stats", []) if isinstance(s, dict) and s.get("id")}
    roles = {s["role"]: i for i, s in stats.items() if s.get("role")}
    slot_types = {s["id"]: s for s in merged.get("slot_types", []) if isinstance(s, dict) and s.get("id")}
    return Vocab(stats, roles, slot_types)


def items(pack: PackFiles) -> Dict[str, dict]:
    return {f.entry["id"]: f.entry for f in pack.entries("items") if f.entry.get("id")}


def sheet(pack: PackFiles, char: dict) -> Sheet:
    known, words = items(pack), vocab(pack)
    skills = {}
    for found in pack.entries("skills"):
        skills.setdefault(found.entry.get("id"), found.entry)
    fit = count_loadout(char, known, words.stats, skills)
    budgets = []
    for stat_id in budget_stats(words.stats):
        stat = words.stats[stat_id]
        budgets.append(Budget(stat_id, stat.get("name", stat_id), stat.get("short", stat_id[:3].upper()),
                              fit.used.get(stat_id, 0), fit.provided.get(stat_id, 0), bool(stat.get("fills"))))
    counted = {b.stat for b in budgets}
    others = {s: fit.totals[s] for s in words.stats if s in fit.totals and s not in counted}
    problems = [_words(problem, known, words) for problem in fit.problems]
    return Sheet(fit.size, fit.slots, fit.extra, budgets, others, problems)


def _words(problem: Problem, known: Dict[str, dict], words: Vocab) -> str:
    """A loadout problem in the editor's words."""
    if problem.what == "no_item":
        return f"No item '{problem.item}'."
    if problem.what == "not_gear":
        return f"'{problem.item}' isn't gear."
    if problem.what == "no_slot":
        name = known.get(problem.item, {}).get("name", problem.item)
        return f"No free {_slot_name(words, problem.slot_type)} slot for {name}."
    stat = words.stats.get(problem.stat, {})
    name = stat.get("name", problem.stat)
    if stat.get("fills"):
        return f"Constant {name.lower()} {problem.used:g} leaves no room below its maximum {problem.provided:g}."
    if stat.get("role") == "cargo":
        return f"The inventory needs {problem.used:g} cargo stacks; the loadout carries {problem.provided:g}."
    return f"Equipped gear needs {problem.used:g} {name.lower()}; the loadout provides {problem.provided:g}."


def _slot_name(words: Vocab, slot_type: str) -> str:
    return words.slot_types.get(slot_type, {}).get("name", slot_type)


def uses_text(item: dict, words: Vocab) -> str:
    """What an item uses and gives, in short: 'PWR 2 MAS 3 · ARM +2'."""
    parts = [f"{words.stats.get(k, {}).get('short', k)} {v:g}" for k, v in (item.get("uses", {}) or {}).items()]
    gives = [f"{words.stats.get(k, {}).get('short', k)} {v:+g}" for k, v in (item.get("stats", {}) or {}).items()]
    return " · ".join(p for p in (" ".join(parts), " ".join(gives)) if p)
