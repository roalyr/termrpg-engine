import unittest
import tempfile
import json
from pathlib import Path
from core.presets import (
    ensure_presets, load_items, load_nodes, load_companions, load_tree,
    init_game_state
)

class TestPresets(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.preset_dir = Path(self.temp_dir.name) / "default-1.0"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_ensure_and_load_presets(self):
        ensure_presets(self.preset_dir)
        self.assertTrue((self.preset_dir / "items.json").exists())
        self.assertTrue((self.preset_dir / "nodes.json").exists())
        self.assertTrue((self.preset_dir / "companions.json").exists())
        self.assertTrue((self.preset_dir / "tree.json").exists())

        items = load_items(self.preset_dir / "items.json")
        nodes = load_nodes(self.preset_dir / "nodes.json")
        comps = load_companions(self.preset_dir / "companions.json")
        tree = load_tree(self.preset_dir / "tree.json")

        self.assertEqual(len(items), 9)
        self.assertEqual(len(nodes), 14)
        self.assertEqual(len(comps), 1)
        self.assertEqual(len(tree), 6)

    def test_init_game_state_variants(self):
        ensure_presets(self.preset_dir)
        # Choice 1: Scraper, Copper fitting
        s1 = init_game_state(self.preset_dir, "Vaelen", 1, 1)
        self.assertEqual(s1.character.name, "Vaelen")
        self.assertEqual(s1.character.personal_anchor.id, "fitting_copper")
        self.assertEqual(s1.character.past_work, "seam_scraper")
        self.assertIn("seal_fitting", s1.character.unlocked_capabilities)

        # Choice 2: Tender, Work pass
        s2 = init_game_state(self.preset_dir, "TenderOne", 2, 2)
        self.assertEqual(s2.character.personal_anchor.id, "pass_work")
        self.assertEqual(s2.character.past_work, "algae_tender")
        self.assertIn("bio_filter", s2.character.unlocked_capabilities)

        # Choice 3: Cargo handler, Steel dice
        s3 = init_game_state(self.preset_dir, "HandlerOne", 3, 3)
        self.assertEqual(s3.character.personal_anchor.id, "dice_steel")
        self.assertEqual(s3.character.past_work, "cargo_handler")
        self.assertIn("heavy_lift", s3.character.unlocked_capabilities)

    def test_schema_validation_error(self):
        ensure_presets(self.preset_dir)
        bad_file = self.preset_dir / "bad_items.json"
        with open(bad_file, "w") as f:
            json.dump([{"id": "bad"}], f)
        with self.assertRaises(ValueError):
            load_items(bad_file)

if __name__ == "__main__":
    unittest.main()
