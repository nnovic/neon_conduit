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
import pygame

import tuner
from tuner import Setting
from neon_conduit import audio as engine
from neon_conduit.config import BASE_SPEED, BOOST_MULT, SPEED_CAP

SIZE = (800, 580)           # the window, in pixels
SPEED_UP = 70.0             # glide rates, in speed per second: the game's (Game._move)...
SLOW_DOWN = 55.0            # ...when speeding up and slowing down
MARKS = (("cruise", BASE_SPEED), ("top cruise", SPEED_CAP),
         ("boost", BASE_SPEED * BOOST_MULT), ("top boost", engine.ENGINE_TOP_SPEED))


def main():
    pygame.init()
    screen = pygame.display.set_mode(SIZE)
    pygame.display.set_caption("Neon Conduit - engine sound")
    sound = engine.Audio()
    if not sound.ok:
        print("No sound device: nothing to hear.")
    speed_set = Setting("speed", None, 0.0, engine.ENGINE_TOP_SPEED, 1.0, "%.0f", value=0.0)

    def changed(s):
        if s.name == "ENGINE_BUZZ" and sound.ok:      # the tone's waveform, made again
            sound.engine_wave = sound._engine_wave()

    panel = tuner.Panel([
        speed_set,
        Setting("pitch standing", "ENGINE_IDLE_HZ", 20.0, 150.0, 1.0, "%.0f Hz"),
        Setting("pitch top speed", "ENGINE_TOP_HZ", 60.0, 600.0, 2.0, "%.0f Hz"),
        Setting("volume standing", "ENGINE_IDLE_VOLUME", 0.0, 1.0, 0.01),
        Setting("volume top speed", "ENGINE_VOLUME", 0.0, 1.0, 0.01),
        Setting("buzz", "ENGINE_BUZZ", 0.0, 1.0, 0.01),
        Setting("shimmer", "ENGINE_SHIMMER", 0.0, 6.0, 0.05, "%.2f %%"),
        Setting("throb", "ENGINE_THROB", 0.0, 1.0, 0.01),
    ], pygame.Rect(20, 70, SIZE[0] - 40, 400), on_change=changed,
        titles=("LISTENING  -  not saved", "ENGINE SOUND  -  S saves it in config.py"))
    big, small = pygame.font.Font(None, 34), pygame.font.Font(None, 21)
    clock = pygame.time.Clock()
    speed, glide, paused, note = 0.0, True, False, ""

    while True:
        dt = clock.tick(60) / 1000.0
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                pygame.quit()
                return
            if panel.handle(ev) or ev.type != pygame.KEYDOWN:
                continue
            if ev.key == pygame.K_g:
                glide = not glide
            elif ev.key == pygame.K_SPACE:
                paused = not paused
            elif ev.key == pygame.K_r:
                panel.revert()
                note = "back to the saved settings"
            elif ev.key == pygame.K_s:
                panel.save()
                note = "saved in neon_conduit/config.py"

        target = speed_set.value
        if not glide:
            speed = target
        elif speed < target:
            speed = min(target, speed + SPEED_UP * dt)
        else:
            speed = max(target, speed - SLOW_DOWN * dt)
        sound.engine(None if paused else speed)

        screen.fill(tuner.BACK)
        f, vol = engine.engine_tone(speed)
        state = "PAUSED" if paused else "speed %.0f: %.0f Hz, volume %.2f" % (speed, f, vol)
        screen.blit(big.render(state, True, tuner.ACCENT if paused else tuner.TEXT), (20, 22))
        panel.draw(screen)
        y = panel.y_of(0)               # the speed slider: race marks, and the speed playing
        for k, (mark, v) in enumerate(MARKS):
            x = panel.x_of(0, v)
            pygame.draw.line(screen, tuner.DIM, (x, y - 8), (x, y + 8), 2)
            img = small.render(mark, True, tuner.DIM)
            screen.blit(img, (x - img.get_width() // 2, y + 10 + 11 * (k % 2)))
        pygame.draw.circle(screen, (90, 220, 255), (panel.x_of(0, speed), y), 5)
        screen.blit(small.render(note, True, tuner.NOTE), (20, SIZE[1] - 70))
        tuner.hints(screen, small, (
            "Up / Down  pick      Left / Right  move (Shift: x10)      Home / End      click / drag",
            "G  glide: %s      Space  pause      S  save      R  revert      Esc  quit"
            % ("on" if glide else "off")), SIZE[1] - 46)
        pygame.display.flip()


if __name__ == "__main__":
    main()
