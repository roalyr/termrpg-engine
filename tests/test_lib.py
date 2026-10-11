"""lib/: code shared by the game and the pack tools."""
import unittest

from lib import graph, pixels, tiles
from lib.text import Style, bar, colour_code


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



class PixelsTest(unittest.TestCase):
    def test_a_picture_is_centred_and_cut(self):
        grid = pixels.centred(["ab", ".a"], {"a": "red", "b": 17}, 4, 4)
        red = colour_code("red")
        self.assertEqual(grid, [[None] * 4, [None, red, 17, None], [None, None, red, None], [None] * 4])
        self.assertEqual(len(pixels.centred(["a" * 9] * 9, {"a": 1}, 4, 2)[0]), 4)

    def test_shapes_without_colour_and_a_marked_pixel_inverse(self):
        grid = [[1, 1, None], [1, None, None]]
        plain = Style(colour=False)
        self.assertEqual(pixels.half_blocks(plain, grid, empty="·"), ["█▀·"])
        self.assertEqual(pixels.half_blocks(plain, grid, marked={(1, 2)}), ["█▀" + plain.inverse(" ")])
        coloured = pixels.half_blocks(Style(colour=True), [[1, None], [2, 3]])
        self.assertIn("\x1b[38;5;1;48;5;2m▀", coloured[0])     # two colours: upper on lower
        self.assertEqual(pixels.half_blocks(plain, [[1]]), ["▀"])  # an odd last row


class TilesTest(unittest.TestCase):
    def test_a_box_rows_and_mismatched_rows(self):
        box = tiles.tiles({"width": 3, "height": 3})
        self.assertEqual((box[(0, 0)], box[(1, 1)]), ("#", "."))
        self.assertEqual(tiles.tiles({"width": 2, "height": 1, "rows": ["#."]}), {(0, 0): "#", (0, 1): "."})
        self.assertIsNone(tiles.tiles({"width": 3, "height": 1, "rows": ["#."]}))
        self.assertIsNone(tiles.tiles({"width": "3"}))
        self.assertEqual(tiles.tile({"width": 3, "height": 3}, (5, 0)), " ")
        self.assertEqual(tiles.tile({"width": 2, "height": 1, "rows": ["# "]}, (0, 1)), " ")

    def test_walls_join_and_doors_break_them(self):
        self.assertEqual(tiles.room_line(["#", "#", "+", "#"], [True, True, False, True], "#", 2), "#### + ##")


class TextTest(unittest.TestCase):
    def test_colours_and_bars(self):
        self.assertEqual((colour_code("grey"), colour_code(42), colour_code("nonsense")), (245, 42, 255))
        self.assertEqual(bar(3, 6, 4, "#", "-"), "##--")
        self.assertEqual(bar(9, 6, 4), "████")
        self.assertEqual(bar(1, 0, 3), "░░░")


if __name__ == "__main__":
    unittest.main()
