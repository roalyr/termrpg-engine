"""
Milestone 1: every check and every effect outside encounters, against the test pack.
"""
import unittest
from pathlib import Path

from core import schema
from engine import effects, stats
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
PLAYER, NPC = "char_player", "char_npc"


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
        self.assertEqual(p.location, "room_a")
        self.assertEqual(p.at, (1, 4))                      # the start entry placement
        self.assertEqual(p.visited, ("room_a",))
        self.assertEqual(s.turn, 0)
        self.assertEqual(phase_of(CONTENT, s.turn), "phase_a")
        self.assertNotIn("char_drone", s.characters)        # templates aren't in play

    def test_loadout_and_pools(self):
        p = char(fresh())
        self.assertEqual(p.frame.item, "frame_a")
        self.assertEqual([i.item for i in p.fitted], ["module_tool", "module_system"])
        self.assertEqual(p.fitted[0].condition, 4)
        self.assertEqual(p.pools["stat_health"], 30)        # body 10 + frame 20
        self.assertEqual(p.pools["stat_heat"], 2)           # starts at the constant heat load
        self.assertEqual(stats.budget_used(CONTENT, p, "power"), 4)
        self.assertEqual(stats.budget_provided(CONTENT, p, "power"), 6)
        self.assertEqual(stats.stat(CONTENT, p, "stat_armor"), 2)
        self.assertEqual(stats.cargo_free(CONTENT, p), 3)   # cargo 2 + 4, three stacks carried

    def test_world_state(self):
        s = fresh()
        self.assertEqual(s.object_states["pl_a_door_b"], "state_closed")
        self.assertEqual(s.object_states["pl_b_door_a"], "state_open")
        self.assertEqual(s.flags["flag_a"], 0)
        self.assertEqual(s.relations["character:char_npc"]["character:char_player"], 10)
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
        yes, no = {"check": "flag", "flag": "flag_a", "max": 0}, {"check": "flag", "flag": "flag_a", "min": 1}
        self.assertTrue(check(s, {"all": [yes, {"not": no}]}))
        self.assertFalse(check(s, {"all": [yes, no]}))
        self.assertTrue(check(s, {"any": [no, yes]}))

    def test_has_tag_sources(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "has_tag", "tag": "tag_a"}))
        self.assertTrue(check(s, {"check": "has_tag", "tag": "tag_a", "source": "fitted"}))
        self.assertFalse(check(s, {"check": "has_tag", "tag": "tag_a", "source": "carried"}))
        s = do(s, {"op": "give_item", "item": "misc_key", "subject": {"character": NPC}})
        self.assertFalse(check(s, {"check": "has_tag", "tag": "tag_a", "source": "party"}))
        s = do(s, {"op": "join_party", "subject": {"character": NPC}})
        self.assertTrue(check(s, {"check": "has_tag", "tag": "tag_a", "source": "party"}))

    def test_has_tag_from_skill_level(self):
        s = do(fresh(), {"op": "grant_xp", "skill": "skill_a", "amount": 300})
        self.assertTrue(check(s, {"check": "has_tag", "tag": "tag_b", "source": "body"}))

    def test_has_item(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "has_item", "item": "consumable_a", "count": 3}))
        self.assertFalse(check(s, {"check": "has_item", "item": "consumable_a", "count": 4}))
        self.assertTrue(check(s, {"check": "has_item", "item": "module_tool"}))   # fitted counts

    def test_skill(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "skill", "skill": "skill_a", "min": 1}))
        self.assertFalse(check(s, {"check": "skill", "skill": "skill_a", "min": 2}))

    def test_stat(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "stat", "stat": "stat_health", "min": 30, "max": 30}))
        s = do(s, {"op": "damage", "amount": 10, "damage_type": "dmg_b", "subject": "self"})
        self.assertTrue(check(s, {"check": "stat", "stat": "stat_health", "max": 20}))

    def test_item_condition(self):
        s = fresh()
        tool = {"check": "item_condition", "pick": {"item": "module_tool"}, "min": 4}
        self.assertTrue(check(s, tool))
        s = do(s, {"op": "wear", "pick": {"item": "module_tool"}, "amount": 1})
        self.assertFalse(check(s, tool))
        self.assertTrue(check(s, {"check": "item_condition", "pick": {"item": "module_system"}, "max": 0}))  # never wears
        self.assertFalse(check(s, {"check": "item_condition", "pick": {"item": "frame_b"}, "min": 0}))      # not held

    def test_knows_design(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "knows_design", "item": "module_tool"}))
        self.assertFalse(check(s, {"check": "knows_design", "item": "module_system"}))

    def test_status(self):
        s = fresh()
        cond = {"check": "status", "status": "status_stun"}
        self.assertFalse(check(s, cond))
        self.assertTrue(check(do(s, {"op": "apply_status", "status": "status_stun", "subject": "self"}), cond))

    def test_flag(self):
        s = do(fresh(), {"op": "set_flag", "flag": "flag_a", "add": 2})
        self.assertTrue(check(s, {"check": "flag", "flag": "flag_a", "min": 2, "max": 2}))

    def test_location_region_visited(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "location", "location": "room_a"}))
        self.assertTrue(check(s, {"check": "region", "region": "region_a_1"}))
        self.assertTrue(check(s, {"check": "region", "region": "region_a"}))   # parent region
        self.assertFalse(check(s, {"check": "visited", "location": "room_b"}))
        s = do(s, {"op": "move_to", "location": "room_b"}, {"op": "move_to", "location": "room_a"})
        self.assertTrue(check(s, {"check": "visited", "location": "room_b"}))

    def test_object_state_and_this(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "object_state", "object": "pl_a_door_b", "state": "state_closed"}))
        ctx = Ctx(self_id=PLAYER, this="pl_b_door_a")
        self.assertTrue(check(s, {"check": "object_state", "object": "this", "state": "state_open"}, ctx))

    def test_size(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "size", "min": 3, "max": 3}))
        self.assertFalse(check(s, {"check": "size", "min": 5}))
        heavy = s._replace(characters=freeze({**s.characters, PLAYER: char(s)._replace(frame=ItemInst("frame_b"))}))
        self.assertTrue(check(heavy, {"check": "size", "min": 5}))

    def test_fits(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "fits", "into_location": "room_a"}))
        heavy = s._replace(characters=freeze({**s.characters, PLAYER: char(s)._replace(frame=ItemInst("frame_b"))}))
        self.assertFalse(check(heavy, {"check": "fits", "into_location": "room_a"}))         # holds 3, frame is 5
        self.assertTrue(check(heavy, {"check": "fits", "into_location": "room_template_a"}))  # no limit set
        self.assertTrue(check(s, {"check": "fits", "item": "module_tool", "into_object": "pl_a_locker"}))
        self.assertFalse(check(s, {"check": "fits", "item": "frame_a", "into_object": "pl_a_locker"}))
        self.assertFalse(check(s, {"check": "fits", "item": "misc_key", "into_item": "module_tool"}))  # holds nothing

    def test_in_party(self):
        s = fresh()
        cond = {"check": "in_party", "subject": {"character": NPC}}
        self.assertFalse(check(s, cond))
        self.assertTrue(check(do(s, {"op": "join_party", "subject": {"character": NPC}}), cond))

    def test_relation_and_faction_fallback(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "relation", "of": {"character": NPC}, "min": 10, "max": 10}))
        self.assertTrue(check(s, {"check": "relation", "of": "self", "toward": {"character": NPC}, "max": 0}))
        s = do(s, {"op": "change_relation", "of": "self", "toward": {"faction": "faction_a"}, "amount": 40})
        # the player has no view of the NPC, so their view of the NPC's faction stands in
        self.assertTrue(check(s, {"check": "relation", "of": "self", "toward": {"character": NPC}, "min": 40}))

    def test_rank(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "rank", "max": 0}))
        self.assertTrue(check(do(s, {"op": "change_rank", "amount": 1}), {"check": "rank", "min": 1}))

    def test_time(self):
        s = fresh()
        self.assertTrue(check(s, {"check": "time", "phase": "phase_a", "day_max": 1}))
        s = do(s, {"op": "spend_time", "turns": 30})
        self.assertTrue(check(s, {"check": "time", "phase": "phase_b"}))
        s = do(s, {"op": "spend_time", "turns": 30})
        self.assertEqual(day_of(CONTENT, s.turn), 2)
        self.assertTrue(check(s, {"check": "time", "day_min": 2, "phase": "phase_a"}))

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
        self.assertFalse(check(s, {"check": "skill", "skill": "skill_a", "min": 1, "subject": "target"}))
        self.assertFalse(check(s, {"check": "skill", "skill": "skill_a", "min": 1, "subject": {"role": "x"}}))


