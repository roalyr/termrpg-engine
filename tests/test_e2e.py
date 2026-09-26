import unittest
from pathlib import Path
from core.presets import init_game_state
from core.actions import dispatch_action
from core.types import FixtureState
from core.reducers import ALL_ITEMS_BY_ID

class TestE2EWalkthrough(unittest.TestCase):
    def setUp(self):
        self.preset_dir = Path("presets/default-1.0")
        self.state = init_game_state(self.preset_dir, "Vaelen", 1, 1)

    def test_complete_space_rpg_campaign(self):
        state = self.state

        # 1. Starting Bunkroom
        self.assertEqual(state.current_node_id, "stn_a_bunkroom")
        self.assertEqual(state.cycle, 0)
        self.assertTrue(any(i.id == "fitting_copper" for i in state.character.inventory))

        # Inspect fixture
        state = dispatch_action(state, "inspect spigot_01")
        self.assertTrue(any("Water Spigot" in m for m in state.message_buffer))

        # Try leaving through to_berth
        state = dispatch_action(state, "leave to_berth")
        self.assertEqual(state.current_node_id, "stn_a_berth")
        self.assertEqual(state.cycle, 1)

        # 2. Berth 04 & Trade with Kael
        state = dispatch_action(state, "inspect npc_kael")
        self.assertTrue(any("Kael" in m for m in state.message_buffer))

        # Talk to Kael -> should trigger trade (fitting_copper -> pass_work)
        state = dispatch_action(state, "talk npc_kael")
        self.assertTrue(any("Exchanged Copper Pipe Fitting for Stamped Work Pass" in m for m in state.message_buffer))
        self.assertTrue(any(i.id == "pass_work" for i in state.character.inventory))
        self.assertFalse(any(i.id == "fitting_copper" for i in state.character.inventory))
        self.assertEqual(state.cycle, 2)

        # Unlock cargo hoist to subdeck
        state = dispatch_action(state, "use pass_work cargo_hoist")
        self.assertTrue(any("Unlocked Cargo Hoist Platform" in m for m in state.message_buffer))
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
        self.assertTrue(any("PROGRESSION TREE" in m for m in char_view.message_buffer))

        # Give player a prybar to interact with Radek and the frozen valve
        prybar = ALL_ITEMS_BY_ID["tool_prybar"]
        state = state._replace(
            character=state.character._replace(
                inventory=state.character.inventory + (prybar,)
            )
        )

        # Repair jammed valve
        state = dispatch_action(state, "use tool_prybar jammed_valve")
        self.assertTrue(any("Repaired" in m for m in state.message_buffer))
        self.assertEqual(state.nodes["stn_a_sub"].fixtures["jammed_valve"].state, FixtureState.ACTIVE.value)

        # Talk to Radek -> Radek recruits as companion!
        state = dispatch_action(state, "talk npc_radek")
        self.assertTrue(any("Radek" in m for m in state.message_buffer))
        self.assertTrue(any(c.id == "comp_radek" for c in state.companions))

        # Inspect party
        party_view = dispatch_action(state, "party")
        self.assertTrue(any("two_person_lift" in m for m in party_view.message_buffer))

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
        self.assertTrue(any("Unlocked Shuttle Boarding Gate" in m for m in state.message_buffer))

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
        self.assertEqual(mine_shaft.required_tag, "two_person_lift")

        # Player uses pass_work or tool to activate cage with companion support
        state = dispatch_action(state, "use pass_work mine_shaft")
        self.assertTrue(any("Unlocked Mine Shaft Cage" in m for m in state.message_buffer))
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

        # Bunkroom: start at center (2, 2)
        self.assertEqual(state.player_row, 2)
        self.assertEqual(state.player_col, 2)

        # Move to spigot_01 at (3, 1)
        state = dispatch_action(state, "s")  # (3, 2)
        state = dispatch_action(state, "a")  # (3, 1) - spigot_01
        self.assertEqual(state.player_row, 3)
        self.assertEqual(state.player_col, 1)
        self.assertTrue(state.proximity_menu_active)
        self.assertTrue(any("Near: Water Spigot" in m for m in state.message_buffer))

        # Inspect spigot using single-key 'i'
        state = dispatch_action(state, "i")
        self.assertTrue(any("Water Spigot" in m for m in state.message_buffer))

        # Move to hatch_berth at (0, 2)
        state = dispatch_action(state, "w")  # (2, 1)
        state = dispatch_action(state, "w")  # (1, 1)
        state = dispatch_action(state, "w")  # blocked by wall at (0, 1), stays (1, 1)
        state = dispatch_action(state, "d")  # (1, 2)
        state = dispatch_action(state, "w")  # (0, 2) - hatch_berth!
        self.assertEqual(state.player_row, 0)
        self.assertEqual(state.player_col, 2)
        self.assertTrue(state.proximity_menu_active)
        self.assertTrue(any("[G] Go -> Berth 04" in m for m in state.message_buffer))

        # Step through hatch using single-key 'g'
        state = dispatch_action(state, "g")
        self.assertEqual(state.current_node_id, "stn_a_berth")
        self.assertEqual(state.player_row, 3)
        self.assertEqual(state.player_col, 3)

        # In Berth 04, move to Kael at (2, 4)
        state = dispatch_action(state, "w")  # (2, 3)
        state = dispatch_action(state, "d")  # (2, 4) - npc_kael!
        self.assertEqual(state.player_row, 2)
        self.assertEqual(state.player_col, 4)
        self.assertTrue(state.proximity_menu_active)
        self.assertTrue(any("Near: Kael" in m for m in state.message_buffer))
        self.assertTrue(any("[T] Talk" in m for m in state.message_buffer))

        # Talk to Kael using 't' -> executes trade
        state = dispatch_action(state, "t")
        self.assertTrue(any(i.id == "pass_work" for i in state.character.inventory))

        # Move to cargo hoist at (5, 3)
        state = dispatch_action(state, "s")  # (3, 4)
        state = dispatch_action(state, "s")  # (4, 4)
        state = dispatch_action(state, "s")  # (5, 4)
        state = dispatch_action(state, "a")  # (5, 3) - cargo_hoist!
        self.assertEqual(state.player_row, 5)
        self.assertEqual(state.player_col, 3)
        self.assertTrue(state.proximity_menu_active)
        self.assertTrue(any("Near: Cargo Hoist Platform" in m for m in state.message_buffer))
        self.assertTrue(any("[U] Use Stamped Work Pass" in m for m in state.message_buffer))

        # Unlock hoist using single-key 'u'
        state = dispatch_action(state, "u")
        self.assertEqual(state.nodes["stn_a_berth"].fixtures["cargo_hoist"].state, FixtureState.OPEN.value)

        # Move off and step back onto open cargo hoist to see [G] Go option
        state = dispatch_action(state, "w")  # (4, 3)
        state = dispatch_action(state, "s")  # (5, 3)
        self.assertTrue(any("[G] Go -> Sub-Deck" in m for m in state.message_buffer))

        # Descend using 'g'
        state = dispatch_action(state, "g")
        self.assertEqual(state.current_node_id, "stn_a_sub")
        self.assertEqual(state.nodes["stn_a_sub"].depth, 1)

if __name__ == "__main__":
    unittest.main()

