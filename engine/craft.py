"""
Crafting at workshops: dismantle, make, modify and repair.

Each needs a workshop within reach that offers the service and whose max_grade (if
any) is at least the item's grade. Results are predictable: no rolls.

- Dismantle destroys one carried item, gives its dismantle yields, and teaches its
  design when dismantle.learn is on and learn_requires holds.
- Make makes one copy of a known design from make.inputs.
- Modify applies a modification to a held item: the item must match applies_to,
  have a free mod slot, not already carry it when 'once', the crafter must meet
  'requires' and carry the material. Equipped gear must still fit the loadout after.
- Repair restores condition from repair.inputs, by 'amount' or fully.

What comes out must fit in cargo, or the action is refused: nothing is lost.
"""
from typing import List, Optional, Sequence, Tuple

from engine import build, conditions, stats, turns
from engine.content import Content
from engine.frozen import Record, freeze
from engine.state import CharState, Ctx, GameState, ItemInst, Message, add_items
from engine.stats import Slot


# --- Workshops -------------------------------------------------------------------------

def _grade_order(content: Content, grade: Optional[str]) -> int:
    if grade is None:
        return -10 ** 6                       # ungraded items count as the lowest grade
    return content.get("grade", grade).get("order", 0)


def _in_reach(content: Content, state: GameState) -> List[Record]:
    player = state.characters[state.player]
    return [p for p in content.all("placement").values()
            if p["location"] == player.location and p.get("workshop")
            and abs(p["at"][0] - player.at[0]) + abs(p["at"][1] - player.at[1]) <= 1]


def offered(content: Content, state: GameState, service: str) -> bool:
    """A workshop within reach offers the service."""
    return any(service in p["workshop"]["services"] for p in _in_reach(content, state))


def service_problem(content: Content, state: GameState, service: str, item_id: str) -> Optional[str]:
    """Why no workshop within reach can do this service on this item, or None."""
    shops = [p for p in _in_reach(content, state) if service in p["workshop"]["services"]]
    if not shops:
        return content.message("needs_service")
    grade = _grade_order(content, content.get("item", item_id).get("grade"))
    if all(p["workshop"].get("max_grade") and grade > _grade_order(content, p["workshop"]["max_grade"])
           for p in shops):
        return content.message("too_advanced", item=content.get("item", item_id)["name"])
    return None


# --- Helpers ---------------------------------------------------------------------------

def _set(state: GameState, cs: CharState) -> GameState:
    chars = dict(state.characters)
    chars[cs.id] = cs
    return state._replace(characters=freeze(chars))


def _say(state: GameState, kind: str, text: str) -> GameState:
    return state._replace(messages=state.messages + (Message(kind, text),))


def _count(content: Content, cs: CharState, item_id: str) -> int:
    return sum(i.count for i in cs.inventory if i.item == item_id and not i.mods and not i.changes)


def _missing(content: Content, cs: CharState, parts: Sequence[Record]) -> Optional[str]:
    """The names of parts not carried in full, or None when everything is there."""
    lacking = [f"{content.get('item', p['item'])['name']} x{p['count']}" for p in parts
               if _count(content, cs, p["item"]) < p["count"]]
    return ", ".join(lacking) if lacking else None


def _take(content: Content, cs: CharState, item_id: str, count: int) -> CharState:
    """Removes plain (unmodified) items from the inventory."""
    inventory, left = [], count
    for inst in cs.inventory:
        if left and inst.item == item_id and not inst.mods and not inst.changes:
            used = min(left, inst.count)
            left -= used
            if inst.count > used:
                inventory.append(inst._replace(count=inst.count - used))
        else:
            inventory.append(inst)
    return cs._replace(inventory=tuple(inventory))


def _give(content: Content, cs: CharState, parts: Sequence[Tuple[str, int]]) -> Optional[CharState]:
    """The character with the items added, or None if they don't fit in cargo."""
    inventory = cs.inventory
    for item_id, count in parts:
        inventory = add_items(content, inventory, item_id, count)
    if len(inventory) > stats.cargo_capacity(content, cs):
        return None
    return cs._replace(inventory=inventory)


def _one_off(cs: CharState, slot: Slot) -> Tuple[CharState, ItemInst]:
    """Takes one item from a slot (one off a stack)."""
    inst = stats.item_at(cs, slot)
    if slot[0] == "inventory" and inst.count > 1:
        return stats.with_item(cs, slot, inst._replace(count=inst.count - 1)), inst._replace(count=1)
    return stats.with_item(cs, slot, None), inst


# --- Dismantle -------------------------------------------------------------------------

