#!/usr/bin/env python3
"""Listen to the sled's engine at any speed, to tune its sound.

    python3 tools/engine_sound.py

Plays the game's engine (neon_conduit/audio.py) endlessly, at a virtual speed picked on a
slider: click or drag on it, or use Left / Right (Shift: in bigger steps), Home for a
standstill, End for top speed. With glide on (G), the speed moves to the one picked at the
game's own rates, as when the sled speeds up or slows down; off, it jumps there at once.
Space pauses (the engine fades out, as in the game's pause). Esc quits.

Marks on the slider show the speeds met in a race: the first cruising speed, the top
cruising speed, a boost at each, and the engine's top speed. The pitch and loudness
shown come from the same settings as the game (ENGINE_* in config.py).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pygame  # noqa: E402

from neon_conduit.audio import ENGINE_TOP_SPEED, Audio, engine_tone  # noqa: E402
from neon_conduit.config import BASE_SPEED, BOOST_MULT, SPEED_CAP  # noqa: E402

SIZE = (760, 260)           # the window, in pixels
SLIDER = (50, 140, 660)     # the slider's left end, height and length, in pixels
STEP = 1.0                  # speed change per Left / Right press...
BIG_STEP = 10.0             # ...and with Shift
SPEED_UP = 70.0             # glide rates, in speed per second: the game's (Game._move)...
SLOW_DOWN = 55.0            # ...when speeding up and slowing down
MARKS = (("cruise", BASE_SPEED), ("top cruise", SPEED_CAP),
         ("boost", BASE_SPEED * BOOST_MULT), ("top boost", ENGINE_TOP_SPEED))
BACK = (12, 14, 30)
TEXT = (230, 235, 255)
DIM = (130, 140, 180)
ACCENT = (255, 50, 170)
TARGET = (90, 220, 255)


def main():
    pygame.init()
    screen = pygame.display.set_mode(SIZE)
    pygame.display.set_caption("Neon Conduit - engine sound")
    audio = Audio()
    if not audio.ok:
        print("No sound device: nothing to hear.")
    big, small = pygame.font.Font(None, 40), pygame.font.Font(None, 22)
    clock = pygame.time.Clock()
    x0, y, length = SLIDER
    speed = target = 0.0
    glide, paused, dragging = True, False, False

    def at(mx):
        """The speed under the mouse's x on the slider."""
        return max(0.0, min(ENGINE_TOP_SPEED, (mx - x0) / length * ENGINE_TOP_SPEED))

    def px(v):
        return x0 + int(v / ENGINE_TOP_SPEED * length)

    while True:
        dt = clock.tick(60) / 1000.0
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                pygame.quit()
                return
            if ev.type == pygame.KEYDOWN:
                step = BIG_STEP if ev.mod & pygame.KMOD_SHIFT else STEP
                if ev.key == pygame.K_RIGHT:
                    target = min(ENGINE_TOP_SPEED, target + step)
                elif ev.key == pygame.K_LEFT:
                    target = max(0.0, target - step)
                elif ev.key == pygame.K_HOME:
                    target = 0.0
                elif ev.key == pygame.K_END:
                    target = ENGINE_TOP_SPEED
                elif ev.key == pygame.K_g:
                    glide = not glide
                elif ev.key == pygame.K_SPACE:
                    paused = not paused
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and abs(ev.pos[1] - y) < 30:
                dragging, target = True, at(ev.pos[0])
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                dragging = False
            elif ev.type == pygame.MOUSEMOTION and dragging:
                target = at(ev.pos[0])

        if not glide:
            speed = target
        elif speed < target:
            speed = min(target, speed + SPEED_UP * dt)
        else:
            speed = max(target, speed - SLOW_DOWN * dt)
        audio.engine(None if paused else speed)

        screen.fill(BACK)
        f, vol = engine_tone(speed)
        screen.blit(big.render("speed %5.1f" % speed, True, TEXT), (x0, 30))
        screen.blit(big.render("%5.1f Hz" % f, True, TEXT), (x0 + 260, 30))
        screen.blit(big.render("volume %.2f" % vol, True, TEXT), (x0 + 460, 30))
        screen.blit(small.render("PAUSED" if paused else "", True, ACCENT), (x0, 70))
        # the slider: its track, the marks, the speed picked and the speed playing
        pygame.draw.line(screen, DIM, (x0, y), (x0 + length, y), 4)
        for i, (name, v) in enumerate(MARKS):
            pygame.draw.line(screen, DIM, (px(v), y - 10), (px(v), y + 10), 2)
            img = small.render(name, True, DIM)
            screen.blit(img, (px(v) - img.get_width() // 2, y + (16 if i % 2 == 0 else 32)))
        pygame.draw.circle(screen, TARGET, (px(target), y), 7, 2)
        pygame.draw.circle(screen, ACCENT, (px(speed), y), 9)
        hint = ("click / drag, Left / Right (Shift: x10), Home / End      G  glide: %s      "
                "Space  pause      Esc  quit" % ("on" if glide else "off"))
        screen.blit(small.render(hint, True, DIM), (x0 - 20, SIZE[1] - 30))
        pygame.display.flip()


if __name__ == "__main__":
    main()
