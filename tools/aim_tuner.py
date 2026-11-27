#!/usr/bin/env python3
"""Fine-tune the guns and their auto-aim (lock-on) on a test bench.

    python3 tools/aim_tuner.py

The sled stands still in a stretch of tube that curves as the bend and slope sliders say
(the same ranges as the level editor's sections, but held all along). Ahead of it hangs a
ring of drones, at the depth and with as many drones as the ring sliders say. Every drone
the auto-aim could hit from where the sled is, as the game itself decides it, wears a green
crosshair; the one the guns are locked on to also gets the game's pink brackets.

Under the race, a top view and a side view, forward to the right: the tube's walls, the sled,
the auto-aim's cone (as wide as the lock angle, as long as the lock range), how far a shot
reaches in its life, the drones (green: can be hit) and the shots in flight. They are drawn
as a shot sees them: straight ahead from the guns, the tube curving away.

Drones on a collision course (close enough to the sled's line round the tube to hit it as
it passes, CRASH_WIDTH) are marked with a red X, and red in the views, where the ship and the
drones are drawn to scale and the sled's crash box (CRASH_BACK, CRASH_FRONT, CRASH_WIDTH)
shows in red. Set the ring depth inside the box (0: right on the sled) and those drones hit
the sled: it shows red with "HIT" (on the bench nothing crashes, so the ring stays to look at).

The other sliders are the guns' settings in neon_conduit/config.py: lock range and angle,
shot speed, life and rate, the guns' spread, how close a shot must pass to down a drone, the
free aim (Up / Down, used when nothing is locked on) and the crash zone. Every change is used
at once.

Left / Right move the sled round the tube, Up / Down aim, Space fires, F fires on its own.
Enter brings back the drones shot down. Click or drag the sliders. S saves the guns'
settings into config.py; R puts back the saved ones. Esc quits.
"""
import math
import random

import pygame

import tuner
from tuner import Setting
from neon_conduit import game as game_mod
from neon_conduit.config import FLOOR_HW, FLOOR_Y, FOCAL, HORIZON, R, SCREEN, SEG
from neon_conduit.game import Controls, Game
from neon_conduit.geometry import lat_dist, wall_xy, wrap
from neon_conduit.render import SHIP, SHIP_HOVER, Renderer
from neon_conduit.track import Track
from neon_conduit.tutorial import Tutorial

PANEL_W = 460               # pixels of sliders right of the race...
BAND_H = 250                # ...and of top and side views under it
TRACK_SEGS = 200            # segments of tube on the bench, the sled near its start...
SLED_SEG = 20               # ...at this segment
MOVE_RATE = 1.6             # how fast Left / Right move the sled round the tube, radians a second
MUZZLE = 3.0                # shots leave this far ahead of the sled (as in Game._shoot)
GREEN = (90, 255, 140)
GREY = (120, 125, 150)
PINK = (255, 80, 160)
WALL = (90, 140, 255)
CONE = (255, 210, 90)
SHOT = (255, 255, 160)
DRONE_R = 1.0               # a drone's half-size as the game draws it (world units)
RED = (255, 60, 60)


def bench_track(bend, slope):
    """A stretch of tube curving evenly all along, with nothing on it."""
    tr = Track(random.Random(0), ())
    tr.ensure(TRACK_SEGS, 0)
    n = len(tr.curv)
    tr.curv, tr.pitch = [bend] * n, [slope] * n
    tr.open, tr.air, tr.width, tr.stretch = [False] * n, [False] * n, [FLOOR_HW] * (n + 1), [0] * n
    tr.objects, tr.doors, tr.no_star = [], set(), set(range(n))   # no gates, drones or stars
    return tr


def bench_game():
    """The game on the bench: the sled still, near the start of the bench track."""
    game = Game(1)
    game.reset()
    game.tutorial = Tutorial(())
    game.track = bench_track(0.0, 0.0)
    game.state = "play"
    game.cam_z = SLED_SEG * SEG
    game.prev_z = game.sled_z
    game.speed = 0.0
    return game


def hittable(game, o, dt):
    """True if the auto-aim could hit drone o from where the sled is: in lock range, and
    a straight shot from the sled's middle reaches it within the lock angle, in its life,
    with nothing in the way (the game's own test, Game._target and Game._intercept)."""
    pz = game.sled_z
    if not pz + MUZZLE < o["z"] < pz + game_mod.LOCK_RANGE:
        return False
    x, y = wall_xy(game.theta, 0.0, 1.0, True, game.flat)
    return bool(game._intercept(o, x, y, pz + MUZZLE, game.speed + game_mod.BULLET_SPEED, dt))


def on_course(game, o):
    """True if drone o is close enough to the sled's line round the tube to hit it as the
    sled passes (as Game._objects decides it)..."""
    return lat_dist(o["a"], game.theta, game.flat) < game_mod.CRASH_WIDTH


