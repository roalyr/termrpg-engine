import unittest
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
        # Check fixture placement: spigot at row 3, col 1
        row3 = grid[3].split()
        self.assertEqual(row3[1], "⌸")

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
        # Player at center (2, 2), which is floor
        grid = build_grid(node, 2, 2)
        row2 = grid[2].split()
        self.assertEqual(row2[2], "@")

        # Player co-located with spigot at (3, 1) -> entity glyph takes priority with inverted color
        grid_co = build_grid(node, 3, 1)
        row3 = grid_co[3].split()
        self.assertEqual(row3[1], "\033[7m⌸\033[0m")

    def test_render_frame_proximity_menu(self):
        st = self.state._replace(
            proximity_menu_active=True,
            message_buffer=("Near: Water Spigot", "[I] Inspect  [U] Use flask_water  [X] Cancel")
        )
        frame = render_frame(st, 40)
        self.assertIn("[I] Inspect", frame)
        self.assertIn("[U] Use", frame)

    def test_render_frame_key_hints(self):
        frame = render_frame(self.state, 40)
        self.assertIn("WASD: move", frame)
        self.assertIn("/: cmd", frame)

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

