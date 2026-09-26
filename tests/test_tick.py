import unittest
from pathlib import Path
from core.presets import init_game_state
from core.tick import process_tick
from core.types import Exposure, Item, ItemCategory

class TestTickProcessor(unittest.TestCase):
    def setUp(self):
        self.preset_dir = Path("presets/default-1.0")
        self.state = init_game_state(self.preset_dir, "Vaelen", 1, 1)

    def test_cycle_increment(self):
        s1 = process_tick(self.state, "Action 1")
        self.assertEqual(s1.cycle, 1)
        s2 = process_tick(s1, "Action 2")
        self.assertEqual(s2.cycle, 2)

    def test_exposure_in_hostile_environment(self):
        # Sub-Deck: pressure 65.0, temp -25, rad 2.0
        # Safe thresholds: P >= 90 (delta = (90-65)/30 = 25/30 = 0.833)
        # T >= -10 (delta = (-10 - (-25))/20 = 15/20 = 0.75)
        # R <= 5 (2.0 <= 5, delta = 0.0)
        s_hostile = self.state._replace(current_node_id="stn_a_sub")
        s1 = process_tick(s_hostile, "Wait in cold conduit")
        exp = s1.character.exposure
        self.assertAlmostEqual(exp.pressure_debt, 0.83, delta=0.05)
        self.assertAlmostEqual(exp.thermal_stress, 0.75, delta=0.05)
        self.assertEqual(exp.radiation_dose, 0.0)

    def test_attunement_mitigations(self):
        # With cold_bypass, thermal stress accumulation is halved
        caps = self.state.character.unlocked_capabilities | {"cold_bypass"}
        char = self.state.character._replace(unlocked_capabilities=caps)
        s_mitigated = self.state._replace(character=char, current_node_id="stn_a_sub")
        s1 = process_tick(s_mitigated, "Wait with bypass")
        exp = s1.character.exposure
        self.assertAlmostEqual(exp.thermal_stress, 0.38, delta=0.05)

    def test_exposure_recovery_at_depth_0(self):
        # Set high exposure, then tick in bunkroom (depth 0, pressurized)
        char = self.state.character._replace(exposure=Exposure(5.0, 5.0, 5.0))
        s_rec = self.state._replace(character=char, current_node_id="stn_a_bunkroom")
        s1 = process_tick(s_rec, "Rest in bunkroom")
        exp = s1.character.exposure
        # Recovers by 2.0 per tick
        self.assertEqual(exp.pressure_debt, 3.0)
        self.assertEqual(exp.radiation_dose, 3.0)
        self.assertEqual(exp.thermal_stress, 3.0)

    def test_incapacitation(self):
        # Exceed threshold (15.0) in hostile environment without recovery
        char = self.state.character._replace(exposure=Exposure(15.0, 0.0, 0.0))
        s_crit = self.state._replace(character=char, current_node_id="stn_a_sub")
        s1 = process_tick(s_crit, "Final tick")
        self.assertFalse(s1.is_running)
        self.assertTrue(any("Incapacitated" in m for m in s1.message_buffer))

    def test_sustenance_decay_every_10_cycles(self):
        ration = Item("ration_dry", "Ration", ItemCategory.SUSTENANCE.value, ("nutrition",), 2, 2, "Test")
        char = self.state.character._replace(inventory=self.state.character.inventory + (ration,))
        s = self.state._replace(character=char, cycle=9)

        # Tick 10 triggers decay
        s10 = process_tick(s, "Tick 10")
        decayed_ration = next(i for i in s10.character.inventory if i.id == "ration_dry")
        self.assertEqual(decayed_ration.integrity, 1)

    def test_action_log_max_20_entries(self):
        s = self.state
        for i in range(25):
            s = process_tick(s, f"Action {i}")
        self.assertEqual(len(s.action_log), 20)
        self.assertEqual(s.action_log[-1], "Action 24")

if __name__ == "__main__":
    unittest.main()
