"""Game state and rules: the sled's physics, the objects on the track, score and clock.

Nothing here draws or reads the keyboard: each update takes a Controls value,
and sounds go to whatever audio object the game was given.
"""
import math
import random
from collections import namedtuple

from .audio import Silent
from .config import (BASE_SPEED, BOOST_HW, BOOST_MULT, AIM_RATE, AIM_SLOPE, BOOST_TIME, CRASH_KEEP, DIVE_SETTLE, INVINCIBLE_TIME,
                     DOOR_OPEN_AT, DRAW, FLAT_MAX, FLOOR_A, BULLET_LIFE, BULLET_SPEED, GUN_SPREAD, LINE_FALLOFF, LOCK_ANGLE, LOCK_RANGE, LINE_SLOW, LINE_TOL, PLAYER_D, SCRAPE_DRAG,
                     SCRAPE_FLOOR, SEG, SLED_HW, SPEED_CAP, STAR_SCORE, START_TIME,
                     DRONE_SPEED, RING_AHEAD, RING_DRONES)
from .geometry import bank, floor_limit, inside, lat_dist, wall_xy, wrap
from .track import Track
from .tutorial import COURSE, SKIP_FADE, SKIP_TO, TIPS, Tutorial

# steer: -1 .. 1, fire: bool, aim: -1 (lowered) .. 0 (along the slope) .. 1 (raised)
Controls = namedtuple("Controls", "steer fire aim", defaults=(0,))
IDLE = Controls(0, False)


