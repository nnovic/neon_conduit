#!/usr/bin/env python3
"""Fine-tune the guns and their auto-aim (lock-on) in a live race.

    python3 tools/aim_tuner.py [--seed N]

Left, a race on the endless track (no tutorial, no clock), the autopilot driving and firing,
with brackets round the drone the guns are locked on to. Right, one slider per setting (in
neon_conduit/config.py): how far ahead and how far off the heading a drone can be locked on
to, the shots' speed, life and rate, the guns' spread, how close a shot must pass to down a
drone, the drones' speed, and the free aim (Up / Down, when nothing is locked on). Every
change is used at once. The last slider, practice drones, is the tool's own: extra drones
sent in on top of the track's, to have plenty to shoot at.

Over the race, the counts since the last change of a setting: the drones met (that came in
lock range), how many were shot down, rammed or got past, how often a drone in range was
locked on to, and the volleys fired. They start again at each change, so two settings can
be compared on a fair number of drones.

Click or drag the sliders. F1 switches between the autopilot and driving yourself (the
game's keys: Left / Right steer, Up / Down aim, Space fires). P pauses, F5 restarts the
counts. S saves the settings into config.py; R puts back the saved ones. Esc quits.
"""
import argparse
import math
import random

import pygame

import tuner
from tuner import Setting
from neon_conduit import config
from neon_conduit.app import read_controls
from neon_conduit.audio import Silent
from neon_conduit.config import FOCAL, HORIZON, SCREEN, SEG
from neon_conduit.game import Game
from neon_conduit.hud import Hud
from neon_conduit.render import Renderer
from neon_conduit.track import Track
from neon_conduit.tutorial import Tutorial

PANEL_W = 460               # pixels of sliders right of the race
SPAWN_AHEAD = (170.0, 260.0)    # practice drones appear this far ahead of the sled (world units)
STATS_BACK = (0, 0, 0, 170)


def degrees(v):
    return "%.1f deg" % math.degrees(v)


class Counting(Silent):
    """No sound, but counts the volleys fired."""

    def __init__(self):
        self.volleys = 0

    def play(self, name):
        if name == "shot":
            self.volleys += 1
        return None


