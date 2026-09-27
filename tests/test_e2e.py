import unittest
from tests.helpers import menu_line, walk_to, find
from pathlib import Path
from core.presets import init_game_state, DEFAULT_DATA_DIR
from core.actions import dispatch_action
from core.types import FixtureState
from core.reducers import ALL_ITEMS_BY_ID

class TestE2EWalkthrough(unittest.TestCase):
    def setUp(self):
        self.preset_dir = DEFAULT_DATA_DIR
        self.state = init_game_state(self.preset_dir, "Vaelen", 1, 1)

    def test_complete_space_rpg_campaign(self):
        state = self.state

        # 1. Starting Bunkroom
        self.assertEqual(state.current_node_id, "stn_a_bunkroom")
        self.assertEqual(state.cycle, 0)
        self.assertTrue(any(i.id == "fitting_copper" for i in state.character.inventory))

        # Inspect fixture with slash command
        state = dispatch_action(state, "/inspect spigot_01")
        self.assertTrue(any("Water Tap" in m for m in state.message_buffer))

        # Check pack with slash command
        pack_state = dispatch_action(state, "/pack")
        self.assertTrue(any("PACK" in m for m in pack_state.message_buffer))

        # Leaving walks to the hatch first: one cycle per tile from the bunkroom center
        _, hr, hc = find(state, "hatch_berth")
        walk = abs(hr - state.player_row) + abs(hc - state.player_col)
        state = dispatch_action(state, "leave to_berth")
        self.assertEqual(state.current_node_id, "stn_a_berth")
        self.assertEqual(state.cycle, walk)

        # 2. Berth 04 & Trade with Kael
        state = dispatch_action(state, "inspect npc_kael")
        self.assertTrue(any("Kael" in m for m in state.message_buffer))

        # Talk to Kael -> offer only; barter executes the trade (fitting_copper -> pass_work)
        state = dispatch_action(state, "talk npc_kael")
        self.assertTrue(any("Offer:" in m for m in state.message_buffer))
        state = dispatch_action(state, "barter npc_kael")
        self.assertTrue(any("Got: Work Pass, for your Pipe Fitting" in m for m in state.message_buffer))
        self.assertTrue(any(i.id == "pass_work" for i in state.character.inventory))
        self.assertFalse(any(i.id == "fitting_copper" for i in state.character.inventory))
        self.assertEqual(state.cycle, walk + 2)

        # Unlock cargo hoist to subdeck
        state = dispatch_action(state, "use pass_work cargo_hoist")
        self.assertTrue(any("The Cargo Hoist opens" in m for m in state.message_buffer))
        self.assertEqual(state.nodes["stn_a_berth"].fixtures["cargo_hoist"].state, FixtureState.OPEN.value)

        # 3. Descend to Sub-Deck (Depth 1)
        state = dispatch_action(state, "leave to_subdeck")
        self.assertEqual(state.current_node_id, "stn_a_sub")
        self.assertEqual(state.nodes["stn_a_sub"].depth, 1)

        # Check progression tree: Bulkhead Ear requires visiting stn_a_sub
        # Seam Discipline was unlocked when visiting or fixture used
        self.assertIn("stn_a_sub", state.visited_nodes)
        bulkhead_node = next(t for t in state.tree if t.id == "bulkhead_ear")
        # Bulkhead ear prerequisite is seam_discipline. Let's inspect tree
        char_view = dispatch_action(state, "character")
        self.assertTrue(any("SKILLS" in m for m in char_view.message_buffer))

        # Give player a prybar to interact with Radek and the frozen valve
        prybar = ALL_ITEMS_BY_ID["tool_prybar"]
        state = state._replace(
            character=state.character._replace(
                inventory=state.character.inventory + (prybar,)
            )
        )

        # Repair jammed valve
        state = dispatch_action(state, "use tool_prybar jammed_valve")
        self.assertTrue(any("is fixed" in m for m in state.message_buffer))
        self.assertEqual(state.nodes["stn_a_sub"].fixtures["jammed_valve"].state, FixtureState.ACTIVE.value)

        # Barter with Radek -> Radek recruits as companion!
        state = dispatch_action(state, "barter npc_radek")
        self.assertTrue(any("Radek" in m for m in state.message_buffer))
        self.assertTrue(any(c.id == "comp_radek" for c in state.companions))

        # Inspect party
        party_view = dispatch_action(state, "party")
        self.assertTrue(any("second lifter" in m for m in party_view.message_buffer))

        # 4. Ascend back to Berth 04
        state = dispatch_action(state, "leave to_berth")
        self.assertEqual(state.current_node_id, "stn_a_berth")

        # 5. Board Shuttle to Luna
        # Unlock shuttle gate with transit pass
        transit_token = ALL_ITEMS_BY_ID["chit_transit"]
        state = state._replace(
            character=state.character._replace(
                inventory=state.character.inventory + (transit_token,)
            )
        )
        state = dispatch_action(state, "use chit_transit shuttle_gate")
        self.assertTrue(any("The Shuttle Gate opens" in m for m in state.message_buffer))

        state = dispatch_action(state, "leave to_shuttle")
        self.assertEqual(state.current_node_id, "shuttle_ab")

        # Unlock lunar descent hatch
        token2 = ALL_ITEMS_BY_ID["chit_transit"]
        state = state._replace(
            character=state.character._replace(
                inventory=state.character.inventory + (token2,)
            )
        )
        state = dispatch_action(state, "use chit_transit gate_luna")
        self.assertEqual(state.nodes["shuttle_ab"].fixtures["gate_luna"].state, FixtureState.OPEN.value)

        # Grant vacuum traversal clearance for lunar surface
        state = state._replace(
            character=state.character._replace(
                unlocked_capabilities=state.character.unlocked_capabilities | {"vacuum_traverse"}
            )
        )

        # Descend to Luna surface pad
        state = dispatch_action(state, "leave to_luna")
        self.assertEqual(state.current_node_id, "luna_pad")
        self.assertEqual(state.nodes["luna_pad"].environment, "vacuum")

        # Move to Habitat Dome
        state = dispatch_action(state, "leave to_dome")
        self.assertEqual(state.current_node_id, "luna_dome")

        # Move to Smelter Flat
        state = dispatch_action(state, "leave to_smelter")
        self.assertEqual(state.current_node_id, "luna_smelter")

        # Mine shaft requires 'two_person_lift'
        # Radek provides this capability!
        mine_shaft = state.nodes["luna_smelter"].fixtures["mine_shaft"]
        self.assertIn("two_person_lift", mine_shaft.required_tags)

        # Player uses pass_work or tool to activate cage with companion support
        state = dispatch_action(state, "use pass_work mine_shaft")
        self.assertTrue(any("The Mine Lift opens" in m for m in state.message_buffer))
        self.assertEqual(state.nodes["luna_smelter"].fixtures["mine_shaft"].state, FixtureState.OPEN.value)

        # Descend into Deep Mine
        state = dispatch_action(state, "leave to_mine")
        self.assertEqual(state.current_node_id, "luna_mine")
        self.assertIn("luna_mine", state.visited_nodes)

        # Check trench hardened attunement (requires visiting luna_mine and vacuum_walk)
        # Verify action log and state integrity
        self.assertGreater(state.cycle, 10)
        self.assertTrue(len(state.action_log) > 5)

        # View map
        state = dispatch_action(state, "map")
        self.assertEqual(state.active_view, "map_topology")
        state = dispatch_action(state, "back")
        self.assertEqual(state.active_view, "compartment")

        # Quit cleanly
        state = dispatch_action(state, "quit")
        self.assertFalse(state.is_running)

    def test_wasd_and_proximity_menu_e2e_walkthrough(self):
        state = self.state
        bunk = state.nodes["stn_a_bunkroom"]

        # Bunkroom: start at the center
        self.assertEqual((state.player_row, state.player_col), (bunk.size // 2, bunk.size // 2))

        # Walk to the water tap with WASD
        state = walk_to(state, "spigot_01")
        self.assertEqual(find(state, "spigot_01")[1:], (state.player_row, state.player_col))
        self.assertTrue(state.proximity_menu_active)
        self.assertTrue("Water Tap" in menu_line(state))

        # Inspect using single-key 'i'
        state = dispatch_action(state, "i")
        self.assertTrue(any("Water Tap" in m for m in state.message_buffer))

        # Walking into a wall does nothing: no time, no message
        before = state._replace(player_row=1, player_col=1, message_buffer=())
        blocked = dispatch_action(before, "w")
        self.assertEqual(blocked, before)

        # Walk to the hatch and step through with 'g'
        state = walk_to(state, "hatch_berth")
        self.assertTrue("G go to Berth 04" in menu_line(state))
        state = dispatch_action(state, "g")
        self.assertEqual(state.current_node_id, "stn_a_berth")
        berth = state.nodes["stn_a_berth"]
        self.assertEqual((state.player_row, state.player_col), (berth.size // 2, berth.size // 2))

        # Walk to Kael: 't' talks and offers; 'b' barters
        state = walk_to(state, "npc_kael")
        self.assertTrue("Kael" in menu_line(state))
        self.assertTrue("T talk" in menu_line(state))
        state = dispatch_action(state, "t")
        self.assertFalse(any(i.id == "pass_work" for i in state.character.inventory))
        self.assertTrue("B trade" in menu_line(state))
        state = dispatch_action(state, "b")
        self.assertTrue(any(i.id == "pass_work" for i in state.character.inventory))

        # Walk to the cargo hoist and open it with 'u'; [G] is offered immediately
        state = walk_to(state, "cargo_hoist")
        self.assertTrue("U open (Work Pass)" in menu_line(state))
        state = dispatch_action(state, "u")
        self.assertEqual(state.nodes["stn_a_berth"].fixtures["cargo_hoist"].state, FixtureState.OPEN.value)
        self.assertTrue("G go to Sub-Deck" in menu_line(state))

        # Descend using 'g'
        state = dispatch_action(state, "g")
        self.assertEqual(state.current_node_id, "stn_a_sub")
        self.assertEqual(state.nodes["stn_a_sub"].depth, 1)

    def test_open_world_multi_cluster_expedition(self):
        """Full open-world expedition: alternate routes, scavenging, companion recruitment, crafting, and lunar descent."""
        state = self.state  # Starts in stn_a_bunkroom with fitting_copper

        # 1. Scavenge personal locker in bunkroom -> unlocks scavenger_instinct
        state = dispatch_action(state, "/scavenge personal_locker")
        self.assertTrue(any(i.id == "wire_spool" for i in state.character.inventory))
        self.assertIn("scavenger_instinct", state.character.unlocked_capabilities)

        # 2. Open-world bypass: unlock service crawlway (vent_duct) directly to sub-deck
        # Uses player's starting fitting_copper (seal_fitting tag)
        state = dispatch_action(state, "/use fitting_copper vent_duct")
        self.assertEqual(state.nodes["stn_a_bunkroom"].fixtures["vent_duct"].state, FixtureState.OPEN.value)

        # Descend directly into stn_a_sub through the service crawlway
        state = dispatch_action(state, "leave to_sub_vent")
        self.assertEqual(state.current_node_id, "stn_a_sub")

        # 3. Scavenge tool rack in sub-deck for thermal prybar
        state = dispatch_action(state, "/scavenge tool_rack")
        self.assertTrue(any(i.id == "tool_prybar" for i in state.character.inventory))

        # 4. Repair jammed valve using prybar
        state = dispatch_action(state, "/use tool_prybar jammed_valve")
        self.assertEqual(state.nodes["stn_a_sub"].fixtures["jammed_valve"].state, FixtureState.ACTIVE.value)

        # 5. Recruit Radek: trade prybar for transit chit and join party
        state = dispatch_action(state, "/barter npc_radek")
        self.assertTrue(any(c.id == "comp_radek" for c in state.companions))
        self.assertTrue(any(i.id == "chit_transit" for i in state.character.inventory))
        self.assertIn("crew_coordination", state.character.unlocked_capabilities)

        # 6. Ascend to Berth 04 and unlock shuttle gate
        state = dispatch_action(state, "leave to_berth")
        self.assertEqual(state.current_node_id, "stn_a_berth")
        state = dispatch_action(state, "/use chit_transit shuttle_gate")
        self.assertEqual(state.nodes["stn_a_berth"].fixtures["shuttle_gate"].state, FixtureState.OPEN.value)

        # 7. Board Shuttle Hopper
        state = dispatch_action(state, "leave to_shuttle")
        self.assertEqual(state.current_node_id, "shuttle_ab")

        # 8. Travel to Station Beta (stn_b_dock)
        state = dispatch_action(state, "leave to_stn_b")
        self.assertEqual(state.current_node_id, "stn_b_dock")

        # 9. In Station Beta: recruit Tarek with steel dice
        dice = ALL_ITEMS_BY_ID["dice_steel"]
        state = state._replace(character=state.character._replace(inventory=state.character.inventory + (dice,)))
        state = dispatch_action(state, "/barter npc_tarek")
        self.assertTrue(any(c.id == "comp_tarek" for c in state.companions))

        # 10. Visit Sensor Array (stn_b_array) and access comms rack
        state = dispatch_action(state, "leave to_array")
        self.assertEqual(state.current_node_id, "stn_b_array")
        state = dispatch_action(state, "/use wire_spool comms_rack")
        self.assertIn("signal_analysis", state.character.unlocked_capabilities)

        # 11. Return to Dock and board Shuttle Hopper back
        state = dispatch_action(state, "leave to_dock")
        state = dispatch_action(state, "leave to_shuttle")
        self.assertEqual(state.current_node_id, "shuttle_ab")

        # 12. Travel to Luna Surface Pad (requires vacuum_walk or clearance)
        state = state._replace(character=state.character._replace(
            unlocked_capabilities=state.character.unlocked_capabilities | {"vacuum_walk"}
        ))
        # Unlock gate_luna with transit chit
        chit = ALL_ITEMS_BY_ID["chit_transit"]
        state = state._replace(character=state.character._replace(inventory=state.character.inventory + (chit,)))
        state = dispatch_action(state, "/use chit_transit gate_luna")
        state = dispatch_action(state, "leave to_luna")
        self.assertEqual(state.current_node_id, "luna_pad")

        # 13. Enter Luna Habitat Dome -> unlocks wayfarer
        state = dispatch_action(state, "leave to_dome")
        self.assertEqual(state.current_node_id, "luna_dome")
        self.assertIn("wayfarer", state.character.unlocked_capabilities)

        # 14. Enter Luna Smelter
        state = dispatch_action(state, "leave to_smelter")
        self.assertEqual(state.current_node_id, "luna_smelter")

        # Scavenge scrap and smelt into a copper pipe fitting
        scrap = ALL_ITEMS_BY_ID["scrap_metal"]
        state = state._replace(character=state.character._replace(inventory=state.character.inventory + (scrap,)))
        state = dispatch_action(state, "/use scrap_metal smelting_crucible")
        self.assertTrue(any(i.id == "fitting_copper" for i in state.character.inventory))

        # 15. Radek provides 'two_person_lift', so player can operate mine_shaft
        state = dispatch_action(state, "/use fitting_copper mine_shaft")
        self.assertEqual(state.nodes["luna_smelter"].fixtures["mine_shaft"].state, FixtureState.OPEN.value)

        # Descend into the Deep Mine
        state = dispatch_action(state, "leave to_mine")
        self.assertEqual(state.current_node_id, "luna_mine")
        self.assertEqual(state.nodes["luna_mine"].depth, 1)

        # Scavenge ore face in deep mine
        state = dispatch_action(state, "/scavenge ore_face")
        self.assertTrue(any(i.id == "ore_sample" for i in state.character.inventory))

        # Verify final party and capability status
        comp_ids = {c.id for c in state.companions}
        self.assertIn("comp_radek", comp_ids)
        self.assertIn("comp_tarek", comp_ids)
        self.assertTrue(state.is_running)


if __name__ == "__main__":
    unittest.main()

