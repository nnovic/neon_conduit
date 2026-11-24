"""The title screen's backdrop: a close-up of a flag rippling in a slow wind, and in front
of it a short section of tunnel, the racer inside, turning slowly as glowing wireframes.

The flag fills the whole screen, its edges out of sight. Its cloth is woven from the
tunnels' checker pattern, in the first zone's blues: along the flag runs the tunnel's
length (one cell per track segment), across it the wall panels.
"""
import math

import pygame

from .config import FLOOR_Y, SEG, SIDES
from .geometry import SIDE_A, SIDE_R
from .model import load_obj
from .palette import mix, tube_palette
from .patterns import BY_NAME, WIDTH

PATTERN = "checker"
NX, NY = 18, WIDTH              # cells along and across the flag
FLAG_W, FLAG_H = 30.0, 21.0     # flag size, world units: well past the screen's edges
DIST = 13.0                     # camera distance to the flag
WAVE = 0.5                      # how deep the waves run (1: deep folds)


class TitleFlag:
    def __init__(self, screen):
        self.screen = screen
        self.w, self.h = screen.get_size()
        self.f = self.w * 0.62               # focal length, pixels
        self.pattern = BY_NAME[PATTERN]
        self.pal = tube_palette(0, self.pattern.contrast)

    def _grid(self, t):
        """Screen position and cloth depth of every grid corner: grid[i][j] = ((x, y), z)."""
        sin = math.sin
        # The whole cloth drifts a little: a slow bob, sway and tilt, never enough to
        # bring an edge into view.
        bob = 0.4 * sin(t * 0.7)
        yaw = 0.06 * sin(t * 0.45)
        roll = 0.03 * sin(t * 0.55)
        cy_, sy_ = math.cos(yaw), math.sin(yaw)
        cr, sr = math.cos(roll), math.sin(roll)
        cx0, cy0, f = self.w * 0.5, self.h * 0.5, self.f
        grid = []
        for i in range(NX + 1):
            x = (i / NX - 0.5) * FLAG_W
            # Waves roll across the cloth, left to right.
            a1, a2 = 1.3 * x - 2.0 * t, 2.2 * x - 2.9 * t + 1.3
            sag = WAVE * 0.4 * sin(0.8 * x - 1.5 * t) + bob      # the cloth lifts and sags
            column = []
            for j in range(NY + 1):
                y = (j / NY - 0.5) * FLAG_H
                z = WAVE * (1.1 * sin(a1 + 0.18 * y) + 0.45 * sin(a2 - 0.4 * y))
                y += sag
                xr, zr = x * cy_ - z * sy_, x * sy_ + z * cy_
                xs, ys = xr * cr - y * sr, xr * sr + y * cr
                d = DIST + zr
                column.append(((cx0 + f * xs / d, cy0 + f * ys / d), z))
            grid.append(column)
        return grid

    def draw(self, t):
        scr, pat, (dark, light) = self.screen, self.pattern, self.pal
        grid = self._grid(t)
        for i in range(NX):
            for j in range(NY):
                (p0, z0), (p1, z1) = grid[i][j], grid[i + 1][j]
                (p2, _), (p3, z3) = grid[i + 1][j + 1], grid[i][j + 1]
                c = mix(dark, light, pat.shade(NX - 1 - i, j % WIDTH, t))
                # Light from the cloth's slope: folds facing us bright, those turned away dark.
                slope = (z1 - z0) + 0.5 * (z3 - z0)
                lt = max(0.6, min(1.2, 0.92 - 0.45 * slope))
                c = (min(255, int(c[0] * lt)), min(255, int(c[1] * lt)), min(255, int(c[2] * lt)))
                pygame.draw.polygon(scr, c, (p0, p1, p2, p3))


# The wireframe tunnel section.
TUBE_SEGS = 9                   # its length, in track segments
TUBE_DIST = 55.0                # camera distance to its centre
TUBE_CENTRE = (0.5, 0.55)       # where its centre sits on screen, as fractions of the screen
TUBE_SPIN = 0.3                 # how fast it turns round the upright, radians per second
TUBE_TILT = 0.42                # how far the camera looks down on it, radians
SHIP_SCALE = 2.0                # the racer, a little larger than life so it reads from afar
SHIP_HOVER = 0.3
RING_COL = (255, 80, 160)       # the tube's ribs
RAIL_COL = (40, 210, 255)       # the lines running along it
SHIP_COLS = {"glow": (90, 180, 255), "neon": (255, 80, 160)}
SHIP_COL = (255, 245, 170)      # every other edge of the racer
DIM = 0.5                       # brightness of the farthest lines (1: the nearest)