def new_race(seed):
    """A race on the endless random track, straight into play: no tutorial, no start line."""
    game = Game(seed, Counting())
    game.reset()
    game.tutorial = Tutorial(())
    game.track = Track(game.rng, ())
    game.state = "play"
    return game


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seed", type=int, default=1, help="the track's seed")
    args = ap.parse_args()
    pygame.init()
    screen = pygame.display.set_mode((SCREEN[0] + PANEL_W, SCREEN[1]))
    pygame.display.set_caption("Neon Conduit - auto-aim")
    view = screen.subsurface(pygame.Rect((0, 0), SCREEN))
    renderer, hud = Renderer(view, FOCAL, HORIZON), Hud(view)
    config.DEVELOPER_MODE = True            # the lock-on brackets (and the fast line)
    game = new_race(args.seed)
    stats = {}

    def restart_counts(*_):
        # followed: the drones in lock range, by id, until shot down, rammed or got past
        stats.update(followed={}, down=0, rammed=0, past=0, in_range=0, locked=0,
                     volleys0=game.audio.volleys)

    restart_counts()
    practice = Setting("practice drones", None, 0.0, 3.0, 0.1, "%.1f / s", value=0.5)
    panel = tuner.Panel([
        Setting("lock range", "LOCK_RANGE", 10.0, 200.0, 1.0, "%.0f"),
        Setting("lock angle", "LOCK_ANGLE", 0.01, 0.5, 0.005, degrees),
        Setting("shot speed", "BULLET_SPEED", 50.0, 600.0, 5.0, "%.0f"),
        Setting("shot life", "BULLET_LIFE", 0.2, 2.0, 0.05, "%.2f s"),
        Setting("fire interval", "FIRE_INTERVAL", 0.04, 0.5, 0.01, "%.2f s"),
        Setting("gun spread", "GUN_SPREAD", 0.0, 3.0, 0.05),
        Setting("hit radius", "DRONE_HIT_R", 0.5, 6.0, 0.1, "%.1f"),
        Setting("drone speed", "DRONE_SPEED", 0.0, 1.0, 0.01, "%.2f x top"),
        Setting("free aim slope", "AIM_SLOPE", 0.0, 0.3, 0.005, "%.3f"),
        Setting("free aim swing", "AIM_RATE", 0.5, 10.0, 0.1, "%.1f / s"),
        practice,
    ], pygame.Rect(SCREEN[0] + 16, 24, PANEL_W - 24, 11 * tuner.ROW), keys=False,
        on_change=restart_counts)
    font, small = pygame.font.Font(None, 26), pygame.font.Font(None, 21)
    clock = pygame.time.Clock()
    auto, paused, spawn_t, note = True, False, 0.0, ""
    stats_box = pygame.Surface((360, 146), pygame.SRCALPHA)

    while True:
        dt = min(0.05, clock.tick(60) / 1000.0)
        fire = False
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                pygame.quit()
                return
            if panel.handle(ev) or ev.type != pygame.KEYDOWN:
                continue
            if ev.key == pygame.K_F1:
                auto = not auto
            elif ev.key == pygame.K_p:
                paused = not paused
            elif ev.key == pygame.K_F5:
                restart_counts()
            elif ev.key == pygame.K_SPACE:
                fire = True
            elif ev.key == pygame.K_r:
                panel.revert()
                note = "back to the saved settings"
            elif ev.key == pygame.K_s:
                panel.save()
                note = "saved in neon_conduit/config.py"

        if not paused:
            game.time_left = 999.0              # no clock: race on for as long as it takes
            pz = game.sled_z
            spawn_t += dt * practice.value
            if spawn_t >= 1.0:                  # a practice drone, somewhere ahead
                spawn_t -= 1.0
                game.track.objects.append({
                    "kind": "drone", "z": pz + random.uniform(*SPAWN_AHEAD), "a0": random.uniform(-0.9, 0.9),
                    "a": 0.0, "amp": random.uniform(0.2, 0.7), "w": random.uniform(1.0, 2.5),
                    "ph": random.uniform(0, 6.28)})
            controls = game.autopilot() if auto else read_controls(pygame.key.get_pressed(), fire)
            game.update(dt, controls)
            pz = game.sled_z
            # The counts: each drone that came in lock range, and how it went.
            drones = {id(o): o for o in game.track.objects if o["kind"] == "drone"}
            followed = stats["followed"]
            for k, o in list(followed.items()):
                if k not in drones:             # gone: shot down ahead, or hit by the sled
                    stats["down" if o["z"] > pz + 2.5 else "rammed"] += 1
                elif o["z"] < pz - 2.5:         # behind the sled: it got past
                    stats["past"] += 1
                else:
                    continue
                del followed[k]
            ahead = [o for o in drones.values() if pz + 3 < o["z"] < pz + config.LOCK_RANGE]
            for o in ahead:
                followed[id(o)] = o
            if ahead:
                stats["in_range"] += 1
                stats["locked"] += game.lock is not None

        renderer.draw(game)
        hud.draw(game)
        met = len(stats["followed"]) + stats["down"] + stats["rammed"] + stats["past"]
        lines = ("drones met %d" % met,
                 "shot down %d (%.0f %%)" % (stats["down"], 100.0 * stats["down"] / max(1, met)),
                 "rammed %d      got past %d" % (stats["rammed"], stats["past"]),
                 "locked on %.0f %% of the time one was in range"
                 % (100.0 * stats["locked"] / max(1, stats["in_range"])),
                 "volleys fired %d" % (game.audio.volleys - stats["volleys0"]),
                 "%s%s" % ("AUTOPILOT" if auto else "YOU DRIVE", "   PAUSED" if paused else ""))
        stats_box.fill(STATS_BACK)
        for k, line in enumerate(lines):
            stats_box.blit(small.render(line, True, tuner.TEXT), (10, 8 + 22 * k))
        view.blit(stats_box, (SCREEN[0] - stats_box.get_width() - 10, 10))   # top right
        pygame.draw.rect(screen, tuner.BACK, (SCREEN[0], 0, PANEL_W, SCREEN[1]))
        panel.draw(screen)
        screen.blit(font.render(note, True, tuner.NOTE), (SCREEN[0] + 16, SCREEN[1] - 96))
        hint = small.render
        for k, h in enumerate(("click / drag the sliders      F1  autopilot / you drive",
                               "P  pause      F5  restart the counts",
                               "S  save      R  revert      Esc  quit")):
            screen.blit(hint(h, True, tuner.DIM), (SCREEN[0] + 16, SCREEN[1] - 68 + 20 * k))
        pygame.display.flip()


if __name__ == "__main__":
    main()
