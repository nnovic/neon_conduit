"""The title screen's backdrop: a close-up of a flag rippling in a slow wind, and in front
of it a short section of tunnel, the racer inside, turning slowly as glowing wireframes.

The flag fills the whole screen, its edges out of sight. Its cloth is woven from the
tunnels' checker pattern, in the first zone's blues: along the flag runs the tunnel's
length (one cell per track segment), across it the wall panels.
"""
import math

import pygame

from .config import CAM_H, FLOOR_Y, NEAR, PLAYER_D, SEG, SIDES
from .geometry import SIDE_A, SIDE_R
from .model import DEFAULT, MATERIALS, load_obj
from .render import SHIP_HOVER as GAME_HOVER, SHIP_LIGHT, SHIP_WINDING, SHIP_WINDING_N
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
TUBE_CENTRE = (0.5, 0.6)        # where its centre sits on screen, as fractions of the screen
TUBE_SPIN = 0.3                 # how fast it turns round the upright, radians per second
TUBE_TILT = 0.42                # how far the camera looks down on it, radians
SHIP_SCALE = 2.0                # the racer, a little larger than life so it reads from afar
SHIP_HOVER = 0.3
SHIP_AT = 0.2                   # where the racer sits along the section: 0 its entrance, 1 its far end
DRONE_AT = 0.85                 # ...and a drone, waiting further along
DRONE_SIZE = 2.0                # the drone's half-width (a flattened diamond, as in the race), title scale
DRONE_HOVER = 3.0               # its height over the floor
DRONE_SPIN = 1.2                # how fast it turns on itself, radians per second
DRONE_COL = (255, 120, 30)      # the race's drone orange
SHIP_OUTLINE = (255, 80, 160)   # neon round the racer's silhouette: seen from above its hull is dark
RING_COL = (255, 80, 160)       # the tube's ribs
RAIL_COL = (40, 210, 255)       # the lines running along it
DIM = 0.5                       # brightness of the farthest lines (1: the nearest)
# The drone's eight faces, as corners of its diamond: four round the middle, then top, bottom.
DRONE_FACES = [(k, (k + 1) % 4, 4) for k in range(4)] + [((k + 1) % 4, k, 5) for k in range(4)]


def _normal(p0, p1, p2):
    """Unit normal of the triangle p0 p1 p2 (by the right-hand rule)."""
    u = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    v = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    ln = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]) or 1.0
    return n[0] / ln, n[1] / ln, n[2] / ln


def _shade(col, lt):
    return (min(255, int(col[0] * lt)), min(255, int(col[1] * lt)), min(255, int(col[2] * lt)))


def ease(u):
    """0 to 1, starting and ending gently."""
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


