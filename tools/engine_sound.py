#!/usr/bin/env python3
"""Listen to the sled's engine at any speed, and tune its sound by ear.

    python3 tools/engine_sound.py

Plays the game's engine (neon_conduit/audio.py) endlessly. The first slider is the virtual
speed; the others are the engine's settings (ENGINE_* in neon_conduit/config.py): its pitch
and loudness at a standstill and at top speed, and its tone (buzz, shimmer, throb). Every
change is heard at once.

Up / Down pick a slider, Left / Right move it (Shift: in bigger steps), or click and drag
any slider. Home / End take the picked one to its lowest / highest. With glide on (G), the
speed moves to the one picked at the game's own rates, as when the sled speeds up or slows
down; off, it jumps there. Space pauses (the engine fades out, as in the game's pause).
S saves the settings into config.py; R puts back the saved ones. Esc quits.

Marks on the speed slider show the speeds met in a race: the first cruising speed, the
top cruising speed, a boost, and the engine's top speed.
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from neon_conduit import audio as engine  # noqa: E402  (its ENGINE_* settings are changed live)
from neon_conduit.config import BASE_SPEED, BOOST_MULT, SPEED_CAP  # noqa: E402

CONFIG = os.path.join(ROOT, "neon_conduit", "config.py")
SIZE = (800, 560)           # the window, in pixels
LEFT, WIDTH = 230, 470      # the sliders' left end and length, in pixels
TOP, ROW = 80, 52           # the first slider's height and the gap between two, in pixels
SPEED_UP = 70.0             # glide rates, in speed per second: the game's (Game._move)...
SLOW_DOWN = 55.0            # ...when speeding up and slowing down
MARKS = (("cruise", BASE_SPEED), ("top cruise", SPEED_CAP),
         ("boost", BASE_SPEED * BOOST_MULT), ("top boost", engine.ENGINE_TOP_SPEED))
# The sliders: label, setting (None: the speed), lowest, highest, step (Shift: x10), format.
SLIDERS = (
    ("speed", None, 0.0, engine.ENGINE_TOP_SPEED, 1.0, "%.0f"),
    ("pitch standing", "ENGINE_IDLE_HZ", 20.0, 150.0, 1.0, "%.0f Hz"),
    ("pitch top speed", "ENGINE_TOP_HZ", 60.0, 600.0, 2.0, "%.0f Hz"),
    ("volume standing", "ENGINE_IDLE_VOLUME", 0.0, 0.6, 0.01, "%.2f"),
    ("volume top speed", "ENGINE_VOLUME", 0.0, 0.6, 0.01, "%.2f"),
    ("buzz", "ENGINE_BUZZ", 0.0, 1.0, 0.01, "%.2f"),
    ("shimmer", "ENGINE_SHIMMER", 0.0, 3.0, 0.05, "%.2f %%"),
    ("throb", "ENGINE_THROB", 0.0, 1.0, 0.01, "%.2f"),
)
BACK = (12, 14, 30)
TEXT = (230, 235, 255)
DIM = (130, 140, 180)
ACCENT = (255, 50, 170)
TARGET = (90, 220, 255)
SAVED = (120, 230, 140)


def save(values):
    """Write the settings into config.py, in place of the numbers there (comments kept)."""
    text = open(CONFIG).read()
    for name, v in values.items():
        num = ("%.3f" % v).rstrip("0")
        num += "0" if num.endswith(".") else ""
        text, n = re.subn(r"^(%s\s*=\s*)[-+0-9.eE]+" % name, lambda m: m.group(1) + num, text, flags=re.M)
        if n != 1:
            raise RuntimeError("%s not found in %s" % (name, CONFIG))
    open(CONFIG, "w").write(text)


def main():
    pygame.init()
    screen = pygame.display.set_mode(SIZE)
    pygame.display.set_caption("Neon Conduit - engine sound")
    sound = engine.Audio()
    if not sound.ok:
        print("No sound device: nothing to hear.")
    big, font, small = pygame.font.Font(None, 34), pygame.font.Font(None, 26), pygame.font.Font(None, 21)
    clock = pygame.time.Clock()
    saved = {s[1]: getattr(engine, s[1]) for s in SLIDERS if s[1]}    # as in config.py
    speed = target = 0.0
    sel, glide, paused, dragging, note = 0, True, False, None, ""

    def get(i):
        name = SLIDERS[i][1]
        return target if name is None else getattr(engine, name)

    def put(i, v):
        nonlocal target
        _, name, lo, hi, _, _ = SLIDERS[i]
        v = max(lo, min(hi, v))
        if name is None:
            target = v
            return
        setattr(engine, name, v)
        if name == "ENGINE_BUZZ" and sound.ok:      # the tone's waveform, made again
            sound.engine_wave = sound._engine_wave()

    def x_of(i, v):
        lo, hi = SLIDERS[i][2:4]
        return LEFT + int((v - lo) / (hi - lo) * WIDTH)

    def from_x(i, x):
        lo, hi = SLIDERS[i][2:4]
        return lo + (x - LEFT) / WIDTH * (hi - lo)

    while True:
        dt = clock.tick(60) / 1000.0
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                pygame.quit()
                return
            if ev.type == pygame.KEYDOWN:
                step = SLIDERS[sel][4] * (10 if ev.mod & pygame.KMOD_SHIFT else 1)
                if ev.key == pygame.K_UP:
                    sel = (sel - 1) % len(SLIDERS)
                elif ev.key == pygame.K_DOWN:
                    sel = (sel + 1) % len(SLIDERS)
                elif ev.key == pygame.K_RIGHT:
                    put(sel, get(sel) + step)
                elif ev.key == pygame.K_LEFT:
                    put(sel, get(sel) - step)
                elif ev.key == pygame.K_HOME:
                    put(sel, SLIDERS[sel][2])
                elif ev.key == pygame.K_END:
                    put(sel, SLIDERS[sel][3])
                elif ev.key == pygame.K_g:
                    glide = not glide
                elif ev.key == pygame.K_SPACE:
                    paused = not paused
                elif ev.key == pygame.K_r:
                    for name, v in saved.items():
                        put([s[1] for s in SLIDERS].index(name), v)
                    note = "back to the saved settings"
                elif ev.key == pygame.K_s:
                    saved = {s[1]: getattr(engine, s[1]) for s in SLIDERS if s[1]}
                    save(saved)
                    note = "saved in neon_conduit/config.py"
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                i = round((ev.pos[1] - TOP) / ROW)
                if 0 <= i < len(SLIDERS) and abs(ev.pos[1] - (TOP + i * ROW)) < 18 \
                        and LEFT - 15 <= ev.pos[0] <= LEFT + WIDTH + 15:
                    sel = dragging = i
                    put(i, from_x(i, ev.pos[0]))
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                dragging = None
            elif ev.type == pygame.MOUSEMOTION and dragging is not None:
                put(dragging, from_x(dragging, ev.pos[0]))

        if not glide:
            speed = target
        elif speed < target:
            speed = min(target, speed + SPEED_UP * dt)
        else:
            speed = max(target, speed - SLOW_DOWN * dt)
        sound.engine(None if paused else speed)

        screen.fill(BACK)
        f, vol = engine.engine_tone(speed)
        state = "PAUSED" if paused else "playing at %.0f Hz, volume %.2f" % (f, vol)
        screen.blit(big.render(state, True, ACCENT if paused else TEXT), (30, 22))
        for i, (label, name, lo, hi, _, fmt) in enumerate(SLIDERS):
            y, v = TOP + i * ROW, get(i)
            changed = name is not None and abs(v - saved[name]) > 1e-9
            col = TEXT if i == sel else DIM
            screen.blit(font.render(label + (" *" if changed else ""), True, col), (30, y - 9))
            pygame.draw.line(screen, col, (LEFT, y), (LEFT + WIDTH, y), 3 if i == sel else 2)
            screen.blit(font.render(fmt % v, True, col), (LEFT + WIDTH + 18, y - 9))
            if name is None:                 # the speed: race marks, the speed picked and playing
                for k, (mark, mv) in enumerate(MARKS):
                    x = x_of(i, mv)
                    pygame.draw.line(screen, DIM, (x, y - 8), (x, y + 8), 2)
                    img = small.render(mark, True, DIM)
                    screen.blit(img, (x - img.get_width() // 2, y + 10 + 12 * (k % 2)))
                pygame.draw.circle(screen, TARGET, (x_of(i, target), y), 7, 2)
                pygame.draw.circle(screen, ACCENT, (x_of(i, speed), y), 9)
            else:
                pygame.draw.circle(screen, ACCENT if i == sel else DIM, (x_of(i, v), y), 8)
        screen.blit(font.render(note, True, SAVED), (30, SIZE[1] - 80))
        hints = ("Up / Down  pick      Left / Right  move (Shift: x10)      Home / End      "
                 "click / drag",
                 "G  glide: %s      Space  pause      S  save      R  revert      Esc  quit"
                 % ("on" if glide else "off"))
        for k, h in enumerate(hints):
            screen.blit(small.render(h, True, DIM), (30, SIZE[1] - 48 + 20 * k))
        pygame.display.flip()


if __name__ == "__main__":
    main()
