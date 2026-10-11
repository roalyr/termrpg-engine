"""
A character's loadout, worked out from the pack as it is in memory (saved or not): the
slots of the frame and the body and what fills them, what the loadout provides and uses
of power, mass, heat and cargo, its other stats, and what doesn't fit. The numbers are
the checker's (lib.budgets counts for both), so a loadout this calls fine passes the check.
"""
from typing import Dict, List, NamedTuple, Optional

from lib.budgets import BUDGETS, Problem, Slot, over
from lib.budgets import loadout as count_loadout
from tools.lib.packfiles import PackFiles


class Budget(NamedTuple):
    role: str
    name: str
    short: str
    used: float
    provided: float

    @property
    def over(self) -> bool:
        return over(self.role, self.used, self.provided)


class Sheet(NamedTuple):
    frame: Optional[str]
    slots: List[Slot]
    extra: List[Slot]         # fitted items with no free slot (or of the wrong kind)
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
    fit = count_loadout(char, known, words.roles, skills)
    budgets = []
    for role in BUDGETS:
        stat_id = words.roles.get(role)
        if stat_id is not None:
            stat = words.stats[stat_id]
            budgets.append(Budget(role, stat.get("name", role), stat.get("short", role[:3].upper()),
                                  fit.used[role], fit.provided[role]))
    budget_stats = {words.roles[b.role] for b in budgets}
    others = {s: fit.totals[s] for s in words.stats if s in fit.totals and s not in budget_stats}
    problems = [_words(problem, known, words) for problem in fit.problems]
    return Sheet(fit.frame, fit.slots, fit.extra, budgets, others, problems)


def _words(problem: Problem, known: Dict[str, dict], words: Vocab) -> str:
    """A loadout problem in the editor's words."""
    if problem.what == "no_item" and problem.group == "frame" or problem.what == "not_frame":
        return f"'{problem.item}' isn't a frame."
    if problem.what == "no_frame":
        return "Has fitted modules but wears no frame."
    if problem.what == "no_item":
        return f"No item '{problem.item}'."
    if problem.what == "wrong_kind":
        return f"'{problem.item}' isn't {'a module' if problem.group == 'fitted' else 'an implant'}."
    if problem.what == "no_slot":
        name = known.get(problem.item, {}).get("name", problem.item)
        return f"No free {_slot_name(words, problem.slot_type)} slot in the {problem.host} for {name}."
    if problem.role == "heat":
        return f"Constant heat {problem.used:g} leaves no room below maximum heat {problem.provided:g}."
    if problem.role == "cargo":
        return f"The inventory needs {problem.used:g} cargo stacks; the loadout carries {problem.provided:g}."
    return f"Fitted gear needs {problem.used:g} {problem.role}; the loadout provides {problem.provided:g}."


def _slot_name(words: Vocab, slot_type: str) -> str:
    return words.slot_types.get(slot_type, {}).get("name", slot_type)


def uses_text(item: dict, words: Vocab) -> str:
    """What an item uses and gives, in short: 'PWR 2 MAS 3 · ARM +2'."""
    shorts = {role: words.stats[i].get("short", role) for role, i in words.roles.items()}
    parts = [f"{shorts.get(k, k)} {v:g}" for k, v in (item.get("uses", {}) or {}).items()]
    gives = [f"{words.stats.get(k, {}).get('short', k)} {v:+g}" for k, v in (item.get("stats", {}) or {}).items()]
    return " · ".join(p for p in (" ".join(parts), " ".join(gives)) if p)
