#!/usr/bin/env python3
"""Balance the music against the engine and the sound effects, by ear.

    python3 tools/sound_mix.py

One slider per sound: the title and race music, the engine (standing and at top speed), and
each sound effect (the *_VOLUME settings in neon_conduit/config.py). Every change is heard
at once.

Up / Down pick a slider, Left / Right move it (Shift: in bigger steps), or click and drag
any slider. Enter (or a click on its name) plays the picked sound; on a music slider, it
switches to that music (Enter again on the race music: another song). Space starts or
stops a race demo: the engine at cruising speed, rising on boosts, with shots, drones going
down, stars, gates, kerbs and doors at about a race's pace, to judge the balance as a whole.
E turns the engine on or off, M the music. S saves the settings into config.py; R puts back
the saved ones. Esc quits.
"""
import random

import pygame

import tuner
from tuner import Setting
from neon_conduit import audio
from neon_conduit.config import (BASE_SPEED, BOOST_MULT, BOOST_TIME, FIRE_INTERVAL, SPEED_CAP,
                                 TITLE_MUSIC)

SIZE = (800, 740)           # the window, in pixels
CRUISE = (BASE_SPEED + SPEED_CAP) / 2   # the demo's cruising speed, a mid-race one
SPEED_UP = 70.0             # the engine's glide rates, in speed per second: the game's...
SLOW_DOWN = 55.0            # ...when speeding up and slowing down
# The race demo: how often each sound comes, on average, in times per second (shots come
# in bursts: one every FIRE_INTERVAL for BURST seconds, about every BURST_EVERY seconds).
DEMO_RATES = {"boom": 0.35, "star": 0.7, "gate": 1 / 14, "boost": 1 / 9, "scrape": 0.25,
              "hit": 1 / 16, "door": 1 / 25}
BURST, BURST_EVERY = 1.2, 3.0
# The sliders' sounds: the effect each one plays (None: music; "engine": the engine).
SLIDERS = (
    ("title music", "TITLE_MUSIC_VOLUME", "title"),
    ("race music", "RACE_MUSIC_VOLUME", "race"),
    ("engine standing", "ENGINE_IDLE_VOLUME", "engine"),
    ("engine top speed", "ENGINE_VOLUME", "engine"),
    ("shot", "SHOT_SOUND_VOLUME", "shot"),
    ("drone shot down", "BOOM_SOUND_VOLUME", "boom"),
    ("drone hits you", "HIT_SOUND_VOLUME", "hit"),
    ("boost pad", "BOOST_SOUND_VOLUME", "boost"),
    ("star", "STAR_SOUND_VOLUME", "star"),
    ("gate", "GATE_SOUND_VOLUME", "gate"),
    ("kerb scrape", "SCRAPE_SOUND_VOLUME", "scrape"),
    ("door", "DOOR_SOUND_VOLUME", "door"),
)