def touching(game, o):
    """...and true if it is hitting it now: inside the crash box (as Game._objects decides it)."""
    return on_course(game, o) and -game_mod.CRASH_BACK < o["z"] - game.sled_z < game_mod.CRASH_FRONT


def hull(pts):
    """The convex outline of 2D points (to draw the ship's shadow in a view)."""
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts

    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2 and ((out[-1][0] - out[-2][0]) * (p[1] - out[-2][1])
                                     - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0])) <= 0:
                out.pop()
            out.append(p)
        return out
    return half(pts)[:-1] + half(reversed(pts))[:-1]


def red_x(screen, renderer, o):
    """A red X over drone o in the race view: on a collision course."""
    p = renderer.proj(o["z"], o["a"], 0.0, 1.5, True)
    if not p:
        return
    x, y, s = p[0], p[1], max(7.0, p[2] * 1.6)
    pygame.draw.line(screen, RED, (x - s, y - s), (x + s, y + s), 3)
    pygame.draw.line(screen, RED, (x - s, y + s), (x + s, y - s), 3)


def crosshair(screen, renderer, o):
    """A green crosshair over drone o in the race view."""
    p = renderer.proj(o["z"], o["a"], 0.0, 1.5, True)
    if not p:
        return
    x, y, s = p[0], p[1], max(8.0, p[2] * 2.0)
    pygame.draw.circle(screen, GREEN, (int(x), int(y)), int(s), 2)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        pygame.draw.line(screen, GREEN, (x + dx * s * 0.5, y + dy * s * 0.5),
                         (x + dx * s * 1.4, y + dy * s * 1.4), 2)


