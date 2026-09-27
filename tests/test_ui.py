import unittest
from tests.helpers import find
from pathlib import Path
from core.presets import init_game_state, DEFAULT_DATA_DIR
from ui.render import render_frame, build_grid
from ui.topology_view import render_topology
from ui.text_tools import wrap_text, check_terminal, clear_terminal, visible_len
import io
import sys

class TestUI(unittest.TestCase):
    def setUp(self):
        self.preset_dir = DEFAULT_DATA_DIR
        self.state = init_game_state(self.preset_dir, "Vaelen", 1, 1)

    def test_build_grid(self):
        node = self.state.nodes["stn_a_bunkroom"]
        grid = build_grid(node)
        self.assertEqual(len(grid), node.size)
        # Check boundary walls exist
        self.assertTrue(grid[0].startswith(node.grid_wall))
        self.assertTrue(grid[-1].endswith(node.grid_wall))
        # Check fixture placement
        _, r, c = find(self.state, "spigot_01")
        self.assertEqual(grid[r].split()[c], node.fixtures["spigot_01"].glyph)

    def test_render_frame_width_40_all_nodes(self):
        for node_id in self.state.nodes:
            st = self.state._replace(current_node_id=node_id)
            frame = render_frame(st, 40)
            lines = frame.split("\n")
            for idx, line in enumerate(lines):
                if line.startswith(">"):
                    continue
                self.assertEqual(
                    visible_len(line), 40,
                    f"Node {node_id} line {idx} visible len is {visible_len(line)} != 40: '{line}'"
                )

    def test_render_frame_viewport_under_40(self):
        warning = render_frame(self.state, 35)
        self.assertTrue("CONFLICT" in warning)

    def test_render_topology(self):
        topo = render_topology(self.state, 40)
        self.assertTrue("TOPOLOGY" in topo)
        self.assertTrue("[*hab]" in topo or "[*brt]" in topo or "STATION ALPHA" in topo)

    def test_build_grid_with_player_cursor(self):
        node = self.state.nodes["stn_a_bunkroom"]
        # Player at center, which is floor
        mid = node.size // 2
        self.assertEqual(build_grid(node, mid, mid)[mid].split()[mid], "@")

        # Player co-located with the spigot -> entity glyph shown in inverted color
        _, r, c = find(self.state, "spigot_01")
        glyph = node.fixtures["spigot_01"].glyph
        self.assertEqual(build_grid(node, r, c)[r].split()[c], f"\033[7m{glyph}\033[0m")

    def test_render_frame_proximity_menu(self):
        st = self.state._replace(
            proximity_menu_active=True,
            message_buffer=("Near: Water Tap", "[I] Inspect  [U] Use flask_water  [X] Cancel")
        )
        frame = render_frame(st, 40)
        self.assertIn("[I] Inspect", frame)
        self.assertIn("[U] Use", frame)

    def test_render_frame_key_hints(self):
        frame = render_frame(self.state, 40)
        self.assertIn("WASD move", frame)
        self.assertIn("/ command", frame)
        self.assertIn("P pack", frame)
        self.assertIn("C char", frame)
        self.assertIn("T team", frame)

    def test_clear_terminal(self):
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            clear_terminal()
            output = sys.stdout.getvalue()
            self.assertIn("\033[H\033[2J", output)
        finally:
            sys.stdout = old_stdout

if __name__ == "__main__":
    unittest.main()

