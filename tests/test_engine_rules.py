"""
Milestone 1: every check and every effect outside encounters, against the test pack.
"""
import unittest
from pathlib import Path

from core import schema
from engine import effects, stats, turns
from engine.conditions import CHECKS, evaluate
from engine.content import load_pack
from engine.effects import HANDLERS, choose_option, run
from engine.frozen import freeze
from engine.state import Ctx, ItemInst, StatusInst, new_game, phase_of, day_of

ROOT = Path(__file__).resolve().parent.parent
CONTENT = load_pack(ROOT / "packs" / "test")
SCHEMAS = schema.load_schemas(ROOT / "schemas")


def as_loaded(value, definition):
    """Test-written data with schema defaults filled in, as if it came from a pack."""
    return freeze(schema.apply_defaults(value, f"common.schema.json#/$defs/{definition}", SCHEMAS))
PLAYER, NPC = "char_player", "char_juno"


def fresh(seed=1):
    return new_game(CONTENT, seed)


def me(state):
    return Ctx(self_id=state.player)


def check(state, cond, ctx=None):
    return evaluate(CONTENT, state, ctx or me(state), as_loaded(cond, "condition"))[0]


def do(state, *effect_list, ctx=None):
    return run(CONTENT, state, ctx or me(state), [as_loaded(e, "effect") for e in effect_list])


def char(state, cid=PLAYER):
    return state.characters[cid]


def health(state, cid=PLAYER):
    return stats.current(CONTENT, char(state, cid), "stat_health")


def texts(state):
    return [m.text for m in state.messages]


class TestNewGame(unittest.TestCase):
    def test_start(self):
        s = fresh()
        p = char(s)
        self.assertEqual(s.player, PLAYER)
        self.assertEqual(p.location, "loc_workshop")
        self.assertEqual(p.at, (2, 4))                      # next to the start entry, a solid crate
        self.assertEqual(p.visited, ("loc_workshop",))
        self.assertEqual(s.turn, 0)
        self.assertEqual(phase_of(CONTENT, s.turn), "phase_day")
        self.assertNotIn("char_drone", s.characters)        # templates aren't in play

    def test_loadout_and_pools(self):
        p = char(fresh())
        self.assertEqual(p.frame.item, "frame_light")
        self.assertEqual([i.item for i in p.fitted], ["module_cutter", "module_shield"])
        self.assertEqual(p.fitted[0].condition, 4)
        self.assertEqual(p.pools["stat_health"], 30)        # body 10 + frame 20
        self.assertEqual(p.pools["stat_heat"], 2)           # starts at the constant heat load
        self.assertEqual(stats.budget_used(CONTENT, p, "power"), 4)
        self.assertEqual(stats.budget_provided(CONTENT, p, "power"), 6)
        self.assertEqual(stats.stat(CONTENT, p, "stat_armor"), 2)
        self.assertEqual(stats.cargo_free(CONTENT, p), 2)   # cargo 2 + 4, four stacks carried

    def test_world_state(self):
        s = fresh()
        self.assertEqual(s.object_states["workshop_door"], "state_closed")
        self.assertEqual(s.object_states["storage_door"], "state_open")
        self.assertEqual(s.flags["flag_power"], 0)
        self.assertEqual(s.relations["character:char_juno"]["character:char_player"], 10)
        self.assertEqual(char(s, NPC).at, (3, 3))

    def test_every_check_and_effect_is_implemented(self):
        common = SCHEMAS["common.schema.json"]["$defs"]
        checks = {k[6:] for k in common if k.startswith("check_")}
        ops = {k[3:] for k in common if k.startswith("op_")}
        self.assertEqual(set(CHECKS), checks)
        self.assertEqual(set(HANDLERS) | {"choose"}, ops)


