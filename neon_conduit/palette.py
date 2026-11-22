"""Colours: fog, tube palettes, kerbs and doors. (Wall patterns are in patterns.py.)"""
import colorsys
import random

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


def mix(c1, c2, t):
    """Colour t of the way from c1 to c2."""
    return (int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t))


def fogged(c, lt, fog, fog_col=FOG):
    """Colour c lit at strength lt, then faded fog of the way into the fog (of colour fog_col)."""
    lt *= 1 - fog
    return (int(c[0] * lt + fog_col[0] * fog),
            int(c[1] * lt + fog_col[1] * fog),
            int(c[2] * lt + fog_col[2] * fog))


def tube_palette(stretch, contrast="strong"):
    """The two wall colours for a stretch of tube: the zone's pair, pushed further apart
    unless the pattern asks for soft contrast."""
    pal = PALETTES[stretch % len(PALETTES)]
    if contrast != "soft":
        pal = (mix(pal[0], (0, 0, 0), 0.5), tuple(min(255, int(v * 1.45)) for v in pal[1]))
    return pal


def kerb_cols(run):
    """Random bright / dark stripe pair for the kerbs of open run number run."""
    rng = random.Random(run * 7919 + 1)
    h, s = rng.random(), rng.uniform(0.55, 0.85)
    return tuple(tuple(int(255 * x) for x in colorsys.hsv_to_rgb(h, s, v)) for v in (0.9, 0.58))
