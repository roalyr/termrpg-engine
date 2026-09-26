import unittest
from core.types import (
    Item, Fixture, Actor, GridPlacement, Edge, NodeVitals, Node,
    Companion, Exposure, PlayerCharacter, TreeNode, GameState,
    ItemCategory, FixtureState, Environment, ExposureType
)

class TestTypes(unittest.TestCase):
    def test_enums(self):
        self.assertEqual(ItemCategory.CREDENTIAL.value, "credential")
        self.assertEqual(FixtureState.SEALED.value, "sealed")
        self.assertEqual(Environment.PRESSURIZED.value, "pressurized")
        self.assertEqual(ExposureType.RADIATION.value, "radiation")

    def test_namedtuple_immutability(self):
        item = Item(
            id="test_item",
            name="Test",
            category="utility",
            tags=("test",),
            integrity=2,
            max_integrity=2,
            description="A test item"
        )
        with self.assertRaises(AttributeError):
            item.integrity = 1  # type: ignore

        # Test replace
        updated = item._replace(integrity=1)
        self.assertEqual(updated.integrity, 1)
        self.assertEqual(item.integrity, 2)

    def test_exposure_immutability(self):
        exp = Exposure(0.0, 1.0, 2.0)
        with self.assertRaises(AttributeError):
            exp.pressure_debt = 5.0  # type: ignore

if __name__ == "__main__":
    unittest.main()