class TitleTunnel:
    """A few segments of the tube, flat floor and all, as glowing lines turning round the
    upright, nearer lines brighter; inside, the racer on its floor and a drone ahead of
    it, solid and lit as in the race.

    When the race is launched it glides into the game's own view: the camera behind the
    racer, the section filling the first rings of the (straight) start of the track, and
    the racer at its true size, every line on the game's.
    """

    def __init__(self, screen, game_view):
        self.screen = screen
        w, h = screen.get_size()
        self.f = w * 0.62
        self.cx, self.cy = w * TUBE_CENTRE[0], h * TUBE_CENTRE[1]
        self.game_view = game_view          # the game's focal length and screen centre
        self.yaw0 = None                    # the turn it had when the launch began
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
        # Racer: on the floor. On the title, larger than life and centred along the section;
        # in the game's view, true to size and as far ahead of the camera as the game has it.
        ship = load_obj("ship.obj")
        zs = [p[2] for p in ship.verts]
        zmid = (min(zs) + max(zs)) / 2
        base = len(verts)
        at = -half + SHIP_AT * 2 * half
        self.ship_title = [(x * SHIP_SCALE, -FLOOR_Y + SHIP_HOVER + y * SHIP_SCALE, at + (z - zmid) * SHIP_SCALE)
                           for x, y, z in ship.verts]
        self.ship_game = [(x, -FLOOR_Y + GAME_HOVER + y, PLAYER_D + z - half) for x, y, z in ship.verts]
        self.ship = ship
        verts += self.ship_title
        # Drone: a flattened diamond spinning on itself. It isn't in the race's first
        # rings, so it fades away during the launch.
        s, top = DRONE_SIZE, DRONE_SIZE * 0.6
        self.drone = [(s, 0.0, 0.0), (0.0, 0.0, s), (-s, 0.0, 0.0), (0.0, 0.0, -s), (0.0, top, 0.0), (0.0, -top, 0.0)]
        self.drone_at = (-FLOOR_Y + DRONE_HOVER, -half + DRONE_AT * 2 * half)
        self.tube, self.edges = verts[:base], edges
        self.reach = max(math.sqrt(x * x + y * y + z * z) for x, y, z in verts)
        # In the game's view the camera sits CAM_H over the floor, the section's near end
        # at its feet: the section's centre is half its length ahead.
        self.game_shift = (FLOOR_Y - CAM_H, half)

    def depart(self, t):
        """The launch begins now, at title clock t."""
        self.yaw0 = TUBE_SPIN * t

    def draw(self, t, u=0.0):
        """Draw at title clock t, u of the way (0 to 1) from the title's view to the game's."""
        yaw = TUBE_SPIN * t if self.yaw0 is None else self.yaw0
        if u > 0.0:     # straighten up the shorter way round, to face down the track
            yaw += (round(yaw / (2 * math.pi)) * 2 * math.pi - yaw) * u
        pitch = (TUBE_TILT + 0.06 * math.sin(t * 0.4)) * (1 - u)
        bob = 0.4 * math.sin(t * 0.9) * (1 - u)
        gf, gcx, gcy = self.game_view
        f, cx, cy = self.f + (gf - self.f) * u, self.cx + (gcx - self.cx) * u, self.cy + (gcy - self.cy) * u
        ty, tz = self.game_shift[0] * u + bob, TUBE_DIST + (self.game_shift[1] - TUBE_DIST) * u
        cyw, syw = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)
        ship = [(a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u)
                for a, b in zip(self.ship_title, self.ship_game)]
        dy, dz = self.drone_at
        cd, sd = math.cos(DRONE_SPIN * t), math.sin(DRONE_SPIN * t)
        drone = [(x * cd + z * sd, y + dy, -x * sd + z * cd + dz) for x, y, z in self.drone]
        view = []
        for x, y, z in self.tube + ship + drone:
            x, z = x * cyw + z * syw, -x * syw + z * cyw          # turn round the upright
            y, z = y * cp - z * sp, y * sp + z * cp                # tip towards the camera
            view.append((x, y + ty, z + tz))

        def screen(p):
            return cx + f * p[0] / p[2], cy - f * p[1] / p[2]

        near, span = tz - self.reach, 2 * self.reach
        # Everything to paint, far first: the tube's lines one by one, the racer and the
        # drone each as a whole (their own faces sorted inside).
        items = []
        for i, j, col, wide in self.edges:
            (x0, y0, d0), (x1, y1, d1) = view[i], view[j]
            if d0 < NEAR and d1 < NEAR:
                continue
            if d0 < NEAR or d1 < NEAR:                            # cut off at the near plane, as the game does
                k = (NEAR - d0) / (d1 - d0)
                xn, yn = x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
                if d0 < NEAR:
                    x0, y0, d0 = xn, yn, NEAR
                else:
                    x1, y1, d1 = xn, yn, NEAR
            items.append(((d0 + d1) / 2, "line", ((x0, y0, d0), (x1, y1, d1), col, wide)))
        nt, ns = len(self.tube), len(ship)
        sview = view[nt:nt + ns]
        if min(p[2] for p in sview) > NEAR:
            items.append((sum(p[2] for p in sview) / ns, "ship", (ship, sview)))
        if u < 1.0:
            dview = view[nt + ns:]
            items.append((sum(p[2] for p in dview) / len(dview), "drone", (drone, dview, 1.0 - u)))
        items.sort(key=lambda it: -it[0])
        scr = self.screen
        for d, kind, data in items:
            if kind == "line":
                p0, p1, col, wide = data
                k = 1.0 - (1.0 - DIM) * max(0.0, min(1.0, (d - near) / span))
                core = mix((0, 0, 0), col, k)
                a, b = screen(p0), screen(p1)
                pygame.draw.line(scr, mix((0, 0, 0), col, 0.5 * k), a, b, 3 + 2 * wide)  # a soft halo...
                pygame.draw.line(scr, core, a, b, 1 + wide)                     # ...a bright line...
                pygame.draw.aaline(scr, mix(core, (255, 255, 255), 0.35 * k), a, b)  # ...hot core
            elif kind == "ship":
                self._draw_ship(*data, screen)
            else:
                self._draw_drone(*data, screen)

    def _draw_ship(self, world, view, screen):
        """The racer, faces turned towards us only, far ones first, lit as in the race;
        its glowing nozzles and neon edges on top."""
        scr = self.screen
        pts = [screen(p) for p in view]
        faces = []
        for idx, mat in self.ship.faces:
            s = [pts[i] for i in idx]
            area = sum(s[i - 1][0] * s[i][1] - s[i][0] * s[i - 1][1] for i in range(len(s)))
            if area * SHIP_WINDING <= 0:
                continue
            faces.append((mat == "glow", -sum(view[i][2] for i in idx) / len(idx), idx, mat, s))
        faces.sort(key=lambda fc: fc[:2])
        for _, _, idx, mat, s in faces:
            col, lit = MATERIALS.get(mat, DEFAULT)
            if lit:
                n = _normal(world[idx[0]], world[idx[1]], world[idx[2]])
                d = (n[0] * SHIP_LIGHT[0] + n[1] * SHIP_LIGHT[1] + n[2] * SHIP_LIGHT[2]) * SHIP_WINDING_N
                col = _shade(col, 0.38 + 0.62 * max(0.0, d))
            pygame.draw.polygon(scr, col, s)
            pygame.draw.polygon(scr, (col[0] // 2, col[1] // 2, col[2] // 2), s, 1)
        for idx, mat in self.ship.lines:
            pygame.draw.lines(scr, MATERIALS.get(mat, DEFAULT)[0], False, [pts[i] for i in idx], 2)
        # Outline: edges of the visible faces that no other visible face shares.
        count = {}
        for _, _, idx, mat, _ in faces:
            if mat != "glow":
                for i, j in zip(idx, idx[1:] + idx[:1]):
                    e = (min(i, j), max(i, j))
                    count[e] = count.get(e, 0) + 1
        for (i, j), c in count.items():
            if c == 1:
                pygame.draw.line(scr, SHIP_OUTLINE, pts[i], pts[j], 2)

    def _draw_drone(self, world, view, fade, screen):
        """The drone, its faces turned towards us lit from above, faded by fade (0 .. 1)."""
        scr = self.screen
        c = [sum(p[k] for p in view) / len(view) for k in range(3)]
        faces = []
        for idx in DRONE_FACES:
            p = [view[i] for i in idx]
            n = _normal(*p)
            m = [sum(q[k] for q in p) / 3 for k in range(3)]
            out = (m[0] - c[0]) * n[0] + (m[1] - c[1]) * n[1] + (m[2] - c[2]) * n[2]
            if out < 0:
                n = (-n[0], -n[1], -n[2])
            if n[0] * m[0] + n[1] * m[1] + n[2] * m[2] >= 0:       # turned away from us
                continue
            lt = 0.75 + 0.5 * max(0.0, n[1] * 0.8 - n[0] * 0.3 - n[2] * 0.5)
            faces.append((-m[2], [screen(q) for q in p], lt))
        faces.sort(key=lambda fc: fc[0])
        for _, s, lt in faces:
            col = mix((0, 0, 0), _shade(DRONE_COL, lt), fade)
            pygame.draw.polygon(scr, col, s)
            pygame.draw.polygon(scr, mix((0, 0, 0), (255, 220, 160), fade), s, 1)
