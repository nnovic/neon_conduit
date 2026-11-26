# Neon Conduit

A neon tunnel racer in Python with pygame-ce (2.5.8), drawn by its own software 3D renderer
(no OpenGL). `python3 play.py` plays it; `python3 edit_patterns.py` and `python3 edit_level.py`
open the tunnel-pattern and level editors. See README.md for controls, options and the layout.

## Workflow

- **Commit only when asked** ("commit"), and **push only when asked** ("commit and push").
  Never commit on your own after finishing a change: report, then wait.
- Stage only the files of the change you made. Leave the user's own unrelated edits
  (e.g. in play.py) out of the commit unless asked.
- Commit messages: one imperative subject line saying what changes for the player
  ("Start the race music a second after passing the race's first door"), optionally a short
  body, then the Co-Authored-By trailer.
- **Never commit `neon_conduit/music/`**: its files are not licensed for distribution. It is
  git-ignored; keep it that way.
- Any third-party asset (music, sound, font, image) gets an entry in CREDITS.md (title,
  author, where it is used, file, source, license, any conversion), and the title screen's
  credits banner (`CREDITS_LINE` in hud.py) if it is music or a font.
- New features, keys and command-line options go in README.md; refresh the screenshots in
  docs/ when a screen changes noticeably.

## Testing

There is no test suite: check changes by running the game headless.
- `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python3 -m neon_conduit --frames 600 --screenshot out.png`
  self-plays with the autopilot (`Game.autopilot()`) and saves the last frame; look at it.
- To test menus and editors, build `App` / `LevelEditor` in a script, post pygame key and
  mouse events, and draw frames (the level editor has `run(frames, screenshot, script)`).
- Keep scratch screenshots and scripts out of the repo.
- Say plainly what was only tested headless and not in a real window.

## Code conventions

- Tunable numbers are named constants with a comment saying what they mean and in which
  unit: in config.py when shared, otherwise at the top of their module.
- Comments and docstrings in plain English, explaining why and what the player sees.
- Performance matters: it is a software renderer at 60 fps. Watch frame time with F3 / `--fps`
  and prefer cheap drawing (shared projections, cached surfaces) over per-pixel effects.
- Angles round the tube: 0 = middle of the floor, positive = towards the right wall,
  ±π = ceiling. Bend > 0 turns right, slope > 0 climbs.

## Game design decisions

These were settled with the user; don't change them without asking.

### Title and modes
- The title screen has a waving chequered flag, a wireframe tunnel in a dark band, the title
  in Russo One with a neon gradient, a game-mode menu above a scrolling credits banner, and
  "Hero Immortal" playing.
- Game modes are listed in `MODES` (app.py), chosen with Left / Right, started with Enter.
  **Voyage** (the only mode so far) is the endless, randomly generated track with the
  tutorial on the first race. A new mode needs its entry in `MODES` and its own start code.

### Track and race
- Every race starts on a long straight in the "original" pattern; the tutorial runs until a
  door into the real game, and Tab skips it (with a fade) until that door is in view.
- At least `TUNNEL_MIN` (100) segments of tube between two outdoor runs; outdoor runs are
  ground-level or in the air, and their doors sit in a bulkhead.
- The sled is invincible while it boosts.

### Music and HUD
- The race music is a random file from `neon_conduit/music/`. In Voyage it starts 1 s after
  the first door (the end of the tutorial); in a level, 1 s after the start.
- As a song starts, a panel bottom-left, about the speedometer's size, shows its title in
  quotation marks (big), artist (medium), and album + release date (small). It comes back
  every minute while the song plays. No border, except an orange outline the first time it
  shows for each song.

### Boost view effect
- Above cruising speed (~400) the view widens (focal) and bends (perspective warp), eased in
  and out with the boost, scaled by the chain of boosts: barely noticeable for one, very
  noticeable for three or more.
- **No pixelation**: tried and dropped for good.

### Levels (finite courses)
- Levels are JSON files in levels/ (format documented in level.py): sections of tube,
  ground or air track with length, bend, slope, width and pattern / theme, plus objects, and a
  finish line. They are raced with `--level FILE [--from SEG]`, without the tutorial; time left
  at the finish scores 100 points a second.
- Object types (boost, drone, gate, and future obstacles) are entries in `OBJECT_KINDS`
  (level.py); a new one also needs its behaviour in `Game._objects` and its look in
  `Renderer._object`.
- The level editor shows the course as a map (sections, bend and slope curves, the tube
  unrolled, the ruler) with a live 3D preview; P races the level as it stands.
