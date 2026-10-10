"""
Lists the tools. Each one runs on its own from the project root:

  python3 -m tools                 this list
  python3 -m tools.<name> <pack>   a tool, on a pack folder
"""
TOOLS = (
    ("overview", "ready", "A pack at a glance: files, entry counts, checker report"),
    ("map", "planned", "The world graph: locations at their map x/y, exits as links"),
    ("room", "planned", "One location: grid shape, placements, entry, doors"),
    ("art", "planned", "Character portraits (pixels + palette) and encounter art"),
)


def main() -> int:
    print("Pack tools (python3 -m tools.<name> <pack>):\n")
    for name, status, about in TOOLS:
        print(f"  {name:10} {status:8} {about}")
    print("\nAlso: python3 tools/gen_ui_schema.py regenerates schemas/ui.schema.json.")
    print("See tools/README.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
