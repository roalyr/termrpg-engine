"""
The build: the fitting board, storage, and using items.

Frames, modules and implants can be fitted or removed only within reach of a
workshop that offers 'refit'. A fit needs a free slot, the item's fit_requires, power
and mass within what the loadout provides, a constant heat load below maximum heat
and, for a frame, a size that fits the current location. Removed items go to the
inventory, which must still fit in cargo afterwards. A frame comes off only after its
modules.

Objects with 'storage' hold items for anyone within reach; store and take move whole stacks. Items with interactions
can be used from the pack; a consumable spends one per use.

When the loadout changes a pool's maximum, the current value moves with it (never
below 1 when it drops), so putting on a suit adds its health and heat capacity.
"""
from typing import List, Mapping, NamedTuple, Optional, Tuple

from engine import conditions, stats, turns, world
from engine.content import Content
from engine.effects import run
from engine.frozen import Record, freeze
from engine.state import CharState, Ctx, GameState, ItemInst, Message, add_items, is_plain
from engine.stats import Slot

ITEM_KEYS = {"use": None, "fit": "f", "remove": "r", "store": "o", "take": "k",
             "dismantle": "v", "repair": "e", "fabricate": "b"}
SPARE_ITEM_KEYS = "uhjlmnyz"


class ItemOption(NamedTuple):
    """
    One option for an item. 'label' is the content's own label (an item interaction);
    when it's None the UI words the option from its 'kind' and 'params'.
    """
    key: str
    label: Optional[str]
    available: bool
    hint: Optional[str]
    kind: str        # 'use', 'fit', 'remove', 'store', 'take', 'dismantle', 'repair', 'fabricate', 'modify'
    interaction: Optional[Record] = None
    modification: Optional[str] = None
    params: Mapping[str, str] = freeze({})


# --- Where the player is ---------------------------------------------------------------

def _in_reach(content: Content, state: GameState) -> List[Record]:
    """Placements on the player's tile or next to it."""
    player = state.characters[state.player]
    found = []
    for placed in content.all("placement").values():
        if placed["location"] != player.location:
            continue
        if abs(placed["at"][0] - player.at[0]) + abs(placed["at"][1] - player.at[1]) <= 1:
            found.append(placed)
    return found


def refit_here(content: Content, state: GameState) -> bool:
    return any("refit" in (p.get("workshop") or {}).get("services", ()) for p in _in_reach(content, state))


def storage_here(content: Content, state: GameState) -> Optional[str]:
    """The placement id of a storage object within reach, if any."""
    for placed in _in_reach(content, state):
        if placed.get("storage"):
            return placed["id"]
    return None


def stored(state: GameState, placement_id: str) -> Tuple[ItemInst, ...]:
    return state.storage.get(placement_id, ())


# --- Helpers ---------------------------------------------------------------------------

def _set(state: GameState, cs: CharState) -> GameState:
    chars = dict(state.characters)
    chars[cs.id] = cs
    return state._replace(characters=freeze(chars))


def _say(state: GameState, kind: str, text: str) -> GameState:
    return state._replace(messages=state.messages + (Message(kind, text),))


def _name(content: Content, inst: ItemInst) -> str:
    return stats.item_view(content, inst)["name"]


def _carry_pools(content: Content, before: CharState, after: CharState) -> CharState:
    """Pools follow a change in their maximum; the heat pool also follows the constant load."""
    heat = content.stat_roles.get("heat")
    pools = dict(after.pools)
    for stat_id, value in before.pools.items():
        if stat_id == heat:
            load_change = stats.budget_used(content, after, "heat") - stats.budget_used(content, before, "heat")
            value = value + load_change
        else:
            value = value + stats.stat(content, after, stat_id) - stats.stat(content, before, stat_id)
            value = max(1 if before.pools[stat_id] > 0 else 0, value)
        pools[stat_id] = max(0, min(value, stats.stat(content, after, stat_id)))
    return after._replace(pools=freeze(pools))


def _slot_capacity(content: Content, cs: CharState, kind: str) -> dict:
    if kind == "implant":
        return dict(cs.body_slots)
    capacity: dict = {}
    if cs.frame is not None:
        for slot in content.get("item", cs.frame.item).get("slots", ()):
            capacity[slot["slot_type"]] = capacity.get(slot["slot_type"], 0) + slot["count"]
    return capacity


def _take_out(cs: CharState, slot: Slot) -> Tuple[CharState, ItemInst]:
    """Removes one item (one off a stack) from a slot; returns the character and the item."""
    inst = stats.item_at(cs, slot)
    if slot[0] == "inventory" and inst.count > 1:
        return stats.with_item(cs, slot, inst._replace(count=inst.count - 1)), inst._replace(count=1)
    return stats.with_item(cs, slot, None), inst