def dismantle_problem(content: Content, state: GameState, slot: Slot) -> Optional[str]:
    cs = state.characters[state.player]
    inst = stats.item_at(cs, slot)
    if slot[0] != "inventory" or not content.get("item", inst.item).get("dismantle"):
        return content.message("unavailable")
    problem = service_problem(content, state, "dismantle", inst.item)
    if problem:
        return problem
    rest, _ = _one_off(cs, slot)
    yields = [(y["item"], y["count"]) for y in content.get("item", inst.item)["dismantle"]["yields"]]
    if _give(content, rest, yields) is None:
        return content.message("cargo_full", item=content.get("item", yields[0][0])["name"])
    return None


def dismantle(content: Content, state: GameState, slot: Slot) -> GameState:
    state = state._replace(messages=())
    problem = dismantle_problem(content, state, slot)
    if problem:
        return _say(state, "plain", problem)
    cs, inst = _one_off(state.characters[state.player], slot)
    item = content.get("item", inst.item)
    parts = item["dismantle"]
    cs = _give(content, cs, [(y["item"], y["count"]) for y in parts["yields"]])
    state = _set(state, cs)
    names = ", ".join(f"{content.get('item', y['item'])['name']} x{y['count']}" for y in parts["yields"])
    state = _say(state, "gain", content.message("item_dismantled", item=item["name"], items=names))
    if parts.get("learn", True) and inst.item not in cs.designs:
        ok, state = conditions.holds(content, state, Ctx(self_id=cs.id), parts.get("learn_requires"))
        if ok:
            cs = state.characters[cs.id]
            state = _set(state, cs._replace(designs=cs.designs + (inst.item,)))
            state = _say(state, "gain", content.message("design_learned", item=item["name"]))
        else:
            state = _say(state, "plain", content.message("design_not_learned", item=item["name"]))
    return turns.advance(content, state, 1)


# --- Fabricate -------------------------------------------------------------------------

def designs(content: Content, state: GameState) -> List[str]:
    """Known designs that can be made at all (they have make data)."""
    cs = state.characters[state.player]
    return [d for d in cs.designs if content.get("item", d).get("make")]


def make_problem(content: Content, state: GameState, item_id: str) -> Optional[str]:
    cs = state.characters[state.player]
    item = content.get("item", item_id)
    if item_id not in cs.designs or not item.get("make"):
        return content.message("unavailable")
    problem = service_problem(content, state, "make", item_id)
    if problem:
        return problem
    ok, _ = conditions.holds(content, state, Ctx(self_id=cs.id), item["make"].get("requires"))
    if not ok:
        return content.message("cannot_use", item=item["name"])
    lacking = _missing(content, cs, item["make"]["inputs"])
    if lacking:
        return content.message("needs_materials", items=lacking)
    rest = cs
    for part in item["make"]["inputs"]:
        rest = _take(content, rest, part["item"], part["count"])
    if _give(content, rest, [(item_id, 1)]) is None:
        return content.message("cargo_full", item=item["name"])
    return None


def make(content: Content, state: GameState, item_id: str) -> GameState:
    state = state._replace(messages=())
    problem = make_problem(content, state, item_id)
    if problem:
        return _say(state, "plain", problem)
    item = content.get("item", item_id)
    cs = state.characters[state.player]
    for part in item["make"]["inputs"]:
        cs = _take(content, cs, part["item"], part["count"])
    state = _set(state, _give(content, cs, [(item_id, 1)]))
    state = _say(state, "gain", content.message("item_made", item=item["name"]))
    return turns.advance(content, state, item["make"]["time"])


# --- Modify ----------------------------------------------------------------------------

def modifications_for(content: Content, state: GameState, slot: Slot) -> List[str]:
    """Modifications whose applies_to matches the item at a slot."""
    inst = stats.item_at(state.characters[state.player], slot)
    view = stats.item_view(content, inst)
    found = []
    for mod_id, mod in content.all("modification").items():
        rule = mod["applies_to"]
        if view["kind"] != "gear":
            continue
        if rule.get("tags") and not set(rule["tags"]) & set(view["tags"]):
            continue
        if rule.get("slot_types") and view["slot_type"] not in rule["slot_types"]:
            continue
        found.append(mod_id)
    return found


