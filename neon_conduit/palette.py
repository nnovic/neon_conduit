"""Colours: fog, tube palettes, wall patterns, kerbs and doors."""
import colorsys
import math
import random

from .config import SIDES
from .geometry import SIDE_MID

FOG = (6, 8, 22)
PALETTES = [                                  # one per stretch of tube, in turn
    ((20, 70, 150), (28, 110, 200)),
    ((120, 30, 130), (170, 50, 170)),
    ((20, 110, 90), (30, 160, 120)),
    ((150, 70, 20), (200, 110, 30)),
    ((150, 30, 50), (200, 50, 70)),
]
FLOOR_COLS = ((58, 60, 74), (76, 79, 96))     # slate road, same in every zone
GATE_GLOW = (240, 240, 255)
DOOR_COL = (70, 78, 112)
DOOR_EDGE = (255, 200, 60)

# Wall patterns for a stretch of tube; see tube_shade.
TUBE_STYLES = ("checker", "rings", "stripes", "chevrons", "whirl", "pulse")


def mix(c1, c2, t):
    """Colour t of the way from c1 to c2."""
    return (int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t))


def fogged(c, lt, fog):
    """Colour c lit at strength lt, then faded fog of the way into the fog."""
    lt *= 1 - fog
    return (int(c[0] * lt + FOG[0] * fog),
            int(c[1] * lt + FOG[1] * fog),
            int(c[2] * lt + FOG[2] * fog))


def tube_palette(stretch, style):
    """The two wall colours for a stretch of tube; the newer patterns get starker contrast."""
    pal = PALETTES[stretch % len(PALETTES)]
    if style != "checker":
        pal = (mix(pal[0], (0, 0, 0), 0.5), tuple(min(255, int(v * 1.45)) for v in pal[1]))
    return pal


def tube_shade(style, si, s, t):
    """How far along from the palette's first colour to its second (0..1) side s of
    segment si is painted, for a tube style at time t."""
    if style == "checker":
        return (si // 2 + s) & 1
    if style == "rings":                     # bands round the tube: circles down the middle
        return (si // 3) & 1
    if style == "stripes":                   # dashed lines along the tube, staggered side to side
        return 1 if s & 1 and (si + 3 * (s // 2 & 1)) % 6 < 4 else 0
    m = SIDE_MID[s]
    if style == "chevrons":                  # V shapes, mirrored left and right
        return ((si + int(abs(m) * SIDES / (2 * math.pi))) // 2) & 1
    if style == "whirl":                     # barber pole: crisp diagonal bands
        return 1 if (s + si) % 8 < 2 else 0     # two stripes round the tube, wide gaps between
    v = math.sin(0.45 * si + 7.0 * t)        # pulse: soft waves rushing towards the sled
    return max(0.0, min(1.0, 0.5 + 1.5 * v))


def kerb_cols(run):
    """Random bright / dark stripe pair for the kerbs of open run number run."""
    rng = random.Random(run * 7919 + 1)
    h, s = rng.random(), rng.uniform(0.55, 0.85)
    return tuple(tuple(int(255 * x) for x in colorsys.hsv_to_rgb(h, s, v)) for v in (0.9, 0.58))
