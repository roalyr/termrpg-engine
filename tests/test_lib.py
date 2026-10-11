"""lib/: code shared by the game and the pack tools."""
import unittest

from lib import graph


class GraphTest(unittest.TestCase):
    def test_places_and_links_between_neighbours(self):
        glyphs = {(0, 0): "@", (1, 0): "■", (1, 1): "?", (3, 1): "■"}
        links = {((1, 0), (0, 0)), ((1, 0), (1, 1)), ((1, 1), (3, 1))}      # either order; the last isn't neighbours
        lines = graph.draw(glyphs, links, (0, 0), 10, 10, graph.extent(glyphs), blank=".")
        self.assertEqual(lines, ["@───■   .   .", "    │", ".   ?   .   ■", ""])

    def test_a_window_on_a_bigger_map(self):
        glyphs = {(x, 0): str(x) for x in range(8)}
        across, down = graph.fit(12, 2)
        self.assertEqual((across, down), (3, 1))
        start = graph.origin((6, 0), (0, 0), across, down)          # moved just far enough to show the cursor
        self.assertEqual(start, (4, 0))
        self.assertEqual(graph.draw(glyphs, (), start, across, down, graph.extent(glyphs))[0], "4   5   6")
        self.assertEqual(graph.origin((5, 0), start, across, down), start)   # still in view: it stays


if __name__ == "__main__":
    unittest.main()
