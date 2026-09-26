import unittest
from pathlib import Path
from core.presets import init_game_state
from core.reducers import (
    reduce_inspect, reduce_talk, reduce_use, reduce_leave,
    reduce_wait, reduce_map, reduce_back, reduce_pack,
    reduce_character, reduce_party, reduce_log, reduce_flavor,
    reduce_help, ALL_ITEMS_BY_ID
)
from core.types import FixtureState, Exposure

class TestReducers(unittest.TestCase):
    def setUp(self):
        self.preset_dir = Path("presets/default-1.0")
        self.state = init_game_state(self.preset_dir, "Vaelen", 1, 1)

    def test_inspect_fixture_and_actor(self):
        # Inspect fixture in bunkroom
        s1 = reduce_inspect(self.state, "spigot_01")
        self.assertTrue(any("Water Spigot" in m for m in s1.message_buffer))

        # Move to berth and inspect Kael
        s_berth = self.state._replace(current_node_id="stn_a_berth")
        s2 = reduce_inspect(s_berth, "npc_kael")
        self.assertTrue(any("Kael" in m for m in s2.message_buffer))

        # Inspect carried item
        s3 = reduce_inspect(self.state, "fitting_copper")
        self.assertTrue(any("Copper Pipe Fitting" in m for m in s3.message_buffer))

        # Inspect non-existent
        s4 = reduce_inspect(self.state, "ghost_entity")
        self.assertTrue(any("Nothing found matching" in m for m in s4.message_buffer))

    def test_inspect_degradation_under_stress(self):
        char = self.state.character._replace(exposure=Exposure(6.0, 0.0, 0.0))
        s_stressed = self.state._replace(character=char)
        s1 = reduce_inspect(s_stressed, "spigot_01")
        self.assertTrue(any("readings unclear" in m for m in s1.message_buffer))

    def test_talk_and_trade(self):
        s_berth = self.state._replace(current_node_id="stn_a_berth")
        # Player has fitting_copper with tag 'seal_fitting' which Kael needs
        s_traded = reduce_talk(s_berth, "npc_kael")
        self.assertTrue(any("Exchanged Copper Pipe Fitting for Stamped Work Pass" in m for m in s_traded.message_buffer))

        # Kael trade is now completed
        kael = s_traded.nodes["stn_a_berth"].actors["npc_kael"]
        self.assertTrue(kael.trade_completed)

        # Fitting was consumed
        self.assertFalse(any(i.id == "fitting_copper" for i in s_traded.character.inventory))
        # Pass work was gained
        self.assertTrue(any(i.id == "pass_work" for i in s_traded.character.inventory))

        # Repeated talk yields post-trade dialogue
        s_repeated = reduce_talk(s_traded, "npc_kael")
        self.assertTrue(any("Collar's seated" in m for m in s_repeated.message_buffer))

    def test_use_fixture_and_on_use_effects(self):
        # 1. Refill effect: water spigot with canteen
        canteen = ALL_ITEMS_BY_ID["flask_water"]._replace(integrity=1)
        char = self.state.character._replace(inventory=self.state.character.inventory + (canteen,))
        s_canteen = self.state._replace(character=char)
        s_refill = reduce_use(s_canteen, "flask_water", "spigot_01")
        refilled = next(i for i in s_refill.character.inventory if i.id == "flask_water")
        self.assertEqual(refilled.integrity, 3)
        self.assertTrue(any("Refilled" in m for m in s_refill.message_buffer))

        # 2. Unlock effect: cargo hoist in Berth 04 with pass_work
        pass_work = ALL_ITEMS_BY_ID["pass_work"]
        char_pass = self.state.character._replace(inventory=(pass_work,))
        s_berth = self.state._replace(current_node_id="stn_a_berth", character=char_pass)
        s_unlock = reduce_use(s_berth, "pass_work", "cargo_hoist")
        hoist = s_unlock.nodes["stn_a_berth"].fixtures["cargo_hoist"]
        self.assertEqual(hoist.state, FixtureState.OPEN.value)

        # 3. Already done fixture
        s_done = reduce_use(s_unlock, "pass_work", "cargo_hoist")
        self.assertTrue(any("Already done" in m for m in s_done.message_buffer))

        # 4. Incompatible item
        s_incompat = reduce_use(s_berth, "pass_work", "freight_skid")
        self.assertTrue(any("That doesn't work here" in m for m in s_incompat.message_buffer))

    def test_leave_open_and_gated_edges(self):
        # Open edge: bunkroom -> berth
        s1 = reduce_leave(self.state, "to_berth")
        self.assertEqual(s1.current_node_id, "stn_a_berth")

        # Gated edge: cargo hoist to subdeck is locked initially
        s2 = reduce_leave(s1, "to_subdeck")
        # Should be blocked
        self.assertEqual(s2.current_node_id, "stn_a_berth")
        self.assertTrue(any("is LOCKED" in m for m in s2.message_buffer))

        # Invalid edge
        s3 = reduce_leave(s1, "non_existent_edge")
        self.assertEqual(s3.current_node_id, "stn_a_berth")
        self.assertTrue(any("No exit" in m for m in s3.message_buffer))

    def test_companion_unlock_and_party(self):
        # In Sub-deck: trade with Radek unlocks companion comp_radek
        prybar = ALL_ITEMS_BY_ID["tool_prybar"]
        char = self.state.character._replace(inventory=(prybar,))
        s_sub = self.state._replace(current_node_id="stn_a_sub", character=char)

        # Talk to Radek with prybar (matches 'force_lever')
        s_radek = reduce_talk(s_sub, "npc_radek")
        self.assertTrue(any(c.id == "comp_radek" for c in s_radek.companions))

        # Test party command
        s_party = reduce_party(s_radek)
        self.assertTrue(any("Radek" in m for m in s_party.message_buffer))

    def test_non_tick_views(self):
        cycle_before = self.state.cycle
        s_map = reduce_map(self.state)
        self.assertEqual(s_map.active_view, "map_topology")
        self.assertEqual(s_map.cycle, cycle_before)

        s_back = reduce_back(s_map)
        self.assertEqual(s_back.active_view, "compartment")
        self.assertEqual(s_back.cycle, cycle_before)

        s_pack = reduce_pack(self.state)
        self.assertTrue(any("CARRIED GEAR" in m for m in s_pack.message_buffer))

        s_char = reduce_character(self.state)
        self.assertTrue(any("CHARACTER PROFILE" in m for m in s_char.message_buffer))

        s_help = reduce_help(self.state)
        self.assertTrue(any("COMMAND REFERENCE" in m for m in s_help.message_buffer))

        s_flavor = reduce_flavor(self.state, "off")
        self.assertFalse(s_flavor.flavor_enabled)

if __name__ == "__main__":
    unittest.main()
