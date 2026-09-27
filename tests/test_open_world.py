import unittest
from pathlib import Path
from core.presets import init_game_state, DEFAULT_DATA_DIR
from core.reducers import (
    reduce_scavenge, reduce_use, reduce_talk, reduce_inspect,
    reduce_move, reduce_interact_go, reduce_interact_scavenge,
    reduce_interact_use, reduce_interact_talk, reduce_interact_cancel,
    reduce_barter, ALL_ITEMS_BY_ID, ALL_COMPANIONS_BY_ID
)
from core.actions import dispatch_action
from core.tick import process_tick
from core.types import Exposure, FixtureState, Item, ItemCategory, Companion


class TestOpenWorldRPG(unittest.TestCase):
    def setUp(self):
        self.preset_dir = DEFAULT_DATA_DIR
        self.state = init_game_state(self.preset_dir, "Explorer", 1, 1)

    def test_scavenge_all_container_yields(self):
        """Verify each container fixture yields every item listed in its data."""
        containers = {
            f.id: f.yields for node in self.state.nodes.values()
            for f in node.fixtures.values() if f.on_use_effect == "scavenge"
        }
        self.assertEqual(len(containers), 10)
        for fixture_id, yields in containers.items():
            # Find which node hosts this fixture
            host_node_id = None
            for nid, node in self.state.nodes.items():
                if fixture_id in node.fixtures:
                    host_node_id = nid
                    break
            self.assertIsNotNone(host_node_id, f"Fixture {fixture_id} not found in any node.")

            # Prepare state at that node
            st = self.state._replace(current_node_id=host_node_id)
            fix = st.nodes[host_node_id].fixtures[fixture_id]

            # If sealed with tool requirement (e.g. freight_crate), provide the required tool
            if fix.state in (FixtureState.SEALED.value, FixtureState.LOCKED.value) and fix.required_tags:
                prybar = ALL_ITEMS_BY_ID["tool_prybar"]
                st = st._replace(character=st.character._replace(inventory=st.character.inventory + (prybar,)))

            # Execute scavenge
            st_scavenged = reduce_scavenge(st, fixture_id)
            for expected_item_id in yields:
                self.assertTrue(
                    any(it.id == expected_item_id for it in st_scavenged.character.inventory),
                    f"Scavenging {fixture_id} did not yield {expected_item_id}."
                )
            # Verify fixture is now SPENT
            updated_fix = st_scavenged.nodes[host_node_id].fixtures[fixture_id]
            self.assertEqual(updated_fix.state, FixtureState.SPENT.value)

            # Cannot scavenge twice
            st_twice = reduce_scavenge(st_scavenged, fixture_id)
            self.assertTrue(any("picked clean" in m for m in st_twice.message_buffer))

    def test_sealed_container_requires_tool_and_wears_out(self):
        """Verify freight_crate requires force_lever tool and degrades the tool without conduit_mastery."""
        # stn_b_dock has freight_crate (sealed, required_tag: force_lever)
        st = self.state._replace(current_node_id="stn_b_dock")
        # Without tool, scavenge fails
        st_no_tool = reduce_scavenge(st, "freight_crate")
        self.assertTrue(any("sealed tight" in m for m in st_no_tool.message_buffer))
        self.assertFalse(any(it.id == "chit_transit" for it in st_no_tool.character.inventory))

        # With prybar (integrity 3)
        prybar = ALL_ITEMS_BY_ID["tool_prybar"]._replace(integrity=3)
        st_with_tool = st._replace(character=st.character._replace(inventory=(prybar,)))
        st_opened = reduce_scavenge(st_with_tool, "freight_crate")
        self.assertTrue(any(it.id == "chit_transit" for it in st_opened.character.inventory))
        # Tool lost 1 integrity
        tool_after = next(it for it in st_opened.character.inventory if it.id == "tool_prybar")
        self.assertEqual(tool_after.integrity, 2)

        # With conduit_mastery, tool integrity does not degrade
        caps = st_with_tool.character.unlocked_capabilities | {"conduit_mastery"}
        st_master = st_with_tool._replace(character=st_with_tool.character._replace(unlocked_capabilities=caps))
        st_opened_master = reduce_scavenge(st_master, "freight_crate")
        tool_master_after = next(it for it in st_opened_master.character.inventory if it.id == "tool_prybar")
        self.assertEqual(tool_master_after.integrity, 3)

    def test_scavenger_instinct_grants_bonus_scrap(self):
        """Verify scavenger_instinct grants bonus scrap_metal when scavenging."""
        st = self.state._replace(current_node_id="stn_a_bunkroom")
        # Personal locker yields wire_spool
        caps = st.character.unlocked_capabilities | {"scavenger_instinct"}
        st_perk = st._replace(character=st.character._replace(unlocked_capabilities=caps))
        st_result = reduce_scavenge(st_perk, "personal_locker")
        self.assertTrue(any(it.id == "wire_spool" for it in st_result.character.inventory))
        self.assertTrue(any(it.id == "scrap_metal" for it in st_result.character.inventory))
        self.assertTrue(any("Sharp Eye: Found bonus scrap metal" in m for m in st_result.message_buffer))

    def test_harvest_algae_basin(self):
        """Verify harvesting algae basin using bio_filter capability yields algae_paste."""
        # stn_a_hab has algae_basin (requires bio_filter)
        st = self.state._replace(current_node_id="stn_a_hab")
        # Grant bio_filter capability (algae tender background or comp_mira)
        caps = st.character.unlocked_capabilities | {"bio_filter"}
        spanner = ALL_ITEMS_BY_ID["tool_spanner"]
        st = st._replace(character=st.character._replace(
            unlocked_capabilities=caps,
            inventory=(spanner,)
        ))

        st_harvested = reduce_use(st, "tool_spanner", "algae_basin")
        self.assertTrue(any(it.id == "algae_paste" for it in st_harvested.character.inventory))
        self.assertTrue(any("Harvested fresh algae paste" in m for m in st_harvested.message_buffer))

    def test_smelt_ore_and_scrap_in_crucible(self):
        """Ore forges a pry-bar only with Making Parts; scrap always casts a copper fitting."""
        # luna_smelter has smelting_crucible
        st = self.state._replace(current_node_id="luna_smelter")
        ore = ALL_ITEMS_BY_ID["ore_sample"]

        # 0. Ore without Making Parts melts down to scrap
        st_raw = st._replace(character=st.character._replace(inventory=(ore,)))
        st_melted = reduce_use(st_raw, "ore_sample", "smelting_crucible")
        self.assertTrue(any(it.id == "scrap_metal" for it in st_melted.character.inventory))
        self.assertFalse(any(it.id == "tool_prybar" for it in st_melted.character.inventory))

        # 1. Ore -> Pry-Bar with scrap_fabrication
        caps = st.character.unlocked_capabilities | {"scrap_fabrication"}
        st_ore = st._replace(character=st.character._replace(inventory=(ore,), unlocked_capabilities=caps))
        st_smelt_ore = reduce_use(st_ore, "ore_sample", "smelting_crucible")
        self.assertTrue(any(it.id == "tool_prybar" for it in st_smelt_ore.character.inventory))
        self.assertFalse(any(it.id == "ore_sample" for it in st_smelt_ore.character.inventory))
        self.assertTrue(any("Refined" in m and "Thermal Pry-Bar" in m for m in st_smelt_ore.message_buffer))

        # 2. Scrap -> Copper Fitting
        scrap = ALL_ITEMS_BY_ID["scrap_metal"]
        st_scrap = st._replace(character=st.character._replace(inventory=(scrap,)))
        st_smelt_scrap = reduce_use(st_scrap, "scrap_metal", "smelting_crucible")
        self.assertTrue(any(it.id == "fitting_copper" for it in st_smelt_scrap.character.inventory))
        self.assertFalse(any(it.id == "scrap_metal" for it in st_smelt_scrap.character.inventory))
        self.assertTrue(any("Melted" in m and "Copper Pipe Fitting" in m for m in st_smelt_scrap.message_buffer))

    def test_override_crypto_terminal(self):
        """Overriding the crypto terminal with wire forges a dock clearance and spends the terminal."""
        st = self.state._replace(current_node_id="stn_b_array")
        wire = ALL_ITEMS_BY_ID["wire_spool"]
        st = st._replace(character=st.character._replace(inventory=(wire,)))
        st_override = reduce_use(st, "wire_spool", "crypto_terminal")
        self.assertTrue(any("Bypassed" in m for m in st_override.message_buffer))
        self.assertIn("dock_clearance", st_override.character.unlocked_capabilities)
        self.assertEqual(st_override.nodes["stn_b_array"].fixtures["crypto_terminal"].state, FixtureState.SPENT.value)
        # Wire has 2 integrity, one point spent
        self.assertEqual(next(i for i in st_override.character.inventory if i.id == "wire_spool").integrity, 1)

    def test_npc_trades_and_companion_recruitment(self):
        """Verify all NPCs across Alpha, Beta, Luna execute valid trades and companion recruitment."""
        # 1. Radek (stn_a_sub): trades prybar (force_lever) -> chit_transit, recruits comp_radek
        st_radek = self.state._replace(current_node_id="stn_a_sub")
        prybar = ALL_ITEMS_BY_ID["tool_prybar"]
        st_radek = st_radek._replace(character=st_radek.character._replace(inventory=(prybar,)))
        res_radek = reduce_barter(st_radek, "npc_radek")
        self.assertTrue(any(it.id == "chit_transit" for it in res_radek.character.inventory))
        self.assertTrue(any(c.id == "comp_radek" for c in res_radek.companions))
        self.assertTrue(any("Companion joined" in m for m in res_radek.message_buffer))

        # 2. Tarek (stn_b_dock): trades dice_steel (barter_token) -> wire_spool, recruits comp_tarek
        st_tarek = self.state._replace(current_node_id="stn_b_dock")
        dice = ALL_ITEMS_BY_ID["dice_steel"]
        st_tarek = st_tarek._replace(character=st_tarek.character._replace(inventory=(dice,)))
        res_tarek = reduce_barter(st_tarek, "npc_tarek")
        self.assertTrue(any(it.id == "wire_spool" for it in res_tarek.character.inventory))
        self.assertTrue(any(c.id == "comp_tarek" for c in res_tarek.companions))

        # 3. Mira (stn_a_hab): trades fitting_copper (conductive) -> flask_water, recruits comp_mira
        st_mira = self.state._replace(current_node_id="stn_a_hab")
        fitting = ALL_ITEMS_BY_ID["fitting_copper"]
        st_mira = st_mira._replace(character=st_mira.character._replace(inventory=(fitting,)))
        res_mira = reduce_barter(st_mira, "npc_mira")
        self.assertTrue(any(it.id == "flask_water" for it in res_mira.character.inventory))
        self.assertTrue(any(c.id == "comp_mira" for c in res_mira.companions))

        # 4. Kovac (stn_b_fuel): trades ration_dry (nutrition) -> seal_patch
        st_kovac = self.state._replace(current_node_id="stn_b_fuel")
        ration = ALL_ITEMS_BY_ID["ration_dry"]
        st_kovac = st_kovac._replace(character=st_kovac.character._replace(inventory=(ration,)))
        res_kovac = reduce_barter(st_kovac, "npc_kovac")
        self.assertTrue(any(it.id == "seal_patch" for it in res_kovac.character.inventory))

        # 5. Chen (luna_dome): trades scrap_metal (salvage) -> tool_spanner
        st_chen = self.state._replace(current_node_id="luna_dome")
        scrap = ALL_ITEMS_BY_ID["scrap_metal"]
        st_chen = st_chen._replace(character=st_chen.character._replace(inventory=(scrap,)))
        res_chen = reduce_barter(st_chen, "npc_chen")
        self.assertTrue(any(it.id == "tool_spanner" for it in res_chen.character.inventory))

        # 6. Vance (luna_smelter): trades ore_sample (mineral) -> tool_prybar
        st_vance = self.state._replace(current_node_id="luna_smelter")
        ore = ALL_ITEMS_BY_ID["ore_sample"]
        st_vance = st_vance._replace(character=st_vance.character._replace(inventory=(ore,)))
        res_vance = reduce_barter(st_vance, "npc_vance")
        self.assertTrue(any(it.id == "tool_prybar" for it in res_vance.character.inventory))

    def test_crew_coordination_exposure_mitigation(self):
        """Verify crew_coordination reduces exposure accumulation when traveling with any companion."""
        # Subdeck is hostile: base vitals pressure 65.0, temp -25, rad 2.0
        # Normal accumulation without crew_coordination: delta_p = 25/30 = 0.833, delta_t = 15/20 = 0.75
        st = self.state._replace(current_node_id="stn_a_sub")
        st_normal = process_tick(st, "Solo wait")
        normal_p = st_normal.character.exposure.pressure_debt
        normal_t = st_normal.character.exposure.thermal_stress

        # With crew_coordination AND a companion: deltas reduced by 0.2
        caps = st.character.unlocked_capabilities | {"crew_coordination"}
        radek = ALL_COMPANIONS_BY_ID["comp_radek"]
        st_crew = st._replace(
            character=st.character._replace(unlocked_capabilities=caps),
            companions=(radek,)
        )
        st_mitigated = process_tick(st_crew, "Crew wait")
        mitigated_p = st_mitigated.character.exposure.pressure_debt
        mitigated_t = st_mitigated.character.exposure.thermal_stress

        self.assertAlmostEqual(mitigated_p, max(0.0, normal_p - 0.2), places=2)
        self.assertAlmostEqual(mitigated_t, max(0.0, normal_t - 0.2), places=2)

    def test_wayfarer_doubles_decay_interval_and_grants_transit(self):
        """Verify wayfarer doubles sustenance decay interval to 20 cycles and grants transit clearance."""
        # Sustenance decay test
        ration = ALL_ITEMS_BY_ID["ration_dry"]
        st = self.state._replace(
            character=self.state.character._replace(
                inventory=(ration,),
                unlocked_capabilities=frozenset({"wayfarer"})
            ),
            cycle=9
        )
        # At tick 10, normal decay would trigger. With wayfarer, it does not.
        st10 = process_tick(st, "Cycle 10")
        item10 = next(i for i in st10.character.inventory if i.id == "ration_dry")
        self.assertEqual(item10.integrity, 3)

        # Advance to tick 20
        st19 = st10._replace(cycle=19)
        st20 = process_tick(st19, "Cycle 20")
        item20 = next(i for i in st20.character.inventory if i.id == "ration_dry")
        self.assertEqual(item20.integrity, 2)

        # Transit clearance test: shuttle gate in stn_a_berth requires transit_clearance
        st_berth = self.state._replace(
            current_node_id="stn_a_berth",
            character=self.state.character._replace(
                unlocked_capabilities=frozenset({"wayfarer"}),
                inventory=(ALL_ITEMS_BY_ID["fitting_copper"],) # Carry non-transit item
            )
        )
        # Use on shuttle_gate succeeds because wayfarer provides transit_clearance
        st_shuttle = reduce_use(st_berth, "fitting_copper", "shuttle_gate")
        gate = st_shuttle.nodes["stn_a_berth"].fixtures["shuttle_gate"]
        self.assertEqual(gate.state, FixtureState.OPEN.value)

    def test_progression_tree_unlock_pipeline(self):
        """Test the 12-node progression tree unlock chain across all 3 branches."""
        # Branch 1: Engineering
        # 1. seam_discipline (use spigot_01 with flask_water)
        st = self.state
        flask = ALL_ITEMS_BY_ID["flask_water"]._replace(integrity=1)
        st = st._replace(character=st.character._replace(inventory=st.character.inventory + (flask,)))
        st1 = reduce_use(st, "flask_water", "spigot_01")
        self.assertIn("seam_discipline", st1.character.unlocked_capabilities)

        # 2. scrap_fabrication (use/scavenge salvage_bin in berth)
        st1_berth = st1._replace(current_node_id="stn_a_berth")
        st2 = reduce_scavenge(st1_berth, "salvage_bin")
        self.assertIn("scrap_fabrication", st2.character.unlocked_capabilities)

        # 3. bulkhead_ear (visit stn_a_sub)
        st3 = process_tick(st2._replace(current_node_id="stn_a_sub"), "Enter subdeck")
        self.assertIn("bulkhead_ear", st3.character.unlocked_capabilities)

        # 4. conduit_mastery (use jammed_valve in stn_a_sub with force_lever tool)
        prybar = ALL_ITEMS_BY_ID["tool_prybar"]
        st3_tool = st3._replace(character=st3.character._replace(inventory=st3.character.inventory + (prybar,)))
        st4 = reduce_use(st3_tool, "tool_prybar", "jammed_valve")
        self.assertIn("conduit_mastery", st4.character.unlocked_capabilities)

        # Branch 2: Exploration
        # 1. scavenger_instinct (scavenge personal_locker)
        st_exp = self.state
        st_scav = reduce_scavenge(st_exp, "personal_locker")
        self.assertIn("scavenger_instinct", st_scav.character.unlocked_capabilities)

        # 2. crew_coordination (trade with npc_radek)
        prybar = ALL_ITEMS_BY_ID["tool_prybar"]
        st_trade = st_scav._replace(
            current_node_id="stn_a_sub",
            character=st_scav.character._replace(inventory=(prybar,))
        )
        st_crew = reduce_barter(st_trade, "npc_radek")
        self.assertIn("crew_coordination", st_crew.character.unlocked_capabilities)

        # 3. signal_analysis (use comms_rack in stn_b_array)
        st_array = st_crew._replace(
            current_node_id="stn_b_array",
            character=st_crew.character._replace(inventory=(ALL_ITEMS_BY_ID["fitting_copper"],))
        )
        st_comms = reduce_use(st_array, "fitting_copper", "comms_rack")
        self.assertIn("signal_analysis", st_comms.character.unlocked_capabilities)

        # 4. wayfarer (visit luna_dome)
        st_dome = process_tick(st_comms._replace(current_node_id="luna_dome"), "Enter dome")
        self.assertIn("wayfarer", st_dome.character.unlocked_capabilities)

    def test_proximity_menu_and_wasd_interactions(self):
        """Verify WASD movement lands on entity tiles, activates proximity menu, and executes actions."""
        # stn_a_bunkroom: player starts at (2, 2).
        # personal_locker is placed at (1, 3).
        # Move up (w) to (1, 2), then right (d) to (1, 3).
        st = self.state
        st = dispatch_action(st, "w")
        self.assertFalse(st.proximity_menu_active)
        st = dispatch_action(st, "d")
        # Player is now at (1, 3), on personal_locker!
        self.assertEqual((st.player_row, st.player_col), (1, 3))
        self.assertTrue(st.proximity_menu_active)
        self.assertTrue(any("Near: Crew Storage Locker" in m for m in st.message_buffer))
        self.assertTrue(any("[F] Search" in m for m in st.message_buffer))

        # Single key 'f' while on a container searches it; the menu refreshes without [F]
        st_scav = dispatch_action(st, "f")
        self.assertTrue(st_scav.proximity_menu_active)
        self.assertFalse(any("[F] Search" in m for m in st_scav.message_buffer))
        self.assertTrue(any(it.id == "wire_spool" for it in st_scav.character.inventory))

        # Slash commands: /scavenge, /search, /inspect
        st_bunk = self.state._replace(current_node_id="stn_a_bunkroom")
        st_cmd = dispatch_action(st_bunk, "/inspect spigot_01")
        self.assertTrue(any("Water Spigot" in m for m in st_cmd.message_buffer))


if __name__ == "__main__":
    unittest.main()
