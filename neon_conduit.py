#!/usr/bin/env python3
"""Neon Conduit - an original tunnel racer written with pygame.

Ride a hover sled through an endless, procedurally generated tube.  Curves
throw you up the walls, boost pads sit on the fast line, barriers and drones
get in the way, and the clock only stops if you reach the next gate.

Controls
    Left / Right (or A / D)   steer around the tube wall
    Down (or S)               brake
    Space                     fire
    P                         pause
    Enter                     start / restart
    Esc                       quit
"""
import argparse
import math
import random
import sys
from array import array

import pygame

W, H = 1024, 640
CX, CY = W // 2, int(H * 0.47)
FOCAL = 600.0
NEAR = 0.8

R = 10.0            # tube radius
SEG = 5.0           # length of one track segment
SIDES = 16          # polygon sides of the tube
DRAW = 60           # rings drawn ahead of the camera
PLAYER_D = 12.0     # how far ahead of the camera the sled sits
CAM_H = 3.5         # camera height above the surface the sled is riding on
FLOOR_A = math.pi / 4   # the tube is flat below this angle either side of the bottom
FLOOR_Y = R * math.cos(FLOOR_A)
FLOOR_HW = FLOOR_Y * math.tan(FLOOR_A)   # half-width of the flat floor
WALL_H = 2.2        # height of the upright kerbs lining open sections
SLED_HW = 1.5
SCRAPE_DRAG = 130.0     # speed lost per second while grinding along a kerb
SCRAPE_FLOOR = 0.5      # ...down to this fraction of top speed

GATE_SEGS = 260
START_TIME = 25.0
BASE_SPEED = 115.0

FOG = (6, 8, 22)
PALETTES = [
    ((20, 70, 150), (28, 110, 200)),
    ((120, 30, 130), (170, 50, 170)),
    ((20, 110, 90), (30, 160, 120)),
    ((150, 70, 20), (200, 110, 30)),
    ((150, 30, 50), (200, 50, 70)),
]

BOOST_HW = 2.2      # half-widths, in world units
BLOCK_HW = 3.0


def floor_limit(half_width):
    """Largest angle at which something this wide still sits wholly on the flat floor."""
    return math.atan((FLOOR_HW - half_width - 0.2) / FLOOR_Y)


# Open sections are a flat road between upright kerbs: nothing leaves the floor.
OPEN_LIMIT = floor_limit(SLED_HW)

FLOOR_COLS = ((58, 60, 74), (76, 79, 96))   # slate road, same in every zone

SIDE_A = [-math.pi + 2 * math.pi * k / SIDES for k in range(SIDES + 1)]
SIDE_SIN = [math.sin(a) for a in SIDE_A]
SIDE_COS = [math.cos(a) for a in SIDE_A]


def prof(a):
    """Distance from the tube centre to the wall at angle a (flat floor at the bottom)."""
    c = math.cos(a)
    return FLOOR_Y / c if c > FLOOR_Y / R else R


def bank(a):
    """0 on the flat floor, 1 on the curved wall, blended across the corner."""
    return max(0.0, min(1.0, (abs(wrap(a)) - 0.8 * FLOOR_A) / 0.35))


def lat_pos(a):
    """Distance along the wall surface from the middle of the floor to angle a."""
    w = wrap(a)
    if abs(w) < FLOOR_A:
        return FLOOR_Y * math.tan(w)
    return math.copysign(FLOOR_Y * math.tan(FLOOR_A) + R * (abs(w) - FLOOR_A), w)


PERIMETER = 2 * (FLOOR_Y * math.tan(FLOOR_A) + R * (math.pi - FLOOR_A))


def lat_dist(a1, a2):
    """Sideways distance between two wall angles, in world units."""
    d = abs(lat_pos(a1) - lat_pos(a2))
    return min(d, PERIMETER - d)


def snap(a, half_width):
    """Move angle a so an object this wide sits wholly on the floor or wholly on the wall."""
    w = wrap(a)
    lo = math.atan((FLOOR_Y * math.tan(FLOOR_A) - half_width - 0.2) / FLOOR_Y)
    hi = FLOOR_A + (half_width + 0.2) / R
    if lo < abs(w) < hi:
        w = math.copysign(lo if abs(w) < (lo + hi) / 2 else hi, w)
    return w