class TestEffects(unittest.TestCase):
    def test_message_and_strings(self):
        s = do(fresh(), {"op": "message", "text": "@greeting", "kind": "quiet"})
        self.assertEqual(s.messages[-1].kind, "quiet")
        self.assertEqual(s.messages[-1].text, "Hello.")

    def test_give_item_respects_cargo(self):
        s = do(fresh(), {"op": "give_item", "item": "misc_key", "count": 5})
        self.assertEqual(sum(i.count for i in char(s).inventory if i.item == "misc_key"), 3)
        self.assertIn("Got: Key A x3.", texts(s))
        self.assertIn("No room for Key A.", texts(s))

    def test_give_item_stacks(self):
        s = do(fresh(), {"op": "give_item", "item": "material_a", "count": 8})
        stacks = [i.count for i in char(s).inventory if i.item == "material_a"]
        self.assertEqual(stacks, [10, 10])                   # 12 + 8 in stacks of 10

    def test_take_item_by_tag(self):
        s = do(fresh(), {"op": "give_item", "item": "misc_key"}, {"op": "take_item", "tag": "tag_a"})
        self.assertFalse(any(i.item == "misc_key" for i in char(s).inventory))
        self.assertIn("Lost: Key A.", texts(s))

    def test_wear_breaks_and_broken_items_count_for_nothing(self):
        s = do(fresh(), {"op": "wear", "pick": {"tag": "tag_a"}, "amount": 4})
        self.assertEqual(char(s).fitted[0].condition, 0)
        self.assertIn("Tool A breaks.", texts(s))
        self.assertFalse(check(s, {"check": "has_tag", "tag": "tag_a"}))
        s = do(s, {"op": "wear", "pick": {"item": "module_tool"}, "amount": -2})   # negative repairs
        self.assertEqual(char(s).fitted[0].condition, 2)
        self.assertTrue(check(s, {"check": "has_tag", "tag": "tag_a"}))

    def test_wear_the_used_item(self):
        s = fresh()
        ctx = Ctx(self_id=PLAYER, used=(PLAYER, "fitted", 0))
        s = do(s, {"op": "wear", "pick": {"used": True}, "amount": 1}, ctx=ctx)
        self.assertEqual(char(s).fitted[0].condition, 3)

    def test_modify_item(self):
        s = do(fresh(), {"op": "modify_item", "pick": {"slot_type": "slot_frame_a"},
                         "stats": {"stat_armor": 3}, "add_tags": ["tag_b"], "name_suffix": "Tuned"})
        system = char(s).fitted[1]
        self.assertEqual(stats.item_view(CONTENT, system)["name"], "System A (Tuned)")
        self.assertEqual(stats.stat(CONTENT, char(s), "stat_armor"), 5)
        self.assertTrue(check(s, {"check": "has_tag", "tag": "tag_b", "source": "fitted"}))

    def test_modify_item_takes_one_off_a_stack(self):
        s = do(fresh(), {"op": "modify_item", "pick": {"item": "consumable_a"}, "name_suffix": "Odd"})
        consumables = [i for i in char(s).inventory if i.item == "consumable_a"]
        self.assertEqual([(i.count, bool(i.changes)) for i in consumables], [(2, False), (1, True)])

    def test_learn_design(self):
        s = do(fresh(), {"op": "learn_design", "item": "module_system"})
        self.assertTrue(check(s, {"check": "knows_design", "item": "module_system"}))

    def test_roll_loot_is_seeded(self):
        effect = {"op": "roll_loot", "table": "loot_drone"}
        a, b = do(fresh(5), effect), do(fresh(5), effect)
        self.assertEqual(char(a).inventory, char(b).inventory)
        self.assertGreater(sum(i.count for i in char(a).inventory if i.item == "material_a"), 12)  # 'always' gives one

    def test_roll_loot_respects_when(self):
        # loot_rare offers the tool only at rank 1 or more; at rank 0 only the implant is possible
        for seed in range(10):
            s = do(fresh(seed), {"op": "roll_loot", "table": "loot_rare"})
            self.assertFalse(any(i.item == "module_tool" for i in char(s).inventory))

    def test_damage_and_resistance(self):
        s = do(fresh(), {"op": "damage", "amount": 5, "damage_type": "dmg_a", "subject": "self"})
        self.assertEqual(health(s), 27)                     # armor 2 resists dmg_a
        s = do(s, {"op": "damage", "amount": 5, "damage_type": "dmg_b", "subject": "self"})
        self.assertEqual(health(s), 22)                     # dmg_b has no resisting stat

    def test_damage_defaults_to_target(self):
        ctx = Ctx(self_id=PLAYER, target=NPC)
        s = do(fresh(), {"op": "damage", "amount": 4, "damage_type": "dmg_b"}, ctx=ctx)
        self.assertEqual(health(s), 30)
        self.assertEqual(health(s, NPC), 6)

    def test_defeat_runs_on_defeat(self):
        s = do(fresh(), {"op": "move_to", "location": "room_b"},
               {"op": "damage", "amount": 99, "damage_type": "dmg_b", "subject": "self"})
        p = char(s)
        self.assertFalse(p.down)                            # on_defeat restored 5 health
        self.assertEqual(health(s), 5)
        self.assertEqual(p.location, "room_a")              # on_defeat moved them
        self.assertEqual(s.event_requests, ("event_rescue",))
        self.assertIn("You go down.", texts(s))

    def test_restore_is_capped(self):
        s = do(fresh(), {"op": "damage", "amount": 10, "damage_type": "dmg_b", "subject": "self"},
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
        dot = {"op": "apply_status", "status": "status_dot", "subject": "self", "duration": 3}
        s = do(fresh(), dot, dot, dot, dot)
        self.assertEqual(char(s).statuses, (StatusInst("status_dot", 3, 3),))   # max_stacks 3
        stun = {"op": "apply_status", "status": "status_stun", "subject": "self", "duration": 1}
        s = do(s, stun, {**stun, "duration": 4})
        self.assertEqual(next(x for x in char(s).statuses if x.status == "status_stun").turns_left, 4)  # refreshed
        s = do(s, {"op": "remove_status", "status": "status_dot"})
        self.assertEqual([x.status for x in char(s).statuses], ["status_stun"])

    def test_set_flag(self):
        s = do(fresh(), {"op": "set_flag", "flag": "flag_a", "value": 5}, {"op": "set_flag", "flag": "flag_a", "add": -2})
        self.assertEqual(s.flags["flag_a"], 3)

    def test_set_state_this(self):
        ctx = Ctx(self_id=PLAYER, this="pl_a_door_b")
        s = do(fresh(), {"op": "set_state", "object": "this", "state": "state_open"}, ctx=ctx)
        self.assertEqual(s.object_states["pl_a_door_b"], "state_open")

    def test_move_to_takes_the_party(self):
        s = do(fresh(), {"op": "join_party", "subject": {"character": NPC}},
               {"op": "move_to", "location": "room_b", "entry": "pl_b_terminal"})
        self.assertEqual((char(s).location, char(s).at), ("room_b", (2, 5)))
        self.assertEqual(char(s, NPC).location, "room_b")
        self.assertIn("You enter Room B.", texts(s))

    def test_move_to_runs_on_enter(self):
        # room_b has on_turn hazards but no on_enter; give it none and check entry-point defaults instead
        s = do(fresh(), {"op": "move_to", "location": "room_template_a"})
        self.assertEqual(char(s).at, (2, 2))               # grid centre

    def test_spend_time_and_requests(self):
        s = do(fresh(), {"op": "spend_time", "turns": 7}, {"op": "trigger_event", "event": "event_grudge"},
               {"op": "start_encounter", "encounter": "enc_drones"}, {"op": "end_encounter", "result": "won"})
        self.assertEqual(s.turn, 7)
        self.assertEqual(s.event_requests, ("event_grudge",))
        self.assertEqual(s.encounter_request, "enc_drones")

    def test_grant_xp(self):
        s = do(fresh(), {"op": "grant_xp", "skill": "skill_a", "amount": 100})
        self.assertEqual(char(s).skills["skill_a"], 3)
        self.assertEqual(char(s).xp["skill_a"], 100)
        self.assertIn("Skill A 2! Unlocks Burst.", texts(s))
        self.assertIn("Skill A 3! Tougher.", texts(s))
        self.assertEqual(stats.stat(CONTENT, char(s), "stat_health"), 35)   # level 3 adds 5
        s = do(s, {"op": "grant_xp", "skill": "skill_b", "amount": 30})
        self.assertEqual(char(s).skills["skill_b"], 2)     # a skill the character didn't have

    def test_join_and_leave_party(self):
        s = do(fresh(), {"op": "join_party", "subject": {"character": NPC}})
        self.assertEqual(char(s, NPC).leader, PLAYER)
        self.assertIn("Npc joins Player.", texts(s))
        s = do(s, {"op": "leave_party", "subject": {"character": NPC}})
        self.assertIsNone(char(s, NPC).leader)

    def test_change_relation(self):
        s = do(fresh(), {"op": "change_relation", "of": {"character": NPC}, "amount": 500},
               {"op": "change_relation", "of": "self", "toward": {"character": NPC}, "amount": -3, "mutual": True})
        self.assertEqual(s.relations["character:char_npc"]["character:char_player"], 97)   # capped at 100, then -3
        self.assertEqual(s.relations["character:char_player"]["character:char_npc"], -3)

    def test_change_rank_is_clamped(self):
        s = do(fresh(), {"op": "change_rank", "amount": 9})
        self.assertEqual(char(s).rank, 1)                  # the vocabulary's highest rank

    def test_unlock_slot(self):
        s = do(fresh(), {"op": "unlock_slot", "slot_type": "slot_body_a", "count": 2})
        self.assertEqual(char(s).body_slots["slot_body_a"], 3)   # one from the body, two unlocked

    def test_if(self):
        s = do(fresh(), {"op": "if", "if": {"check": "skill", "skill": "skill_a", "min": 5},
                         "then": [{"op": "set_flag", "flag": "flag_a", "value": 1}],
                         "else": [{"op": "set_flag", "flag": "flag_a", "value": 2}]})
        self.assertEqual(s.flags["flag_a"], 2)

    def test_choose_pauses_and_resumes(self):
        effect = {"op": "choose", "prompt": "Pick.", "options": [
            {"label": "A", "effects": [{"op": "set_flag", "flag": "flag_a", "value": 1}]},
            {"label": "B", "condition": {"check": "flag", "flag": "flag_a", "min": 9}, "hint": "Not yet.",
             "effects": [{"op": "set_flag", "flag": "flag_a", "value": 2}]}]}
        s = do(fresh(), effect, {"op": "set_flag", "flag": "flag_a", "add": 10})
        self.assertIsNotNone(s.pending)
        self.assertEqual(s.flags["flag_a"], 0)              # nothing after the choice ran yet
        blocked = choose_option(CONTENT, s, 1)
        self.assertIsNotNone(blocked.pending)
        self.assertEqual(blocked.messages[-1].text, "Not yet.")
        s = choose_option(CONTENT, s, 0)
        self.assertIsNone(s.pending)
        self.assertEqual(s.flags["flag_a"], 11)             # option A, then the rest

    def test_scaled_amount(self):
        effect = {"op": "damage", "damage_type": "dmg_b", "subject": "self",
                  "amount": {"stat": "stat_power", "times": 0.5, "plus": 2}}
        s = do(fresh(), effect)
        self.assertEqual(health(s), 25)                     # floor(6 * 0.5 + 2) = 5


class TestStateStaysImmutable(unittest.TestCase):
    def test_effects_never_change_the_input_state(self):
        s = fresh()
        before = (s.characters, s.flags, s.object_states, s.relations)
        do(s, {"op": "give_item", "item": "misc_key"}, {"op": "set_flag", "flag": "flag_a", "value": 3},
           {"op": "damage", "amount": 3, "damage_type": "dmg_b", "subject": "self"})
        self.assertEqual((s.characters, s.flags, s.object_states, s.relations), before)
        self.assertEqual(health(s), 30)


if __name__ == "__main__":
    unittest.main()
