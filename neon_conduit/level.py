"""Hand-made levels: a finite course with a finish line, saved as a JSON file.

    {
      "name": "My level",
      "start_time": 30,                     seconds on the clock at the start
      "sections": [                         the course, in order
        {"length": 60, "bend": 0.0, "slope": 0.0, "kind": "tube", "pattern": null},
        {"length": 40, "bend": 0.3, "slope": 0.0, "kind": "ground", "width": 14, "theme": null},
        ...
      ],
      "objects": [                          what is on it, anywhere along it
        {"kind": "boost", "seg": 75, "angle": 0.0},
        {"kind": "drone", "seg": 120, "angle": 0.5, "sway": 0.4, "rate": 1.6, "speed": 0.5},
        {"kind": "gate", "seg": 200},
        ...
      ]
    }

A section is `length` segments (SEG world units each) easing into and out of its `bend`
(curvature: < 0 left, > 0 right) and `slope` (pitch: < 0 down, > 0 up). Its `kind` is
"tube", "ground" (an outdoor road, `width` its floor's half-width) or "air" (an outdoor,
see-through tube). A tube's `pattern` names a wall pattern (conduit_patterns.txt), an
outdoor section's `theme` one of the outdoor themes (outdoor_themes.txt); null picks one
at random, as the endless track does. A door closes every outdoor run as the tube resumes.

Objects sit at segment `seg` from the start, at wall angle `angle` (radians: 0 the
middle of the floor, +/- pi the ceiling). Their kinds, with their own settings, are listed
in OBJECT_KINDS: a new kind of obstacle is an entry there, plus what it does in
Game._objects and how it looks in Renderer._object.

The finish line is at the end of the last section.
"""
import json
import math
import random

from .config import (BOOST_HW, DRONE_SPEED, FLOOR_HW, SEG, STAR_REACH, WIDE_HW, WIDE_TAPER)
from .geometry import floor_limit, snap
from .patterns import BY_NAME
from .themes import THEMES
from .track import Track

KINDS = ("tube", "ground", "air")
WIDTH_MAX = WIDE_HW[1]
# Each section setting: (default, lowest, highest, step in the editor).
SECTION_SETTINGS = {
    "length": (40, 4, 400, 4),
    "bend": (0.0, -0.6, 0.6, 0.05),
    "slope": (0.0, -0.3, 0.3, 0.05),
    "width": (FLOOR_HW, FLOOR_HW, WIDTH_MAX, 1.0),
}
START_TIME = (30.0, 5.0, 300.0, 5.0)


class ObjectKind:
    def __init__(self, label, key, colour, angle=True, settings=None, length=0.0):
        self.label = label          # its name in the editor
        self.key = key              # the editor's keyboard shortcut for its tool
        self.colour = colour        # how it shows on the editor's map
        self.angle = angle          # False: it spans the whole tube (no angle)
        self.settings = settings or {}   # name: (default, lowest, highest, step)
        self.length = length        # world units it reaches along the track


OBJECT_KINDS = {
    "boost": ObjectKind("Boost pad", "b", (60, 255, 120), length=10.0),
    "drone": ObjectKind("Drone", "d", (255, 120, 30), settings={
        "sway": (0.4, 0.0, 1.5, 0.1),       # how far it swings either side, radians
        "rate": (1.6, 0.0, 4.0, 0.2),       # how fast it swings
        "speed": (DRONE_SPEED, 0.0, 1.0, 0.1),   # flying forward, as a fraction of top speed
    }),
    "gate": ObjectKind("Gate", "g", (255, 255, 160), angle=False),
}


class LevelError(ValueError):
    pass


def new_section(**over):
    s = {"length": 40, "bend": 0.0, "slope": 0.0, "kind": "tube", "pattern": None,
         "width": FLOOR_HW, "theme": None}
    s.update(over)
    return s


def new_object(kind, seg, angle=0.0):
    o = {"kind": kind, "seg": seg}
    k = OBJECT_KINDS[kind]
    if k.angle:
        o["angle"] = angle
    for name, (default, _, _, _) in k.settings.items():
        o[name] = default
    return o