def _put_in(content: Content, items: Tuple[ItemInst, ...], inst: ItemInst) -> Tuple[ItemInst, ...]:
    if is_plain(content, inst):
        return add_items(content, items, inst.item, inst.count)
    return items + (inst,)


# --- Fitting ---------------------------------------------------------------------------

def fit_problem(content: Content, state: GameState, slot: Slot) -> Optional[str]:
    """Why the item at an inventory slot can't be fitted now, or None if it can."""
    if not refit_here(content, state):
        return content.message("refit_needed")
    cs = state.characters[state.player]
    inst = stats.item_at(cs, slot)
    view = stats.item_view(content, inst)
    kind = view["kind"]
    if kind not in ("frame", "module", "implant"):
        return content.message("unavailable")
    if kind == "frame" and cs.frame is not None:
        return content.message("frame_worn")
    if kind == "module" and cs.frame is None:
        return content.message("frame_needed")
    if kind in ("module", "implant"):
        capacity = _slot_capacity(content, cs, kind)
        taken = sum(1 for i in (cs.fitted if kind == "module" else cs.implants)
                    if stats.item_view(content, i)["slot_type"] == view["slot_type"])
        if taken >= capacity.get(view["slot_type"], 0):
            return content.message("no_free_slot", item=view["name"])
    ok, _ = conditions.holds(content, state, Ctx(self_id=cs.id), content.get("item", inst.item).get("fit_requires"))
    if not ok:
        return content.message("cannot_use", item=view["name"])
    after, _ = _fitted(content, cs, slot)
    for budget in ("power", "mass"):
        need, have = stats.budget_used(content, after, budget), stats.budget_provided(content, after, budget)
        if need > have:
            return content.message("over_budget", stat=_role_name(content, budget), need=f"{need:g}", have=f"{have:g}")
    load, top = stats.budget_used(content, after, "heat"), stats.budget_provided(content, after, "heat")
    if load and load >= top:
        return content.message("over_budget", stat=_role_name(content, "heat"), need=f"{load:g}", have=f"{top:g}")
    location = content.get("location", cs.location)
    if kind == "frame" and location.get("holds_size") is not None and view["size"] > location["holds_size"]:
        return content.message("cannot_fit", thing=view["name"], container=location["name"])
    return None


def _role_name(content: Content, role: str) -> str:
    stat_id = content.stat_roles.get(role)
    return content.get("stat", stat_id)["name"] if stat_id else role


def _fitted(content: Content, cs: CharState, slot: Slot) -> Tuple[CharState, ItemInst]:
    cs, inst = _take_out(cs, slot)
    kind = content.get("item", inst.item)["kind"]
    if kind == "frame":
        return cs._replace(frame=inst), inst
    if kind == "module":
        return cs._replace(fitted=cs.fitted + (inst,)), inst
    return cs._replace(implants=cs.implants + (inst,)), inst


def fit(content: Content, state: GameState, slot: Slot) -> GameState:
    state = state._replace(messages=())
    problem = fit_problem(content, state, slot)
    if problem:
        return _say(state, "plain", problem)
    before = state.characters[state.player]
    after, inst = _fitted(content, before, slot)
    state = _set(state, _carry_pools(content, before, after))
    state = _say(state, "plain", content.message("item_fitted", item=_name(content, inst)))
    return turns.advance(content, state, 1)


def remove_problem(content: Content, state: GameState, slot: Slot) -> Optional[str]:
    if not refit_here(content, state):
        return content.message("refit_needed")
    cs = state.characters[state.player]
    if slot[0] == "frame" and cs.fitted:
        return content.message("remove_modules_first")
    after = _removed(content, cs, slot)
    if len(after.inventory) > stats.budget_provided(content, after, "cargo"):
        return content.message("cargo_full", item=_name(content, stats.item_at(cs, slot)))
    return None


def _removed(content: Content, cs: CharState, slot: Slot) -> CharState:
    inst = stats.item_at(cs, slot)
    cs = stats.with_item(cs, slot, None)
    return cs._replace(inventory=_put_in(content, cs.inventory, inst))


def remove(content: Content, state: GameState, slot: Slot) -> GameState:
    state = state._replace(messages=())
    problem = remove_problem(content, state, slot)
    if problem:
        return _say(state, "plain", problem)
    before = state.characters[state.player]
    inst = stats.item_at(before, slot)
    state = _set(state, _carry_pools(content, before, _removed(content, before, slot)))
    state = _say(state, "plain", content.message("item_removed", item=_name(content, inst)))
    return turns.advance(content, state, 1)


