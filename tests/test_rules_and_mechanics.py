"""Regression tests for the rules consolidation and the v2 mechanics."""
import json
import tempfile
import unittest
from pathlib import Path

from core.actions import dispatch_action
from core.persistence import save_state, load_state, state_from_dict, state_to_dict
from core.presets import init_game_state, DEFAULT_DATA_DIR, ANCHOR_CHOICES, ROUTINE_CHOICES
from core.reducers import ALL_ITEMS_BY_ID, ALL_COMPANIONS_BY_ID, reduce_barter, reduce_talk, reduce_use
from core.rules import resolve_requirement, exposure_status
from core.tick import process_tick
from core.types import Exposure, FixtureState
from main import save_folder_name
from ui.render import render_frame


def at(state, node_id, row, col):
    """Places the player on a tile with the proximity menu open."""
    return state._replace(current_node_id=node_id, player_row=row, player_col=col, proximity_menu_active=True)


def carrying(state, *item_ids, keep=False):
    items = tuple(ALL_ITEMS_BY_ID[i] for i in item_ids)
    inv = (state.character.inventory if keep else ()) + items
    return state._replace(character=state.character._replace(inventory=inv))


def with_caps(state, *caps):
    return state._replace(character=state.character._replace(
        unlocked_capabilities=state.character.unlocked_capabilities | set(caps)))


def ids(state):
    return [i.id for i in state.character.inventory]


def new(anchor=1, routine=1):
    return init_game_state(DEFAULT_DATA_DIR, "Tester", anchor, routine)


class TestRequirementResolution(unittest.TestCase):
    """C1: skills and companions satisfy requirements without spending carried items."""

    def test_seam_scraper_opens_vent_without_losing_fitting(self):
        s = at(new(1, 1), "stn_a_bunkroom", 4, 2)
        s2 = dispatch_action(s, "u")
        self.assertEqual(s2.nodes["stn_a_bunkroom"].fixtures["vent_duct"].state, FixtureState.OPEN.value)
        self.assertIn("fitting_copper", ids(s2))
        self.assertTrue(any("Seam Scraper training" in m for m in s2.message_buffer))

    def test_algae_tender_harvests_without_losing_fitting(self):
        s = at(new(1, 2), "stn_a_hab", 2, 4)
        s2 = dispatch_action(s, "u")
        self.assertIn("fitting_copper", ids(s2))
        self.assertIn("algae_paste", ids(s2))

    def test_empty_pack_can_still_use_capability_fixtures(self):
        s = at(new(1, 2), "stn_a_hab", 2, 4)
        s = s._replace(character=s.character._replace(inventory=()))
        s2 = dispatch_action(s, "u")
        self.assertIn("algae_paste", ids(s2))

    def test_free_source_beats_named_item(self):
        s = with_caps(carrying(new(), "chit_transit"), "wayfarer")
        src = resolve_requirement(s, ("transit_clearance",), preferred_item_idx=0)
        self.assertIsNone(src.item_idx)

    def test_cargo_handler_opens_hoist_and_mine_shaft(self):
        s = at(new(3, 3), "stn_a_berth", 5, 3)
        s = dispatch_action(s, "u")
        self.assertEqual(s.nodes["stn_a_berth"].fixtures["cargo_hoist"].state, FixtureState.OPEN.value)
        s = at(s, "luna_smelter", 5, 3)
        s = dispatch_action(s, "u")
        self.assertEqual(s.nodes["luna_smelter"].fixtures["mine_shaft"].state, FixtureState.OPEN.value)

    def test_heavy_lift_cannot_repair_valve(self):
        s = at(carrying(new(3, 3)), "stn_a_sub", 3, 1)
        s2 = dispatch_action(s, "u")
        self.assertEqual(s2.nodes["stn_a_sub"].fixtures["jammed_valve"].state, FixtureState.DISABLED.value)


