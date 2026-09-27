import json
import re
import unittest
from pathlib import Path

from core.presets import DEFAULT_DATA_DIR

GDD = Path(__file__).resolve().parent.parent / "System Architecture & Game Design Document.md"


class TestGddSync(unittest.TestCase):
    def test_section_9_matches_canonical_presets(self):
        text = GDD.read_text(encoding="utf-8")
        for header, name in (("### 9.1", "items.json"), ("### 9.2", "nodes.json"),
                             ("### 9.3", "companions.json"), ("### 9.4", "skills.json"),
                             ("### 9.5", "jobs.json")):
            with self.subTest(file=name):
                match = re.search(re.escape(header) + r".*?```json\n(.*?)\n```", text, re.S)
                self.assertIsNotNone(match)
                expected = json.loads((DEFAULT_DATA_DIR / name).read_text(encoding="utf-8"))
                self.assertEqual(json.loads(match.group(1)), expected)


if __name__ == "__main__":
    unittest.main()
