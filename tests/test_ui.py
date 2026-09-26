import unittest
from pathlib import Path
from core.presets import init_game_state
from ui.render import render_frame, build_grid
from ui.topology_view import render_topology
from ui.text_tools import wrap_text, check_terminal

class TestUI(unittest.TestCase):
    def setUp(self):
        self.preset_dir = Path("presets/default-1.0")
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
                    len(line), 40,
                    f"Node {node_id} line {idx} len is {len(line)} != 40: '{line}'"
                )

    def test_render_frame_viewport_under_40(self):
        warning = render_frame(self.state, 35)
        self.assertTrue("CONFLICT" in warning)

    def test_render_topology(self):
        topo = render_topology(self.state, 40)
        self.assertTrue("TOPOLOGY" in topo)
        self.assertTrue("[*hab]" in topo or "[*brt]" in topo or "STATION ALPHA" in topo)

    def test_wrap_text(self):
        text = "This is a sentence designed to test whether text wraps properly without truncating words."
        wrapped = wrap_text(text, 20)
        for line in wrapped:
            self.assertLessEqual(len(line), 20)
        self.assertEqual(" ".join(wrapped), text)

if __name__ == "__main__":
    unittest.main()