class TestTrade(unittest.TestCase):
    """C2, C3, M6: barter is explicit, currency is spent, every start can reach Tarek."""

    def test_talk_never_trades(self):
        s = at(new(), "stn_a_berth", 2, 4)
        s2 = dispatch_action(s, "t")
        self.assertIn("fitting_copper", ids(s2))
        self.assertFalse(s2.nodes["stn_a_berth"].actors["npc_kael"].trade_completed)

    def test_dice_are_handed_over(self):
        s = carrying(new(3, 1), "dice_steel")._replace(current_node_id="stn_b_dock")
        s2 = reduce_barter(s, "npc_tarek")
        self.assertNotIn("dice_steel", ids(s2))
        self.assertIn("wire_spool", ids(s2))

    def test_credentials_are_shown_not_given(self):
        # A credential that matches a trade tag is kept.
        s = carrying(new(), "pass_work")._replace(current_node_id="stn_b_dock")
        actor = s.nodes["stn_b_dock"].actors["npc_tarek"]._replace(trade_required_tags=("dock_clearance",))
        node = s.nodes["stn_b_dock"]._replace(actors={"npc_tarek": actor})
        s = s._replace(nodes={**s.nodes, "stn_b_dock": node})
        s2 = reduce_barter(s, "npc_tarek")
        self.assertIn("pass_work", ids(s2))
        self.assertIn("wire_spool", ids(s2))

    def test_scrip_from_locker_recruits_tarek(self):
        s = dispatch_action(new(1, 1), "/search personal_locker")
        self.assertIn("scrip_shift", ids(s))
        s = s._replace(current_node_id="stn_b_dock")
        s2 = dispatch_action(s, "/barter npc_tarek scrip_shift")
        self.assertTrue(any(c.id == "comp_tarek" for c in s2.companions))
        self.assertNotIn("scrip_shift", ids(s2))

    def test_recruited_actor_leaves_the_grid(self):
        s = carrying(new(), "tool_prybar")._replace(current_node_id="stn_a_sub")
        s2 = reduce_barter(s, "npc_radek")
        self.assertFalse(any(p.entity_id == "npc_radek" for p in s2.nodes["stn_a_sub"].placements))
        self.assertTrue(any("Radek (Cargo Rigger)" in m for m in s2.message_buffer))

    def test_barter_rejects_unsuitable_named_item(self):
        s = carrying(new(), "fitting_copper", "dice_steel")._replace(current_node_id="stn_b_dock")
        s2 = dispatch_action(s, "/barter npc_tarek fitting_copper")
        self.assertIn("fitting_copper", ids(s2))
        self.assertFalse(s2.nodes["stn_b_dock"].actors["npc_tarek"].trade_completed)

    def test_dialogue_variant_by_background(self):
        s = new(1, 3)._replace(current_node_id="stn_a_berth")
        s2 = reduce_talk(s, "npc_kael")
        self.assertTrue(any("Berth hand" in m for m in s2.message_buffer))


class TestInputAndMenu(unittest.TestCase):
    """C4, C7."""

    def test_s_moves_south_on_a_container(self):
        s = at(new(), "stn_a_bunkroom", 1, 3)
        s2 = dispatch_action(s, "s")
        self.assertEqual((s2.player_row, s2.player_col), (2, 3))
        self.assertNotIn("wire_spool", ids(s2))

    def test_menu_refreshes_after_unlock(self):
        s = at(new(1, 1), "stn_a_bunkroom", 4, 2)
        s2 = dispatch_action(s, "u")
        self.assertTrue(s2.proximity_menu_active)
        self.assertTrue(any("[G] Go -> " in m for m in s2.message_buffer))

    def test_b_goes_back_from_map_but_barters_in_menu(self):
        s = at(new(), "stn_a_berth", 2, 4)
        s2 = dispatch_action(s, "b")
        self.assertIn("pass_work", ids(s2))
        m = dispatch_action(new(), "m")
        self.assertEqual(dispatch_action(m, "b").active_view, "compartment")