def wall_xy(a, lat, h, rigid=False):
    """Point in the tube cross-section: at wall angle a, lat units sideways, h above the surface.

    Fixed scenery follows the surface (flat on the floor, curved on the wall).
    Moving things are rigid: they use one local frame, which stays upright on
    the floor and turns smoothly to the wall normal past the corner.
    """
    w = wrap(a)
    if rigid:
        r = prof(w)
        na = w * bank(w)
        return (r * math.sin(w) + lat * math.cos(na) - h * math.sin(na),
                r * math.cos(w) - lat * math.sin(na) - h * math.cos(na))
    if abs(w) < FLOOR_A:
        return FLOOR_Y * math.tan(w) + lat, FLOOR_Y - h
    a2 = w + lat / R
    return (R - h) * math.sin(a2), (R - h) * math.cos(a2)


SIDE_R = [prof(a) for a in SIDE_A]
SIDE_MID = [SIDE_A[k] + math.pi / SIDES for k in range(SIDES)]
# Sides lit from below so the floor reads brighter than the ceiling.
SIDE_LIGHT = [0.62 + 0.38 * math.cos(m) for m in SIDE_MID]
FLOOR_SIDES = [s for s in range(SIDES) if abs(SIDE_MID[s]) < FLOOR_A]
# Kerbs in open sections: (floor-edge ring vertex, index of the kerb-top point, x of the kerb).
KERBS = ((FLOOR_SIDES[0], SIDES + 1, -FLOOR_HW), (FLOOR_SIDES[-1] + 1, SIDES + 2, FLOOR_HW))
KERB_COLS = ((230, 200, 60), (150, 120, 40))


def wrap(a):
    """Wrap an angle to [-pi, pi]."""
    return (a + math.pi) % (2 * math.pi) - math.pi


def mix(c1, c2, t):
    return (int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t))


# --------------------------------------------------------------------- audio
class Audio:
    RATE = 22050

    def __init__(self):
        self.ok = False
        self.sounds = {}
        try:
            pygame.mixer.init(self.RATE, -16, 1, 512)
            self.sounds = {
                "shot": self._sweep(900, 300, 0.09, 0.25),
                "boost": self._sweep(200, 900, 0.35, 0.3),
                "hit": self._noise(0.3, 0.45),
                "boom": self._noise(0.22, 0.3),
                "gate": self._sweep(500, 1300, 0.45, 0.3),
                "scrape": self._noise(0.14, 0.22),
            }
            self.ok = True
        except pygame.error:
            pass

    def _sweep(self, f0, f1, dur, vol):
        n = int(self.RATE * dur)
        buf, phase = array("h"), 0.0
        for i in range(n):
            t = i / n
            phase += 2 * math.pi * (f0 + (f1 - f0) * t) / self.RATE
            sq = 1.0 if math.sin(phase) > 0 else -1.0
            buf.append(int(32767 * vol * (1 - t) * sq))
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def _noise(self, dur, vol):
        n = int(self.RATE * dur)
        buf, v = array("h"), 0.0
        for i in range(n):
            if i % 6 == 0:
                v = random.uniform(-1, 1)
            buf.append(int(32767 * vol * (1 - i / n) * v))
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def play(self, name):
        if self.ok:
            self.sounds[name].play()


