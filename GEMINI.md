# Instructions for Gemini

All instructions for working on this project are in [AGENTS.md](AGENTS.md). Read it
completely before making any change, and follow it. It is imported below.

The short version:

- Your usual workspace is a game pack in `packs/`. Ask before touching `schemas/`,
  the validator (`core/schema.py`, `core/pack.py`, `core/packtool.py`), `engine/`,
  `packs/test/` or `tests/`. Never edit `VISION.md` unless asked.
- Look things up instead of guessing:
  `python3 -m core.packtool explain …` and `python3 -m core.packtool ids <pack> …`.
- After every edit: `python3 -m core.packtool check <pack>` until it reports
  `0 error(s)`. Before finishing: `python3 -B -m unittest discover -s tests`.
- Never change a schema, the validator or a test to silence an error. Fix the data,
  or explain to the user what the schema can't express.

@./AGENTS.md