def _edges(model):
    """The model's face outlines and lines as [(i, j, material)], each edge once; lines
    and glowing faces keep their own colour where they share an edge with the hull."""
    loops = [(idx + idx[:1], mat) for idx, mat in model.faces] + model.lines
    loops.sort(key=lambda l: l[1] in SHIP_COLS, reverse=True)   # coloured edges claim first
    seen, out = set(), []
    for idx, mat in loops:
        for i, j in zip(idx, idx[1:]):
            key = (min(i, j), max(i, j))
            if key not in seen:
                seen.add(key)
                out.append((i, j, mat))
    return out


class TitleTunnel:
    """A few segments of the tube, flat floor and all, with the racer on its floor, as
    glowing lines turning round the upright; nearer lines brighter."""

    def __init__(self, screen):
        self.screen = screen
        w, h = screen.get_size()
        self.f = w * 0.62
        self.cx, self.cy = w * TUBE_CENTRE[0], h * TUBE_CENTRE[1]
        # Tube: wall corners round each ring, x right, y up, z along; centred on the origin.
        half = TUBE_SEGS * SEG / 2
        verts, edges = [], []
        for k in range(TUBE_SEGS + 1):
            z = -half + k * SEG
            for v in range(SIDES):
                a, r = SIDE_A[v], SIDE_R[v]
                verts.append((r * math.sin(a), -r * math.cos(a), z))
        for k in range(TUBE_SEGS + 1):
            for v in range(SIDES):
                edges.append((k * SIDES + v, k * SIDES + (v + 1) % SIDES, RING_COL))
                if k < TUBE_SEGS:
                    edges.append((k * SIDES + v, (k + 1) * SIDES + v, RAIL_COL))
        edges = [e + (1,) for e in edges]
        # Racer: on the floor, centred along the section.
        ship = load_obj("ship.obj")
        zs = [p[2] for p in ship.verts]
        zmid = (min(zs) + max(zs)) / 2
        base = len(verts)
        for x, y, z in ship.verts:
            verts.append((x * SHIP_SCALE, -FLOOR_Y + SHIP_HOVER + y * SHIP_SCALE, (z - zmid) * SHIP_SCALE))
        for i, j, mat in _edges(ship):
            edges.append((base + i, base + j, SHIP_COLS.get(mat, SHIP_COL), 2))   # bolder
        self.verts, self.edges = verts, edges
        self.reach = max(math.sqrt(x * x + y * y + z * z) for x, y, z in verts)

    def draw(self, t):
        yaw = TUBE_SPIN * t
        pitch = TUBE_TILT + 0.06 * math.sin(t * 0.4)
        cyw, syw = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)
        bob = 0.4 * math.sin(t * 0.9)
        f, cx, cy = self.f, self.cx, self.cy
        pts = []
        for x, y, z in self.verts:
            x, z = x * cyw + z * syw, -x * syw + z * cyw          # turn round the upright
            y += bob
            y, z = y * cp - z * sp, y * sp + z * cp                # tip towards the camera
            d = TUBE_DIST + z
            pts.append((cx + f * x / d, cy - f * y / d, d))
        near, span = TUBE_DIST - self.reach, 2 * self.reach
        lines = []
        for i, j, col, wide in self.edges:
            (x0, y0, d0), (x1, y1, d1) = pts[i], pts[j]
            lines.append(((d0 + d1) / 2, (x0, y0), (x1, y1), col, wide))
        lines.sort(key=lambda l: -l[0])                           # far first: near lines on top
        scr = self.screen
        for d, p0, p1, col, wide in lines:
            k = 1.0 - (1.0 - DIM) * max(0.0, min(1.0, (d - near) / span))
            core = mix((0, 0, 0), col, k)
            pygame.draw.line(scr, mix((0, 0, 0), col, 0.5 * k), p0, p1, 3 + 2 * wide)  # a soft halo...
            pygame.draw.line(scr, core, p0, p1, 1 + wide)                     # ...a bright line...
            pygame.draw.aaline(scr, mix(core, (255, 255, 255), 0.35 * k), p0, p1)  # ...hot core