class TestExposure(unittest.TestCase):
    """C5, C8, C9, D2, D6."""

    def test_iron_body_reload_at_16_is_not_a_collapse(self):
        s = with_caps(new(), "trench_hardened")._replace(current_node_id="luna_dome")
        s = s._replace(character=s.character._replace(exposure=Exposure(16.0, 0.0, 0.0)))
        r = state_from_dict(state_to_dict(s))
        self.assertEqual(r.current_node_id, "luna_dome")
        self.assertEqual(r.character.exposure.pressure_debt, 16.0)

    def test_status_uses_iron_body_thresholds(self):
        s = with_caps(new(), "trench_hardened")
        s = s._replace(character=s.character._replace(exposure=Exposure(12.0, 0.0, 0.0)))
        self.assertEqual(exposure_status(s), "STRESSED")
        self.assertIn(" STRESSED", render_frame(s, 40))

    def test_lead_skin_needs_its_own_depth_time(self):
        s = with_caps(new(), "cold_bypass", "vacuum_walk")
        tree = tuple(t._replace(attuned=t.id in ("cold_bypass", "vacuum_walk")) for t in s.tree)
        s = s._replace(tree=tree, depth_ticks={1: 5}, current_node_id="stn_a_sub")
        s1 = process_tick(s, "wait")
        self.assertNotIn("deep_well", s1.character.unlocked_capabilities)
        s20 = s._replace(depth_ticks={1: 19})
        self.assertIn("deep_well", process_tick(s20, "wait").character.unlocked_capabilities)

    def test_safe_rooms_do_not_count_as_surviving_depth(self):
        s = at(carrying(new(), "tool_prybar"), "stn_a_sub", 3, 1)
        s = dispatch_action(s, "u")  # repair valve: 92 kPa, -5 C
        before = s.depth_ticks.get(1, 0)
        s = dispatch_action(s, "/wait")
        self.assertEqual(s.depth_ticks.get(1, 0), before)

    def test_critical_work_costs_two_cycles_but_walking_does_not(self):
        s = at(new(), "stn_a_bunkroom", 1, 3)
        s = s._replace(current_node_id="stn_a_sub", player_row=2, player_col=4,
                       character=s.character._replace(exposure=Exposure(11.0, 0.0, 0.0)))
        c0 = s.cycle
        self.assertEqual(dispatch_action(s, "f").cycle, c0 + 2)
        self.assertEqual(dispatch_action(s, "a").cycle, c0 + 1)

    def test_zone3_shows_exposure_numbers_and_rate(self):
        s = new()._replace(current_node_id="luna_pad", player_row=3, player_col=3)
        s = s._replace(character=s.character._replace(exposure=Exposure(12.0, 5.3, 14.0)))
        frame = render_frame(s, 40)
        self.assertIn("P12.0 R5.3 T14.0", frame)
        self.assertIn("MAX 15 T+3.5/c", frame)


class TestFixtures(unittest.TestCase):
    """C6, C10, M2, M4, M5."""

    def test_read_with_empty_pack_and_locked_text(self):
        s = at(new(), "stn_a_hab", 2, 1)._replace(character=new().character._replace(inventory=()))
        s2 = dispatch_action(s, "r")
        self.assertTrue(any("Shift roster" in m for m in s2.message_buffer))
        self.assertTrue(any("encrypted" in m for m in s2.message_buffer))
        s3 = dispatch_action(carrying(s, "slate_tally"), "r")
        self.assertTrue(any("[Decoded]" in m and "umbilical" in m for m in s3.message_buffer))

    def test_logs_are_distinct(self):
        texts = {f.log_text for n in new().nodes.values() for f in n.fixtures.values() if f.on_use_effect == "log"}
        self.assertEqual(len(texts), 5)

    def test_repair_once_changes_vitals_then_refuses(self):
        s = at(carrying(new(), "tool_prybar"), "stn_a_sub", 3, 1)
        s2 = dispatch_action(s, "u")
        self.assertEqual(s2.nodes["stn_a_sub"].base_vitals.pressure_kpa, 92.0)
        self.assertEqual(s2.character.inventory[0].integrity, 3)
        s3 = reduce_use(s2, "tool_prybar", "jammed_valve")
        self.assertTrue(any("already running" in m for m in s3.message_buffer))
        self.assertEqual(s3.cycle, s2.cycle)
        self.assertEqual(s3.character.inventory[0].integrity, 3)

    def test_seal_patch_fixes_lava_tube(self):
        s = at(carrying(new(), "seal_patch"), "luna_tube", 4, 4)
        s2 = dispatch_action(s, "u")
        self.assertEqual(s2.nodes["luna_tube"].base_vitals.pressure_kpa, 78.0)
        self.assertEqual(s2.character.inventory[0].integrity, 1)

    def test_shuttle_gate_reseals_after_boarding(self):
        s = at(carrying(new(), "chit_transit"), "stn_a_berth", 3, 6)
        s = dispatch_action(s, "u")
        self.assertNotIn("chit_transit", ids(s))
        s = dispatch_action(s, "g")
        self.assertEqual(s.current_node_id, "shuttle_ab")
        self.assertEqual(s.nodes["stn_a_berth"].fixtures["shuttle_gate"].state, FixtureState.SEALED.value)
        self.assertTrue(any("reseals" in m for m in s.message_buffer))

    def test_umbilical_collar_opens_gate_once(self):
        s = at(new(1, 1), "stn_a_berth", 2, 5)  # seam scraper: seal_fitting
        s = dispatch_action(s, "u")
        berth = s.nodes["stn_a_berth"]
        self.assertEqual(berth.fixtures["shuttle_gate"].state, FixtureState.OPEN.value)
        self.assertEqual(berth.fixtures["umbilical_collar"].state, FixtureState.SPENT.value)

    def test_stowaway_route_is_repeatable(self):
        s = at(new(1, 3), "stn_a_berth", 1, 2)  # cargo handler releases clamps
        for _ in range(2):
            s = dispatch_action(s, "u")
            s = dispatch_action(s, "g")
            self.assertEqual(s.current_node_id, "shuttle_ab")
            s = at(s, "stn_a_berth", 1, 2)

    def test_forged_clearance_opens_hoist(self):
        s = carrying(new(), "wire_spool")._replace(current_node_id="stn_b_array")
        s = reduce_use(s, "wire_spool", "crypto_terminal")
        s = at(s._replace(character=s.character._replace(inventory=())), "stn_a_berth", 5, 3)
        s = dispatch_action(s, "u")
        self.assertEqual(s.nodes["stn_a_berth"].fixtures["cargo_hoist"].state, FixtureState.OPEN.value)

    def test_hatches_cannot_be_scavenged(self):
        s = dispatch_action(new(), "/search hatch_berth")
        self.assertTrue(any("Nothing to search" in m for m in s.message_buffer))


