"""
The build: equipping gear, storage, and using items.

Gear goes into a free slot of its type, from the body or from other equipped gear, and
needs its equip_requires, budgets within what the loadout provides, a constant load on
each filling pool below its maximum and, for gear with a worn_size, a size that fits the
current location. Slot types marked equip_at_workshop change only within reach of a
workshop offering 'equip' (for that slot type); the rest change anywhere. Removed gear
goes to the inventory, which must still fit in cargo afterwards. Gear with slots comes
off only after what is in them.

Objects with 'storage' hold items for anyone within reach; store and take move whole stacks. Items with interactions
can be used from the pack; a consumable spends one per use.

When the loadout changes a pool's maximum, the current value moves with it (never
below 1 when it drops), so putting on a suit adds its health; a filling pool moves with
its constant load.
"""
from typing import List, Mapping, NamedTuple, Optional, Tuple, Union

from engine import conditions, stats, turns, world
from engine.content import Content
from engine.effects import run
from engine.frozen import Record, freeze
from engine.state import CharState, Ctx, GameState, ItemInst, Message, add_items, is_plain
from engine.stats import Slot

ITEM_KEYS = {"use": None, "equip": "f", "remove": "r", "store": "o", "take": "k",
             "dismantle": "v", "repair": "e", "make": "b"}
SPARE_ITEM_KEYS = "uhjlnyz"
MODIFY_KEY = "m"          # opens the list of modifications on the gear screen

# Which options each place offers: the pack panel is for carrying, the gear screen for building.
SCOPES = {"pack": {"use", "store", "take"},
          "gear": {"equip", "remove", "dismantle", "repair", "make", "modify"}}


class ItemOption(NamedTuple):
    """
    One option for an item. 'label' is the content's own label (an item interaction);
    when it's None the UI words the option from its 'kind' and 'params'.
    """
    key: str
    label: Optional[str]
    available: bool
    hint: Optional[str]
    kind: str        # 'use', 'equip', 'remove', 'store', 'take', 'dismantle', 'repair', 'make', 'modify'
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


def equip_here(content: Content, state: GameState, slot_type: Optional[str] = None) -> bool:
    """Whether a workshop within reach offers 'equip' (for this slot type, when given)."""
    for placed in _in_reach(content, state):
        shop = placed.get("workshop") or {}
        if "equip" in shop.get("services", ()) and (
                slot_type is None or not shop.get("equip_slot_types") or slot_type in shop["equip_slot_types"]):
            return True
    return False


def gate(content: Content, state: GameState, slot_type: Optional[str]) -> Optional[str]:
    """Why gear in this slot type can't change here, or None: some slot types need a workshop."""
    record = content.all("slot_type").get(slot_type or "", {})
    if record.get("equip_at_workshop") and not equip_here(content, state, slot_type):
        return content.message("workshop_needed")
    return None


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
    """Pools follow a change in their maximum; a filling pool also follows its constant load."""
    pools = dict(after.pools)
    for stat_id, value in before.pools.items():
        if stats.fills(content, stat_id):
            value = value + stats.budget_used(content, after, stat_id) - stats.budget_used(content, before, stat_id)
        else:
            value = value + stats.stat(content, after, stat_id) - stats.stat(content, before, stat_id)
            value = max(1 if before.pools[stat_id] > 0 else 0, value)
        pools[stat_id] = max(0, min(value, stats.stat(content, after, stat_id)))
    return after._replace(pools=freeze(pools))


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


# --- Equipping -------------------------------------------------------------------------

def fit_problem(content: Content, state: GameState, slot: Slot) -> Optional[str]:
    """Why the item at an inventory slot can't be equipped now, or None if it can."""
    cs = state.characters[state.player]
    inst = stats.item_at(cs, slot)
    view = stats.item_view(content, inst)
    if view["kind"] != "gear":
        return content.message("unavailable")
    problem = gate(content, state, view["slot_type"])
    if problem:
        return problem
    after, _ = _fitted(content, cs, slot)
    if stats.slots(content, after)[1]:
        return content.message("no_free_slot", item=view["name"])
    ok, _ = conditions.holds(content, state, Ctx(self_id=cs.id), content.get("item", inst.item).get("equip_requires"))
    if not ok:
        return content.message("cannot_use", item=view["name"])
    problem = budget_problem(content, after)
    if problem:
        return problem
    location = content.get("location", cs.location)
    if location.get("holds_size") is not None and stats.size(content, after) > location["holds_size"]:
        return content.message("cannot_fit", thing=view["name"], container=location["name"])
    return None