class Level:
    def __init__(self, name="Untitled", start_time=START_TIME[0], sections=None, objects=None):
        self.name = name
        self.start_time = start_time
        self.sections = sections if sections is not None else [new_section(length=60)]
        self.objects = objects if objects is not None else []

    @property
    def length(self):
        """Segments from the start to the finish line."""
        return sum(s["length"] for s in self.sections)

    def section_at(self, seg):
        """Index of the section segment seg is in (the last one past the finish), and where
        that section starts."""
        start = 0
        for i, s in enumerate(self.sections):
            if seg < start + s["length"]:
                return i, start
            start += s["length"]
        return len(self.sections) - 1, start - self.sections[-1]["length"]

    def section_start(self, i):
        return sum(s["length"] for s in self.sections[:i])

    # ------------------------------------------------------------ file
    def to_dict(self):
        sections = []
        for s in self.sections:
            d = {"length": s["length"], "bend": round(s["bend"], 3), "slope": round(s["slope"], 3),
                 "kind": s["kind"]}
            if s["kind"] == "tube":
                d["pattern"] = s.get("pattern")
            else:
                if s["kind"] == "ground":
                    d["width"] = round(s["width"], 2)
                d["theme"] = s.get("theme")
            sections.append(d)
        objects = []
        for o in sorted(self.objects, key=lambda o: o["seg"]):
            d = {"kind": o["kind"], "seg": o["seg"]}
            k = OBJECT_KINDS[o["kind"]]
            if k.angle:
                d["angle"] = round(o["angle"], 3)
            for name in k.settings:
                d[name] = round(o[name], 3)
            objects.append(d)
        return {"name": self.name, "start_time": self.start_time, "sections": sections,
                "objects": objects}

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
            f.write("\n")

    def copy(self):
        return from_dict(self.to_dict())

    def build(self):
        """The game's track for this level: see CourseTrack."""
        return CourseTrack(self)


def _num(d, key, where, rng, default=None):
    v = d.get(key, default)
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        raise LevelError("%s: %s should be a number, not %r" % (where, key, v))
    lo, hi = rng
    if not lo <= v <= hi:
        raise LevelError("%s: %s should be between %g and %g, not %g" % (where, key, lo, hi, v))
    return v


def from_dict(d):
    if not isinstance(d, dict):
        raise LevelError("a level is a JSON object")
    sections = []
    for i, s in enumerate(d.get("sections") or []):
        where = "section %d" % (i + 1)
        kind = s.get("kind", "tube")
        if kind not in KINDS:
            raise LevelError("%s: kind should be one of %s, not %r" % (where, ", ".join(KINDS), kind))
        sec = new_section(kind=kind)
        for key, (default, lo, hi, _) in SECTION_SETTINGS.items():
            sec[key] = _num(s, key, where, (lo, hi), default)
        sec["length"] = int(sec["length"])
        pattern, theme = s.get("pattern"), s.get("theme")
        if kind == "tube" and pattern is not None and pattern not in BY_NAME:
            raise LevelError("%s: no wall pattern called %r" % (where, pattern))
        if kind != "tube" and theme is not None:
            if theme not in THEMES:
                raise LevelError("%s: no outdoor theme called %r" % (where, theme))
            if kind not in THEMES[theme].kinds:
                raise LevelError("%s: theme %r is not for %s sections" % (where, theme, kind))
        sec["pattern"], sec["theme"] = pattern, theme
        sections.append(sec)
    if not sections:
        raise LevelError("a level needs at least one section")
    total = sum(s["length"] for s in sections)
    objects = []
    for i, o in enumerate(d.get("objects") or []):
        where = "object %d" % (i + 1)
        kind = o.get("kind")
        if kind not in OBJECT_KINDS:
            raise LevelError("%s: kind should be one of %s, not %r" % (where, ", ".join(OBJECT_KINDS), kind))
        k = OBJECT_KINDS[kind]
        obj = new_object(kind, int(_num(o, "seg", where, (0, total - 1))))
        if k.angle:
            obj["angle"] = _num(o, "angle", where, (-math.pi, math.pi), 0.0)
        for name, (default, lo, hi, _) in k.settings.items():
            obj[name] = _num(o, name, where, (lo, hi), default)
        objects.append(obj)
    st = _num(d, "start_time", "the level", START_TIME[1:3], START_TIME[0])
    return Level(str(d.get("name", "Untitled")), st, sections, objects)


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except json.JSONDecodeError as e:
        raise LevelError("not valid JSON: %s" % e) from None
    return from_dict(d)


