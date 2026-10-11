import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from core import packtool
from core import schema
from core.pack import SCHEMA_DIR

TEST_PACK = str(Path(__file__).resolve().parent.parent / "packs" / "test_scifi")


def run(*argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = packtool.main(list(argv))
    return code, out.getvalue()


class TestPackTool(unittest.TestCase):
    def test_check(self):
        code, out = run("check", TEST_PACK)
        self.assertEqual(code, 0)
        self.assertIn("OK: 0 error(s)", out)

    def test_ids_lists_namespaces(self):
        code, out = run("ids", TEST_PACK)
        self.assertEqual(code, 0)
        self.assertIn("placement", out)

    def test_ids_of_a_namespace(self):
        code, out = run("ids", TEST_PACK, "item")
        self.assertEqual(code, 0)
        self.assertIn("frame_light", out)
        self.assertIn("items.json: entries[0]", out)

    def test_ids_unknown_namespace(self):
        code, out = run("ids", TEST_PACK, "spaceship")
        self.assertEqual(code, 1)
        self.assertIn("Namespaces:", out)

    def test_refs_shows_declaration_and_uses(self):
        code, out = run("refs", TEST_PACK, "workshop_door")
        self.assertEqual(code, 0)
        self.assertIn("declared  placement", out)
        self.assertIn("exit.entry", out)

    def test_refs_unknown(self):
        code, out = run("refs", TEST_PACK, "nothing_here")
        self.assertEqual(code, 1)

    def test_explain_every_check_and_op(self):
        common = schema.load_schemas(SCHEMA_DIR)["common.schema.json"]["$defs"]
        for key in common:
            for prefix, word in (("check_", "check"), ("op_", "op")):
                if key.startswith(prefix):
                    code, out = run("explain", word, key[len(prefix):])
                    self.assertEqual(code, 0, key)
                    self.assertIn("Fields (* required):", out, key)

    def test_explain_item_kinds_and_definitions(self):
        for topic in (["item", "frame"], ["item", "module"], ["location"], ["placement"], ["event"],
                      ["character"], ["vocab", "stats"], ["pack"], ["modification"]):
            code, out = run("explain", *topic)
            self.assertEqual(code, 0, topic)
            self.assertIn("Fields (* required):", out, topic)

    def test_explain_lists(self):
        code, out = run("explain", "ops")
        self.assertIn("damage", out)
        code, out = run("explain", "checks")
        self.assertIn("has_tag", out)

    def test_explain_unknown_topic(self):
        code, out = run("explain", "warp", "drive")
        self.assertEqual(code, 2)
        self.assertIn("Nothing called 'warp drive'", out)

    def test_usage(self):
        code, out = run()
        self.assertEqual(code, 2)
        self.assertIn("explain", out)


if __name__ == "__main__":
    unittest.main()
