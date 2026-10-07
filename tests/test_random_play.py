"""
Random play: thousands of random keys through the app, from several starting points and
seeds. Nothing may crash, every frame must keep the terminal's size, saves must round-trip
mid-game, and replaying the same seed and keys must give the same game.

Set RANDOM_PLAY_STEPS for a longer run, e.g.  RANDOM_PLAY_STEPS=5000 python3 -B -m unittest tests.test_random_play
"""
import os
import random
import unittest
from pathlib import Path

from engine import encounter, save
from engine.content import load_pack
from engine.effects import run
from engine.frozen import freeze
from engine.state import Ctx, new_game
from tui import app, render
from tui.text import visible_len
from tui.ui import default_ui

ROOT = Path(__file__).resolve().parent.parent
CONTENT = load_pack(ROOT / "packs" / "test")
UI = default_ui()
STEPS = int(os.environ.get("RANDOM_PLAY_STEPS", "250"))
SEEDS = range(1, 7)
SIZES = ((40, 20), (44, 30), (72, 50))
STARTS = ("start", "loc_storage", "fight", "choice")
# Every bound key except quit, the digits, and letters menus and the board use.
KEYS = sorted((UI.bound_keys - {UI.bindings["quit"]}) | set("123456789") | set("ufrbehjklmnoyvzgtio"))


def start(name, seed):
    s = new_game(CONTENT, seed)
    if name == "loc_storage":
        return run(CONTENT, s, Ctx(self_id=s.player), [freeze({"op": "move_to", "location": "loc_storage"})])
    if name == "fight":
        return encounter.begin(CONTENT, s._replace(encounter_request="enc_drones"))
    if name == "choice":                                     # the terminal's question, waiting
        return run(CONTENT, s, Ctx(self_id=s.player), CONTENT.get("object", "obj_terminal")["interactions"][0]["effects"])
    return s


def play(name, seed, check=None):
    """Plays STEPS random keys; calls check(step, state, view) after each. Returns the final state and the keys."""
    rng = random.Random(f"{name}:{seed}")
    state, view = start(name, seed), app.View()
    pressed = []
    for step in range(STEPS):
        key = rng.choice(KEYS)
        pressed.append(key)
        state, view, _ = app.handle(CONTENT, state, key, view, UI)
        if check:
            check(step, state, view)
    return state, pressed


class TestRandomPlay(unittest.TestCase):
    def test_no_crash_and_every_frame_fits(self):
        for name in STARTS:
            for seed in SEEDS:
                def check(step, state, view):
                    columns, rows = SIZES[step % len(SIZES)]
                    try:
                        frame = render.render(CONTENT, state, columns, rows, view.panel, True, view.selected,
                                              view.page, UI, view.scroll, view.screen)
                    except Exception as error:
                        self.fail(f"{name} seed {seed} step {step}: drawing raised {error!r}")
                    lines = frame.rstrip("\n").split("\n")
                    widths = {visible_len(line) for line in lines}
                    self.assertEqual(widths, {columns}, f"{name} seed {seed} step {step} at {columns}x{rows}")
                    self.assertLessEqual(len(lines), rows, f"{name} seed {seed} step {step} at {columns}x{rows}")
                with self.subTest(start=name, seed=seed):
                    play(name, seed, check)

    def test_saves_round_trip_mid_game(self):
        for name in STARTS:
            for seed in SEEDS:
                def check(step, state, view):
                    if step % 25 == 0:
                        self.assertEqual(save.from_json(CONTENT, save.to_json(CONTENT, state)), state,
                                         f"{name} seed {seed} step {step}")
                with self.subTest(start=name, seed=seed):
                    play(name, seed, check)

    def test_replays_are_identical(self):
        for name in STARTS:
            for seed in SEEDS[:3]:
                with self.subTest(start=name, seed=seed):
                    first, keys = play(name, seed)
                    state, view = start(name, seed), app.View()
                    for key in keys:
                        state, view, _ = app.handle(CONTENT, state, key, view, UI)
                    self.assertEqual(state, first)


if __name__ == "__main__":
    unittest.main()