# --- Storage ---------------------------------------------------------------------------

def store_problem(content: Content, state: GameState, slot: Slot) -> Optional[str]:
    where = storage_here(content, state)
    if where is None:
        return content.message("unavailable")
    placed = content.get("placement", where)
    inst = stats.item_at(state.characters[state.player], slot)
    view = stats.item_view(content, inst)
    if placed.get("holds_size") is not None and view["size"] > placed["holds_size"]:
        return content.message("cannot_fit", thing=view["name"], container=placed["name"])
    if len(_put_in(content, stored(state, where), inst)) > placed["storage"]:
        return content.message("storage_full", container=placed["name"])
    return None


def store(content: Content, state: GameState, slot: Slot) -> GameState:
    """Puts a whole stack from the inventory into storage within reach."""
    state = state._replace(messages=())
    problem = store_problem(content, state, slot)
    if problem:
        return _say(state, "plain", problem)
    where = storage_here(content, state)
    cs = state.characters[state.player]
    inst = stats.item_at(cs, slot)
    state = _set(state, stats.with_item(cs, slot, None))
    state = state._replace(storage=freeze({**state.storage, where: _put_in(content, stored(state, where), inst)}))
    state = _say(state, "plain", content.message("item_stored", item=_name(content, inst),
                                                 container=content.get("placement", where)["name"]))
    return turns.advance(content, state, 1)


def take(content: Content, state: GameState, index: int) -> GameState:
    """Takes a whole stored stack into the inventory."""
    state = state._replace(messages=())
    where = storage_here(content, state)
    if where is None or not 0 <= index < len(stored(state, where)):
        return state
    items = list(stored(state, where))
    inst = items.pop(index)
    cs = state.characters[state.player]
    inventory = _put_in(content, cs.inventory, inst)
    if len(inventory) > stats.budget_provided(content, cs, "cargo"):
        return _say(state, "plain", content.message("cargo_full", item=_name(content, inst)))
    state = _set(state, cs._replace(inventory=inventory))
    state = state._replace(storage=freeze({**state.storage, where: tuple(items)}))
    state = _say(state, "plain", content.message("item_taken", item=_name(content, inst),
                                                 container=content.get("placement", where)["name"]))
    return turns.advance(content, state, 1)


# --- Using items -------------------------------------------------------------------------

def _usage_key(inst: ItemInst, interaction_id: str) -> str:
    return f"item:{inst.item}:{interaction_id}"


def use(content: Content, state: GameState, slot: Slot, interaction: Record) -> GameState:
    """Runs an item's interaction. A consumable spends one before its effects run."""
    state = state._replace(messages=())
    cs = state.characters[state.player]
    inst = stats.item_at(cs, slot)
    ctx = Ctx(self_id=cs.id, used=(cs.id, slot[0], slot[1]))
    ok, state = conditions.holds(content, state, ctx, interaction.get("requires"))
    if not ok:
        return _say(state, "plain", content.text(interaction["hint"]) if interaction.get("hint")
                    else content.message("unavailable"))
    if content.get("item", inst.item)["kind"] == "consumable":
        cs, _ = _take_out(cs, slot)
        state = _set(state, cs)
        ctx = ctx._replace(used=None)
    state = state._replace(used=freeze({**state.used, _usage_key(inst, interaction["id"]): turns.today(content, state)}))
    state = _say(state, "plain", content.message("item_used", item=_name(content, inst)))
    state = run(content, state, ctx, interaction["effects"])
    return turns.advance(content, state, interaction["time"])


# --- The item menu -------------------------------------------------------------------------

