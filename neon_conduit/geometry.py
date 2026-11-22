"""Shape of the tube: wall angles, positions on the surface, distances, and polygon clipping.

Angles go round the tube with 0 at the bottom of the floor. The cross-section has
a flat floor up to FLOOR_A either side, then a circular wall of radius R; open
sections carry the floor on flat instead.
"""
import math

from .config import FLAT_MAX, FLOOR_A, FLOOR_HW, FLOOR_Y, R, SIDES


def wrap(a):
    """Wrap an angle to [-pi, pi]."""
    return (a + math.pi) % (2 * math.pi) - math.pi


def prof(a):
    """Distance from the tube centre to the wall at angle a (flat floor at the bottom)."""
    c = math.cos(a)
    return FLOOR_Y / c if c > FLOOR_Y / R else R


def bank(a):
    """0 on the flat floor, 1 on the curved wall, blended across the corner."""
    return max(0.0, min(1.0, (abs(wrap(a)) - 0.8 * FLOOR_A) / 0.35))


def floor_limit(half_width, hw=None):
    """Largest angle at which something this wide still sits wholly on a floor of half-width hw.

    Open sections are a flat road between upright kerbs, so nothing there goes past this.
    """
    if hw is None:
        hw = FLOOR_HW
    return math.atan((hw - half_width - 0.2) / FLOOR_Y)


def lat_pos(a, flat=False):
    """Distance along the surface from the middle of the floor to angle a.

    flat: in an open section the floor carries on flat instead of curving up into the wall.
    """
    w = wrap(a)
    if flat:
        return FLOOR_Y * math.tan(max(-FLAT_MAX, min(FLAT_MAX, w)))
    if abs(w) < FLOOR_A:
        return FLOOR_Y * math.tan(w)
    return math.copysign(FLOOR_Y * math.tan(FLOOR_A) + R * (abs(w) - FLOOR_A), w)


PERIMETER = 2 * (FLOOR_Y * math.tan(FLOOR_A) + R * (math.pi - FLOOR_A))


def lat_dist(a1, a2, flat=False):
    """Sideways distance between two wall angles, in world units."""
    d = abs(lat_pos(a1, flat) - lat_pos(a2, flat))
    return min(d, PERIMETER - d)


def snap(a, half_width):
    """Move angle a so an object this wide sits wholly on the floor or wholly on the wall."""
    w = wrap(a)
    lo = math.atan((FLOOR_Y * math.tan(FLOOR_A) - half_width - 0.2) / FLOOR_Y)
    hi = FLOOR_A + (half_width + 0.2) / R
    if lo < abs(w) < hi:
        w = math.copysign(lo if abs(w) < (lo + hi) / 2 else hi, w)
    return w


def wall_xy(a, lat, h, rigid=False, flat=0.0):
    """Point in the tube cross-section: at wall angle a, lat units sideways, h above the surface.

    Fixed scenery follows the surface (flat on the floor, curved on the wall).
    Moving things are rigid: they use one local frame, which stays upright on
    the floor and turns smoothly to the wall normal past the corner.
    flat: 1 in open sections, where the floor carries on flat past the tube's
    corner; in between, rigid things blend from the tube frame to the flat one.
    """
    w = wrap(a)
    if flat > 0.0 or abs(w) < FLOOR_A:
        fx = FLOOR_Y * math.tan(max(-FLAT_MAX, min(FLAT_MAX, w))) + lat
        fy = FLOOR_Y - h
        if flat >= 1.0 or abs(w) < FLOOR_A and not rigid:
            return fx, fy
    if rigid:
        r = prof(w)
        na = w * bank(w)
        x = r * math.sin(w) + lat * math.cos(na) - h * math.sin(na)
        y = r * math.cos(w) - lat * math.sin(na) - h * math.cos(na)
        if flat > 0.0:
            return x + (fx - x) * flat, y + (fy - y) * flat
        return x, y
    a2 = w + lat / R
    return (R - h) * math.sin(a2), (R - h) * math.cos(a2)


def clip(poly, c, below, axis=0):
    """The part of convex polygon poly where coordinate axis is <= c (below) or >= c."""
    out = []
    n = len(poly)
    for j in range(n):
        p, q = poly[j], poly[(j + 1) % n]
        pin = p[axis] <= c if below else p[axis] >= c
        qin = q[axis] <= c if below else q[axis] >= c
        if pin:
            out.append(p)
        if pin != qin:
            t = (c - p[axis]) / (q[axis] - p[axis])
            m = (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)
            out.append((c, m[1]) if axis == 0 else (m[0], c))
    return out


# ------------------------------------------------------- per-side tables
SIDE_A = [-math.pi + 2 * math.pi * k / SIDES for k in range(SIDES + 1)]   # vertex angles
SIDE_SIN = [math.sin(a) for a in SIDE_A]
SIDE_COS = [math.cos(a) for a in SIDE_A]
SIDE_R = [prof(a) for a in SIDE_A]
SIDE_MID = [SIDE_A[k] + math.pi / SIDES for k in range(SIDES)]           # side centre angles
# Sides lit from below so the floor reads brighter than the ceiling.
SIDE_LIGHT = [0.62 + 0.38 * math.cos(m) for m in SIDE_MID]
FLOOR_SIDES = [s for s in range(SIDES) if abs(SIDE_MID[s]) < FLOOR_A]
# Floor vertices across an open section, as fractions of its half-width (-1 .. 1).
OPEN_X = [math.tan(SIDE_A[v]) / math.tan(FLOOR_A)
          for v in range(FLOOR_SIDES[0], FLOOR_SIDES[-1] + 2)]
# Cross-section of the tube, (x, y) with y pointing down: the shape a door has to fill.
TUBE_XS = [(SIDE_R[s] * math.sin(SIDE_A[s]), SIDE_R[s] * math.cos(SIDE_A[s])) for s in range(SIDES)]
