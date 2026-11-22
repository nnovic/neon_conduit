"""The endless, procedurally generated track."""
import math
import random

from .config import (BOOST_CHANCE, BOOST_HW, FLOOR_HW, FLOOR_Y, GATE_SEGS, LINE_BEND, LINE_GAIN,
                     LINE_MAX, OPEN_CHANCE, OPEN_RUN, SEG, SLED_HW, STAR_BEND, STAR_EVERY, STAR_REACH,
                     WIDE_CHANCE, WIDE_HW, WIDE_TAPER)
from .geometry import floor_limit, lat_pos, snap
from .palette import kerb_cols
from .patterns import PATTERNS


class Track:
    """Endless track: per-segment curvature, pitch and open/closed flag, plus the objects on it.

    Sections are generated on demand (see ensure) from the track's own rng, so a seed
    always gives the same course. Purely decorative choices (patterns, colours, door
    tilts) use separate generators and never disturb it.
    """

    def __init__(self, rng):
        self.rng = rng
        self.curv = []
        self.pitch = []
        self.open = []
        self.width = []            # floor half-width at the start of each segment
        self.stretch = []          # per segment: how many open runs come before it
        self.objects = []          # dicts: kind, z, a, ...
        self.door_angles = {}
        self.kerb_cols = {}
        self.tube_styles = {}
        self.no_star = set()       # segments whose star would overlap a boost pad
        self.runs = 0
        self.next_gate = GATE_SEGS
        self._section(30, 0.0, 0.0, False, 0, empty=True)

    def ensure(self, seg_index, level):
        """Generate track up to segment seg_index, with the difficulty of gate level."""
        while len(self.curv) < seg_index:
            # Never two open runs back to back: there is always tube in between.
            if not self.open[-1] and self.rng.random() < OPEN_CHANCE:
                self._open_run(level)
            else:
                self._section(*self._shape(level), False, level)

    # ------------------------------------------------------------ queries
    def line(self, i):
        """Wall angle of the fast line in segment i: the outside of the bend."""
        c = self.curv[i]
        a = -math.copysign(min(LINE_MAX, LINE_GAIN * abs(c)), c)
        if self.open[i]:
            # Same distance from the middle, but on the flat and inside the kerbs.
            lim = self.width[i] - SLED_HW - 0.2
            a = math.atan(max(-lim, min(lim, lat_pos(a))) / FLOOR_Y)
        return a

    def bend(self, i):
        """0 on a straight, 1 in a proper bend."""
        return min(1.0, abs(self.curv[i]) / LINE_BEND)

    def has_star(self, i):
        """True where a hint star floats over the fast line at the start of segment i."""
        return i % STAR_EVERY == 0 and self.bend(i) >= STAR_BEND and i not in self.no_star

    def hw_at(self, z):
        """Floor half-width at depth z."""
        f = z / SEG
        i = int(f)
        return self.width[i] + (self.width[i + 1] - self.width[i]) * (f - i)

    def is_door(self, i):
        """True where segment i is tube following an open section: a door closes it off."""
        return 0 < i < len(self.open) and self.open[i - 1] and not self.open[i]

    def door_angle(self, i):
        """Tilt of door i's split line: vertical, horizontal or either diagonal, picked at
        random once per door (and kept off the track's own rng)."""
        if i not in self.door_angles:
            self.door_angles[i] = random.Random(i).choice((0.0, 0.5, 0.25, 0.75)) * math.pi
        return self.door_angles[i]

    def tube_style(self, i):
        """Name of the wall pattern of tube segment i: one random pattern per stretch of tube."""
        run = self.stretch[i]
        if run not in self.tube_styles:
            self.tube_styles[run] = random.Random(run * 104729 + 7).choice(PATTERNS).name
        return self.tube_styles[run]

    def kerb_col(self, i, band):
        """Kerb colour in open segment i: one random scheme per open run, striped by band."""
        run = self.stretch[i]
        if run not in self.kerb_cols:
            self.kerb_cols[run] = kerb_cols(run)
        return self.kerb_cols[run][band & 1]

    # --------------------------------------------------------- generation
    def _shape(self, level):
        """Length, peak curvature and peak pitch of a new section."""
        rng = self.rng
        n = rng.randint(24, 56)
        c = 0.0
        if rng.random() < 0.72:
            peak = min(0.55, 0.30 + 0.04 * level)
            c = rng.uniform(0.14, peak) * rng.choice((-1, 1))
        p = rng.uniform(-0.2, 0.2) if rng.random() < 0.5 else 0.0
        return n, c, p

    def _open_run(self, level):
        """Several open sections back to back; some runs splay out to a wider floor."""
        rng = self.rng
        self.runs += 1
        shapes = [self._shape(level) for _ in range(rng.randint(*OPEN_RUN))]
        total = sum(n for n, _, _ in shapes)
        peak = rng.uniform(*WIDE_HW) if rng.random() < WIDE_CHANCE else FLOOR_HW
        widths = []
        for j in range(total):
            # Tube width where the run meets the tube, easing out to the peak and back.
            t = min(1.0, min(j, total - j) / WIDE_TAPER)
            widths.append(FLOOR_HW + (peak - FLOOR_HW) * t * t * (3 - 2 * t))
        j = 0
        for n, c, p in shapes:
            self._section(n, c, p, True, level, widths=widths[j:j + n])
            j += n

    def _section(self, n, c, p, is_open, level, empty=False, widths=None):
        """n segments easing into and out of curvature c and pitch p, with boosts and drones."""
        rng = self.rng
        start = len(self.curv)
        for j in range(n):
            env = math.sin(math.pi * (j + 0.5) / n)
            self.curv.append(c * env)
            self.pitch.append(p * env)
            self.open.append(is_open)
            self.stretch.append(self.runs)
            self.width.append(widths[j] if widths else FLOOR_HW)
        # Checkpoint gates at fixed intervals.
        while self.next_gate < start + n:
            self.objects.append({"kind": "gate", "z": self.next_gate * SEG})
            self.next_gate += GATE_SEGS
        if empty:
            return

        n_boost = 1 if rng.random() < BOOST_CHANCE else 0
        n_drone = rng.randint(0, min(3, 1 + level // 3))
        slots = rng.sample(range(3, n - 2), n_boost + n_drone)
        for i, j in enumerate(slots):
            z = (start + j) * SEG
            hw = min(self.width[start + j], self.width[start + j + 2])
            if i < n_boost:
                lim = floor_limit(BOOST_HW, hw)
                if abs(c) > 0.05:
                    a = self.line(start + j)        # on the fast line
                    if is_open:
                        a = max(-lim, min(lim, a))
                elif is_open:
                    a = rng.uniform(-lim, lim)
                else:
                    a = rng.uniform(-1.0, 1.0)
                self.objects.append({"kind": "boost", "z": z, "a": a if is_open else snap(a, BOOST_HW)})
                # Keep stars off the pad (it runs from z to z + 10).
                for k in range(int((z - STAR_REACH) // SEG), int((z + 10 + STAR_REACH) // SEG) + 1):
                    self.no_star.add(k)
            else:
                self.objects.append({
                    "kind": "drone", "z": z, "a0": rng.uniform(-0.9, 0.9),
                    "a": 0.0, "amp": rng.uniform(0.2, 0.7),
                    "w": rng.uniform(1.0, 2.5), "ph": rng.uniform(0, 6.28),
                })