class TestChecks(unittest.TestCase):
    def test_combinators(self):
        s = fresh()
        yes, no = {"check": "flag", "flag": "flag_power", "max": 0}, {"check": "flag", "flag": "flag_power", "min": 1}
        self.assertTrue(check(s, {"all": [yes, {"not": no}]}))
        self.assertFalse(check(s, {"all": [yes, no]}))
        self.assertTrue(check(s, {"any": [no, yes]}))

    def test_has_tag_sources(self):
        s = do(fresh(), {"op": "take_item", "item": "misc_keycard"})   # leave only the fitted tool with tool
        self.assertTrue(check(s, {"check": "has_tag", "tag": "tag_tool"}))
        self.assertTrue(check(s, {"check": "has_tag", "tag": "tag_tool", "source": "fitted"}))
        self.assertFalse(check(s, {"check": "has_tag", "tag": "tag_tool", "source": "carried"}))
        s = do(s, {"op": "give_item", "item": "misc_keycard", "subject": {"character": NPC}})
        self.assertFalse(check(s, {"check": "has_tag", "tag": "tag_tool", "source": "party"}))
        s = do(s, {"op": "join_party", "subject": {"character": NPC}})
        self.assertTrue(check(s, {"check": "has_tag", "tag": "tag_tool", "source": "party"}))

    def test_has_tag_from_skill_level(self):
        s = do(fresh(), {"op": "grant_xp", "skill": "skill_salvage", "amount": 300})
        self.assertTrue(check(s, {"check": "has_tag", "tag": "tag_filter", "source": "body"}))

    def test_has_item(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "has_item", "item": "consumable_medkit", "count": 3}))
        self.assertFalse(check(s, {"check": "has_item", "item": "consumable_medkit", "count": 4}))
        # carried by default (what take_item can take); fitted only when asked for
        self.assertFalse(check(s, {"check": "has_item", "item": "module_cutter"}))
        self.assertTrue(check(s, {"check": "has_item", "item": "module_cutter", "source": "fitted"}))
        self.assertTrue(check(s, {"check": "has_item", "item": "module_cutter", "source": "any"}))
        self.assertFalse(check(s, {"check": "has_item", "item": "consumable_medkit", "source": "fitted"}))

    def test_skill(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "skill", "skill": "skill_salvage", "min": 1}))
        self.assertFalse(check(s, {"check": "skill", "skill": "skill_salvage", "min": 2}))

    def test_stat(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "stat", "stat": "stat_health", "min": 30, "max": 30}))
        s = do(s, {"op": "damage", "amount": 10, "damage_type": "dmg_toxic", "subject": "self"})
        self.assertTrue(check(s, {"check": "stat", "stat": "stat_health", "max": 20}))

    def test_item_condition(self):
        s = fresh()
        tool = {"check": "item_condition", "pick": {"item": "module_cutter"}, "min": 4}
        self.assertTrue(check(s, tool))
        s = do(s, {"op": "wear", "pick": {"item": "module_cutter"}, "amount": 1})
        self.assertFalse(check(s, tool))
        self.assertTrue(check(s, {"check": "item_condition", "pick": {"item": "module_shield"}, "max": 0}))  # never wears
        self.assertFalse(check(s, {"check": "item_condition", "pick": {"item": "frame_heavy"}, "min": 0}))      # not held

    def test_knows_design(self):
        s = fresh()
        self.assertFalse(check(s, {"check": "knows_design", "item": "module_cutter"}))
        s = do(s, {"op": "learn_design", "item": "module_cutter"})
        self.assertTrue(check(s, {"check": "knows_design", "item": "module_cutter"}))
        self.assertFalse(check(s, {"check": "knows_design", "item": "module_shield"}))

    def test_status(self):
        s = fresh()
        cond = {"check": "status", "status": "status_stun"}
        self.assertFalse(check(s, cond))
        self.assertTrue(check(do(s, {"op": "apply_status", "status": "status_stun", "subject": "self"}), cond))

    def test_flag(self):
        s = do(fresh(), {"op": "set_flag", "flag": "flag_power", "add": 2})
        self.assertTrue(check(s, {"check": "flag", "flag": "flag_power", "min": 2, "max": 2}))

    def test_location_region_visited(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "location", "location": "loc_workshop"}))
        self.assertTrue(check(s, {"check": "region", "region": "reg_lower_deck"}))
        self.assertTrue(check(s, {"check": "region", "region": "reg_station"}))   # parent region
        self.assertFalse(check(s, {"check": "visited", "location": "loc_storage"}))
        s = do(s, {"op": "move_to", "location": "loc_storage"}, {"op": "move_to", "location": "loc_workshop"})
        self.assertTrue(check(s, {"check": "visited", "location": "loc_storage"}))

    def test_object_state_and_this(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "object_state", "object": "workshop_door", "state": "state_closed"}))
        ctx = Ctx(self_id=PLAYER, this="storage_door")
        self.assertTrue(check(s, {"check": "object_state", "object": "this", "state": "state_open"}, ctx))

    def test_size(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "size", "min": 3, "max": 3}))
        self.assertFalse(check(s, {"check": "size", "min": 5}))
        heavy = s._replace(characters=freeze({**s.characters, PLAYER: char(s)._replace(frame=ItemInst("frame_heavy"))}))
        self.assertTrue(check(heavy, {"check": "size", "min": 5}))

    def test_fits(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "fits", "into_location": "loc_workshop"}))
        heavy = s._replace(characters=freeze({**s.characters, PLAYER: char(s)._replace(frame=ItemInst("frame_heavy"))}))
        self.assertFalse(check(heavy, {"check": "fits", "into_location": "loc_workshop"}))         # holds 3, frame is 5
        self.assertTrue(check(heavy, {"check": "fits", "into_location": "loc_side_room"}))  # no limit set
        self.assertTrue(check(s, {"check": "fits", "item": "module_cutter", "into_object": "workshop_locker"}))
        self.assertFalse(check(s, {"check": "fits", "item": "frame_light", "into_object": "workshop_locker"}))
        self.assertFalse(check(s, {"check": "fits", "item": "misc_keycard", "into_item": "module_cutter"}))  # holds nothing

    def test_in_party(self):
        s = fresh()
        cond = {"check": "in_party", "subject": {"character": NPC}}
        self.assertFalse(check(s, cond))
        self.assertTrue(check(do(s, {"op": "join_party", "subject": {"character": NPC}}), cond))

    def test_relation_and_faction_fallback(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "relation", "of": {"character": NPC}, "min": 10, "max": 10}))
        self.assertTrue(check(s, {"check": "relation", "of": "self", "toward": {"character": NPC}, "max": 0}))
        s = do(s, {"op": "change_relation", "of": "self", "toward": {"faction": "faction_crew"}, "amount": 40})
        # the player has no view of the NPC, so their view of the NPC's faction stands in
        self.assertTrue(check(s, {"check": "relation", "of": "self", "toward": {"character": NPC}, "min": 40}))

    def test_rank(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "rank", "max": 0}))
        self.assertTrue(check(do(s, {"op": "change_rank", "amount": 1}), {"check": "rank", "min": 1}))

    def test_time(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "time", "phase": "phase_day", "day_max": 1}))
        s = turns.advance(CONTENT, s, 30)
        self.assertTrue(check(s, {"check": "time", "phase": "phase_night"}))
        s = turns.advance(CONTENT, s, 30)
        self.assertEqual(day_of(CONTENT, s.turn), 2)
        self.assertTrue(check(s, {"check": "time", "day_min": 2, "phase": "phase_day"}))

    def test_chance_is_seeded(self):
        cond = {"check": "chance", "p": 0.5}
        cond = as_loaded(cond, "condition")
        first = [evaluate(CONTENT, fresh(3), me(fresh(3)), cond)[0] for _ in range(3)]
        self.assertEqual(len(set(first)), 1)                 # same seed, same answer
        state, results = fresh(3), []
        for _ in range(40):
            hit, state = evaluate(CONTENT, state, me(state), cond)
            results.append(hit)
        self.assertEqual(state.rng.counter, 40)
        self.assertTrue(0 < sum(results) < 40)

    def test_unknown_subjects_fail(self):
        s = fresh()
        self.assertFalse(check(s, {"check": "skill", "skill": "skill_salvage", "min": 1, "subject": "target"}))
        self.assertFalse(check(s, {"check": "skill", "skill": "skill_salvage", "min": 1, "subject": {"role": "x"}}))


