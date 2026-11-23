#!/usr/bin/env python3
"""Build the player's racer as a low-poly model.

    python3 tools/make_ship.py

Writes neon_conduit/assets/ship.obj, a plain Wavefront OBJ that any 3D editor
(Blender, ...) can open and re-export. The game reads vertices, faces, lines and
the material names (usemtl); the colours behind each name live in model.py.

Axes: x to the right, y up from the surface, z forward. One unit is one game unit
(the track tube has radius 10). The model rests on y = 0, nose towards +z.

The ship is an arrowhead: a needle nose, two rear corners and a tall fin between
them, closed underneath. A glowing nozzle sits on the back face (material glow:
the renderer paints it over the hull and trails the exhaust flame from it), and a
neon line runs along the leading edges.
"""
import os

OUT = os.path.join(os.path.dirname(__file__), "..", "neon_conduit", "assets", "ship.obj")

VERTS = [
    (-1.5, 0.25, -1.5),     # 1 rear left
    (1.5, 0.25, -1.5),      # 2 rear right
    (0.0, 0.32, 4.5),       # 3 nose
    (0.0, 1.25, -1.5),      # 4 fin tip: low enough that the camera sees both flanks
    (-0.45, 0.34, -1.52),   # 5-7 exhaust nozzle, just behind the back face
    (0.45, 0.34, -1.52),
    (0.0, 0.8, -1.52),
]
FACES = [                   # corners (1-based), material
    ((1, 3, 4), "body"),    # left flank
    ((2, 4, 3), "body"),    # right flank
    ((1, 4, 2), "dark"),    # back
    ((1, 2, 3), "dark"),    # belly
    ((5, 7, 6), "glow"),    # nozzle
]
LINES = [((1, 3, 2), "neon")]   # leading edges: rear left, nose, rear right


def outward(face):
    """Wind a face so its normal points away from the hull's centre (the hull is convex)."""
    idx, mat = face
    p0, p1, p2 = (VERTS[i - 1] for i in idx[:3])
    u = [p1[i] - p0[i] for i in range(3)]
    v = [p2[i] - p0[i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    hull = VERTS[:4]
    centre = [sum(p[c] for p in hull) / 4 for c in range(3)]
    mid = [sum(VERTS[i - 1][c] for i in idx) / len(idx) for c in range(3)]
    if sum(n[c] * (mid[c] - centre[c]) for c in range(3)) < 0:
        idx = tuple(reversed(idx))
    return idx, mat


def write(path):
    with open(path, "w") as f:
        f.write("# Neon Conduit racer, written by tools/make_ship.py\n")
        for v in VERTS:
            f.write("v %.3f %.3f %.3f\n" % v)
        for idx, mat in [outward(face) for face in FACES] + LINES:
            kind = "l" if (idx, mat) in LINES else "f"
            f.write("usemtl %s\n%s %s\n" % (mat, kind, " ".join(map(str, idx))))


if __name__ == "__main__":
    write(OUT)
    print("wrote %s: %d vertices, %d faces, %d lines"
          % (os.path.normpath(OUT), len(VERTS), len(FACES), len(LINES)))