# ------------------------------------------------------------------- track
def _smooth(t):
    return t * t * (3 - 2 * t)


class CourseTrack(Track):
    """The track of a level: its sections and objects as they are, the finish line at the
    end, and past it a straight run-out (so there is always track to draw ahead)."""

    def __init__(self, level):
        self.rng = random.Random(0)          # unused: nothing here is random but decoration
        self._clear()
        self.level = level
        self.patterns = []                   # per segment: wall pattern name, or None
        self.themes = []                     # per segment: outdoor theme name, or None
        self.gates = set()                   # segments with a gate (or the finish) at their start
        prev = "tube"
        for s in level.sections:
            kind = s["kind"]
            if kind != "tube" and kind != prev:  # a new outdoor run: its own look, and the
                self.runs += 1                   # tube after it too (see Track.stretch)
            n = s["length"]
            for j in range(n):
                env = math.sin(math.pi * (j + 0.5) / n)
                self.curv.append(s["bend"] * env)
                self.pitch.append(s["slope"] * env)
                self.open.append(kind == "ground")
                self.air.append(kind == "air")
                self.stretch.append(self.runs)
                self.width.append(s["width"] if kind == "ground" else FLOOR_HW)
                self.patterns.append(s.get("pattern") if kind == "tube" else None)
                self.themes.append(s.get("theme") if kind != "tube" else None)
            prev = kind
        self.finish = len(self.curv)
        self._ease_widths()
        self.next_gate = self.finish             # the HUD's progress bar runs to the finish
        self.ensure(self.finish + 1, 0)
        for i, o in enumerate(level.objects):
            self.objects.extend(self._place(i, o))
        self.objects.append({"kind": "finish", "z": self.finish * SEG})
        self.gates.update((self.finish, self.finish - 1))

    def _ease_widths(self):
        """Ground runs splay out to their sections' widths and back in where they meet the
        tube, and ease from one section's width to the next."""
        i, n = 0, self.finish
        while i < n:
            if not self.open[i]:
                i += 1
                continue
            j = i
            while j < n and self.open[j]:
                j += 1
            raw = self.width[i:j]
            total, half = j - i, WIDE_TAPER // 2
            for k in range(total):
                win = raw[max(0, k - half):k + half + 1]
                w = sum(win) / len(win)
                t = _smooth(min(1.0, min(k, total - k) / WIDE_TAPER))
                self.width[i + k] = FLOOR_HW + (w - FLOOR_HW) * t
            i = j

    def _place(self, i, o):
        """The game's objects for level object o (the i-th)."""
        z = o["seg"] * SEG
        kind = o["kind"]
        if kind == "boost":
            seg = o["seg"]
            if self.open[seg]:
                hw = min(self.width[seg], self.width[min(seg + 2, len(self.width) - 1)])
                lim = floor_limit(BOOST_HW, hw)
                a = max(-lim, min(lim, o["angle"]))
            else:
                a = snap(o["angle"], BOOST_HW)
            for k in range(int((z - STAR_REACH) // SEG), int((z + 10 + STAR_REACH) // SEG) + 1):
                self.no_star.add(k)                # keep hint stars off the pad
            return [{"kind": "boost", "z": z, "a": a}]
        if kind == "drone":
            return [{"kind": "drone", "z": z, "a0": o["angle"], "a": o["angle"], "amp": o["sway"],
                     "w": o["rate"], "ph": random.Random(i).uniform(0, 2 * math.pi),
                     "v": o["speed"]}]
        if kind == "gate":
            self.gates.update((o["seg"], o["seg"] - 1))
            return [{"kind": "gate", "z": z}]
        return []

    def ensure(self, seg_index, level):
        """Past the finish, the run-out: the last section's kind, straightened out."""
        while len(self.curv) < seg_index:
            last = len(self.curv) - 1
            self.curv.append(0.0)
            self.pitch.append(0.0)
            self.open.append(self.open[last])
            self.air.append(self.air[last])
            self.stretch.append(self.stretch[last])
            self.width.append(self.width[last])
            self.patterns.append(self.patterns[last])
            self.themes.append(self.themes[last])

    def gate_glow(self, i):
        return i in self.gates

    def tube_style(self, i):
        return self.patterns[i] or super().tube_style(i)

    def outdoor_theme(self, i):
        return self.themes[i] or super().outdoor_theme(i)
