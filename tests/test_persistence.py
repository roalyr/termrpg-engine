import unittest
import tempfile
from pathlib import Path
from core.presets import init_game_state, DEFAULT_DATA_DIR
from core.persistence import save_state, load_state
from core.reducers import ALL_ITEMS_BY_ID, ALL_COMPANIONS_BY_ID

class TestPersistence(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.save_dir = Path(self.temp_dir.name) / "saves" / "TestPilot"
        self.preset_dir = DEFAULT_DATA_DIR

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_save_returns_none(self):
        loaded = load_state(self.save_dir)
        self.assertIsNone(loaded)

    def test_full_roundtrip_persistence(self):
        state = init_game_state(self.preset_dir, "TestPilot", 1, 1)

        # Modify state: add item, add companion, gain experience, change location
        modified_char = state.character._replace(
            inventory=state.character.inventory + (ALL_ITEMS_BY_ID["tool_prybar"],),
            unlocked_capabilities=state.character.unlocked_capabilities | {"seam_discipline"}
        )
        modified_state = state._replace(
            character=modified_char,
            current_node_id="stn_a_sub",
            companions=(ALL_COMPANIONS_BY_ID["comp_radek"],),
            skills={**state.skills, "survival": 44},
            day=3,
            woke_at=40,
            visited_nodes=state.visited_nodes | {"stn_a_sub"},
            cycle=42,
            player_row=3,
            player_col=1,
            proximity_menu_active=True
        )

        save_state(modified_state, self.save_dir)
        self.assertTrue((self.save_dir / "state.json").exists())

        loaded = load_state(self.save_dir)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.character.name, "TestPilot")
        self.assertEqual(loaded.current_node_id, "stn_a_sub")
        self.assertEqual(loaded.cycle, 42)
        self.assertEqual(loaded.player_row, 3)
        self.assertEqual(loaded.player_col, 1)
        self.assertTrue(loaded.proximity_menu_active)
        self.assertTrue(any(i.id == "tool_prybar" for i in loaded.character.inventory))
        self.assertTrue(any(c.id == "comp_radek" for c in loaded.companions))
        self.assertIn("seam_discipline", loaded.character.unlocked_capabilities)
        self.assertEqual(loaded.skills["survival"], 44)
        self.assertEqual((loaded.day, loaded.woke_at), (3, 40))
        self.assertEqual(loaded.jobs, state.jobs)
        self.assertIn("stn_a_sub", loaded.visited_nodes)
        self.assertTrue(loaded.is_running)

    def test_saved_with_is_running_false_restores_as_running(self):
        state = init_game_state(self.preset_dir, "TestPilot", 1, 1)
        # Simulate quit action setting is_running=False
        quitted_state = state._replace(is_running=False)
        save_state(quitted_state, self.save_dir)

        loaded = load_state(self.save_dir)
        self.assertIsNotNone(loaded)
        self.assertTrue(loaded.is_running)

    def test_resuming_and_executing_actions(self):
        state = init_game_state(self.preset_dir, "TestPilot", 1, 1)
        # Move player
        from core.reducers import reduce_move
        s1 = reduce_move(state, "w")
        save_state(s1, self.save_dir)

        # Restore from save
        loaded = load_state(self.save_dir)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.player_row, state.player_row - 1)
        self.assertEqual(loaded.cycle, 1)
        self.assertTrue(loaded.is_running)

        # Execute next action from restored state
        s2 = reduce_move(loaded, "a")
        self.assertEqual(s2.player_row, state.player_row - 1)
        self.assertEqual(s2.player_col, state.player_col - 1)
        self.assertEqual(s2.cycle, 2)

    def test_incapacitation_reload_revival(self):
        from core.types import Exposure
        state = init_game_state(self.preset_dir, "TestPilot", 1, 1)
        incapacitated_char = state.character._replace(exposure=Exposure(16.0, 0.0, 0.0))
        incap_state = state._replace(
            character=incapacitated_char,
            current_node_id="luna_mine",
            is_running=False
        )
        save_state(incap_state, self.save_dir)

        loaded = load_state(self.save_dir)
        self.assertIsNotNone(loaded)
        self.assertTrue(loaded.is_running)
        self.assertEqual(loaded.character.exposure.pressure_debt, 0.0)
        self.assertEqual(loaded.current_node_id, "stn_a_bunkroom")

if __name__ == "__main__":
    unittest.main()