def budget_problem(content: Content, cs: CharState) -> Optional[str]:
    """Why a loadout doesn't work: a budget used above what it provides, or a filling pool's load at its maximum."""
    cargo = content.stat_roles.get("cargo")
    for stat_id in stats.budget_stats(content):
        if stat_id == cargo:
            continue
        need, have = stats.budget_used(content, cs, stat_id), stats.budget_provided(content, cs, stat_id)
        if stats.over(content, stat_id, need, have):
            return content.message("over_budget", stat=content.get("stat", stat_id)["name"],
                                   need=f"{need:g}", have=f"{have:g}")
    return None


def _fitted(content: Content, cs: CharState, slot: Slot) -> Tuple[CharState, ItemInst]:
    cs, inst = _take_out(cs, slot)
    return cs._replace(equipped=cs.equipped + (inst,)), inst


def fit(content: Content, state: GameState, slot: Slot) -> GameState:
    state = state._replace(messages=())
    problem = fit_problem(content, state, slot)
    if problem:
        return _say(state, "plain", problem)
    before = state.characters[state.player]
    after, inst = _fitted(content, before, slot)
    state = _set(state, _carry_pools(content, before, after))
    state = _say(state, "plain", content.message("item_equipped", item=_name(content, inst)))
    return turns.advance(content, state, 1)


def remove_problem(content: Content, state: GameState, slot: Slot) -> Optional[str]:
    cs = state.characters[state.player]
    inst = stats.item_at(cs, slot)
    problem = gate(content, state, stats.item_view(content, inst)["slot_type"])
    if problem:
        return problem
    after = _removed(content, cs, slot)
    if stats.slots(content, after)[1]:
        return content.message("empty_slots_first", item=_name(content, inst))
    if len(after.inventory) > stats.cargo_capacity(content, after):
        return content.message("cargo_full", item=_name(content, inst))
    return budget_problem(content, after)     # what it provided may be what the rest needs


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
    if len(inventory) > stats.cargo_capacity(content, cs):
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
                 bindings: Optional[frozenset] = None, scope: str = "all") -> Tuple[ItemOption, ...]:
    """
    What the player can do with one of their items, or a stored one (slot ('storage', i)).
    'bindings' are the UI's keys, which interaction keys must avoid. 'scope' keeps the
    options of one place: 'pack' (use, store, take) or 'gear' (equip, remove and the
    workshop's services; these are listed even away from a workshop, greyed out with
    why, so the gear screen can be used for planning).
    """
    options = _item_options(content, state, slot, bindings, scope == "gear")
    if scope in SCOPES:
        options = tuple(o for o in options if o.kind in SCOPES[scope])
    return options


def _item_options(content: Content, state: GameState, slot: Slot, bindings: Optional[frozenset],
                  planning: bool) -> Tuple[ItemOption, ...]:
    reserved = world.reserved_keys(bindings)
    from engine import craft  # craft builds on this module's helpers
    options: List[ItemOption] = []
    if slot[0] == "storage":
        where = storage_here(content, state)
        if where is not None:
            options.append(ItemOption(ITEM_KEYS["take"], None, True, None, "take"))
            if slot[1] < len(stored(state, where)) and content.get("item", stored(state, where)[slot[1]].item)["kind"] == "gear":
                problem = stored_fit_problem(content, state, slot[1])
                options.append(ItemOption(ITEM_KEYS["equip"], None, problem is None, problem, "equip"))
        return tuple(options)
    if slot[0] == "design":
        item_id = craft.designs(content, state)[slot[1]]
        problem = craft.make_problem(content, state, item_id)
        return (ItemOption(ITEM_KEYS["make"], None, problem is None, problem, "make"),)
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
    if slot[0] == "inventory" and kind == "gear":
        problem = fit_problem(content, state, slot)
        options.append(ItemOption(ITEM_KEYS["equip"], None, problem is None, problem, "equip"))
    if slot[0] == "equipped":
        problem = remove_problem(content, state, slot)
        options.append(ItemOption(ITEM_KEYS["remove"], None, problem is None, problem, "remove"))
    if slot[0] == "inventory" and storage_here(content, state) is not None:
        problem = store_problem(content, state, slot)
        options.append(ItemOption(ITEM_KEYS["store"], None, problem is None, problem, "store"))
    item = content.get("item", inst.item)
    if slot[0] == "inventory" and item.get("dismantle") and (planning or craft.offered(content, state, "dismantle")):
        problem = craft.dismantle_problem(content, state, slot)
        options.append(ItemOption(ITEM_KEYS["dismantle"], None, problem is None, problem, "dismantle"))
    if item.get("repair") and inst.condition is not None and (planning or craft.offered(content, state, "repair")):
        problem = craft.repair_problem(content, state, slot)
        options.append(ItemOption(ITEM_KEYS["repair"], None, problem is None, problem, "repair"))
    if planning or craft.offered(content, state, "modify"):
        for mod_id in craft.modifications_for(content, state, slot):
            problem = craft.modify_problem(content, state, slot, mod_id)
            key = next(k for k in SPARE_ITEM_KEYS if k not in taken)
            taken.add(key)
            options.append(ItemOption(key, None, problem is None, problem, "modify", modification=mod_id,
                                      params=freeze({"modification": content.get("modification", mod_id)["name"]})))
    return tuple(options)