class TestEffects(unittest.TestCase):
    def test_message_and_strings(self):
        s = do(fresh(), {"op": "message", "text": "@str_greeting", "kind": "quiet"})
        self.assertEqual(s.messages[-1].kind, "quiet")
        self.assertEqual(s.messages[-1].text, "Hello.")

    def test_give_item_respects_cargo(self):
        s = do(fresh(), {"op": "give_item", "item": "misc_keycard", "count": 5})
        self.assertEqual(sum(i.count for i in char(s).inventory if i.item == "misc_keycard"), 3)   # had one
        self.assertIn("Got: Keycard x2.", texts(s))
        self.assertIn("No room for Keycard.", texts(s))

    def test_give_item_stacks(self):
        s = do(fresh(), {"op": "give_item", "item": "material_scrap", "count": 8})
        stacks = [i.count for i in char(s).inventory if i.item == "material_scrap"]
        self.assertEqual(stacks, [10, 10])                   # 12 + 8 in stacks of 10

    def test_take_item_by_tag(self):
        s = do(fresh(), {"op": "take_item", "tag": "tag_tool"})
        self.assertFalse(any(i.item == "misc_keycard" for i in char(s).inventory))
        self.assertIn("Lost: Keycard.", texts(s))

    def test_wear_breaks_and_broken_items_count_for_nothing(self):
        s = do(fresh(), {"op": "wear", "pick": {"tag": "tag_tool"}, "amount": 4})
        self.assertEqual(char(s).fitted[0].condition, 0)
        self.assertIn("Cutter breaks.", texts(s))
        self.assertFalse(check(s, {"check": "has_tag", "tag": "tag_tool", "source": "fitted"}))
        s = do(s, {"op": "wear", "pick": {"item": "module_cutter"}, "amount": -2})   # negative repairs
        self.assertEqual(char(s).fitted[0].condition, 2)
        self.assertTrue(check(s, {"check": "has_tag", "tag": "tag_tool", "source": "fitted"}))

    def test_wear_the_used_item(self):
        s = fresh()
        ctx = Ctx(self_id=PLAYER, used=(PLAYER, "fitted", 0))
        s = do(s, {"op": "wear", "pick": {"used": True}, "amount": 1}, ctx=ctx)
        self.assertEqual(char(s).fitted[0].condition, 3)

    def test_modify_item(self):
        s = do(fresh(), {"op": "modify_item", "pick": {"slot_type": "slot_back"},
                         "stats": {"stat_armor": 3}, "add_tags": ["tag_filter"], "name_suffix": "Tuned"})
        system = char(s).fitted[1]
        self.assertEqual(stats.item_view(CONTENT, system)["name"], "Shield (Tuned)")
        self.assertEqual(stats.stat(CONTENT, char(s), "stat_armor"), 5)
        self.assertTrue(check(s, {"check": "has_tag", "tag": "tag_filter", "source": "fitted"}))

    def test_modify_item_takes_one_off_a_stack(self):
        s = do(fresh(), {"op": "modify_item", "pick": {"item": "consumable_medkit"}, "name_suffix": "Odd"})
        consumables = [i for i in char(s).inventory if i.item == "consumable_medkit"]
        self.assertEqual([(i.count, bool(i.changes)) for i in consumables], [(2, False), (1, True)])

    def test_learn_design(self):
        s = do(fresh(), {"op": "learn_design", "item": "module_shield"})
        self.assertTrue(check(s, {"check": "knows_design", "item": "module_shield"}))

    def test_roll_loot_is_seeded(self):
        effect = {"op": "roll_loot", "table": "loot_drone"}
        a, b = do(fresh(5), effect), do(fresh(5), effect)
        self.assertEqual(char(a).inventory, char(b).inventory)
        self.assertGreater(sum(i.count for i in char(a).inventory if i.item == "material_scrap"), 12)  # 'always' gives one

    def test_roll_loot_respects_when(self):
        # loot_rare offers the tool only at rank 1 or more; at rank 0 only the implant is possible
        for seed in range(10):
            s = do(fresh(seed), {"op": "roll_loot", "table": "loot_rare"})
            self.assertFalse(any(i.item == "module_cutter" for i in char(s).inventory))

    def test_damage_and_resistance(self):
        s = do(fresh(), {"op": "damage", "amount": 5, "damage_type": "dmg_impact", "subject": "self"})
        self.assertEqual(health(s), 27)                     # armor 2 resists dmg_impact
        s = do(s, {"op": "damage", "amount": 5, "damage_type": "dmg_toxic", "subject": "self"})
        self.assertEqual(health(s), 22)                     # dmg_toxic has no resisting stat

    def test_damage_defaults_to_target(self):
        ctx = Ctx(self_id=PLAYER, target=NPC)
        s = do(fresh(), {"op": "damage", "amount": 4, "damage_type": "dmg_toxic"}, ctx=ctx)
        self.assertEqual(health(s), 30)
        self.assertEqual(health(s, NPC), 6)

    def test_defeat_runs_on_defeat(self):
        s = do(fresh(), {"op": "move_to", "location": "loc_storage"},
               {"op": "damage", "amount": 99, "damage_type": "dmg_toxic", "subject": "self"})
        p = char(s)
        self.assertFalse(p.down)                            # on_defeat restored 5 health
        self.assertEqual(health(s), 5)
        self.assertEqual(p.location, "loc_workshop")              # on_defeat moved them
        self.assertEqual(s.event_requests, ("event_rescue",))
        self.assertIn("You go down.", texts(s))

    def test_restore_is_capped(self):
        s = do(fresh(), {"op": "damage", "amount": 10, "damage_type": "dmg_toxic", "subject": "self"},
               {"op": "restore", "stat": "stat_health", "amount": 50})
        self.assertEqual(health(s), 30)

    def test_modify_stat(self):
        s = do(fresh(), {"op": "modify_stat", "stat": "stat_armor", "amount": 4, "duration": 1},
               {"op": "modify_stat", "stat": "stat_health", "amount": -10})
        p = char(s)
        self.assertEqual(stats.stat(CONTENT, p, "stat_armor"), 6)
        self.assertEqual(p.mods[0].turns_left, 1)
        self.assertEqual(health(s), 20)                     # lowering the maximum lowers the current

    def test_apply_status_stacking(self):
        dot = {"op": "apply_status", "status": "status_burning", "subject": "self", "duration": 3}
        s = do(fresh(), dot, dot, dot, dot)
        self.assertEqual(char(s).statuses, (StatusInst("status_burning", 3, 3),))   # max_stacks 3
        stun = {"op": "apply_status", "status": "status_stun", "subject": "self", "duration": 1}
        s = do(s, stun, {**stun, "duration": 4})
        self.assertEqual(next(x for x in char(s).statuses if x.status == "status_stun").turns_left, 4)  # refreshed
        s = do(s, {"op": "remove_status", "status": "status_burning"})
        self.assertEqual([x.status for x in char(s).statuses], ["status_stun"])

    def test_set_flag(self):
        s = do(fresh(), {"op": "set_flag", "flag": "flag_power", "value": 5}, {"op": "set_flag", "flag": "flag_power", "add": -2})
        self.assertEqual(s.flags["flag_power"], 3)

    def test_set_state_this(self):
        ctx = Ctx(self_id=PLAYER, this="workshop_door")
        s = do(fresh(), {"op": "set_state", "object": "this", "state": "state_open"}, ctx=ctx)
        self.assertEqual(s.object_states["workshop_door"], "state_open")

    def test_move_to_takes_the_party(self):
        s = do(fresh(), {"op": "join_party", "subject": {"character": NPC}},
               {"op": "move_to", "location": "loc_storage", "entry": "storage_terminal"})
        self.assertEqual((char(s).location, char(s).at), ("loc_storage", (1, 5)))   # next to the solid terminal
        self.assertEqual(char(s, NPC).location, "loc_storage")
        self.assertIn("You enter Storage.", texts(s))

    def test_move_to_runs_on_enter(self):
        # loc_storage has on_turn hazards but no on_enter; give it none and check entry-point defaults instead
        s = do(fresh(), {"op": "move_to", "location": "loc_side_room"})
        self.assertEqual(char(s).at, (2, 2))               # grid centre

    def test_spend_time_and_requests(self):
        s = do(fresh(), {"op": "spend_time", "turns": 7}, {"op": "trigger_event", "event": "event_grudge"},
               {"op": "start_encounter", "encounter": "enc_drones"}, {"op": "end_encounter", "result": "won"})
        self.assertEqual(s.turns_owed, 7)                   # paid by engine.turns after the action
        self.assertEqual(turns.advance(CONTENT, s, 0).turn, 7)
        self.assertEqual(s.event_requests, ("event_grudge",))
        self.assertEqual(s.encounter_request, "enc_drones")

    def test_grant_xp(self):
        s = do(fresh(), {"op": "grant_xp", "skill": "skill_salvage", "amount": 100})
        self.assertEqual(char(s).skills["skill_salvage"], 3)
        self.assertEqual(char(s).xp["skill_salvage"], 100)
        self.assertIn("Salvage 2! Unlocks Burn.", texts(s))
        self.assertIn("Salvage 3! Tougher.", texts(s))
        self.assertEqual(stats.stat(CONTENT, char(s), "stat_health"), 35)   # level 3 adds 5
        s = do(s, {"op": "grant_xp", "skill": "skill_repair", "amount": 30})
        self.assertEqual(char(s).skills["skill_repair"], 2)     # a skill the character didn't have

    def test_join_and_leave_party(self):
        s = do(fresh(), {"op": "join_party", "subject": {"character": NPC}})
        self.assertEqual(char(s, NPC).leader, PLAYER)
        self.assertIn("Juno joins Player.", texts(s))
        s = do(s, {"op": "leave_party", "subject": {"character": NPC}})
        self.assertIsNone(char(s, NPC).leader)

    def test_change_relation(self):
        s = do(fresh(), {"op": "change_relation", "of": {"character": NPC}, "amount": 500},
               {"op": "change_relation", "of": "self", "toward": {"character": NPC}, "amount": -3, "mutual": True})
        self.assertEqual(s.relations["character:char_juno"]["character:char_player"], 97)   # capped at 100, then -3
        self.assertEqual(s.relations["character:char_player"]["character:char_juno"], -3)

    def test_change_rank_is_clamped(self):
        s = do(fresh(), {"op": "change_rank", "amount": 9})
        self.assertEqual(char(s).rank, 1)                  # the vocabulary's highest rank

    def test_unlock_slot(self):
        s = do(fresh(), {"op": "unlock_slot", "slot_type": "slot_head", "count": 2})
        self.assertEqual(char(s).body_slots["slot_head"], 3)   # one from the body, two unlocked

    def test_if(self):
        s = do(fresh(), {"op": "if", "if": {"check": "skill", "skill": "skill_salvage", "min": 5},
                         "then": [{"op": "set_flag", "flag": "flag_power", "value": 1}],
                         "else": [{"op": "set_flag", "flag": "flag_power", "value": 2}]})
        self.assertEqual(s.flags["flag_power"], 2)

    def test_choose_pauses_and_resumes(self):
        effect = {"op": "choose", "prompt": "Pick.", "options": [
            {"label": "A", "effects": [{"op": "set_flag", "flag": "flag_power", "value": 1}]},
            {"label": "B", "condition": {"check": "flag", "flag": "flag_power", "min": 9}, "hint": "Not yet.",
             "effects": [{"op": "set_flag", "flag": "flag_power", "value": 2}]}]}
        s = do(fresh(), effect, {"op": "set_flag", "flag": "flag_power", "add": 10})
        self.assertIsNotNone(s.pending)
        self.assertEqual(s.flags["flag_power"], 0)              # nothing after the choice ran yet
        blocked = choose_option(CONTENT, s, 1)
        self.assertIsNotNone(blocked.pending)
        self.assertEqual(blocked.messages[-1].text, "Not yet.")
        s = choose_option(CONTENT, s, 0)
        self.assertIsNone(s.pending)
        self.assertEqual(s.flags["flag_power"], 11)             # option A, then the rest

    def test_scaled_amount(self):
        effect = {"op": "damage", "damage_type": "dmg_toxic", "subject": "self",
                  "amount": {"stat": "stat_power", "times": 0.5, "plus": 2}}
        s = do(fresh(), effect)
        self.assertEqual(health(s), 25)                     # floor(6 * 0.5 + 2) = 5


class TestStateStaysImmutable(unittest.TestCase):
    def test_effects_never_change_the_input_state(self):
        s = fresh()
        before = (s.characters, s.flags, s.object_states, s.relations)
        do(s, {"op": "give_item", "item": "misc_keycard"}, {"op": "set_flag", "flag": "flag_power", "value": 3},
           {"op": "damage", "amount": 3, "damage_type": "dmg_toxic", "subject": "self"})
        self.assertEqual((s.characters, s.flags, s.object_states, s.relations), before)
        self.assertEqual(health(s), 30)


if __name__ == "__main__":
    unittest.main()