class Views:
    """The top view (axis 0: sideways) and side view (axis 1: up and down) of the bench, in
    the frame of a straight shot from the guns: a point at depth z, at (x, y) in the tube's
    cross-section there, is drawn at (x, y) minus how far the tube has turned by z."""

    def __init__(self, rect):
        self.rect = rect
        self.font = pygame.font.Font(None, 20)

    def draw(self, screen, game, ring_depth, can_hit, course):
        pz = game.sled_z
        z0 = pz + MUZZLE
        reach = (game.speed + game_mod.BULLET_SPEED) * (game_mod.BULLET_LIFE - 0.05)
        zmin, zmax = pz - 10.0, pz + max(game_mod.LOCK_RANGE, ring_depth) + 15.0
        zs = [zmin + (zmax - zmin) * k / 48 for k in range(49)]
        centre = {z: game._drift(z0, z) for z in zs}            # how far the tube has turned
        gx, gy = wall_xy(game.theta, 0.0, 1.0, True, game.flat)  # the guns
        half_w = self.rect.w // 2
        for axis, name in ((0, "top view (right is down)"), (1, "side view (floor is down)")):
            r = pygame.Rect(self.rect.x + axis * half_w, self.rect.y, half_w, self.rect.h)
            pygame.draw.rect(screen, (8, 10, 22), r)
            pygame.draw.rect(screen, (40, 45, 70), r, 1)
            # One scale both ways, so angles show true: the whole depth, and the tube across
            # (as far as it turns, within reason).
            span = min(60.0, max(R + 2.0, max(abs(c[axis]) for c in centre.values()) + R + 2.0))
            scale = min((r.w - 24) / (zmax - zmin), (r.h - 34) / (2 * span))

            def at(z, v):
                return r.x + 12 + (z - zmin) * scale, r.centery + 10 + v * scale

            def clip(pt):
                return (pt[0], max(r.y + 20, min(r.bottom - 2, pt[1])))

            # The tube: its walls, as the tube turns away from the straight line.
            lo, hi = (-R, R) if axis == 0 else (-R, FLOOR_Y)
            for side in (lo, hi):
                pygame.draw.lines(screen, WALL, False, [clip(at(z, side - centre[z][axis])) for z in zs], 2)
            # The auto-aim's cone, from the guns to the lock range, and how far a shot reaches.
            g = (gx, gy)[axis]
            end = pz + game_mod.LOCK_RANGE
            w = (end - z0) * math.tan(game_mod.LOCK_ANGLE)
            cone = [at(z0, g), at(end, g - w), at(end, g + w)]
            layer = pygame.Surface(r.size, pygame.SRCALPHA)
            pygame.draw.polygon(layer, CONE + (50,), [(x - r.x, y - r.y) for x, y in cone])
            screen.blit(layer, r.topleft)
            pygame.draw.polygon(screen, CONE, cone, 1)
            if z0 + reach < zmax:
                x = at(z0 + reach, 0)[0]
                pygame.draw.line(screen, SHOT, (x, r.y + 20), (x, r.bottom - 4), 1)
                screen.blit(self.font.render("shot reach", True, SHOT), (x + 4, r.bottom - 18))
            # The sled, the drones and the shots.
            # The ship, to scale: the outline of its model seen from above or from the side.
            ship = [at(pz + z, wall_xy(game.theta, x, y + SHIP_HOVER, True, game.flat)[axis])
                    for x, y, z in SHIP.verts]
            pygame.draw.polygon(screen, (230, 235, 255), hull([(round(x, 1), round(y, 1)) for x, y in ship]))
            # The crash box: a drone's middle inside it hits the sled. Across, CRASH_WIDTH along
            # the wall either side (drawn straight: near enough round a sled's width of tube);
            # in the side view, over a drone's height range.
            across = [wall_xy(game.theta, lat, h, True, game.flat)[axis]
                      for lat in (-game_mod.CRASH_WIDTH, game_mod.CRASH_WIDTH) for h in (0.0, 3.0)]
            x0, y0 = at(pz - game_mod.CRASH_BACK, min(across))
            x1, y1 = at(pz + game_mod.CRASH_FRONT, max(across))
            pygame.draw.rect(screen, RED, (x0, y0, max(2, x1 - x0), max(2, y1 - y0)), 1)
            for o in game.track.objects:
                if o["kind"] != "drone":
                    continue
                c = wall_xy(o["a"], 0.0, 1.5, True, 0.0)[axis] - game._drift(z0, o["z"])[axis]
                p = clip(at(o["z"], c))
                pt = (int(p[0]), int(p[1]))
                rad = max(3, int(DRONE_R * scale))      # to scale
                pygame.draw.circle(screen, RED if id(o) in course else GREY, pt, rad)
                if id(o) in can_hit:
                    pygame.draw.circle(screen, GREEN, pt, rad + 2, 2)
                if o is game.lock:
                    pygame.draw.circle(screen, PINK, pt, rad + 5, 2)
            for b in game.bullets:
                c = (b["x"], b["y"])[axis] - game._drift(z0, b["z"])[axis]
                p = clip(at(b["z"], c))
                pygame.draw.circle(screen, SHOT, (int(p[0]), int(p[1])), 2)
            title = name + ("" if z0 + reach < zmax else "      shot reach %.0f: further right" % reach)
            screen.blit(self.font.render(title, True, tuner.DIM), (r.x + 8, r.y + 4))


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN[0] + PANEL_W, SCREEN[1] + BAND_H))
    pygame.display.set_caption("Neon Conduit - auto-aim bench")
    view = screen.subsurface(pygame.Rect((0, 0), SCREEN))
    renderer = Renderer(view, FOCAL, HORIZON)
    views = Views(pygame.Rect(0, SCREEN[1], SCREEN[0], BAND_H))
    game = bench_game()

    bend = Setting("tube bend", None, -0.6, 0.6, 0.05, "%+.2f", value=0.0)
    slope = Setting("tube slope", None, -0.3, 0.3, 0.05, "%+.2f", value=0.0)
    depth = Setting("ring depth", None, 0.0, 250.0, 1.0, "%.0f", value=50.0)
    count = Setting("drones in ring", None, 1.0, 24.0, 1.0, "%.0f", value=12.0)

    def make_ring():
        """The ring of drones, evenly round the tube from the floor's middle, hanging still."""
        n, z = int(round(count.value)), game.sled_z + depth.value
        game.track.objects = [o for o in game.track.objects if o["kind"] != "drone"]
        for k in range(n):
            a = 2 * math.pi * k / n
            game.track.objects.append({"kind": "drone", "z": z, "v": 0.0, "a0": a, "a": a,
                                       "amp": 0.0, "w": 0.0, "ph": 0.0})

    def changed(s):
        if s is bend or s is slope:
            tr = game.track
            tr.curv[:] = [bend.value] * len(tr.curv)
            tr.pitch[:] = [slope.value] * len(tr.pitch)
        elif s is depth or s is count:
            make_ring()

    panel = tuner.Panel([
        bend, slope, depth, count,
        Setting("lock range", "LOCK_RANGE", 10.0, 200.0, 1.0, "%.0f"),
        Setting("lock angle", "LOCK_ANGLE", 0.01, 0.5, 0.005, lambda v: "%.1f deg" % math.degrees(v)),
        Setting("shot speed", "BULLET_SPEED", 50.0, 600.0, 5.0, "%.0f"),
        Setting("shot life", "BULLET_LIFE", 0.2, 2.0, 0.05, "%.2f s"),
        Setting("fire interval", "FIRE_INTERVAL", 0.04, 0.5, 0.01, "%.2f s"),
        Setting("gun spread", "GUN_SPREAD", 0.0, 3.0, 0.05),
        Setting("hit radius", "DRONE_HIT_R", 0.5, 6.0, 0.1, "%.1f"),
        Setting("free aim slope", "AIM_SLOPE", 0.0, 0.3, 0.005, "%.3f"),
        Setting("free aim swing", "AIM_RATE", 0.5, 10.0, 0.1, "%.1f / s"),
        Setting("crash box behind", "CRASH_BACK", 0.0, 8.0, 0.1, "%.1f"),
        Setting("crash box ahead", "CRASH_FRONT", 0.0, 10.0, 0.1, "%.1f"),
        Setting("crash box width", "CRASH_WIDTH", 0.5, 8.0, 0.1, "%.1f"),
    ], pygame.Rect(SCREEN[0] + 16, 12, PANEL_W - 24, 16 * tuner.ROW), keys=False, on_change=changed,
        titles=("BENCH  -  what you look at, not saved", "GAMEPLAY  -  S saves it in config.py"))
    make_ring()
    font, small, big = pygame.font.Font(None, 26), pygame.font.Font(None, 21), pygame.font.Font(None, 72)
    clock = pygame.time.Clock()
    autofire, note = False, ""

    while True:
        dt = min(0.05, clock.tick(60) / 1000.0)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                pygame.quit()
                return
            if panel.handle(ev) or ev.type != pygame.KEYDOWN:
                continue
            if ev.key == pygame.K_f:
                autofire = not autofire
            elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                make_ring()
            elif ev.key == pygame.K_r:
                panel.revert()
                note = "back to the saved settings"
            elif ev.key == pygame.K_s:
                panel.save()
                note = "saved in neon_conduit/config.py"

        # The bench's step: the sled stays put; lock-on, guns, drones and explosions go on.
        keys = pygame.key.get_pressed()
        move = keys[pygame.K_RIGHT] - keys[pygame.K_LEFT]
        game.theta = game.roll = wrap(game.theta + move * MOVE_RATE * dt)
        controls = Controls(0, autofire or keys[pygame.K_SPACE], keys[pygame.K_DOWN] - keys[pygame.K_UP])
        pz = game.sled_z
        game.t += dt
        rate = game_mod.AIM_RATE * dt
        game.aim += max(-rate, min(rate, controls.aim - game.aim))
        game.lock = game._target(pz, dt)
        game._shoot(dt, controls.fire, pz)
        # Drones hitting the sled are kept out of the game's hands meanwhile: on the bench,
        # nothing crashes; they only show it.
        hitting = [o for o in game.track.objects if o["kind"] == "drone" and touching(game, o)]
        game.track.objects = [o for o in game.track.objects if not any(o is h for h in hitting)]
        game._objects(dt, pz)
        game.track.objects += hitting
        game._effects(dt)
        drones = [o for o in game.track.objects if o["kind"] == "drone"]
        can_hit = {id(o) for o in drones if hittable(game, o, dt)}
        course = {id(o) for o in drones if on_course(game, o)}

        renderer.draw(game)
        for o in drones:
            if id(o) in can_hit:
                crosshair(view, renderer, o)
            if id(o) in course:
                red_x(view, renderer, o)
        renderer._reticle(game)                 # the game's brackets on the drone locked on to
        if hitting:                             # the sled hit: a red ring round it, and HIT
            p = renderer.proj(pz, game.theta, 0.0, 1.0, True)
            if p:
                pygame.draw.circle(view, RED, (int(p[0]), int(p[1])), int(max(30, p[2] * 5)), 4)
            img = big.render("HIT", True, RED)
            view.blit(img, ((SCREEN[0] - img.get_width()) // 2, 60))
        views.draw(screen, game, depth.value, can_hit, course)
        line = "%d of %d drones can be hit" % (len(can_hit), len(drones))
        view.blit(font.render(line, True, GREEN if can_hit else tuner.TEXT), (16, 14))
        line = "%d on a collision course%s" % (len(course), ", %d hitting the sled" % len(hitting) if hitting else "")
        view.blit(font.render(line, True, RED if course else tuner.TEXT), (16, 38))
        if autofire:
            view.blit(font.render("AUTO-FIRE", True, GREEN), (16, 62))
        pygame.draw.rect(screen, tuner.BACK, (SCREEN[0], 0, PANEL_W, SCREEN[1] + BAND_H))
        panel.draw(screen)
        screen.blit(font.render(note, True, tuner.NOTE), (SCREEN[0] + 16, panel.bottom + 6))
        for k, h in enumerate(("click / drag the sliders",
                               "Left / Right  move round the tube      Up / Down  aim",
                               "Space  fire      F  auto-fire      Enter  bring the ring back",
                               "S  save      R  revert      Esc  quit")):
            screen.blit(small.render(h, True, tuner.DIM), (SCREEN[0] + 16, SCREEN[1] + BAND_H - 84 + 20 * k))
        pygame.display.flip()


if __name__ == "__main__":
    main()