# --------------------------------------------------------------------- track
class Track:
    """Endless track: per-segment curvature, pitch and open/closed flag."""

    def __init__(self, rng):
        self.rng = rng
        self.curv = []
        self.pitch = []
        self.open = []
        self.objects = []          # dicts: kind, z, a, ...
        self.next_gate = GATE_SEGS
        self._section(30, 0.0, 0.0, False, 0, empty=True)

    def ensure(self, seg_index, level):
        while len(self.curv) < seg_index:
            rng = self.rng
            n = rng.randint(24, 56)
            c = 0.0
            if rng.random() < 0.72:
                peak = min(0.55, 0.30 + 0.04 * level)
                c = rng.uniform(0.14, peak) * rng.choice((-1, 1))
            p = rng.uniform(-0.2, 0.2) if rng.random() < 0.5 else 0.0
            self._section(n, c, p, rng.random() < 0.3, level)

    def _section(self, n, c, p, is_open, level, empty=False):
        rng = self.rng
        start = len(self.curv)
        for j in range(n):
            env = math.sin(math.pi * (j + 0.5) / n)
            self.curv.append(c * env)
            self.pitch.append(p * env)
            self.open.append(is_open)
        # Checkpoint gates at fixed intervals.
        while self.next_gate < start + n:
            self.objects.append({"kind": "gate", "z": self.next_gate * SEG})
            self.next_gate += GATE_SEGS
        if empty:
            return

        n_boost = rng.randint(1, 2)
        n_block = rng.randint(0, min(4, 1 + level // 2))
        n_drone = rng.randint(0, min(3, 1 + level // 3))
        slots = rng.sample(range(3, n - 2), n_boost + n_block + n_drone)
        for i, j in enumerate(slots):
            z = (start + j) * SEG
            if i < n_boost:
                lim = floor_limit(BOOST_HW)
                if abs(c) > 0.05:
                    # The outside of the bend, where the sled gets thrown.
                    lo, hi = (0.5 * lim, lim) if is_open else (0.7, 1.2)
                    a = -math.copysign(rng.uniform(lo, hi), c)
                elif is_open:
                    a = rng.uniform(-lim, lim)
                else:
                    a = rng.uniform(-1.0, 1.0)
                self.objects.append({"kind": "boost", "z": z, "a": snap(a, BOOST_HW)})
            elif i < n_boost + n_block:
                if is_open:
                    lim = floor_limit(BLOCK_HW)
                    a = rng.uniform(-lim, lim)
                elif rng.random() < 0.7:
                    a = rng.uniform(-1.2, 1.2)
                else:
                    a = rng.uniform(-math.pi, math.pi)
                self.objects.append({"kind": "block", "z": z, "a": snap(a, BLOCK_HW)})
            else:
                self.objects.append({
                    "kind": "drone", "z": z, "a0": rng.uniform(-0.9, 0.9),
                    "a": 0.0, "amp": rng.uniform(0.2, 0.7),
                    "w": rng.uniform(1.0, 2.5), "ph": rng.uniform(0, 6.28),
                })


# ---------------------------------------------------------------------- game
class Game:
    def __init__(self, seed=None):
        pygame.init()
        pygame.display.set_caption("Neon Conduit")
        self.screen = pygame.display.set_mode((W, H))
        self.clock = pygame.time.Clock()
        self.audio = Audio()
        self.font = pygame.font.Font(None, 30)
        self.big = pygame.font.Font(None, 84)
        self.mid = pygame.font.Font(None, 44)
        self.seed = seed
        star_rng = random.Random(7)
        self.stars = [(star_rng.uniform(-900, 900), star_rng.uniform(-900, 900),
                       star_rng.randint(90, 230)) for _ in range(220)]
        self.best = 0
        self.state = "title"
        self.reset()

    def reset(self):
        self.rng = random.Random(self.seed)
        self.track = Track(self.rng)
        self.cam_z = 0.0
        self.theta = 0.0        # sled angle on the wall, 0 = floor
        self.omega = 0.0
        self.roll = 0.0         # camera position angle, follows theta
        self.speed = 0.0
        self.boost = 0.0
        self.time_left = START_TIME
        self.level = 0
        self.score = 0
        self.bullets = []
        self.effects = []
        self.cooldown = 0.0
        self.shake = 0.0
        self.flash = 0.0
        self.msg = ("", 0.0)
        self.heading = 0.0
        self.steer = 0.0
        self.t = 0.0
        self.paused = False
        self.sparks = []
        self.scrape_cd = 0.0

    # -------------------------------------------------------------- update
    @property
    def max_speed(self):
        return min(150.0, BASE_SPEED + 4.0 * self.level)

    def update(self, dt, keys, auto=False):
        self.t += dt
        tr = self.track
        steer = (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a])
        brake = keys[pygame.K_DOWN] or keys[pygame.K_s]
        fire = keys[pygame.K_SPACE]
        if auto:
            steer = max(-1, min(1, -wrap(self.theta) * 2 - self.omega))
            fire = True
        self.steer = steer

        # --- speed
        self.boost = max(0.0, self.boost - dt)
        target = self.max_speed * (1.45 if self.boost > 0 else 1.0)
        if brake:
            target *= 0.35
        rate = 70.0 if self.speed < target else 55.0
        if self.speed < target:
            self.speed = min(target, self.speed + rate * dt)
        else:
            self.speed = max(target, self.speed - rate * dt)

        prev_pz = self.cam_z + PLAYER_D
        self.cam_z += self.speed * dt
        pz = self.cam_z + PLAYER_D
        seg = int(pz // SEG)
        tr.ensure(seg + DRAW + 80, self.level)

        # --- wall physics: steering, gravity, and the bend throwing you out
        vr = self.speed / BASE_SPEED
        # Gravity only pulls you back once you are up on the curved wall.
        w = abs(wrap(self.theta))
        slope = max(0.0, min(1.0, (w - 0.8 * FLOOR_A) / 0.35))
        acc = (16.0 * steer - 14.0 * slope * math.sin(self.theta)
               - 24.0 * tr.curv[seg] * vr * vr - 3.5 * self.omega)
        self.omega += acc * dt
        self.theta += self.omega * dt
        if tr.open[seg]:
            w = wrap(self.theta)
            if abs(w) > OPEN_LIMIT:
                lim = math.copysign(OPEN_LIMIT, w)
                # Slide down quickly if we arrived on a tube wall, then stop dead at the kerb.
                w += (lim - w) * min(1.0, 10.0 * dt)
                touching = abs(w - lim) < 0.1
                self.theta = lim if touching else w
                if self.omega * w > 0:
                    if touching:
                        self.scrape(dt, pz, math.copysign(1.0, w), abs(self.omega))
                    self.omega = 0.0
        self.roll += wrap(self.theta - self.roll) * min(1.0, 9.0 * dt)
        self.heading += tr.curv[seg] * self.speed * dt / SEG

        # --- shooting
        self.cooldown -= dt
        if fire and self.cooldown <= 0:
            self.cooldown = 0.16
            self.bullets.append({"z": pz + 3, "pz": pz + 3, "a": self.theta, "life": 0.9})
            self.audio.play("shot")
        for b in self.bullets:
            b["pz"] = b["z"]
            b["z"] += (self.speed + 260.0) * dt
            b["life"] -= dt
        self.bullets = [b for b in self.bullets if b["life"] > 0]

        # --- objects
        keep = []
        for o in tr.objects:
            z, kind = o["z"], o["kind"]
            if z < self.cam_z - 20:
                continue
            alive = True
            if kind == "drone":
                if z - pz < 320:
                    o["z"] = z = z + 0.5 * self.max_speed * dt
                o["a"] = o["a0"] + o["amp"] * math.sin(self.t * o["w"] + o["ph"])
                if tr.open[int(z // SEG)]:
                    o["a"] = max(-OPEN_LIMIT, min(OPEN_LIMIT, o["a"]))
                for b in self.bullets:
                    if b["pz"] - 2 <= z <= b["z"] + 2 and lat_dist(b["a"], o["a"]) < 3.0:
                        b["life"] = 0
                        alive = False
                        self.score += 500
                        self.effects.append({"z": z, "a": o["a"], "age": 0.0})
                        self.audio.play("boom")
                        break
                if alive and abs(z - pz) < 2.5 and lat_dist(o["a"], self.theta) < 3.2:
                    alive = False
                    self.crash(0.5)
                    self.effects.append({"z": z, "a": o["a"], "age": 0.0})
            elif kind == "block":
                if prev_pz < z <= pz and lat_dist(o["a"], self.theta) < BLOCK_HW + 1.2:
                    self.crash(0.3)
            elif kind == "boost":
                if z <= pz <= z + 10 and lat_dist(o["a"], self.theta) < BOOST_HW + 1.0:
                    if self.boost < 1.0:
                        self.audio.play("boost")
                        self.score += 100
                    self.boost = 1.6
            elif kind == "gate":
                if prev_pz < z <= pz:
                    alive = False
                    self.level += 1
                    bonus = max(11.0, 16.0 - 0.6 * self.level)
                    self.time_left += bonus
                    self.score += 1000
                    self.msg = ("GATE %d   +%d s" % (self.level, bonus), 2.0)
                    self.audio.play("gate")
            if alive:
                keep.append(o)
        tr.objects = keep

        for e in self.effects:
            e["age"] += dt
        self.effects = [e for e in self.effects if e["age"] < 0.45]
        self.scrape_cd -= dt
        for p in self.sparks:
            p["age"] += dt
            p["z"] += p["vz"] * dt
            p["x"] += p["vx"] * dt
            p["vh"] -= 30.0 * dt
            p["h"] = max(0.0, p["h"] + p["vh"] * dt)
        self.sparks = [p for p in self.sparks if p["age"] < p["life"]]

        self.score += int(self.speed * dt)
        self.shake = max(0.0, self.shake - dt)
        self.flash = max(0.0, self.flash - dt)
        self.msg = (self.msg[0], self.msg[1] - dt)
        self.time_left -= dt
        if self.time_left <= 0:
            self.time_left = 0.0
            self.best = max(self.best, self.score)
            self.state = "over"

    def scrape(self, dt, pz, side, impact):
        """Grinding along a kerb (side = -1 left, +1 right): bleeds speed and throws sparks."""
        floor = SCRAPE_FLOOR * self.max_speed
        if self.speed > floor:
            self.speed = max(floor, self.speed - SCRAPE_DRAG * dt)
        self.shake = max(self.shake, min(0.25, 0.07 + 0.15 * impact))
        if self.scrape_cd <= 0:
            self.scrape_cd = 0.11
            self.audio.play("scrape")
        vr = self.speed / BASE_SPEED
        for _ in range(3 if impact > 0.5 else 2):
            self.sparks.append({
                "z": pz + random.uniform(-1.5, 3.5), "x": side * FLOOR_HW,
                "h": random.uniform(0.2, 1.0), "vz": self.speed * random.uniform(0.35, 0.85),
                "vx": -side * random.uniform(1.0, 9.0) * vr, "vh": random.uniform(2.0, 11.0),
                "age": 0.0, "life": random.uniform(0.15, 0.4),
            })

    def crash(self, keep_frac):
        self.speed *= keep_frac
        self.boost = 0.0
        self.shake = 0.4
        self.flash = 0.25
        self.audio.play("hit")

    # ---------------------------------------------------------------- draw
    def draw(self):
        scr = self.screen
        tr = self.track
        scr.fill(FOG)

        # Camera sits above the sled's spot on the surface, rolled to match it:
        # level on the floor, banked on the walls.
        tilt = wrap(self.roll) * bank(self.roll)
        cr, sr = math.cos(tilt), math.sin(tilt)
        camx, camy = wall_xy(self.roll, 0.0, CAM_H, rigid=True)
        ox_s = oy_s = 0
        if self.shake > 0:
            ox_s = random.uniform(-1, 1) * 22 * self.shake
            oy_s = random.uniform(-1, 1) * 22 * self.shake
        pcx, pcy = CX + ox_s, CY + oy_s
        focal = FOCAL * (0.88 if self.boost > 0 else 1.0)

        # stars (seen in open sections and at the far end of the tube)
        hs = self.heading * 140.0
        for x, y, b in self.stars:
            x = (x - hs + 900) % 1800 - 900
            sx = pcx + x * cr - y * sr
            sy = pcy + x * sr + y * cr
            if 0 <= sx < W and 0 <= sy < H:
                scr.set_at((int(sx), int(sy)), (b, b, b))

        base = int(self.cam_z // SEG)
        frac = self.cam_z / SEG - base
        tr.ensure(base + DRAW + 2, self.level)

        # tube centre line relative to the camera, tangent-aligned
        rcx, rcy = [0.0] * (DRAW + 1), [0.0] * (DRAW + 1)
        x = y = dx = dy = 0.0
        sx0, sy0 = frac * tr.curv[base], frac * tr.pitch[base]
        for i in range(DRAW + 1):
            rcx[i] = x - sx0 * (i - frac)
            rcy[i] = y - sy0 * (i - frac)
            x += dx
            y += dy
            if i > 0:
                dx += tr.curv[base + i - 1]
                dy += tr.pitch[base + i - 1]

        def centre(z):
            f = z / SEG - base
            i = max(0, min(DRAW - 1, int(f)))
            t = f - i
            return rcx[i] + (rcx[i + 1] - rcx[i]) * t, rcy[i] + (rcy[i + 1] - rcy[i]) * t

        def proj(z, a, lat=0.0, h=0.0, rigid=False):
            """Screen point at depth z; see wall_xy for a / lat / h / rigid."""
            d = z - self.cam_z
            if d < NEAR:
                return None
            ccx, ccy = centre(z)
            wx, wy = wall_xy(a, lat, h, rigid)
            px = ccx + wx - camx
            py = ccy + wy - camy
            k = focal / d
            return pcx + k * (px * cr - py * sr), pcy + k * (px * sr + py * cr), k

        # project ring vertices
        rings = []
        for i in range(DRAW + 1):
            d = max(NEAR, (i - frac) * SEG)
            k = focal / d
            ox, oy = rcx[i] - camx, rcy[i] - camy
            pts = []
            for s in range(SIDES + 1):
                px = ox + SIDE_R[s] * SIDE_SIN[s]
                py = oy + SIDE_R[s] * SIDE_COS[s]
                pts.append((pcx + k * (px * cr - py * sr), pcy + k * (px * sr + py * cr)))
            for _, _, kx in KERBS:                  # kerb tops, used in open sections
                px, py = ox + kx, oy + FLOOR_Y - WALL_H
                pts.append((pcx + k * (px * cr - py * sr), pcy + k * (px * sr + py * cr)))
            rings.append(pts)

        # bucket objects per segment so nearer walls correctly hide them
        buckets = {}
        far_z = (base + DRAW) * SEG
        for o in tr.objects:
            if o["z"] < far_z:
                buckets.setdefault(int(o["z"] // SEG), []).append(o)
        for b in self.bullets:
            buckets.setdefault(int(b["z"] // SEG), []).append(b)
        for e in self.effects:
            buckets.setdefault(int(e["z"] // SEG), []).append(e)

        pal = PALETTES[self.level % len(PALETTES)]
        polygon = pygame.draw.polygon
        for i in range(DRAW - 1, -1, -1):
            if (i + 1 - frac) * SEG > NEAR:
                si = base + i
                fog = min(1.0, (max(0.0, i - frac) / DRAW) ** 1.3 * 1.15)
                is_open = tr.open[si]
                r0, r1 = rings[i], rings[i + 1]
                band = si // 2
                gate_glow = si % GATE_SEGS in (0, GATE_SEGS - 1)
                for s in (FLOOR_SIDES if is_open else range(SIDES)):
                    if abs(SIDE_MID[s]) < FLOOR_A:
                        c = FLOOR_COLS[band & 1]
                    else:
                        c = pal[(band + s) & 1]
                    if gate_glow:
                        c = (240, 240, 255)
                    lt = SIDE_LIGHT[s] * (1 - fog)
                    col = (int(c[0] * lt + FOG[0] * fog),
                           int(c[1] * lt + FOG[1] * fog),
                           int(c[2] * lt + FOG[2] * fog))
                    polygon(scr, col, (r0[s], r0[s + 1], r1[s + 1], r1[s]))
                if is_open:
                    # Upright kerbs at the floor edges: too steep to ride up.
                    c = (240, 240, 255) if gate_glow else KERB_COLS[band & 1]
                    lt = 0.85 * (1 - fog)
                    col = (int(c[0] * lt + FOG[0] * fog),
                           int(c[1] * lt + FOG[1] * fog),
                           int(c[2] * lt + FOG[2] * fog))
                    for v, t, _ in KERBS:
                        polygon(scr, col, (r0[v], r0[t], r1[t], r1[v]))
            for o in buckets.get(base + i, ()):
                self.draw_object(o, proj)

        self.draw_sled(proj)
        for p in self.sparks:
            q0 = proj(p["z"], 0.0, p["x"], p["h"])
            q1 = proj(p["z"] + 1.6, 0.0, p["x"] + 0.02 * p["vx"], p["h"] + 0.02 * p["vh"])
            if q0 and q1:
                t = p["age"] / p["life"]
                pygame.draw.line(scr, mix((255, 250, 200), (255, 110, 20), t), q0[:2], q1[:2],
                                 max(1, int(q0[2] * 0.14 * (1 - 0.5 * t))))
        if self.flash > 0:
            veil = pygame.Surface((W, H))
            veil.fill((255, 60, 40))
            veil.set_alpha(int(400 * self.flash))
            scr.blit(veil, (0, 0))
        self.draw_hud()

    def draw_object(self, o, proj):
        scr = self.screen
        kind = o.get("kind")
        z = o["z"]
        if kind == "boost":
            a, hw = o["a"], BOOST_HW
            q = [proj(z, a, -hw, 0.15), proj(z, a, hw, 0.15),
                 proj(z + 10, a, hw, 0.15), proj(z + 10, a, -hw, 0.15)]
            if all(q):
                pulse = 0.6 + 0.4 * math.sin(self.t * 12)
                pygame.draw.polygon(scr, (int(60 * pulse), int(255 * pulse), int(120 * pulse)),
                                    [p[:2] for p in q])
                tip, l, r_ = proj(z + 8, a, 0, 0.2), proj(z + 3, a, -1.3, 0.2), proj(z + 3, a, 1.3, 0.2)
                if tip and l and r_:
                    pygame.draw.polygon(scr, (10, 60, 30), (tip[:2], l[:2], r_[:2]))
        elif kind == "block":
            a, hw = o["a"], BLOCK_HW
            q = [proj(z, a, -hw, 0.0), proj(z, a, hw, 0.0),
                 proj(z, a, hw * 0.9, 3.0), proj(z, a, -hw * 0.9, 3.0)]
            if all(q):
                pts = [p[:2] for p in q]
                pygame.draw.polygon(scr, (215, 50, 40), pts)
                pygame.draw.polygon(scr, (255, 210, 60), pts, max(1, int(q[0][2] * 0.12)))
        elif kind == "drone":
            p = proj(z, o["a"], 0.0, 1.5, True)
            if p:
                s = max(2, p[2] * 1.0)
                x, y = p[0], p[1]
                pygame.draw.polygon(scr, (255, 120, 30),
                                    ((x - s, y), (x, y - s * 0.6), (x + s, y), (x, y + s * 0.6)))
                pygame.draw.circle(scr, (255, 240, 200), (x, y), max(1, s * 0.3))
        elif kind == "gate":
            pts = [proj(z, a, 0.0, 0.3) for a in SIDE_A]
            if all(pts):
                pygame.draw.lines(scr, (255, 255, 160), False, [p[:2] for p in pts],
                                  max(2, int(pts[0][2] * 0.5)))
        elif "age" in o:                                      # explosion
            p = proj(z, o["a"], 0.0, 1.5, True)
            if p:
                t = o["age"] / 0.45
                pygame.draw.circle(scr, mix((255, 255, 200), (255, 60, 0), t), p[:2],
                                   max(2, p[2] * (0.6 + 3.5 * t)), max(1, int(p[2] * 0.5 * (1 - t)) + 1))
        else:                                                 # bullet
            p0, p1 = proj(z, o["a"], 0.0, 1.0, True), proj(z + 5, o["a"], 0.0, 1.0, True)
            if p0 and p1:
                pygame.draw.line(scr, (255, 255, 120), p0[:2], p1[:2], max(2, int(p0[2] * 0.12)))

    def draw_sled(self, proj):
        scr = self.screen
        pz, a = self.cam_z + PLAYER_D, self.theta
        rl = proj(pz - 1.5, a, -SLED_HW, 0.25, True)
        rr = proj(pz - 1.5, a, SLED_HW, 0.25, True)
        nose = proj(pz + 4.5, a, 0.0, 0.45, True)
        fin = proj(pz - 1.5, a, -self.steer * 0.6, 1.6, True)
        if not (rl and rr and nose and fin):
            return
        rl, rr, nose, fin = rl[:2], rr[:2], nose[:2], fin[:2]
        hot = self.boost > 0
        flame = (120, 255, 160) if hot else (90, 180, 255)
        tail = proj(pz - (5.0 if hot else 3.0) - random.random(), a, 0.0, 0.7, True)
        if tail:
            pygame.draw.polygon(scr, flame, (rl, rr, tail[:2]))
        pygame.draw.polygon(scr, (200, 205, 220), (rl, nose, fin))
        pygame.draw.polygon(scr, (120, 125, 150), (rr, nose, fin))
        pygame.draw.polygon(scr, (40, 44, 70), (rl, rr, fin))
        pygame.draw.lines(scr, (255, 80, 160), True, (rl, nose, rr), 2)

    def text(self, font, s, pos, col=(235, 240, 255), center=False):
        img = font.render(s, True, col)
        shadow = font.render(s, True, (0, 0, 0))
        r = img.get_rect()
        if center:
            r.center = pos
        else:
            r.topleft = pos
        self.screen.blit(shadow, r.move(2, 2))
        self.screen.blit(img, r)

    def draw_hud(self):
        scr = self.screen
        tcol = (255, 70, 60) if self.time_left < 6 and int(self.t * 4) % 2 else (235, 240, 255)
        self.text(self.mid, "%04.1f" % self.time_left, (W // 2, 30), tcol, center=True)
        self.text(self.font, "SCORE %07d" % self.score, (20, 16))
        self.text(self.font, "GATE %d" % self.level, (20, 44))
        spd = "%3d km/h" % int(self.speed * 4)
        self.text(self.font, spd, (W - 150, 16), (120, 255, 160) if self.boost > 0 else (235, 240, 255))
        # progress to the next gate
        pz = self.cam_z + PLAYER_D
        prog = (pz / SEG % GATE_SEGS) / GATE_SEGS
        pygame.draw.rect(scr, (40, 44, 70), (W // 2 - 150, 56, 300, 8))
        pygame.draw.rect(scr, (255, 255, 160), (W // 2 - 150, 56, int(300 * prog), 8))
        if self.msg[1] > 0:
            self.text(self.mid, self.msg[0], (W // 2, 120), (255, 255, 160), center=True)

    def draw_overlay(self):
        veil = pygame.Surface((W, H))
        veil.set_alpha(150)
        self.screen.blit(veil, (0, 0))
        mid = W // 2
        if self.state == "title":
            self.text(self.big, "NEON CONDUIT", (mid, 190), (255, 80, 160), center=True)
            lines = ["Reach each gate before the clock runs out.",
                     "Ride the outside of bends for the green boost pads.",
                     "",
                     "Left / Right  steer      Down  brake      Space  fire",
                     "P  pause      Esc  quit",
                     "",
                     "Press ENTER to start"]
        elif self.state == "over":
            self.text(self.big, "TIME UP", (mid, 190), (255, 70, 60), center=True)
            lines = ["Score %d     Gates %d" % (self.score, self.level),
                     "Best %d" % self.best, "", "Press ENTER to race again"]
        else:
            self.text(self.big, "PAUSED", (mid, 250), center=True)
            lines = []
        for i, s in enumerate(lines):
            self.text(self.font, s, (mid, 280 + i * 32), center=True)

    # ---------------------------------------------------------------- loop
    def run(self, frames=None, screenshot=None):
        auto = frames is not None
        if auto:
            self.state = "play"
        count = 0
        while True:
            dt = 1 / 60 if auto else min(0.05, self.clock.tick(60) / 1000.0)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    return
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        return
                    if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.state != "play":
                        self.reset()
                        self.state = "play"
                    elif ev.key == pygame.K_p and self.state == "play":
                        self.paused = not self.paused
            if self.state == "play" and not self.paused:
                self.update(dt, pygame.key.get_pressed(), auto)
            self.draw()
            if self.state != "play" or self.paused:
                self.draw_overlay()
            pygame.display.flip()
            count += 1
            if frames is not None and count >= frames:
                if screenshot:
                    pygame.image.save(self.screen, screenshot)
                return


def main():
    ap = argparse.ArgumentParser(description="Neon Conduit - tunnel racer")
    ap.add_argument("--seed", type=int, help="fixed track seed")
    ap.add_argument("--frames", type=int, help="self-play this many frames, then exit (for testing)")
    ap.add_argument("--screenshot", help="with --frames, save the last frame to this file")
    args = ap.parse_args()
    game = Game(args.seed)
    try:
        game.run(args.frames, args.screenshot)
    finally:
        pygame.quit()


if __name__ == "__main__":
    sys.exit(main())