class Game:
    def __init__(self, seed=None, audio=None):
        self.seed = seed
        self.audio = audio or Silent()
        self.best = 0
        self.state = "title"        # "title", "brief" (on the start line), "play" or "over"
        self.tutorial = None
        self.reset()

    def reset(self):
        # The tutorial is for the first race only: once that is under way, later ones get none.
        self.tutorial = Tutorial(() if self.tutorial and self.tutorial.started else TIPS)
        self.rng = random.Random(self.seed)
        # With a tutorial, the track starts on its fixed course; the random track comes after.
        self.track = Track(self.rng, COURSE if self.tutorial.tips else ())
        self.cam_z = 0.0
        self.theta = 0.0        # sled angle on the wall, 0 = floor
        self.omega = 0.0
        self.roll = 0.0         # camera position angle, follows theta
        self.speed = 0.0
        self.boost = 0.0
        self.invincible = 0.0   # seconds left during which drones can't hurt the sled
        self.time_left = START_TIME
        self.level = 0
        self.score = 0
        self.bullets = []
        self.effects = []
        self.stars_taken = set()    # segments whose hint star has been scored (it stays on the track)
        self.cooldown = 0.0
        self.aim = 0.0          # gun elevation off the track slope, -1 (low) .. 1 (high)
        self.lock = None        # the drone the guns are locked on to, if any
        self.shake = 0.0
        self.flash = 0.0
        self.msg = ("", 0.0)
        self.heading = 0.0
        self.dive = 0.0         # how far the track has tipped downhill lately (< 0: uphill)
        self.steer = 0.0
        self.t = 0.0
        self.sparks = []
        self.flat = 0.0         # 0 in the tube, 1 on the flat floor of an open section
        self.off_line = 0.0     # 0 on the fast line (or on a straight), 1 far off it in a bend
        self.scrape_cd = 0.0
        self.gate_from = 0.0    # depth from which the run to the next gate counts: the last
                                # gate passed, or where the clock started
        self.skipping = None    # seconds into skipping the tutorial, or None

    @property
    def veil(self):
        """How dark the screen is while skipping the tutorial: 0 .. 1 (black) .. 0."""
        if self.skipping is None:
            return 0.0
        return max(0.0, 1.0 - abs(self.skipping - SKIP_FADE) / SKIP_FADE)

    @property
    def can_skip(self):
        """True while the tutorial can be skipped (and is not being skipped already)."""
        return self.tutorial.can_skip and self.skipping is None

    def skip_tutorial(self):
        """Skip the tutorial, if it still can be: the screen fades to black, the racer
        jumps to just short of its door, and the screen fades back in."""
        if self.can_skip:
            self.skipping = 0.0

    def _skip_jump(self):
        """The jump under the black: on to the tutorial's last straight, centred, at speed."""
        self.tutorial.skip()
        self.cam_z = SKIP_TO * SEG - PLAYER_D
        self.prev_z = self.gate_from = self.sled_z
        self.theta = self.omega = self.roll = self.dive = self.flat = self.off_line = 0.0
        self.speed = max(self.speed, self.max_speed)
        self.bullets, self.effects, self.sparks, self.lock = [], [], [], None

    @property
    def gate_progress(self):
        """How far the racer has come from the last gate (or the clock's start) to the
        next one, 0 .. 1."""
        tr, pz = self.track, self.sled_z
        nxt = min((o["z"] for o in tr.objects if o["kind"] == "gate" and o["z"] > pz),
                  default=tr.next_gate * SEG)               # the next gate, placed or not yet
        return max(0.0, min(1.0, (pz - self.gate_from) / max(1e-6, nxt - self.gate_from)))

    @property
    def max_speed(self):
        return min(SPEED_CAP, BASE_SPEED + 4.0 * self.level)

    @property
    def sled_z(self):
        return self.cam_z + PLAYER_D

    def autopilot(self):
        """Controls that steer for the fast line and keep firing (self-play and demos)."""
        aim = self.track.line(int(self.sled_z // SEG))
        return Controls(max(-1, min(1, wrap(aim - self.theta) * 2 - self.omega)), True)

    # -------------------------------------------------------------- update
    def update(self, dt, controls):
        self.t += dt
        if self.skipping is not None:
            jump = self.skipping < SKIP_FADE <= self.skipping + dt
            self.skipping += dt
            if jump:
                self._skip_jump()
            if self.skipping >= 2 * SKIP_FADE:
                self.skipping = None
        self.steer = controls.steer

        self._move(dt)
        pz = self.sled_z
        seg = int(pz // SEG)
        self._steer(dt, controls.steer, pz, seg)
        self.aim += max(-AIM_RATE * dt, min(AIM_RATE * dt, controls.aim - self.aim))
        self.lock = self._target(pz, dt)
        self._shoot(dt, controls.fire, pz)
        self._objects(dt, pz)
        self._hint_stars(pz)
        self._effects(dt)

        self.score += int(self.speed * dt)
        self.shake = max(0.0, self.shake - dt)
        self.flash = max(0.0, self.flash - dt)
        self.msg = (self.msg[0], self.msg[1] - dt)
        clock = self.tutorial.clock
        gone = self.tutorial.update(dt, seg)
        if gone and gone.then:
            self._tutorial_event(gone.then, pz)
        if self.tutorial.clock and not clock:   # the clock starts: so does the run to the next gate
            self.gate_from = pz
        if self.tutorial.clock:             # the tutorial holds the clock back for a while
            self.time_left -= dt
        if self.time_left <= 0:
            self.time_left = 0.0
            self.best = max(self.best, self.score)
            self.state = "over"

    def _move(self, dt):
        """Speed up or slow down towards the target speed, then move along the track."""
        tr = self.track
        self.boost = max(0.0, self.boost - dt)
        self.invincible = max(0.0, self.invincible - dt)
        target = self.max_speed * (BOOST_MULT if self.boost > 0 else 1.0)
        target *= 1.0 - LINE_SLOW * self.off_line
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
        self.dive += tr.pitch[seg] * self.speed * dt / SEG
        self.dive -= self.dive * min(1.0, dt / DIVE_SETTLE)

    def _shoot(self, dt, fire, pz):
        self.cooldown -= dt
        if fire and self.cooldown <= 0:
            self.cooldown = 0.16
            v = self.speed + BULLET_SPEED
            for side in (-GUN_SPREAD, GUN_SPREAD):              # twin guns, side by side
                x, y = wall_xy(self.theta, side, 1.0, True, self.flat)
                aimed = self.lock and self._intercept(self.lock, x, y, pz + 3, v, dt)
                if aimed:                                       # locked: straight at the drone
                    vx, vy = aimed
                else:                                           # free: along the slope, Up / Down aim
                    ux, uy = wall_xy(self.theta, side, 2.0, True, self.flat)   # one unit up
                    lift = self.aim * AIM_SLOPE * SEG                    # sideways drift per segment
                    vx, vy = (ux - x) * lift, (uy - y) * lift
                self.bullets.append({"z": pz + 3, "pz": pz + 3, "x": x, "y": y,
                                     "vx": vx, "vy": vy, "v": v, "life": BULLET_LIFE})
            self.audio.play("shot")
        for b in self.bullets:
            b["pz"] = b["z"]
            self._fly(b, b["v"] * dt)
            b["life"] -= dt
        self.bullets = [b for b in self.bullets if b["life"] > 0]

    # ------------------------------------------------------------ lock-on
    def _drone_later(self, o, wait, dt):
        """Where drone o will be after wait seconds: depth and cross-section point.

        Mirrors the drone's moves in _objects (forward at its share of top speed, swaying
        on its sine). Shots and drones both move in the frame a shot is fired, but the drone's
        sway reads the clock already advanced for that frame, hence the - dt.
        """
        z = o["z"] + o.get("v", DRONE_SPEED) * self.max_speed * wait
        a = o["a0"] + o["amp"] * math.sin((self.t + wait - dt) * o["w"] + o["ph"])
        flat = self.track.open[int(z // SEG)]
        if flat:
            lim = floor_limit(1.0, self.track.hw_at(z))
            a = max(-lim, min(lim, a))
        return z, wall_xy(a, 0.0, 1.5, True, 1.0 if flat else 0.0)

    def _drift(self, z0, z1):
        """How far a straight shot fired with no drift from z0 moves off its start in the
        cross-section frame by z1 (the track turning under it), as _fly would move it."""
        tr = self.track
        x = y = vx = vy = 0.0
        z = z0
        while z < z1:
            s = int(z // SEG)
            nxt = min(z1, (s + 1) * SEG)
            x += vx * (nxt - z) / SEG
            y += vy * (nxt - z) / SEG
            z = nxt
            if z >= (s + 1) * SEG:
                vx -= tr.curv[s]
                vy -= tr.pitch[s]
        return x, y

    def _intercept(self, o, x0, y0, z0, v, dt):
        """Drift (vx, vy) for a straight shot from (x0, y0) at depth z0, speed v, that meets
        drone o; None if that needs too wide an angle, hits a wall on the way or can't
        catch it in time.

        A shot's place at any depth is its start, plus its drift times the distance, plus
        the track's turning (the same whatever the drift): solving for the drift is exact.
        """
        closing = v - o.get("v", DRONE_SPEED) * self.max_speed
        if closing <= 0:
            return None
        wait = (o["z"] - z0) / closing
        if not 0 < wait < BULLET_LIFE - 0.05:
            return None
        z1, (tx, ty) = self._drone_later(o, wait, dt)
        segs = (z1 - z0) / SEG
        cx, cy = self._drift(z0, z1)
        vx, vy = (tx - x0 - cx) / segs, (ty - y0 - cy) / segs
        if math.hypot(vx, vy) / SEG > math.tan(LOCK_ANGLE):
            return None
        # A clear line of fire: the shot stays inside the tube all the way.
        b = {"z": z0, "x": x0, "y": y0, "vx": vx, "vy": vy, "life": 1.0}
        while b["z"] < z1 and b["life"] > 0:
            self._fly(b, min(SEG, z1 - b["z"]))
        return (vx, vy) if b["life"] > 0 else None

    def _target(self, pz, dt):
        """The drone to lock on to: the nearest one ahead in range that a straight shot from
        the middle of the sled can reach, roughly in front and in plain sight."""
        x, y = wall_xy(self.theta, 0.0, 1.0, True, self.flat)
        v = self.speed + BULLET_SPEED
        ahead = sorted((o for o in self.track.objects if o["kind"] == "drone"
                        and pz + 3 < o["z"] < pz + LOCK_RANGE), key=lambda o: o["z"])
        for o in ahead:
            if self._intercept(o, x, y, pz + 3, v, dt):
                return o
        return None

    def _fly(self, b, dz):
        """Move a bullet dz along the track in a straight line, so it does not follow the bends.

        Bullets live in the cross-section frame, which turns with the track: x, y is the offset
        from the tube centre and vx, vy its drift per segment. A shot leaves along the slope
        where it was fired (raised by the aim); at each ring the track turns by curv / pitch,
        so the straight shot drifts that much the other way. Hitting the wall ends it.
        """
        tr = self.track
        z, end = b["z"], b["z"] + dz
        while z < end:
            s = int(z // SEG)
            nxt = min(end, (s + 1) * SEG)
            f = (nxt - z) / SEG
            b["x"] += b["vx"] * f
            b["y"] += b["vy"] * f
            z = nxt
            if z >= (s + 1) * SEG:
                b["vx"] -= tr.curv[s]
                b["vy"] -= tr.pitch[s]
        b["z"] = end
        if not inside(b["x"], b["y"], tr.open[int(end // SEG)]):
            b["life"] = 0

    def _tutorial_event(self, name, pz):
        """What a tutorial tip sets off as it goes."""
        z = pz + RING_AHEAD
        ring = [2 * math.pi * k / RING_DRONES for k in range(RING_DRONES)]   # from the floor's middle
        if name == "drone_ring":
            # Drones evenly round the tube, too close together to slip between: the only
            # way through is to shoot one. They hang still, so the racer rushes at them.
            for a in ring:
                self.track.objects.append({"kind": "drone", "z": z, "v": 0.0, "a0": a, "a": 0.0,
                                           "amp": 0.0, "w": 0.0, "ph": 0.0})
        elif name == "boost_ring":
            # Boost pads evenly round the tube, too close together to miss. Spaced from the
            # floor's middle, none of them straddles a corner between floor and wall.
            for a in ring:
                self.track.objects.append({"kind": "boost", "z": z, "a": a})

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
                    o["z"] = z = z + o.get("v", DRONE_SPEED) * self.max_speed * dt
                o["a"] = o["a0"] + o["amp"] * math.sin(self.t * o["w"] + o["ph"])
                if flat:
                    lim = floor_limit(1.0, tr.hw_at(z))
                    o["a"] = max(-lim, min(lim, o["a"]))
                ox, oy = wall_xy(o["a"], 0.0, 1.5, True, 1.0 if flat else 0.0)
                for b in self.bullets:
                    if (b["life"] > 0 and b["pz"] - 2 <= z <= b["z"] + 2
                            and math.hypot(b["x"] - ox, b["y"] - oy) < 3.0):
                        b["life"] = 0
                        alive = False
                        self.score += 500
                        self.effects.append({"z": z, "a": o["a"], "age": 0.0})
                        self.audio.play("boom")
                        break
                if alive and abs(z - pz) < 2.5 and lat_dist(o["a"], self.theta, flat) < 3.2:
                    alive = False
                    if self.invincible > 0:             # rammed out of the way: scores like a shot
                        self.score += 500
                        self.shake = max(self.shake, 0.15)
                        self.audio.play("boom")
                    else:
                        self.crash(CRASH_KEEP)
                    self.effects.append({"z": z, "a": o["a"], "age": 0.0})
            elif kind == "boost":
                if z <= pz <= z + 10 and lat_dist(o["a"], self.theta, flat) < BOOST_HW + 1.0:
                    if self.boost < BOOST_TIME - 0.6:       # not while still on the same pad
                        self.audio.play("boost")
                        self.score += 100
                        # The exhaust bursts: an explosion ring that rides along on the nozzle.
                        self.effects.append({"z": pz - 1.5, "a": self.theta, "age": 0.0,
                                             "follow": -1.5, "drift": 4.0, "h": 0.55, "size": 1.5, "life": 0.22,
                                             "cols": ((230, 255, 240), (40, 255, 130))})
                    self.boost = BOOST_TIME
                    self.invincible = max(self.invincible, INVINCIBLE_TIME)
            elif kind == "gate":
                if self.prev_z < z <= pz:
                    alive = False
                    self.level += 1
                    self.gate_from = z
                    self.score += 1000
                    bonus = max(11.0, 16.0 - 0.6 * self.level)
                    self.time_left += bonus
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
        """Age explosions and sparks; bursts that follow the sled stay on it."""
        for e in self.effects:
            e["age"] += dt
            if "follow" in e:                       # ...sliding back off the sled by drift
                back = e.get("drift", 0.0) * e["age"] / e.get("life", 0.45)
                e["z"], e["a"] = self.sled_z + e["follow"] - back, self.theta
        self.effects = [e for e in self.effects if e["age"] < e.get("life", 0.45)]
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
        self.invincible = 0.0
        self.shake = 0.4
        self.flash = 0.25
        self.audio.play("hit")