def item_act(content: Content, state: GameState, slot: Slot, key: str, bindings: Optional[frozenset] = None,
             scope: str = "all") -> GameState:
    option = next((o for o in item_options(content, state, slot, bindings, scope) if o.key == key), None)
    if option is None:
        return state
    if not option.available:
        return _say(state._replace(messages=()), "plain", option.hint or content.message("unavailable"))
    if option.kind == "use":
        return use(content, state, slot, option.interaction)
    if option.kind == "equip":
        return fit_stored(content, state, slot[1]) if slot[0] == "storage" else fit(content, state, slot)
    if option.kind == "remove":
        return remove(content, state, slot)
    if option.kind == "store":
        return store(content, state, slot)
    if option.kind in ("dismantle", "repair", "make", "modify"):
        from engine import craft
        if option.kind == "dismantle":
            return craft.dismantle(content, state, slot)
        if option.kind == "repair":
            return craft.repair(content, state, slot)
        if option.kind == "modify":
            return craft.modify(content, state, slot, option.modification)
        return craft.make(content, state, craft.designs(content, state)[slot[1]])
    return take(content, state, slot[1])


def entry_at(content: Content, state: GameState, slot: Slot) -> Union[ItemInst, str, None]:
    """What a pack slot holds: an item, a design's item id, or None when the slot is gone."""
    from engine import craft
    if slot[0] == "design":
        known = craft.designs(content, state)
        return known[slot[1]] if slot[1] < len(known) else None
    if slot[0] == "storage":
        where = storage_here(content, state)
        items = stored(state, where) if where is not None else ()
        return items[slot[1]] if slot[1] < len(items) else None
    return stats.item_at(state.characters[state.player], slot)


MOVES = {"equip": ("equipped",), "remove": ("inventory",), "store": ("storage",), "take": ("inventory",)}


def follow(content: Content, before: GameState, after: GameState, slot: Slot, kind: Optional[str]) -> Optional[int]:
    """
    Where the pack entry at 'slot' went after an action of this kind, as its new index in
    pack_slots(), or None when it's gone. Equipping, removing, storing and taking move it to
    another group, where it's found by value; anything else leaves it in place (repaired,
    modified, one used from a stack) as long as the slot still holds the same item.
    """
    old = entry_at(content, before, slot)
    if old is None:
        return None
    slots = pack_slots(content, after)
    if kind in MOVES:
        return next((i for i, s in enumerate(slots) if s[0] in MOVES[kind] and entry_at(content, after, s) == old), None)
    if slot in slots:
        now = entry_at(content, after, slot)
        if now is not None and _entry_item(now) == _entry_item(old):
            return slots.index(slot)
    return None


def _entry_item(entry: Union[ItemInst, str]) -> str:
    return entry if isinstance(entry, str) else entry.item


def pack_slots(content: Content, state: GameState) -> List[Slot]:
    """The pack panel's numbered list: carried items, then storage within reach."""
    cs = state.characters[state.player]
    slots: List[Slot] = [("inventory", i) for i in range(len(cs.inventory))]
    where = storage_here(content, state)
    if where is not None:
        slots += [("storage", i) for i in range(len(stored(state, where)))]
    return slots


