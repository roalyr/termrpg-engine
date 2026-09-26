import unittest
import tempfile
from pathlib import Path
from core.presets import init_game_state
from core.persistence import save_state, load_state
from core.reducers import ALL_ITEMS_BY_ID, ALL_COMPANIONS_BY_ID

class TestPersistence(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.save_dir = Path(self.temp_dir.name) / "saves" / "TestPilot"
        self.preset_dir = Path("presets/default-1.0")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_save_returns_none(self):
        loaded = load_state(self.save_dir)
        self.assertIsNone(loaded)

    def test_full_roundtrip_persistence(self):
        state = init_game_state(self.preset_dir, "TestPilot", 1, 1)

        # Modify state: add item, add companion, attune tree node, change location
        modified_char = state.character._replace(
            inventory=state.character.inventory + (ALL_ITEMS_BY_ID["tool_prybar"],),
            unlocked_capabilities=state.character.unlocked_capabilities | {"seam_discipline"}
        )
        modified_tree = tuple(
            t._replace(attuned=True) if t.id == "seam_discipline" else t
            for t in state.tree
        )
        modified_state = state._replace(
            character=modified_char,
            current_node_id="stn_a_sub",
            companions=(ALL_COMPANIONS_BY_ID["comp_radek"],),
            tree=modified_tree,
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
        self.assertIn("stn_a_sub", loaded.visited_nodes)

if __name__ == "__main__":
    unittest.main()