def modify_problem(content: Content, state: GameState, slot: Slot, mod_id: str) -> Optional[str]:
    cs = state.characters[state.player]
    inst = stats.item_at(cs, slot)
    mod = content.get("modification", mod_id)
    item = content.get("item", inst.item)
    problem = service_problem(content, state, "modify", inst.item)
    if problem:
        return problem
    if mod.get("once", True) and mod_id in inst.mods:
        return content.message("already_modified", item=stats.item_view(content, inst)["name"], modification=mod["name"])
    if len(inst.mods) >= item.get("mod_slots", 0):
        return content.message("no_mod_slot", item=stats.item_view(content, inst)["name"])
    ok, _ = conditions.holds(content, state, Ctx(self_id=cs.id), mod.get("requires"))
    if not ok:
        return content.message("cannot_use", item=mod["name"])
    lacking = _missing(content, cs, [{"item": mod["material"], "count": mod["count"]}])
    if lacking:
        return content.message("needs_materials", items=lacking)
    if slot[0] == "inventory" and inst.count > 1:       # one off the stack needs a cargo stack of its own
        stacks = len(_take(content, cs, mod["material"], mod["count"]).inventory) + 1
        if stacks > stats.cargo_capacity(content, cs):
            return content.message("cargo_full", item=stats.item_view(content, inst)["name"])
    if slot[0] == "equipped":
        problem = build.budget_problem(content, _modified(content, cs, slot, mod_id))
        if problem:
            return problem
    return None


def _modified(content: Content, cs: CharState, slot: Slot, mod_id: str) -> CharState:
    mod = content.get("modification", mod_id)
    cs = _take(content, cs, mod["material"], mod["count"]) if slot[0] != "inventory" else cs
    inst = stats.item_at(cs, slot)
    changed = ItemInst(item=inst.item, count=1, condition=inst.condition, mods=inst.mods + (mod_id,),
                       changes=inst.changes)
    if mod["adds"].get("max_condition") and changed.condition is not None:
        changed = changed._replace(condition=changed.condition + mod["adds"]["max_condition"])
    if slot[0] == "inventory" and inst.count > 1:
        cs = stats.with_item(cs, slot, inst._replace(count=inst.count - 1))
        return cs._replace(inventory=cs.inventory + (changed,))
    return stats.with_item(cs, slot, changed)


def modify(content: Content, state: GameState, slot: Slot, mod_id: str) -> GameState:
    state = state._replace(messages=())
    problem = modify_problem(content, state, slot, mod_id)
    if problem:
        return _say(state, "plain", problem)
    cs = state.characters[state.player]
    before_name = stats.item_view(content, stats.item_at(cs, slot))["name"]
    mod = content.get("modification", mod_id)
    if slot[0] == "inventory":
        # take the material first, then find the item again: taking may have moved it
        inst = stats.item_at(cs, slot)
        cs = _take(content, cs, mod["material"], mod["count"])
        index = next(i for i, other in enumerate(cs.inventory) if other.item == inst.item
                     and other.mods == inst.mods and other.changes == inst.changes and other.condition == inst.condition)
        cs = _modified(content, cs, ("inventory", index), mod_id)
    else:
        cs = _modified(content, cs, slot, mod_id)
    state = _set(state, stats.clamp_pools(content, cs))
    state = _say(state, "gain", content.message("item_modified", item=before_name, modification=mod["name"]))
    return turns.advance(content, state, 1)


# --- Repair ----------------------------------------------------------------------------

def repair_problem(content: Content, state: GameState, slot: Slot) -> Optional[str]:
    cs = state.characters[state.player]
    inst = stats.item_at(cs, slot)
    item = content.get("item", inst.item)
    if not item.get("repair") or inst.condition is None:
        return content.message("unavailable")
    problem = service_problem(content, state, "repair", inst.item)
    if problem:
        return problem
    if inst.condition >= stats.item_view(content, inst)["max_condition"]:
        return content.message("not_damaged", item=stats.item_view(content, inst)["name"])
    lacking = _missing(content, cs, item["repair"]["inputs"])
    if lacking:
        return content.message("needs_materials", items=lacking)
    return None


def repair(content: Content, state: GameState, slot: Slot) -> GameState:
    state = state._replace(messages=())
    problem = repair_problem(content, state, slot)
    if problem:
        return _say(state, "plain", problem)
    cs = state.characters[state.player]
    inst = stats.item_at(cs, slot)
    item = content.get("item", inst.item)
    top = stats.item_view(content, inst)["max_condition"]
    amount = item["repair"].get("amount")
    fixed = inst._replace(condition=top if amount is None else min(top, inst.condition + amount))
    cs = stats.with_item(cs, slot, fixed)
    for part in item["repair"]["inputs"]:
        cs = _take(content, cs, part["item"], part["count"])
    state = _set(state, stats.clamp_pools(content, cs))
    state = _say(state, "gain", content.message("item_repaired", item=stats.item_view(content, fixed)["name"]))
    return turns.advance(content, state, 1)