def main():
    pygame.init()
    screen = pygame.display.set_mode(SIZE)
    pygame.display.set_caption("Neon Conduit - sound mix")
    sound = audio.Audio()
    if not sound.ok:
        print("No sound device: nothing to hear.")
    music = {"which": None, "song": ""}     # the music playing ("title", "race" or None)

    def play_music(which):
        sound.stop_music()
        music["which"], music["song"] = which, ""
        if which == "title":
            sound.music(TITLE_MUSIC, tuner.config.TITLE_MUSIC_VOLUME)
            music["song"] = "Hero Immortal"
        elif which == "race":
            tags = sound.race_music()
            if tags:
                music["song"] = '"%s"  %s' % (tags["title"], tags["artist"])
            else:
                music["which"], music["song"] = None, "no race music in neon_conduit/music/"

    def changed(s):
        if s.name.endswith("_MUSIC_VOLUME"):
            if music["which"] and s.name.startswith(music["which"].upper()) and sound.ok:
                pygame.mixer.music.set_volume(s.value)
        elif s.name.endswith("_SOUND_VOLUME") and sound.ok:
            sound.apply_mix()

    panel = tuner.Panel([Setting(label, name, 0.0, 1.0, 0.01) for label, name, _ in SLIDERS],
                        pygame.Rect(20, 110, SIZE[0] - 40, 12 * tuner.ROW), on_change=changed)

    def play(i):
        what = SLIDERS[i][2]
        if what in ("title", "race"):
            play_music(what)
        elif what != "engine":
            sound.play(what)

    big, small = pygame.font.Font(None, 34), pygame.font.Font(None, 21)
    clock = pygame.time.Clock()
    speed, boost, engine_on, demo, note = 0.0, 0.0, True, False, ""
    burst, next_burst = 0.0, 0.0
    play_music("race")

    while True:
        dt = clock.tick(60) / 1000.0
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                sound.engine(None)
                pygame.quit()
                return
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and ev.pos[0] < 20 + tuner.LABEL_W:
                i = round((ev.pos[1] - panel.y_of(0)) / tuner.ROW)
                if 0 <= i < len(SLIDERS):           # a click on a name: play that sound
                    panel.sel = i
                    play(i)
                continue
            if panel.handle(ev) or ev.type != pygame.KEYDOWN:
                continue
            if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                play(panel.sel)
            elif ev.key == pygame.K_SPACE:
                demo = not demo
                burst, next_burst = 0.0, 0.5
            elif ev.key == pygame.K_e:
                engine_on = not engine_on
            elif ev.key == pygame.K_m:
                play_music(None if music["which"] else "race")
            elif ev.key == pygame.K_r:
                panel.revert()
                note = "back to the saved settings"
            elif ev.key == pygame.K_s:
                panel.save()
                note = "saved in neon_conduit/config.py"

        # The race demo: random sounds at about a race's pace, the engine boosting with the pads.
        if demo:
            for name, rate in DEMO_RATES.items():
                if random.random() < rate * dt:
                    sound.play(name)
                    if name == "boost":
                        boost = BOOST_TIME
            next_burst -= dt
            if next_burst <= 0:
                burst, next_burst = BURST, random.uniform(0.5, 2.0) * BURST_EVERY
            if burst > 0:
                if int(burst / FIRE_INTERVAL) != int((burst - dt) / FIRE_INTERVAL):
                    sound.play("shot")
                burst -= dt
        boost = max(0.0, boost - dt)
        if demo:
            target = CRUISE * (BOOST_MULT if boost > 0 else 1.0)
        elif SLIDERS[panel.sel][1] == "ENGINE_VOLUME":
            target = audio.ENGINE_TOP_SPEED     # the top-speed slider picked: hear it there
        else:
            target = 0.0                        # otherwise idling, as at the start line
        if speed < target:
            speed = min(target, speed + SPEED_UP * dt)
        else:
            speed = max(target, speed - SLOW_DOWN * dt)
        sound.engine(speed if engine_on else None)

        screen.fill(tuner.BACK)
        line = "RACE DEMO" if demo else "Space: race demo"
        screen.blit(big.render(line, True, tuner.ACCENT if demo else tuner.TEXT), (20, 18))
        state = "music: %s      engine: %s, speed %.0f" % (
            music["song"] or "off", "on" if engine_on else "off", speed)
        screen.blit(small.render(state, True, tuner.TEXT), (20, 58))
        screen.blit(small.render("(the door is heard as from right next to it)", True, tuner.DIM), (20, 78))
        panel.draw(screen)
        screen.blit(small.render(note, True, tuner.NOTE), (20, SIZE[1] - 70))
        tuner.hints(screen, small, (
            "Up / Down  pick      Left / Right  move (Shift: x10)      click / drag      "
            "Enter or click a name  play",
            "Space  race demo      E  engine      M  music      S  save      R  revert      Esc  quit"),
            SIZE[1] - 46)
        pygame.display.flip()


if __name__ == "__main__":
    main()