def item_options(content: Content, state: GameState, slot: Slot,
                 bindings: Optional[frozenset] = None) -> Tuple[ItemOption, ...]:
    """
    What the player can do with one of their items, or a stored one (slot ('storage', i)).
    'bindings' are the UI's keys, which interaction keys must avoid.
    """
    reserved = world.reserved_keys(bindings)
    from engine import craft  # craft builds on this module's helpers
    options: List[ItemOption] = []
    if slot[0] == "storage":
        if storage_here(content, state) is not None:
            options.append(ItemOption(ITEM_KEYS["take"], None, True, None, "take"))
        return tuple(options)
    if slot[0] == "design":
        item_id = craft.designs(content, state)[slot[1]]
        problem = craft.fabricate_problem(content, state, item_id)
        return (ItemOption(ITEM_KEYS["fabricate"], None, problem is None, problem, "fabricate"),)
    cs = state.characters[state.player]
    inst = stats.item_at(cs, slot)
    if inst is None:
        return ()
    ctx = Ctx(self_id=cs.id, used=(cs.id, slot[0], slot[1]))
    taken = set(ITEM_KEYS.values()) | set(reserved)
    for interaction in content.get("item", inst.item).get("interactions", ()):
        shown, state = conditions.holds(content, state, ctx, interaction.get("shown_if"))
        if not shown:
            continue
        ok, state = conditions.holds(content, state, ctx, interaction.get("requires"))
        hint = content.text(interaction["hint"]) if not ok and interaction.get("hint") else None
        last = state.used.get(_usage_key(inst, interaction["id"]))
        if ok and last is not None and (interaction["repeat"] == "once" or
                                         (interaction["repeat"] == "daily" and last == turns.today(content, state))):
            ok, hint = False, content.message("already_used")
        wanted = interaction.get("key")
        key = wanted if wanted and wanted not in taken else next(k for k in SPARE_ITEM_KEYS if k not in taken)
        taken.add(key)
        options.append(ItemOption(key, content.text(interaction["label"]), ok, hint, "use", interaction))
    kind = content.get("item", inst.item)["kind"]
    if slot[0] == "inventory" and kind in ("frame", "module", "implant"):
        problem = fit_problem(content, state, slot)
        options.append(ItemOption(ITEM_KEYS["fit"], None, problem is None, problem, "fit"))
    if slot[0] in ("frame", "fitted", "implants"):
        problem = remove_problem(content, state, slot)
        options.append(ItemOption(ITEM_KEYS["remove"], None, problem is None, problem, "remove"))
    if slot[0] == "inventory" and storage_here(content, state) is not None:
        problem = store_problem(content, state, slot)
        options.append(ItemOption(ITEM_KEYS["store"], None, problem is None, problem, "store"))
    item = content.get("item", inst.item)
    if slot[0] == "inventory" and item.get("salvage") and craft.offered(content, state, "dismantle"):
        problem = craft.dismantle_problem(content, state, slot)
        options.append(ItemOption(ITEM_KEYS["dismantle"], None, problem is None, problem, "dismantle"))
    if item.get("repair") and inst.condition is not None and craft.offered(content, state, "repair"):
        problem = craft.repair_problem(content, state, slot)
        options.append(ItemOption(ITEM_KEYS["repair"], None, problem is None, problem, "repair"))
    if craft.offered(content, state, "modify"):
        for mod_id in craft.modifications_for(content, state, slot):
            problem = craft.modify_problem(content, state, slot, mod_id)
            key = next(k for k in SPARE_ITEM_KEYS if k not in taken)
            taken.add(key)
            options.append(ItemOption(key, None, problem is None, problem, "modify", modification=mod_id,
                                      params=freeze({"modification": content.get("modification", mod_id)["name"]})))
    return tuple(options)


def item_act(content: Content, state: GameState, slot: Slot, key: str, bindings: Optional[frozenset] = None) -> GameState:
    option = next((o for o in item_options(content, state, slot, bindings) if o.key == key), None)
    if option is None:
        return state
    if not option.available:
        return _say(state._replace(messages=()), "plain", option.hint or content.message("unavailable"))
    if option.kind == "use":
        return use(content, state, slot, option.interaction)
    if option.kind == "fit":
        return fit(content, state, slot)
    if option.kind == "remove":
        return remove(content, state, slot)
    if option.kind == "store":
        return store(content, state, slot)
    if option.kind in ("dismantle", "repair", "fabricate", "modify"):
        from engine import craft
        if option.kind == "dismantle":
            return craft.dismantle(content, state, slot)
        if option.kind == "repair":
            return craft.repair(content, state, slot)
        if option.kind == "modify":
            return craft.modify(content, state, slot, option.modification)
        return craft.fabricate(content, state, craft.designs(content, state)[slot[1]])
    return take(content, state, slot[1])


def pack_slots(content: Content, state: GameState) -> List[Slot]:
    """The pack panel's numbered list: worn and fitted items, carried items, storage within reach, then
    known designs when a fabricating workshop is within reach."""
    cs = state.characters[state.player]
    slots: List[Slot] = [slot for slot, _ in stats.held(cs)]
    where = storage_here(content, state)
    if where is not None:
        slots += [("storage", i) for i in range(len(stored(state, where)))]
    from engine import craft
    if craft.offered(content, state, "fabricate"):
        slots += [("design", i) for i in range(len(craft.designs(content, state)))]
    return slots
