"""3D drawing of the world: tube, open and in-the-air sections, doors, objects, the sled
and its sparks.

Everything is projected by hand with a simple pinhole camera and painted back to
front, segment by segment, so nearer walls hide what lies behind them.
"""
import colorsys
import math
import random

import pygame

from . import config
from .config import (BOOST_HW, CAM_H, CAM_LAG, DOOR_OPEN_AT, DOOR_SLIDE, DRAW, FLOOR_A, FLOOR_Y,
                     FOCAL, GATE_SEGS, HORIZON, LINE_HW, NEAR, R, SEG, SIDES,
                     SKY_RISE_GAIN, SKY_RISE_MAX, SLED_HW, SPEED_CAP, STAR_R,
                     STAR_REACH, STAR_STRETCH, WALL_H, WALL_T)
from .geometry import (FLOOR_SIDES, OPEN_X, SIDE_A, SIDE_COS, SIDE_LIGHT, SIDE_MID, SIDE_R, SIDE_SIN,
                       TUBE_XS, WALL_COLUMN, bank, clip, wall_xy, wrap)
from . import decor
from .themes import THEMES
from .palette import DOOR_COL, DOOR_EDGE, FLOOR_COLS, FOG, GATE_GLOW, fogged, mix, tube_palette
from .patterns import BY_NAME
from .model import DEFAULT, MATERIALS, load_obj

SHIP = load_obj("ship.obj")
SHIP_HOVER = 0.15           # gap between the ship and the surface
SHIP_PIVOT = 0.5            # height the ship banks round
SHIP_WINDING = 1            # sign of a face's screen-space area when it faces the camera
SHIP_WINDING_N = 1          # sign that turns the model's face normals outward
_l = (-0.45, 0.8, -0.4)     # light: from above, a little left and behind
SHIP_LIGHT = tuple(c / math.sqrt(sum(c * c for c in _l)) for c in _l)
# The bulkhead round a door at the end of an outdoor run: a thick slab with the door set
# in it. (x, y) in the door's plane, y down, from the tube's centre;
# depths in units beyond the door (negative: towards the camera).
GATE_W = 1.7 * R            # slab half-width
GATE_TOP = -1.8 * R         # slab top...
GATE_CHAMFER = 0.5 * R      # ...with its upper corners cut off this much
GATE_BOTTOM = 1.8 * R       # the slab reaches this far down, below the road
GATE_DEPTH = 8.0           # slab thickness
GATE_SLAB = [(-GATE_W, GATE_BOTTOM), (-GATE_W, GATE_TOP + GATE_CHAMFER), (-GATE_W + GATE_CHAMFER, GATE_TOP),
             (GATE_W - GATE_CHAMFER, GATE_TOP), (GATE_W, GATE_TOP + GATE_CHAMFER), (GATE_W, GATE_BOTTOM)]
GATE_COLLAR = 1.2          # the door's collar, as a multiple of the tube's cross-section
GATE_METAL = (40, 44, 64)
GATE_HAZE = 0.7            # the haze dims it less than the track: it looms out of it
GATE_LIGHTS = 5             # warning lights over the door, flashing in turn while it slides


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _ray_hit(outer, d):
    """Where the ray from (0, 0) along d leaves the convex polygon outer round (0, 0)."""
    best = None
    for p, q in zip(outer, outer[1:] + outer[:1]):
        e = (q[0] - p[0], q[1] - p[1])
        den = _cross(d, e)
        if abs(den) < 1e-12:
            continue
        t, u = _cross(p, e) / den, _cross(p, d) / den
        if t > 0 and -1e-9 <= u <= 1 + 1e-9 and (best is None or t < best):
            best = t
    return (d[0] * best, d[1] * best)


def _inside(pt, poly):
    """True if point pt is inside polygon poly (even-odd rule)."""
    x, y, ins = pt[0], pt[1], False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            ins = not ins
    return ins


def ring_around(inner, outer):
    """The area between polygon inner and the convex polygon outer round it, as polygons
    pygame can fill: one per edge of inner, out along the rays from the centre (0, 0)
    through its ends to outer, taking in outer's corners in between."""
    polys = []
    for a, b in zip(inner, inner[1:] + inner[:1]):
        a0 = math.atan2(a[1], a[0])
        span = wrap(math.atan2(b[1], b[0]) - a0)
        turn = [(wrap(math.atan2(c[1], c[0]) - a0) * math.copysign(1, span), c) for c in outer]
        corners = [c for t, c in sorted(turn, key=lambda tc: -tc[0]) if 0 < t < abs(span)]
        polys.append([a, b, _ray_hit(outer, b)] + corners + [_ray_hit(outer, a)])
    return polys


GATE_FACE = ring_around(TUBE_XS, GATE_SLAB)                     # the slab's face, mouth cut out
GATE_COLLAR_RING = ring_around(TUBE_XS, [(x * GATE_COLLAR, y * GATE_COLLAR) for x, y in TUBE_XS])
FLAME_BASE = 0.4            # exhaust flame length when standing still
FLAME_STRETCH = 3.0         # ...plus this much at top cruising speed
FLAME_BOOST = 2.2           # ...and the stretch is this much longer while boosting
FLAME_CLEAR = 4.5           # flame tips never come closer to the camera than this
# Flame layers, drawn outermost first: (length, width, how far towards white).
FLAME_LAYERS = ((1.15, 1.9, 0.0), (1.0, 1.0, 0.35), (0.55, 0.45, 0.85))
# While invincible the hull shimmers: each face tinted along the rainbow, the hues rippling.
SHIMMER_SPEED = 1.5         # turns of the rainbow per second
SHIMMER_SPREAD = 0.27       # hue step from one face to the next
SHIMMER_TINT = 0.6          # how far each face's colour goes towards its hue
SHIMMER_ALPHA = 100         # hull opacity (0 .. 255)...
SHIMMER_PULSE = 30          # ...give or take this much, pulsing
SHIMMER_OUTLINE = 4         # width of the ship's outline, in pixels


