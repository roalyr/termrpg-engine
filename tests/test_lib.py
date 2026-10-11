"""lib/: code shared by the game and the pack tools."""
import unittest

from lib import budgets, graph, pixels, tiles
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


class BudgetsTest(unittest.TestCase):
    ROLES = {"power": "pwr", "mass": "mas", "heat": "hot", "cargo": "car"}
    ITEMS = {
        "suit": {"kind": "frame", "stats": {"pwr": 4, "mas": 6, "hot": 5, "car": 1, "arm": 2},
                 "slots": [{"slot_type": "hand", "count": 2}]},
        "drill": {"kind": "module", "slot_type": "hand", "uses": {"power": 3, "mass": 2, "heat": 1}},
        "eye": {"kind": "implant", "slot_type": "head", "stats": {"arm": 1}},
        "scrap": {"kind": "material", "stack": 10},
    }
    SKILLS = {"lift": {"levels": [{"level": 1}, {"level": 2, "stats": {"mas": 4}}, {"level": 3, "stats": {"mas": 9}}]}}

    def fit(self, **char):
        char.setdefault("body", {"stats": {"car": 1}, "slots": [{"slot_type": "head"}]})
        return budgets.loadout(char, self.ITEMS, self.ROLES, self.SKILLS)

    def test_slots_numbers_and_totals(self):
        fit = self.fit(frame="suit", fitted=["drill"], implants=["eye"], skills={"lift": 2},
                       inventory=[{"item": "scrap", "count": 11}])
        self.assertEqual(fit.slots, [budgets.Slot("frame", "hand", "drill", 0), budgets.Slot("frame", "hand", None, -1),
                                     budgets.Slot("body", "head", "eye", 0)])
        self.assertEqual(fit.used, {"power": 3, "mass": 2, "heat": 1, "cargo": 2})     # 11 scrap is two stacks
        self.assertEqual(fit.provided, {"power": 4, "mass": 10, "heat": 5, "cargo": 2})  # level 2 lifts, not 3
        self.assertEqual(fit.totals["arm"], 3)
        self.assertEqual(fit.problems, [])

    def test_each_limit(self):
        over = self.fit(frame="suit", fitted=["drill", "drill"], inventory=[{"item": "scrap", "count": 30}]).problems
        self.assertEqual([(p.what, p.role, p.used, p.provided) for p in over],
                         [("over", "power", 6, 4), ("over", "cargo", 3, 2)])
        self.assertFalse(budgets.over("heat", 0, 0))            # no load, no maximum: fine
        self.assertTrue(budgets.over("heat", 5, 5))             # heat must stay below its maximum
        self.assertFalse(budgets.over("power", 5, 5))

    def test_what_doesnt_fit(self):
        fit = self.fit(frame="drill", fitted=["drill", "eye", "nope"], implants=["eye", "eye"])
        self.assertEqual([(p.what, p.item, p.kind, p.group) for p in fit.problems],
                         [("not_frame", "drill", "module", ""), ("no_slot", "drill", "module", "fitted"),
                          ("wrong_kind", "eye", "implant", "fitted"), ("no_item", "nope", "", "fitted"),
                          ("no_slot", "eye", "implant", "implants"),
                          ("over", "", "", ""), ("over", "", "", ""), ("over", "", "", "")])
        self.assertEqual([p.role for p in fit.problems[-3:]], ["power", "mass", "heat"])     # nothing provides them
        self.assertIsNone(fit.frame)
        self.assertEqual([s.item for s in fit.extra], ["drill", "eye", "nope", "eye"])
        self.assertEqual([p.what for p in self.fit(fitted=["drill"]).problems], ["no_frame", "no_slot", "over", "over", "over"])

    def test_bad_numbers_are_skipped(self):
        items = dict(self.ITEMS, drill=dict(self.ITEMS["drill"], uses={"power": "lots"}))
        fit = budgets.loadout({"frame": "suit", "fitted": ["drill"], "body": {"stats": {"pwr": "x"}}},
                              items, self.ROLES, {})
        self.assertEqual((fit.used["power"], fit.provided["power"]), (0, 4))


if __name__ == "__main__":
    unittest.main()
