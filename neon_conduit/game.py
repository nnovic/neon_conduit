"""Game state and rules: the sled's physics, the objects on the track, score and clock.

Nothing here draws or reads the keyboard: each update takes a Controls value,
and sounds go to whatever audio object the game was given.
"""
import math
import random
from collections import namedtuple

from .audio import Silent
from .config import (BASE_SPEED, BOOST_HW, BOOST_MULT, CRASH_KEEP, DOOR_OPEN_AT, DRAW, FLAT_MAX,
                     FLOOR_A, LINE_FALLOFF, LINE_SLOW, LINE_TOL, PLAYER_D, SCRAPE_DRAG,
                     SCRAPE_FLOOR, SEG, SLED_HW, SPEED_CAP, STAR_SCORE, START_TIME)
from .geometry import bank, floor_limit, lat_dist, wrap
from .track import Track

Controls = namedtuple("Controls", "steer brake fire")   # steer: -1 .. 1, brake / fire: bool
IDLE = Controls(0, False, False)


class Game:
    def __init__(self, seed=None, audio=None):
        self.seed = seed
        self.audio = audio or Silent()
        self.best = 0
        self.state = "title"        # "title", "play" or "over"
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
        self.stars_taken = set()    # segments whose hint star the sled has ridden through
        self.cooldown = 0.0
        self.shake = 0.0
        self.flash = 0.0
        self.msg = ("", 0.0)
        self.heading = 0.0
        self.steer = 0.0
        self.t = 0.0
        self.sparks = []
        self.flat = 0.0         # 0 in the tube, 1 on the flat floor of an open section
        self.off_line = 0.0     # 0 on the fast line (or on a straight), 1 far off it in a bend
        self.scrape_cd = 0.0

    @property
    def max_speed(self):
        return min(SPEED_CAP, BASE_SPEED + 4.0 * self.level)

    @property
    def sled_z(self):
        return self.cam_z + PLAYER_D

    def autopilot(self):
        """Controls that steer for the fast line and keep firing (self-play and demos)."""
        aim = self.track.line(int(self.sled_z // SEG))
        return Controls(max(-1, min(1, wrap(aim - self.theta) * 2 - self.omega)), False, True)

    # -------------------------------------------------------------- update
    def update(self, dt, controls):
        self.t += dt
        self.steer = controls.steer

        self._move(dt, controls.brake)
        pz = self.sled_z
        seg = int(pz // SEG)
        self._steer(dt, controls.steer, pz, seg)
        self._shoot(dt, controls.fire, pz)
        self._objects(dt, pz)
        self._hint_stars(pz)
        self._effects(dt)

        self.score += int(self.speed * dt)
        self.shake = max(0.0, self.shake - dt)
        self.flash = max(0.0, self.flash - dt)
        self.msg = (self.msg[0], self.msg[1] - dt)
        self.time_left -= dt
        if self.time_left <= 0:
            self.time_left = 0.0
            self.best = max(self.best, self.score)
            self.state = "over"

    def _move(self, dt, brake):
        """Speed up or slow down towards the target speed, then move along the track."""
        tr = self.track
        self.boost = max(0.0, self.boost - dt)
        target = self.max_speed * (BOOST_MULT if self.boost > 0 else 1.0)
        target *= 1.0 - LINE_SLOW * self.off_line
        if brake:
            target *= 0.35
        rate = 70.0 if self.speed < target else 55.0
        if self.speed < target:
            self.speed = min(target, self.speed + rate * dt)
        else:
            self.speed = max(target, self.speed - rate * dt)

        self.prev_z = self.sled_z
        self.cam_z += self.speed * dt
        pz = self.sled_z
        tr.ensure(int(pz // SEG) + DRAW + 80, self.level)
        # Doors back into the tube start sliding open as the sled draws near.
        for i in range(int((self.prev_z + DOOR_OPEN_AT) // SEG) + 1, int((pz + DOOR_OPEN_AT) // SEG) + 1):
            if tr.is_door(i):
                self.audio.play("door")

    def _steer(self, dt, steer, pz, seg):
        """Steering and gravity round the tube wall, kerbs in the open, and the fast line."""
        tr = self.track
        # Gravity only pulls you back once you are up on the curved wall.
        is_open = tr.open[seg]
        hw = tr.hw_at(pz)
        open_limit = floor_limit(SLED_HW, hw)
        w = abs(wrap(self.theta))
        # Switch to the flat-floor frame once in the open, but only after a sled
        # that arrived up on a tube wall has slid down to the floor.
        if not is_open:
            self.flat = max(0.0, self.flat - 8.0 * dt)
        elif w <= max(FLOOR_A, open_limit) + 0.02:
            self.flat = min(1.0, self.flat + 8.0 * dt)
        slope = bank(w) * (1.0 - self.flat)
        acc = (16.0 * steer - 14.0 * slope * math.sin(self.theta) - 3.5 * self.omega)
        self.omega += acc * dt
        step = self.omega * dt
        if w > FLOOR_A:
            # Past the tube's corner a flat floor stretches the angle scale; keep
            # the sideways speed what it is at the corner.
            step *= 1.0 + self.flat * (2.0 * math.cos(min(w, FLAT_MAX)) ** 2 - 1.0)
        self.theta += step
        if is_open:
            w = wrap(self.theta)
            if abs(w) > open_limit:
                lim = math.copysign(open_limit, w)
                # Slide down quickly if we arrived on a tube wall, then stop dead at the kerb.
                w += (lim - w) * min(1.0, 10.0 * dt)
                touching = abs(w - lim) < 0.1
                self.theta = lim if touching else w
                if self.omega * w > 0:
                    if touching:
                        self.scrape(dt, pz, math.copysign(hw, w), abs(self.omega))
                    self.omega = 0.0
        self.roll += wrap(self.theta - self.roll) * min(1.0, 9.0 * dt)
        # Bends don't push the sled around; being off the fast line costs speed instead.
        off = lat_dist(self.theta, tr.line(seg), is_open) - LINE_TOL
        self.off_line = tr.bend(seg) * max(0.0, min(1.0, off / LINE_FALLOFF))
        self.heading += tr.curv[seg] * self.speed * dt / SEG

    def _shoot(self, dt, fire, pz):
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

    def _objects(self, dt, pz):
        """Drones, boost pads and gates: movement, hits and pick-ups."""
        tr = self.track
        keep = []
        for o in tr.objects:
            z, kind = o["z"], o["kind"]
            if z < self.cam_z - 20:
                continue
            alive = True
            flat = kind != "gate" and tr.open[int(z // SEG)]
            if kind == "drone":
                if z - pz < 320:
                    o["z"] = z = z + 0.5 * self.max_speed * dt
                o["a"] = o["a0"] + o["amp"] * math.sin(self.t * o["w"] + o["ph"])
                if flat:
                    lim = floor_limit(1.0, tr.hw_at(z))
                    o["a"] = max(-lim, min(lim, o["a"]))
                for b in self.bullets:
                    if b["pz"] - 2 <= z <= b["z"] + 2 and lat_dist(b["a"], o["a"], flat) < 3.0:
                        b["life"] = 0
                        alive = False
                        self.score += 500
                        self.effects.append({"z": z, "a": o["a"], "age": 0.0})
                        self.audio.play("boom")
                        break
                if alive and abs(z - pz) < 2.5 and lat_dist(o["a"], self.theta, flat) < 3.2:
                    alive = False
                    self.crash(CRASH_KEEP)
                    self.effects.append({"z": z, "a": o["a"], "age": 0.0})
            elif kind == "boost":
                if z <= pz <= z + 10 and lat_dist(o["a"], self.theta, flat) < BOOST_HW + 1.0:
                    if self.boost < 1.0:
                        self.audio.play("boost")
                        self.score += 100
                    self.boost = 1.6
            elif kind == "gate":
                if self.prev_z < z <= pz:
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

    def _hint_stars(self, pz):
        """Ride through a hint star (on the fast line) to pick it up."""
        tr = self.track
        for i in range(int(self.prev_z // SEG) + 1, int(pz // SEG) + 1):
            if (tr.has_star(i) and i not in self.stars_taken
                    and lat_dist(self.theta, tr.line(i), tr.open[i]) < LINE_TOL):
                self.stars_taken.add(i)
                self.score += STAR_SCORE
                self.effects.append({"kind": "sparkle", "z": i * SEG, "a": tr.line(i), "age": 0.0})
                self.audio.play("star")

    def _effects(self, dt):
        """Age explosions and sparks."""
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

    # ------------------------------------------------------------- events
    def scrape(self, dt, pz, kerb_x, impact):
        """Grinding along the kerb at sideways position kerb_x: bleeds speed and throws sparks."""
        side = math.copysign(1.0, kerb_x)
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
                "z": pz + random.uniform(-1.5, 3.5), "x": kerb_x,
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