class TestSelfAndTravel(unittest.TestCase):
    """M3, D8, C11, D1."""

    def test_consume_sheds_exposure(self):
        s = carrying(new(), "flask_water", "algae_paste")
        s = s._replace(current_node_id="stn_a_sub", character=s.character._replace(exposure=Exposure(3.0, 4.0, 5.0)))
        s2 = dispatch_action(s, "/drink flask_water")
        self.assertEqual(s2.character.inventory[0].integrity, 2)
        self.assertAlmostEqual(s2.character.exposure.thermal_stress, 5.0 - 1.5 + 0.75, places=2)
        # Biomass purges radiation only with a bio filter in the party
        s3 = dispatch_action(with_caps(s, "bio_filter"), "/eat algae_paste")
        self.assertAlmostEqual(s3.character.exposure.radiation_dose, 4.0 - 1.0 - 2.0, places=2)

    def test_consume_refuses_non_food(self):
        s2 = dispatch_action(new(), "/eat fitting_copper")
        self.assertEqual(s2.cycle, 0)

    def test_leave_costs_walking_distance(self):
        s = new()._replace(current_node_id="stn_a_berth", player_row=3, player_col=3)
        s2 = dispatch_action(s, "/leave to_hab")  # hab hatch at (3, 0): 3 tiles
        self.assertEqual(s2.current_node_id, "stn_a_hab")
        self.assertEqual(s2.cycle, 3)

    def test_save_folder_name_is_sanitized(self):
        self.assertEqual(save_folder_name("../evil/x"), "___evil_x")
        self.assertEqual(save_folder_name("  "), "pilot")
        self.assertEqual(save_folder_name("Vaelen-7"), "Vaelen-7")

    def test_fourth_anchor(self):
        self.assertEqual(new(4, 1).character.personal_anchor.id, "slate_tally")