# --- The gear screen -------------------------------------------------------------------

class FitRow(NamedTuple):
    """
    One line of the gear screen's list. 'slot' is None for an empty slot; 'slot_type'
    names the slot equipped gear sits in; 'host' is the equipped index of the gear that
    adds the slot (-1 for the body); 'where' is a stored item's placement id.
    """
    group: str                       # 'worn', 'spare' or 'designs'
    slot: Optional[Slot]
    slot_type: Optional[str] = None
    where: Optional[str] = None
    host: int = -1


def gear_rows(content: Content, state: GameState) -> List[FitRow]:
    """
    The loadout by slot (the body's slots, then each piece of gear's, empty ones included),
    then spare gear carried or stored within reach, then known designs.
    """
    from engine import craft
    cs = state.characters[state.player]
    placed, unplaced = stats.slots(content, cs)
    rows: List[FitRow] = [FitRow("worn", ("equipped", s.index) if s.item is not None else None, s.slot_type, host=s.host)
                          for s in placed]
    rows += [FitRow("worn", ("equipped", i), stats.item_view(content, cs.equipped[i])["slot_type"]) for i in unplaced]
    rows += [FitRow("spare", ("inventory", i)) for i, inst in enumerate(cs.inventory) if _is_gear(content, inst)]
    where = storage_here(content, state)
    if where is not None:
        rows += [FitRow("spare", ("storage", i), where=where) for i, inst in enumerate(stored(state, where))
                 if _is_gear(content, inst)]
    rows += [FitRow("designs", ("design", i)) for i in range(len(craft.designs(content, state)))]
    return rows


def _is_gear(content: Content, inst: ItemInst) -> bool:
    """Items the gear screen deals with: gear, and what can be taken apart."""
    item = content.get("item", inst.item)
    return item["kind"] == "gear" or bool(item.get("dismantle"))


def workshop_here(content: Content, state: GameState) -> Optional[str]:
    """The placement id of a workshop within reach (one offering equip first), if any."""
    shops = [p for p in _in_reach(content, state) if p.get("workshop")]
    shops.sort(key=lambda p: "equip" not in p["workshop"]["services"])
    return shops[0]["id"] if shops else None


def stored_fit_problem(content: Content, state: GameState, index: int) -> Optional[str]:
    """Why a stored item can't be equipped straight from storage, or None."""
    trial = _taken_for_fitting(content, state, index)
    if trial is None:
        return content.message("unavailable")
    return fit_problem(content, trial, ("inventory", len(trial.characters[trial.player].inventory) - 1))


def _taken_for_fitting(content: Content, state: GameState, index: int) -> Optional[GameState]:
    """The state with a stored item moved to the end of the inventory (cargo isn't checked: it's equipped at once)."""
    where = storage_here(content, state)
    if where is None or not 0 <= index < len(stored(state, where)):
        return None
    items = list(stored(state, where))
    inst = items.pop(index)
    cs = state.characters[state.player]
    state = _set(state, cs._replace(inventory=cs.inventory + (inst,)))
    return state._replace(storage=freeze({**state.storage, where: tuple(items)}))


def fit_stored(content: Content, state: GameState, index: int) -> GameState:
    """Equips a stored item straight from storage within reach."""
    problem = stored_fit_problem(content, state, index)
    if problem:
        return _say(state._replace(messages=()), "plain", problem)
    trial = _taken_for_fitting(content, state, index)
    return fit(content, trial, ("inventory", len(trial.characters[trial.player].inventory) - 1))


def preview(content: Content, state: GameState, slot: Slot, kind: str,
            modification: Optional[str] = None) -> Optional[CharState]:
    """The player as they'd be after equipping, removing or modifying, without doing it; None for other actions."""
    from engine import craft
    cs = state.characters[state.player]
    if kind == "equip" and slot[0] == "storage":
        trial = _taken_for_fitting(content, state, slot[1])
        if trial is None:
            return None
        tcs = trial.characters[trial.player]
        return _fitted(content, tcs, ("inventory", len(tcs.inventory) - 1))[0]
    if kind == "equip" and slot[0] == "inventory":
        return _fitted(content, cs, slot)[0]
    if kind == "remove":
        return _removed(content, cs, slot)
    if kind == "modify" and modification:
        return craft._modified(content, cs, slot, modification)
    return None
