"""The UI schema and the default UI pack: validation rules and defaults."""
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from core import packtool, uipack

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_UI = ROOT / "packs" / "ui" / "default"


class TestSchemaGenerator(unittest.TestCase):
    def test_the_committed_schema_is_generated(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("gen_ui_schema", ROOT / "tools" / "gen_ui_schema.py")
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        committed = (ROOT / "schemas" / "ui.schema.json").read_text(encoding="utf-8")
        self.assertEqual(gen.text(), committed, "edit tools/gen_ui_schema.py and run it, not the schema")


class TestDefaultUi(unittest.TestCase):
    def test_default_ui_pack_is_valid(self):
        report = uipack.validate_ui_pack(DEFAULT_UI)
        self.assertEqual((report.errors, report.warnings), ((), ()))

    def test_checker_recognises_ui_packs(self):
        with redirect_stdout(io.StringIO()) as out:
            code = packtool.main(["check", str(DEFAULT_UI)])
        self.assertEqual(code, 0)
        self.assertIn("OK: 0 error(s)", out.getvalue())

    def test_explain_widgets(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(packtool.main(["explain", "widget", "tiles"]), 0)
            self.assertEqual(packtool.main(["explain", "ui", "tokens"]), 0)
        self.assertIn("per_row", out.getvalue())


class TestUiRules(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.pack = Path(self.temp.name) / "ui"
        shutil.copytree(DEFAULT_UI, self.pack)

    def tearDown(self):
        self.temp.cleanup()

    def edit(self, name, change):
        path = self.pack / name
        data = json.loads(path.read_text())
        change(data)
        path.write_text(json.dumps(data))

    def report(self):
        return uipack.validate_ui_pack(self.pack)

    def errors(self):
        return "\n".join(self.report().errors)

    def test_unknown_widget(self):
        self.edit("screens.json", lambda d: d["world"].append({"content": {"widget": "radar"}}))
        self.assertIn("unknown widget 'radar'", self.errors())

    def test_widget_on_the_wrong_screen(self):
        self.edit("screens.json", lambda d: d["world"].append({"content": {"widget": "tiles"}}))
        self.assertIn("world: widget 'tiles' isn't allowed here (only on encounter)", self.errors())

    def test_widget_twice(self):
        self.edit("screens.json", lambda d: d["debrief"].append({"content": {"widget": "log"}}))
        self.assertIn("debrief: widget 'log' appears 2 times", self.errors())

    def test_unknown_widget_option(self):
        self.edit("screens.json", lambda d: d["encounter"][2]["content"].__setitem__("columns", 3))
        self.assertIn("unknown field 'columns'", self.errors())

    def test_two_actions_on_one_key(self):
        self.edit("keys.json", lambda d: d["bindings"].__setitem__("wait", "w"))
        self.assertIn("'w' is bound to move_north and wait", self.errors())

    def test_digits_cant_be_bound(self):
        self.edit("keys.json", lambda d: d["bindings"].__setitem__("pack", "1"))
        self.assertIn("bindings.pack: '1' does not match", self.errors())

    def test_unknown_hint_label(self):
        self.edit("keys.json", lambda d: d["hints"]["walk"].append({"label": "hint_missing"}))
        self.assertIn("unknown word 'hint_missing'", self.errors())

    def test_hint_shows_actions_or_digits(self):
        self.edit("keys.json", lambda d: d["hints"]["walk"].append(
            {"actions": ["wait"], "digits": True, "label": "hint_wait"}))
        self.assertIn("show actions or digits, not both", self.errors())

    def test_word_placeholders(self):
        self.edit("words.json", lambda d: d["engine"].__setitem__("round_log", "Turn {turn}:"))
        self.assertIn("engine.round_log: unknown placeholder {turn} (allowed: {round})", self.errors())

    def test_duplicate_word(self):
        self.edit("words.json", lambda d: d["entries"].append({"id": "hint_move", "text": "again"}))
        self.assertIn("duplicate word 'hint_move'", self.errors())

    def test_grid_must_fit_the_narrowest_screen(self):
        self.edit("tokens.json", lambda d: d["size"].__setitem__("cell_width", 3))
        self.assertIn("the world screen needs 49 columns", self.errors())

    def test_screen_without_keys_warns(self):
        self.edit("screens.json", lambda d: d.__setitem__("debrief", d["debrief"][:2]))
        report = self.report()
        self.assertEqual(report.errors, ())
        self.assertIn("screens: debrief: has no 'keys' widget, so players won't see the keys", report.warnings)

    def test_everything_defaults_to_the_standard(self):
        for name in ("tokens.json", "keys.json", "words.json"):
            (self.pack / name).write_text("{}")
        report, ui = uipack.load_merged(self.pack)
        self.assertEqual(report.errors, ())
        self.assertEqual(ui["keys"]["bindings"]["move_north"], "w")
        self.assertEqual(ui["tokens"]["size"]["min_columns"], 40)
        self.assertEqual(ui["tokens"]["glyphs"]["border"]["top_left"], "┌")
        self.assertEqual(ui["tokens"]["styles"]["danger"]["colour"], "orange")

    def test_files_of_a_kind_merge(self):
        (self.pack / "more_words.json").write_text(json.dumps(
            {"entries": [{"id": "hint_extra", "text": "extra"}], "engine": {"talk": "Speak"}}))
        self.edit("ui.json", lambda d: d["files"]["words"].append("more_words.json"))
        report, ui = uipack.load_merged(self.pack)
        self.assertEqual(report.errors, ())
        self.assertEqual(ui["words"]["engine"]["talk"], "Speak")                       # later files win
        self.assertIn("hint_extra", [e["id"] for e in ui["words"]["entries"]])          # entries add up
        self.assertIn("hint_move", [e["id"] for e in ui["words"]["entries"]])


if __name__ == "__main__":
    unittest.main()