def rainbow(hue):
    """Bright colour at hue (0 .. 1, wrapping round)."""
    return tuple(int(255 * c) for c in colorsys.hsv_to_rgb(hue % 1.0, 0.65, 1.0))


def star_fan(radius):
    """A five-pointed star pointing ahead, stretched along the track, as a fan of triangles
    in surface coordinates (along the track, sideways along the wall) around its centre."""
    pts = []
    for j in range(10):
        ang = j * math.pi / 5
        rr = radius if j % 2 == 0 else radius * 0.42
        pts.append((STAR_STRETCH * rr * math.cos(ang), rr * math.sin(ang)))
    return [((0.0, 0.0), pts[j], pts[(j + 1) % 10]) for j in range(10)]


FLOOR_EDGES = set(FLOOR_SIDES) | {s + 1 for s in FLOOR_SIDES}    # vertices on the floor

STAR_GLOW = star_fan(STAR_R * 1.4)
STAR_CORE = star_fan(STAR_R)


class Renderer:
    def __init__(self, screen, focal=FOCAL, horizon=HORIZON):
        self.screen = screen
        self.w, self.h = screen.get_size()
        self.cx, self.cy = self.w // 2, int(self.h * horizon)
        self.focal = focal
        star_rng = random.Random(7)
        self.stars = [(star_rng.uniform(-900, 900), star_rng.uniform(-900, 900),
                       star_rng.randint(90, 230)) for _ in range(220)]
        self.panoramas = decor.panoramas(THEMES, focal / FOCAL)

    def draw(self, game):
        """Draw the world as seen from behind game's sled (no HUD)."""
        self.game = game
        scr = self.screen
        tr = game.track
        base = int(game.cam_z // SEG)
        frac = game.cam_z / SEG - base
        tr.ensure(base + DRAW + 2, game.level)
        self._camera(game)
        theme, self.fog_col = self._outdoors(tr, base)
        # The track dipping or climbing tilts the view: the horizon rises or sinks.
        k = self.focal / FOCAL
        self.rise = -SKY_RISE_MAX * k * math.tanh(game.dive * SKY_RISE_GAIN / SKY_RISE_MAX)
        if theme:
            decor.draw(self, theme, game.heading, self.rise)
        else:
            scr.fill(FOG)
            self._stars(game)

        self.base = base
        self._centre_line(tr, base, frac)
        rings, orings, frames = self._rings(tr, base, frac)

        # Bucket objects per segment so nearer walls correctly hide them.
        buckets = {}
        far_z = (base + DRAW) * SEG
        for o in tr.objects:
            if o["z"] < far_z:
                si = int(o["z"] // SEG)
                if o.get("kind") == "boost":
                    si = max(base, si)          # a pad half behind the camera: draw what is left
                buckets.setdefault(si, []).append(o)
        for b in game.bullets:
            buckets.setdefault(int(b["z"] // SEG), []).append(b)
        for e in game.effects:
            if "follow" not in e:                   # bursts riding on the sled are drawn with it
                buckets.setdefault(int(e["z"] // SEG), []).append(e)

        # Past the door at the end of an outdoor run, the tube is only seen from inside,
        # through the door's mouth: it is painted on a layer, cut to the mouth.
        gate = next((i for i in range(DRAW) if (i - frac) * SEG > NEAR and tr.is_door(base + i)
                     and base + i > 0 and tr.outdoor(base + i - 1)), None)
        inside = self._inside_begin(frames[gate]) if gate is not None else None

        for i in range(DRAW - 1, -1, -1):
            si = base + i
            if gate is not None and i > gate and inside is False:
                continue                                    # the mouth is off-screen
            if (i + 1 - frac) * SEG > NEAR:
                fog = min(1.0, (max(0.0, i - frac) / DRAW) ** 1.3 * 1.15)
                if tr.open[si]:
                    self._open_segment(tr, si, orings[i], orings[i + 1], fog)
                elif tr.air[si]:
                    self._air_segment(tr, si, rings[i], rings[i + 1], fog)
                else:
                    self._tube_segment(tr, si, rings[i], rings[i + 1], fog)
                if config.DEVELOPER_MODE and tr.bend(si) > 0.25:
                    self._fast_line(tr, si, fog)
                self._hint_stars(tr, si)
            for o in buckets.get(si, ()):
                self._object(o)
            if i == gate and inside:
                self._inside_end(inside)
            if tr.is_door(si) and (i - frac) * SEG > NEAR:
                if si > 0 and tr.outdoor(si - 1):
                    self._bulkhead(frames, i, si, max(0.0, i - frac) / DRAW)
                self._door(frames[i], si, max(0.0, i - frac) / DRAW)

        self._sled(game)
        if config.DEVELOPER_MODE:
            self._reticle(game)
        self._sparks(game)
        if game.flash > 0:
            veil = pygame.Surface((self.w, self.h))
            veil.fill((255, 60, 40))
            veil.set_alpha(int(400 * game.flash))
            scr.blit(veil, (0, 0))

    # ------------------------------------------------------------- camera
    def _camera(self, game):
        """Camera position in the cross-section, its roll, and the screen centre."""
        # Camera sits above the surface part of the way round to the sled, rolled to
        # match that spot: level on the floor, banked on the walls. Lagging behind the
        # sled like this lets it swing out towards the sides of the screen. The lag
        # fades out towards the ceiling, so looping right round the tube stays smooth.
        w = wrap(game.roll)
        cam_a = w - CAM_LAG * math.sin(w)
        tilt = cam_a * bank(cam_a) * (1.0 - game.flat)
        self.cr, self.sr = math.cos(tilt), math.sin(tilt)
        self.camx, self.camy = wall_xy(cam_a, 0.0, CAM_H, rigid=True, flat=game.flat)
        ox_s = oy_s = 0
        if game.shake > 0:
            ox_s = random.uniform(-1, 1) * 22 * game.shake
            oy_s = random.uniform(-1, 1) * 22 * game.shake
        self.pcx, self.pcy = self.cx + ox_s, self.cy + oy_s
        self.f = self.focal * (0.88 if game.boost > 0 else 1.0)

    def _outdoors(self, tr, base):
        """The backdrop to show, and the colour of the fog.

        An outdoor run's backdrop shows while the run is in view; its haze takes over the fog
        gradually as the run comes closer, and gives way again after it's left behind.
        """
        fade_in, fade_out = 30, 12                  # segments
        ahead = next((i for i in range(DRAW) if tr.outdoor(base + i)), None)
        behind = next((j for j in range(1, fade_out + 1) if base >= j and tr.outdoor(base - j)), None)
        theme, haze, amount = None, FOG, 0.0
        if ahead is not None:
            theme = self.panoramas[tr.outdoor_theme(base + ahead)]
            haze, amount = theme.fog, max(0.0, 1.0 - ahead / fade_in)
        if behind is not None and 1.0 - behind / fade_out > amount:
            haze, amount = self.panoramas[tr.outdoor_theme(base - behind)].fog, 1.0 - behind / fade_out
        return theme, mix(FOG, haze, amount)

    def _stars(self, game):
        """Stars at the far end of the tube, when no outdoor backdrop is in view."""
        cr, sr, pcx, pcy = self.cr, self.sr, self.pcx, self.pcy
        hs = game.heading * 140.0
        for x, y, b in self.stars:
            y += self.rise
            x = (x - hs + 900) % 1800 - 900
            sx = pcx + x * cr - y * sr
            sy = pcy + x * sr + y * cr
            if 0 <= sx < self.w and 0 <= sy < self.h:
                self.screen.set_at((int(sx), int(sy)), (b, b, b))

    def _centre_line(self, tr, base, frac):
        """Tube centre line at each drawn ring, relative to the camera and tangent-aligned."""
        rcx, rcy = [0.0] * (DRAW + 1), [0.0] * (DRAW + 1)
        x = y = dx = dy = 0.0
        sx0, sy0 = frac * tr.curv[base], frac * tr.pitch[base]
        for i in range(DRAW + 1):
            rcx[i] = x - sx0 * (i - frac)
            rcy[i] = y - sy0 * (i - frac)
            x += dx
            y += dy
            if i > 0:
                dx += tr.curv[base + i - 1]
                dy += tr.pitch[base + i - 1]
        self.rcx, self.rcy = rcx, rcy

    def _centre(self, z):
        f = z / SEG - self.base
        i = max(0, min(DRAW - 1, int(f)))
        t = f - i
        rcx, rcy = self.rcx, self.rcy
        return rcx[i] + (rcx[i + 1] - rcx[i]) * t, rcy[i] + (rcy[i + 1] - rcy[i]) * t

    def proj(self, z, a, lat=0.0, h=0.0, rigid=False, flat=None):
        """Screen point (x, y, scale) at depth z, or None behind the camera; see wall_xy
        for a / lat / h / rigid / flat."""
        game = self.game
        if z - game.cam_z < NEAR:
            return None
        if flat is None:
            flat = 1.0 if game.track.open[int(z // SEG)] else 0.0
        return self.proj_xy(z, *wall_xy(a, lat, h, rigid, flat))

    def proj_xy(self, z, wx, wy):
        """Screen point (x, y, scale) of cross-section point (wx, wy) at depth z, or None."""
        d = z - self.game.cam_z
        if d < NEAR:
            return None
        ccx, ccy = self._centre(z)
        px = ccx + wx - self.camx
        py = ccy + wy - self.camy
        k = self.f / d
        cr, sr = self.cr, self.sr
        return self.pcx + k * (px * cr - py * sr), self.pcy + k * (px * sr + py * cr), k

    def _rings(self, tr, base, frac):
        """Screen outline of every drawn ring: as tube, as open section, and its frame."""
        cr, sr, pcx, pcy = self.cr, self.sr, self.pcx, self.pcy
        rings, orings, frames = [], [], []
        for i in range(DRAW + 1):
            d = max(NEAR, (i - frac) * SEG)
            k = self.f / d
            ox, oy = self.rcx[i] - self.camx, self.rcy[i] - self.camy
            frames.append((ox, oy, k))
            pts = []
            for s in range(SIDES + 1):
                px = ox + SIDE_R[s] * SIDE_SIN[s]
                py = oy + SIDE_R[s] * SIDE_COS[s]
                pts.append((pcx + k * (px * cr - py * sr), pcy + k * (px * sr + py * cr)))
            rings.append(pts)
            # Open-section outline at this ring: floor vertices, then the two kerb tops
            # (inner edges, then outer edges).
            hw = tr.width[base + i]
            py = oy + FLOOR_Y
            opts = [(pcx + k * ((ox + f * hw) * cr - py * sr), pcy + k * ((ox + f * hw) * sr + py * cr))
                    for f in OPEN_X]
            py -= WALL_H
            for f in (-1.0, 1.0, -1.0, 1.0):
                px = ox + f * (hw if len(opts) < len(OPEN_X) + 2 else hw + WALL_T)
                opts.append((pcx + k * (px * cr - py * sr), pcy + k * (px * sr + py * cr)))
            orings.append(opts)
        return rings, orings, frames

    # ----------------------------------------------------------- segments
    def _tube_segment(self, tr, si, r0, r1, fog):
        band = si // 2
        gate_glow = si % GATE_SEGS in (0, GATE_SEGS - 1)
        # One colour scheme and pattern per stretch of tube: they only change out in the open.
        pattern = BY_NAME[tr.tube_style(si)]
        pal = tube_palette(tr.stretch[si], pattern.contrast)
        for s in range(SIDES):
            if gate_glow:
                c = GATE_GLOW
            elif abs(SIDE_MID[s]) < FLOOR_A:
                c = FLOOR_COLS[band & 1]
            else:
                c = mix(pal[0], pal[1], pattern.shade(si, WALL_COLUMN[s], self.game.t))
            pygame.draw.polygon(self.screen, fogged(c, SIDE_LIGHT[s], fog, self.fog_col),
                                (r0[s], r0[s + 1], r1[s + 1], r1[s]))

    def _open_segment(self, tr, si, r0, r1, fog):
        band = si // 2
        gate_glow = si % GATE_SEGS in (0, GATE_SEGS - 1)
        off = FLOOR_SIDES[0]
        for s in FLOOR_SIDES:
            c = GATE_GLOW if gate_glow else FLOOR_COLS[band & 1]
            pygame.draw.polygon(self.screen, fogged(c, SIDE_LIGHT[s], fog, self.fog_col),
                                (r0[s - off], r0[s - off + 1], r1[s - off + 1], r1[s - off]))
        # Upright kerbs at the floor edges: too steep to ride up. Inner face, then top.
        c = GATE_GLOW if gate_glow else tr.kerb_col(si, band)
        nf = len(OPEN_X)
        for c, lt, quads in ((c, 0.72, ((0, nf), (nf - 1, nf + 1))),
                             (mix(c, (255, 250, 225), 0.35), 1.0, ((nf, nf + 2), (nf + 1, nf + 3)))):
            col = fogged(c, lt, fog, self.fog_col)
            for v, t in quads:
                pygame.draw.polygon(self.screen, col, (r0[v], r0[t], r1[t], r1[v]))

    def _air_segment(self, tr, si, r0, r1, fog):
        """A see-through stretch of tube, up in the air: only its edges, as glowing lines,
        so the backdrop shows through. Lines along every edge, a ring every other segment;
        the floor's edges are brighter, to read which way is down."""
        if fog >= 1.0:
            return
        scr = self.screen
        pal = tube_palette(tr.stretch[si])
        wall = mix(pal[1], (255, 255, 255), 0.3)
        floor = mix(pal[1], (255, 255, 255), 0.75)
        near = (1.0 - fog) ** 2
        wide = 1 + int(2.5 * near)                  # thicker close up
        halo = wide + 2
        fc = self.fog_col
        gate = si % GATE_SEGS in (0, GATE_SEGS - 1)
        edges = [(r0[s], r1[s], floor if s in FLOOR_EDGES else wall) for s in range(SIDES)]
        if gate or si % 2 == 0:
            ring = GATE_GLOW if gate else wall
            edges += [(r0[s], r0[s + 1], ring) for s in range(SIDES)]
        for p0, p1, c in edges:
            core = fogged(c, 1.0, fog, fc)
            pygame.draw.line(scr, mix(fc, core, 0.4), p0, p1, halo)       # a soft glow...
            pygame.draw.line(scr, core, p0, p1, wide)                     # ...and the line

    def _fast_line(self, tr, si, fog):
        """The fast line (developer mode): cyan while the sled is on it, amber when it has strayed."""
        c = (255, 170, 40) if self.game.off_line > 0.05 else (80, 230, 255)
        col = fogged(c, 0.75 + 0.25 * ((si // 2) & 1), fog, self.fog_col)
        fl = 1.0 if tr.open[si] else 0.0
        z0, a0, a1 = si * SEG, tr.line(si), tr.line(si + 1)
        proj = self.proj
        q = (proj(z0, a0, -LINE_HW, 0.06, False, fl), proj(z0, a0, LINE_HW, 0.06, False, fl),
             proj(z0 + SEG, a1, LINE_HW, 0.06, False, fl), proj(z0 + SEG, a1, -LINE_HW, 0.06, False, fl))
        if all(q):
            pygame.draw.polygon(self.screen, col, [p[:2] for p in q])

    # ------------------------------------------------------------ objects
    def _object(self, o):
        scr, proj = self.screen, self.proj
        kind = o.get("kind")
        z = o["z"]
        if kind == "boost":
            a, hw = o["a"], BOOST_HW
            z0 = max(z, self.game.cam_z + NEAR + 0.05)          # cut off where it passes the camera
            if z0 >= z + 10:
                return
            q = [proj(z0, a, -hw, 0.15), proj(z0, a, hw, 0.15),
                 proj(z + 10, a, hw, 0.15), proj(z + 10, a, -hw, 0.15)]
            if all(q):
                pulse = 0.6 + 0.4 * math.sin(self.game.t * 12)
                pygame.draw.polygon(scr, (int(60 * pulse), int(255 * pulse), int(120 * pulse)),
                                    [p[:2] for p in q])
                tip, l, r_ = proj(z + 8, a, 0, 0.2), proj(z + 3, a, -1.3, 0.2), proj(z + 3, a, 1.3, 0.2)
                if tip and l and r_:
                    pygame.draw.polygon(scr, (10, 60, 30), (tip[:2], l[:2], r_[:2]))
        elif kind == "drone":
            p = proj(z, o["a"], 0.0, 1.5, True)
            if p:
                s = max(2, p[2] * 1.0)
                x, y = p[0], p[1]
                pygame.draw.polygon(scr, (255, 120, 30),
                                    ((x - s, y), (x, y - s * 0.6), (x + s, y), (x, y + s * 0.6)))
                pygame.draw.circle(scr, (255, 240, 200), (x, y), max(1, s * 0.3))
        elif kind == "gate":
            tr = self.game.track
            if tr.open[int(z // SEG)]:
                # No tube to ring: a goalpost arch from kerb to kerb.
                hw = tr.hw_at(z)
                pts = [proj(z, 0.0, x, h) for x, h in ((-hw, 0.0), (-hw, 9.0), (hw, 9.0), (hw, 0.0))]
            else:
                pts = [proj(z, a, 0.0, 0.3) for a in SIDE_A]
            if all(pts):
                pygame.draw.lines(scr, (255, 255, 160), False, [p[:2] for p in pts],
                                  max(2, int(pts[0][2] * 0.5)))
        elif "age" in o:                                      # explosion (or exhaust burst)
            p = proj(z, o["a"], 0.0, o.get("h", 1.5), True)
            if p:
                t = o["age"] / o.get("life", 0.45)
                c0, c1 = o.get("cols", ((255, 255, 200), (255, 60, 0)))
                k = p[2] * o.get("size", 1.0)
                pygame.draw.circle(scr, mix(c0, c1, t), p[:2],
                                   max(2, k * (0.6 + 3.5 * t)), max(1, int(k * 0.5 * (1 - t)) + 1))
        else:                                                 # bullet
            x, y, k = o["x"], o["y"], 11 / SEG                # trail runs along the bullet's own path
            p0, p1 = self.proj_xy(z, x, y), self.proj_xy(z + 11, x + o["vx"] * k, y + o["vy"] * k)
            if p0 and p1:
                w = max(4, int(p0[2] * 0.26))
                pygame.draw.line(scr, (255, 220, 60), p0[:2], p1[:2], w)
                pygame.draw.line(scr, (255, 255, 210), p0[:2], p1[:2], max(2, w // 2))

    def _hint_stars(self, tr, si):
        """The parts of hint stars that lie on segment si, painted on its surface.

        Stars are longer than a segment, so each is sliced at segment boundaries and
        every slice is drawn in its own segment's turn: nearer surfaces then hide
        exactly what they should, no more.
        """
        lo, hi = si * SEG, (si + 1) * SEG
        for k in range(int((lo - STAR_REACH) // SEG), int((hi + STAR_REACH) // SEG) + 1):
            if k < 0 or not tr.has_star(k):
                continue
            zk, a = k * SEG, tr.line(k)
            fl = 1.0 if tr.open[k] else 0.0
            tw = 0.5 + 0.5 * math.sin(self.game.t * 8 + k)               # twinkle, 0 .. 1
            for fan, h, col in ((STAR_GLOW, 0.04, mix((110, 80, 15), (170, 125, 25), tw)),
                                (STAR_CORE, 0.08, mix((240, 200, 60), (255, 245, 170), tw))):
                for tri in fan:
                    # A little past the far boundary, over the seam the surface leaves there.
                    piece = clip(clip(tri, lo - zk, False), hi + 0.4 - zk, True)
                    if len(piece) < 3:
                        continue
                    pts = [self.proj(zk + u, a, v, h, False, fl) for u, v in piece]
                    if all(pts):
                        pygame.draw.polygon(self.screen, col, [p[:2] for p in pts])

    def _inside_begin(self, frame):
        """Start painting on the layer for the inside of the tube beyond a door at frame:
        the box round the door's mouth on screen, or False if the mouth is off-screen."""
        ox, oy, k = frame
        cr, sr, pcx, pcy = self.cr, self.sr, self.pcx, self.pcy
        mouth = [(pcx + k * ((ox + x) * cr - (oy + y) * sr), pcy + k * ((ox + x) * sr + (oy + y) * cr))
                 for x, y in TUBE_XS]
        xs, ys = [p[0] for p in mouth], [p[1] for p in mouth]
        box = pygame.Rect(int(min(xs)) - 1, int(min(ys)) - 1, int(max(xs) - min(xs)) + 3,
                          int(max(ys) - min(ys)) + 3).clip(self.screen.get_rect())
        if not box.w or not box.h:
            return False
        if getattr(self, "_inside", None) is None or self._inside.get_size() != self.screen.get_size():
            self._inside = pygame.Surface(self.screen.get_size())
            self._inside.set_colorkey((0, 0, 0))
            self._inside_mask = pygame.Surface(self.screen.get_size())
        layer = self._inside
        layer.set_clip(box)
        layer.fill(FOG)
        self._real_screen, self.screen = self.screen, layer
        return box, mouth

    def _inside_end(self, inside):
        """Cut the inside of the tube to the door's mouth and lay it on the screen."""
        box, mouth = inside
        layer, mask = self.screen, self._inside_mask
        self.screen = self._real_screen
        mask.set_clip(box)
        mask.fill((0, 0, 0))
        pygame.draw.polygon(mask, (255, 255, 255), mouth)
        layer.blit(mask, box, box, special_flags=pygame.BLEND_MULT)   # black outside the mouth...
        self.screen.blit(layer, box, box)                             # ...which is see-through
        layer.set_clip(None)

    def _bulkhead(self, frames, i, si, depth):
        """The structure round a door at the end of an outdoor run: a slab with the tube's
        mouth cut through it, neon trim in the colours of the tube beyond, and warning
        lights that flash in turn while the door slides."""
        scr, f = self.screen, self.f
        cr, sr, pcx, pcy = self.cr, self.sr, self.pcx, self.pcy
        ox, oy, k = frames[i]
        d = f / k
        # Built straight along the track's heading at the door, whatever it does beyond.
        j0, j1 = (i, i + 1) if i + 1 < len(frames) else (i - 1, i)
        dox, doy = (frames[j1][0] - frames[j0][0]) / SEG, (frames[j1][1] - frames[j0][1]) / SEG
        fog = GATE_HAZE * min(1.0, depth ** 1.3 * 1.15)
        fc = self.fog_col
        if depth >= 1.0:
            return

        def at(pts, n):
            kk = f / (d + n)
            cx, cy = ox + dox * n, oy + doy * n
            return [(pcx + kk * ((cx + x) * cr - (cy + y) * sr), pcy + kk * ((cx + x) * sr + (cy + y) * cr))
                    for x, y in pts]

        # Close up the mouth fills the screen and all of this is out of sight.
        mouth = at(TUBE_XS, 0.0)
        if all(_inside(c, mouth) for c in ((0, 0), (self.w, 0), (0, self.h), (self.w, self.h))):
            return

        def fill(col, pts):
            """Fill a polygon, cut to the screen first: close up the bulkhead's are huge."""
            for c, below, axis in ((-2, False, 0), (self.w + 2, True, 0), (-2, False, 1), (self.h + 2, True, 1)):
                pts = clip(pts, c, below, axis)
                if len(pts) < 3:
                    return
            pygame.draw.polygon(scr, col, pts)

        def area(poly):
            return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]))

        def sides(outline, n0, n1, col):
            """The sides of outline pushed from depth n0 back to n1 (only those facing the camera)."""
            front, back = at(outline, n0), at(outline, n1)
            facing = area(front)
            m = len(outline)
            for a in range(m):
                b = (a + 1) % m
                quad = [front[a], front[b], back[b], back[a]]
                if area(quad) * facing >= 0:
                    continue
                (x0, y0), (x1, y1) = outline[a], outline[b]
                ln = math.hypot(x1 - x0, y1 - y0) or 1.0
                up = max(0.0, (x1 - x0) / ln)           # outward normal pointing up: lit from above
                fill(fogged(col, 0.55 + 0.6 * up, fog, fc), quad)
            return front

        pal = tube_palette(self.game.track.stretch[si])
        neon = mix(pal[1], (255, 255, 255), 0.35)

        def glow_line(surf, pts, width, closed=False):
            """A neon tube: a wide soft halo, then a bright core."""
            core = fogged(neon, 1.0, fog * 0.6, fc)
            draw = (lambda c, w: pygame.draw.lines(surf, c, True, pts, w)) if closed else \
                   (lambda c, w: pygame.draw.line(surf, c, pts[0], pts[1], w))
            draw(mix(fogged(GATE_METAL, 1.0, fog, fc), core, 0.45), max(3, int(width * 2.6)))
            draw(core, max(1, int(width)))

        dist = si * SEG - self.game.sled_z
        sliding = 0.0 < DOOR_OPEN_AT - dist < DOOR_SLIDE
        wide = k * 0.45
        sides(GATE_SLAB, 0.0, GATE_DEPTH, GATE_METAL)
        col = fogged(GATE_METAL, 1.0, fog, fc)
        for piece in GATE_FACE:
            fill(col, at(piece, 0.0))
        # A neon bar under the lintel.
        bar = at([(-GATE_W + GATE_CHAMFER, GATE_TOP + 0.2 * R), (GATE_W - GATE_CHAMFER, GATE_TOP + 0.2 * R)], 0.0)
        glow_line(scr, bar, k * 0.6)
        # Warning lights over the door: dim at rest, a chase of flashes while it slides.
        for n in range(GATE_LIGHTS):
            x = (n - (GATE_LIGHTS - 1) / 2) * 0.45 * R
            lit = sliding and (int(self.game.t * 14) - n) % 3 == 0
            c = (255, 210, 70) if lit else (120, 80, 20)
            p = at([(x, -1.38 * R)], 0.0)[0]
            pygame.draw.circle(scr, fogged(c, 1.0, fog * (0.5 if lit else 1.0), fc), p, max(1, int(k * 0.6)))
        # The collar round the door, with neon on its outer edge.
        col = fogged(GATE_METAL, 1.7, fog, fc)
        for piece in GATE_COLLAR_RING:
            fill(col, at(piece, 0.0))
        glow_line(scr, at([(x * GATE_COLLAR, y * GATE_COLLAR) for x, y in TUBE_XS], 0.0), wide, closed=True)

    def _door(self, frame, i, depth):
        """Sliding door across the mouth of segment i; it parts as the sled draws near.

        The panels are laid out in the door's own frame, tilted by its random angle:
        they split along that frame's vertical and slide apart along its horizontal.
        """
        ox, oy, k = frame
        cr, sr, pcx, pcy = self.cr, self.sr, self.pcx, self.pcy
        phi = self.game.track.door_angle(i)
        dc, ds = math.cos(phi), math.sin(phi)

        def to_screen(pts):
            out = []
            for u, v in pts:
                x, y = ox + u * dc - v * ds, oy + u * ds + v * dc
                out.append((pcx + k * (x * cr - y * sr), pcy + k * (x * sr + y * cr)))
            return out

        shape = [(x * dc + y * ds, -x * ds + y * dc) for x, y in TUBE_XS]   # tube in the door's frame
        fog = 0.6 * min(1.0, depth ** 1.3 * 1.15)   # lit doorway: shows through the haze

        def door_fog(c, lt=1.0):
            fc = self.fog_col
            return (int(c[0] * lt * (1 - fog) + fc[0] * fog),
                    int(c[1] * lt * (1 - fog) + fc[1] * fog),
                    int(c[2] * lt * (1 - fog) + fc[2] * fog))

        dist = i * SEG - self.game.sled_z
        u = max(0.0, min(1.0, (DOOR_OPEN_AT - dist) / DOOR_SLIDE))
        u = u * u * (3 - 2 * u)
        gap = u * R * 1.05          # each panel has slid this far into the wall
        strip = 0.9                 # width of the warning strip along each leading edge
        for side in (-1.0, 1.0):
            left = side < 0
            edge = side * gap
            body = clip(shape, edge, left)
            if len(body) < 3:
                continue
            pygame.draw.polygon(self.screen, door_fog(DOOR_COL), to_screen(body))
            # Lighter ribs across the panel, then a warning strip on its leading edge.
            inner = clip(body, edge + side * strip, left)
            for y in (-5.0, -1.5, 2.0, 5.5):
                rib = clip(clip(inner, y - 0.3, False, 1), y + 0.3, True, 1)
                if len(rib) >= 3:
                    pygame.draw.polygon(self.screen, door_fog(DOOR_COL, 1.6), to_screen(rib))
            lip = clip(body, edge + side * strip, not left)
            if len(lip) >= 3:
                pygame.draw.polygon(self.screen, door_fog(DOOR_EDGE), to_screen(lip))
        # Glowing frame around the tube mouth.
        pygame.draw.lines(self.screen, door_fog((255, 80, 160)), True, to_screen(shape), max(1, int(k * 0.35)))

    def _sled(self, game):
        """The racer: the ship model, banked into the steering and hovering a little,
        projected vertex by vertex and painted far faces first."""
        scr, proj = self.screen, self.proj
        pz, a, fl = game.sled_z, game.theta, game.flat
        roll = -0.35 * game.steer
        cr, sr = math.cos(roll), math.sin(roll)
        lift = SHIP_HOVER + 0.05 * math.sin(game.t * 7.0)
        pts, scr_pts = [], []
        for x, y, z in SHIP.verts:
            y -= SHIP_PIVOT                                       # bank round a point mid-height
            x, y = x * cr - y * sr, x * sr + y * cr
            y += SHIP_PIVOT + lift
            p = proj(pz + z, a, x, y, True, fl)
            if not p:
                return
            pts.append((x, y, z))
            scr_pts.append(p)

        hot = game.boost > 0
        flame = (60, 255, 140) if hot else (60, 150, 255)
        # Exhaust flames first, one per nozzle: they trail behind the ship, so it covers them.
        # They stretch with speed, much further on boost, and flicker: a wide outer glow,
        # the flame, and a white-hot core.
        s = game.speed / SPEED_CAP
        length = FLAME_BASE + FLAME_STRETCH * s * (FLAME_BOOST if hot else 1.0)
        length *= 1.0 + (0.35 if hot else 0.2) * random.random()
        nearest = game.cam_z + FLAME_CLEAR                       # tails stop short of the camera
        for idx, mat in SHIP.faces:
            if mat != "glow":
                continue
            cx, cy, cz = (sum(pts[i][c] for i in idx) / len(idx) for c in range(3))
            corners = [scr_pts[i][:2] for i in idx]
            mx = sum(p[0] for p in corners) / len(corners)
            my = sum(p[1] for p in corners) / len(corners)
            for f_len, f_wide, f_white in FLAME_LAYERS:
                tail = proj(max(nearest, pz + cz - length * f_len), a, cx, cy, True, fl)
                if not tail:
                    continue
                base = [(mx + (x - mx) * f_wide, my + (y - my) * f_wide) for x, y in corners]
                col = mix(flame, (255, 255, 255), f_white)
                for i in range(len(base)):
                    pygame.draw.polygon(scr, col, (base[i], base[i - 1], tail[:2]))

        for e in game.effects:                                   # exhaust bursts, behind the hull
            if "follow" in e:
                self._object(e)

        faces = []
        for idx, mat in SHIP.faces:
            s = [scr_pts[i] for i in idx]
            # Facing the camera? Screen-space winding tells, perspective included.
            area = sum(s[i - 1][0] * s[i][1] - s[i][0] * s[i - 1][1] for i in range(len(s)))
            if area * SHIP_WINDING <= 0:
                continue
            # Glowing nozzles are decals on the hull: paint them last. Otherwise far first
            # (a small projection scale means far away).
            faces.append((mat == "glow", sum(p[2] for p in s) / len(s), idx, mat, s))
        faces.sort(key=lambda f: f[:2])
        # Invincible: the hull shimmers, a rainbow rippling across its faces, and turns a
        # little see-through. It is painted on a layer of its own, then laid over the scene.
        shield = game.invincible > 0
        hull = scr
        if shield:
            xs = [p[0] for p in scr_pts]
            ys = [p[1] for p in scr_pts]
            x0, y0 = int(min(xs)) - 2, int(min(ys)) - 2
            hull = pygame.Surface((int(max(xs)) - x0 + 4, int(max(ys)) - y0 + 4), pygame.SRCALPHA)
        for k, (_, _, idx, mat, s) in enumerate(faces):
            col, lit = MATERIALS.get(mat, DEFAULT)
            if mat == "glow":
                col = flame
            if lit:
                p0, p1, p2 = pts[idx[0]], pts[idx[1]], pts[idx[2]]
                u = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
                v = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
                n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
                ln = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]) or 1.0
                d = (n[0] * SHIP_LIGHT[0] + n[1] * SHIP_LIGHT[1] + n[2] * SHIP_LIGHT[2]) / ln
                shade = 0.38 + 0.62 * max(0.0, d * SHIP_WINDING_N)
                col = (int(col[0] * shade), int(col[1] * shade), int(col[2] * shade))
            poly = [p[:2] for p in s]
            if shield:
                hue = (game.t * SHIMMER_SPEED + k * SHIMMER_SPREAD) % 1.0
                col = mix(col, rainbow(hue), SHIMMER_TINT)
                poly = [(x - x0, y - y0) for x, y in poly]
            pygame.draw.polygon(hull, col, poly)
            pygame.draw.polygon(hull, (col[0] // 2, col[1] // 2, col[2] // 2), poly, 1)
        if shield:
            hull.set_alpha(int(SHIMMER_ALPHA + SHIMMER_PULSE * math.sin(game.t * 9)))
            scr.blit(hull, (x0, y0))
            neon = rainbow(game.t * SHIMMER_SPEED)              # edges cycle too, drawn bolder
            # The outline: edges of the faces turned towards us that no other such face
            # shares (the silhouette), opaque and bold, so the see-through ship still reads.
            count = {}
            for _, _, idx, mat, _ in faces:
                if mat != "glow":
                    for i, j in zip(idx, idx[1:] + idx[:1]):
                        e = (min(i, j), max(i, j))
                        count[e] = count.get(e, 0) + 1
            for (i, j), c in count.items():
                if c == 1:
                    pygame.draw.line(scr, neon, scr_pts[i][:2], scr_pts[j][:2], SHIMMER_OUTLINE)
        for idx, mat in SHIP.lines:                              # neon edges, on top of it all
            col = neon if shield else MATERIALS.get(mat, DEFAULT)[0]
            pygame.draw.lines(scr, col, False, [scr_pts[i][:2] for i in idx], 3 if shield else 2)

    def _reticle(self, game):
        """Corner brackets round the drone the guns are locked on to (developer mode)."""
        o = game.lock
        p = o and self.proj(o["z"], o["a"], 0.0, 1.5, True)
        if not p:
            return
        x, y = p[0], p[1]
        s = max(10.0, p[2] * 2.4) * (1.0 + 0.08 * math.sin(game.t * 14))
        k = s * 0.45                                             # bracket arm length
        col = (255, 80, 160)
        for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            cx, cy = x + dx * s, y + dy * s
            pygame.draw.lines(self.screen, col, False,
                              ((cx - dx * k, cy), (cx, cy), (cx, cy - dy * k)), 2)

    def _sparks(self, game):
        proj = self.proj
        for p in game.sparks:
            q0 = proj(p["z"], 0.0, p["x"], p["h"])
            q1 = proj(p["z"] + 1.6, 0.0, p["x"] + 0.02 * p["vx"], p["h"] + 0.02 * p["vh"])
            if q0 and q1:
                t = p["age"] / p["life"]
                pygame.draw.line(self.screen, mix((255, 250, 200), (255, 110, 20), t), q0[:2], q1[:2],
                                 max(1, int(q0[2] * 0.14 * (1 - 0.5 * t))))