class TestPersistenceV2(unittest.TestCase):
    def test_catalog_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            save_state(new(), Path(tmp))
            loaded = load_state(Path(tmp))
        self.assertIn("scrip_shift", loaded.item_catalog)
        self.assertIn("comp_tarek", loaded.companion_catalog)

    def test_v1_save_is_upgraded_without_losing_progress(self):
        data = state_to_dict(new())
        data.pop("schema_version")
        data.pop("item_catalog")
        data.pop("companion_catalog")
        berth = data["nodes"]["stn_a_berth"]
        del berth["fixtures"]["umbilical_collar"]
        berth["placements"] = [p for p in berth["placements"] if p["entity_id"] != "umbilical_collar"]
        hoist = berth["fixtures"]["cargo_hoist"]
        hoist["state"] = "open"
        hoist.pop("required_tags")
        hoist["required_tag"] = "dock_clearance"
        loaded = state_from_dict(data)
        b = loaded.nodes["stn_a_berth"]
        self.assertIn("umbilical_collar", b.fixtures)
        self.assertTrue(any(p.entity_id == "umbilical_collar" for p in b.placements))
        self.assertEqual(b.fixtures["cargo_hoist"].state, "open")
        self.assertIn("heavy_lift", b.fixtures["cargo_hoist"].required_tags)
        self.assertIn("scrip_shift", loaded.item_catalog)


class TestSolvability(unittest.TestCase):
    """Static check: every start can reach all 14 nodes and recruit all 3 companions."""

    @classmethod
    def setUpClass(cls):
        cls.nodes = json.loads((DEFAULT_DATA_DIR / "nodes.json").read_text())
        cls.items = {i["id"]: i for i in json.loads((DEFAULT_DATA_DIR / "items.json").read_text())}
        comps = json.loads((DEFAULT_DATA_DIR / "companions.json").read_text())
        cls.comp_tags = {c["id"]: c["capability_tag"] for c in comps}

    def explore(self, anchor_id, routine_cap):
        nodes = {n["id"]: n for n in self.nodes}
        have_items, companions = {anchor_id}, set()
        caps = {routine_cap}
        opened = {f["id"] for n in self.nodes for f in n["fixtures"].values()
                  if f["state"] in ("open", "active")}
        reached = {"stn_a_bunkroom"}
        while True:
            before = (len(have_items), len(companions), len(caps), len(opened), len(reached))
            tags = set(caps) | {self.comp_tags[c] for c in companions}
            for i in have_items:
                tags |= set(self.items[i]["tags"])
            for nid in list(reached):
                node = nodes[nid]
                for f in node["fixtures"].values():
                    fits = not f.get("required_tags") or bool(tags & set(f["required_tags"]))
                    effect = f.get("on_use_effect")
                    if fits:
                        opened.add(f["id"])
                    if effect == "scavenge" and f["id"] in opened:
                        have_items |= set(f.get("yields", []))
                    elif effect == "harvest" and fits:
                        have_items |= set(f.get("yields") or ["algae_paste"])
                    elif effect == "smelt":
                        if "mineral" in tags:
                            have_items |= {"scrap_metal", "tool_prybar"}
                        if "salvage" in tags:
                            have_items.add("fitting_copper")
                    elif effect == "override" and fits:
                        if f.get("grants_capability"):
                            caps.add(f["grants_capability"])
                        if f.get("opens_fixture"):
                            opened.add(f["opens_fixture"])
                for a in node["actors"].values():
                    if tags & set(a.get("trade_required_tags", [])):
                        have_items.add(a["trade_offered_id"])
                        if a.get("companion_unlock"):
                            companions.add(a["companion_unlock"])
                for e in node["edges"].values():
                    gate = e.get("gated_by_fixture")
                    if (not gate or gate in opened) and (not e.get("requires_capability") or e["requires_capability"] in tags):
                        reached.add(e["target_node_id"])
            if (len(have_items), len(companions), len(caps), len(opened), len(reached)) == before:
                return reached, companions, tags

    def test_every_start_reaches_everything(self):
        required = {t for n in self.nodes for f in n["fixtures"].values() for t in f.get("required_tags", [])}
        for anchor_id in ANCHOR_CHOICES.values():
            for _, routine_cap in ROUTINE_CHOICES.values():
                with self.subTest(anchor=anchor_id, routine=routine_cap):
                    reached, companions, tags = self.explore(anchor_id, routine_cap)
                    self.assertEqual(len(reached), 14)
                    self.assertEqual(companions, set(self.comp_tags))
                    # Every fixture requirement has at least one obtainable tag
                    for n in self.nodes:
                        for f in n["fixtures"].values():
                            if f.get("required_tags"):
                                self.assertTrue(tags & set(f["required_tags"]), f["id"])
                    self.assertTrue(required)


if __name__ == "__main__":
    unittest.main()
