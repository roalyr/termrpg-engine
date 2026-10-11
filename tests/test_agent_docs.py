"""
Keeps AGENTS.md honest: every recipe in it must validate against the test pack, and
every command it recommends must exist.
"""
import io
import json
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from core import packtool
from core.pack import validate_pack

ROOT = Path(__file__).resolve().parent.parent
TEST_PACK = ROOT / "packs" / "test_scifi"
RECIPE = re.compile(r"<!-- recipe -->\s*```json\n(.*?)```", re.S)


def recipes():
    return RECIPE.findall((ROOT / "AGENTS.md").read_text(encoding="utf-8"))


def apply_recipe(pack: Path, recipe: dict) -> None:
    """Adds a recipe's entries to a copy of the test pack."""
    manifest = json.loads((pack / "pack.json").read_text())
    for key, entries in recipe.items():
        if key.startswith("placements:"):
            location_id = key.split(":", 1)[1]
            for rel in manifest["files"]["locations"]:
                data = json.loads((pack / rel).read_text())
                for loc in data["entries"]:
                    if loc["id"] == location_id:
                        loc.setdefault("placements", []).extend(entries)
                (pack / rel).write_text(json.dumps(data))
            continue
        rel = manifest["files"][key][0]
        data = json.loads((pack / rel).read_text())
        data["entries"].extend(entries)
        (pack / rel).write_text(json.dumps(data))


class TestAgentRecipes(unittest.TestCase):
    def test_recipes_found(self):
        self.assertGreaterEqual(len(recipes()), 7)

    def test_each_recipe_validates(self):
        for i, text in enumerate(recipes()):
            with self.subTest(recipe=i):
                recipe = json.loads(text)
                with tempfile.TemporaryDirectory() as tmp:
                    pack = Path(tmp) / "pack"
                    shutil.copytree(TEST_PACK, pack)
                    apply_recipe(pack, recipe)
                    report = validate_pack(pack)
                    self.assertEqual(report.errors, (), f"recipe {i}")

    def test_documented_commands_exist(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for command in re.findall(r"python3 -m core\.packtool (\w+)", text):
            self.assertIn(command, ("check", "ids", "refs", "explain"), command)
        topics = re.findall(r"`(?:python3 -m core\.packtool )?explain ([^`]*)`", text)
        self.assertGreaterEqual(len(topics), 8)
        for topic in topics:
            if "…" in topic:
                continue  # a placeholder in prose, not a real topic
            with redirect_stdout(io.StringIO()):
                self.assertEqual(packtool.main(["explain"] + topic.split()), 0, topic)


if __name__ == "__main__":
    unittest.main()
