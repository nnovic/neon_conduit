#!/usr/bin/env python3
"""Open the visual level editor: build a course with a finish line, then race it.

    python3 edit_level.py [level-file]          (default: levels/level.json)

Race a level without the editor with: python3 play.py --level levels/level.json
"""
from neon_conduit.level_editor import main

if __name__ == "__main__":
    main()
