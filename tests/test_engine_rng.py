import unittest

from engine import rng
from engine.rng import Rng


class TestRng(unittest.TestCase):
    def test_same_state_same_result(self):
        a, _ = rng.unit(Rng(42, 7))
        b, _ = rng.unit(Rng(42, 7))
        self.assertEqual(a, b)

    def test_known_value_is_stable(self):
        # Pinned so a change in how draws are made can't slip by unnoticed: it would
        # change every saved game's future.
        self.assertEqual(rng.between(Rng(1, 0), 1, 1000)[0], 744)
        self.assertEqual(rng.between(Rng(2024, 5), 1, 6)[0], 1)
        self.assertEqual(rng.unit(Rng(7, 3))[0], 0.7743612107349676)

    def test_each_draw_advances_the_counter(self):
        r = Rng(1)
        _, r = rng.unit(r)
        _, r = rng.chance(r, 0.5)
        _, r = rng.between(r, 1, 6)
        _, r = rng.weighted(r, [1, 2])
        _, r = rng.pick(r, ["a", "b"])
        self.assertEqual(r, Rng(1, 5))

    def test_different_seeds_differ(self):
        draws = {rng.unit(Rng(seed))[0] for seed in range(50)}
        self.assertEqual(len(draws), 50)

    def test_unit_range(self):
        r = Rng(3)
        for _ in range(200):
            value, r = rng.unit(r)
            self.assertTrue(0 <= value < 1)

    def test_chance_edges_and_rate(self):
        r = Rng(5)
        hits = 0
        for _ in range(2000):
            hit, r = rng.chance(r, 0.25)
            hits += hit
        self.assertTrue(400 < hits < 600, hits)
        self.assertFalse(rng.chance(Rng(1), 0)[0])
        self.assertTrue(rng.chance(Rng(1), 1)[0])

    def test_between_integers_inclusive(self):
        r, seen = Rng(9), set()
        for _ in range(300):
            value, r = rng.between(r, 1, 3)
            self.assertIsInstance(value, int)
            seen.add(value)
        self.assertEqual(seen, {1, 2, 3})

    def test_between_floats(self):
        value, _ = rng.between(Rng(9), 0.5, 1.5)
        self.assertIsInstance(value, float)
        self.assertTrue(0.5 <= value <= 1.5)

    def test_weighted(self):
        r, counts = Rng(11), [0, 0, 0]
        for _ in range(3000):
            index, r = rng.weighted(r, [1, 0, 3])
            counts[index] += 1
        self.assertEqual(counts[1], 0)
        self.assertTrue(2000 < counts[2] < 2500, counts)
        with self.assertRaises(ValueError):
            rng.weighted(Rng(1), [0, 0])

    def test_pick(self):
        item, _ = rng.pick(Rng(4), ["only"])
        self.assertEqual(item, "only")
        with self.assertRaises(ValueError):
            rng.pick(Rng(4), [])


if __name__ == "__main__":
    unittest.main()
