"""3D drawing of the world: tube and open sections, doors, objects, the sled and its sparks.

Everything is projected by hand with a simple pinhole camera and painted back to
front, segment by segment, so nearer walls hide what lies behind them.
"""
import math
import random

import pygame

from . import config
from .config import (BOOST_HW, CAM_H, CAM_LAG, DOOR_OPEN_AT, DOOR_SLIDE, DRAW, FLOOR_A, FLOOR_Y,
                     FOCAL, GATE_SEGS, HORIZON, LINE_HW, NEAR, R, SEG, SIDES, SLED_HW, STAR_R,
                     STAR_REACH, STAR_STRETCH, WALL_H, WALL_T)
from .geometry import (FLOOR_SIDES, OPEN_X, SIDE_A, SIDE_COS, SIDE_LIGHT, SIDE_MID, SIDE_R, SIDE_SIN,
                       TUBE_XS, bank, clip, wall_xy, wrap)
from .palette import (DOOR_COL, DOOR_EDGE, FLOOR_COLS, FOG, GATE_GLOW, fogged, mix, tube_palette,
                      tube_shade)


def star_fan(radius):
    """A five-pointed star pointing ahead, stretched along the track, as a fan of triangles
    in surface coordinates (along the track, sideways along the wall) around its centre."""
    pts = []
    for j in range(10):
        ang = j * math.pi / 5
        rr = radius if j % 2 == 0 else radius * 0.42
        pts.append((STAR_STRETCH * rr * math.cos(ang), rr * math.sin(ang)))
    return [((0.0, 0.0), pts[j], pts[(j + 1) % 10]) for j in range(10)]


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

    def draw(self, game):
        """Draw the world as seen from behind game's sled (no HUD)."""
        self.game = game
        scr = self.screen
        tr = game.track
        scr.fill(FOG)
        self._camera(game)
        self._stars(game)

        base = int(game.cam_z // SEG)
        frac = game.cam_z / SEG - base
        tr.ensure(base + DRAW + 2, game.level)
        self.base = base
        self._centre_line(tr, base, frac)
        rings, orings, frames = self._rings(tr, base, frac)

        # Bucket objects per segment so nearer walls correctly hide them.
        buckets = {}
        far_z = (base + DRAW) * SEG
        for o in tr.objects:
            if o["z"] < far_z:
                buckets.setdefault(int(o["z"] // SEG), []).append(o)
        for b in game.bullets:
            buckets.setdefault(int(b["z"] // SEG), []).append(b)
        for e in game.effects:
            buckets.setdefault(int(e["z"] // SEG), []).append(e)

        for i in range(DRAW - 1, -1, -1):
            si = base + i
            if (i + 1 - frac) * SEG > NEAR:
                fog = min(1.0, (max(0.0, i - frac) / DRAW) ** 1.3 * 1.15)
                if tr.open[si]:
                    self._open_segment(tr, si, orings[i], orings[i + 1], fog)
                else:
                    self._tube_segment(tr, si, rings[i], rings[i + 1], fog)
                if config.DEVELOPER_MODE and tr.bend(si) > 0.25:
                    self._fast_line(tr, si, fog)
                self._hint_stars(tr, si)
            for o in buckets.get(si, ()):
                self._object(o)
            if tr.is_door(si) and (i - frac) * SEG > NEAR:
                self._door(frames[i], si, max(0.0, i - frac) / DRAW)

        self._sled(game)
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

    def _stars(self, game):
        """Stars, seen in open sections and at the far end of the tube."""
        cr, sr, pcx, pcy = self.cr, self.sr, self.pcx, self.pcy
        hs = game.heading * 140.0
        for x, y, b in self.stars:
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
        if flat is None:
            flat = 1.0 if game.track.open[int(z // SEG)] else 0.0
        d = z - game.cam_z
        if d < NEAR:
            return None
        ccx, ccy = self._centre(z)
        wx, wy = wall_xy(a, lat, h, rigid, flat)
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
        style = tr.tube_style(si)
        pal = tube_palette(tr.stretch[si], style)
        for s in range(SIDES):
            if gate_glow:
                c = GATE_GLOW
            elif abs(SIDE_MID[s]) < FLOOR_A:
                c = FLOOR_COLS[band & 1]
            else:
                c = mix(pal[0], pal[1], tube_shade(style, si, s, self.game.t))
            pygame.draw.polygon(self.screen, fogged(c, SIDE_LIGHT[s], fog),
                                (r0[s], r0[s + 1], r1[s + 1], r1[s]))

    def _open_segment(self, tr, si, r0, r1, fog):
        band = si // 2
        gate_glow = si % GATE_SEGS in (0, GATE_SEGS - 1)
        off = FLOOR_SIDES[0]
        for s in FLOOR_SIDES:
            c = GATE_GLOW if gate_glow else FLOOR_COLS[band & 1]
            pygame.draw.polygon(self.screen, fogged(c, SIDE_LIGHT[s], fog),
                                (r0[s - off], r0[s - off + 1], r1[s - off + 1], r1[s - off]))
        # Upright kerbs at the floor edges: too steep to ride up. Inner face, then top.
        c = GATE_GLOW if gate_glow else tr.kerb_col(si, band)
        nf = len(OPEN_X)
        for c, lt, quads in ((c, 0.72, ((0, nf), (nf - 1, nf + 1))),
                             (mix(c, (255, 250, 225), 0.35), 1.0, ((nf, nf + 2), (nf + 1, nf + 3)))):
            col = fogged(c, lt, fog)
            for v, t in quads:
                pygame.draw.polygon(self.screen, col, (r0[v], r0[t], r1[t], r1[v]))

    def _fast_line(self, tr, si, fog):
        """The fast line (developer mode): cyan while the sled is on it, amber when it has strayed."""
        c = (255, 170, 40) if self.game.off_line > 0.05 else (80, 230, 255)
        col = fogged(c, 0.75 + 0.25 * ((si // 2) & 1), fog)
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
            q = [proj(z, a, -hw, 0.15), proj(z, a, hw, 0.15),
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
        elif kind == "sparkle":                               # hint star picked up
            p = proj(z, o["a"], 0.0, 0.3)
            if p:
                t = o["age"] / 0.45
                r = p[2] * (0.8 + 2.5 * t)
                col = mix((255, 255, 230), (255, 200, 60), t)
                for j in range(8):
                    ang = j * math.pi / 4
                    pygame.draw.line(scr, col, (p[0] + 0.4 * r * math.cos(ang), p[1] + 0.4 * r * math.sin(ang)),
                                     (p[0] + r * math.cos(ang), p[1] + r * math.sin(ang)),
                                     max(1, int(p[2] * 0.25 * (1 - t)) + 1))
        elif "age" in o:                                      # explosion
            p = proj(z, o["a"], 0.0, 1.5, True)
            if p:
                t = o["age"] / 0.45
                pygame.draw.circle(scr, mix((255, 255, 200), (255, 60, 0), t), p[:2],
                                   max(2, p[2] * (0.6 + 3.5 * t)), max(1, int(p[2] * 0.5 * (1 - t)) + 1))
        else:                                                 # bullet
            p0, p1 = proj(z, o["a"], 0.0, 1.0, True), proj(z + 5, o["a"], 0.0, 1.0, True)
            if p0 and p1:
                pygame.draw.line(scr, (255, 255, 120), p0[:2], p1[:2], max(2, int(p0[2] * 0.12)))

    def _hint_stars(self, tr, si):
        """The parts of hint stars that lie on segment si, painted on its surface.

        Stars are longer than a segment, so each is sliced at segment boundaries and
        every slice is drawn in its own segment's turn: nearer surfaces then hide
        exactly what they should, no more.
        """
        lo, hi = si * SEG, (si + 1) * SEG
        taken = self.game.stars_taken
        for k in range(int((lo - STAR_REACH) // SEG), int((hi + STAR_REACH) // SEG) + 1):
            if k < 0 or k in taken or not tr.has_star(k):
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
            return (int(c[0] * lt * (1 - fog) + FOG[0] * fog),
                    int(c[1] * lt * (1 - fog) + FOG[1] * fog),
                    int(c[2] * lt * (1 - fog) + FOG[2] * fog))

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
        scr, proj = self.screen, self.proj
        pz, a, fl = game.sled_z, game.theta, game.flat
        rl = proj(pz - 1.5, a, -SLED_HW, 0.25, True, fl)
        rr = proj(pz - 1.5, a, SLED_HW, 0.25, True, fl)
        nose = proj(pz + 4.5, a, 0.0, 0.45, True, fl)
        fin = proj(pz - 1.5, a, -game.steer * 0.6, 1.6, True, fl)
        if not (rl and rr and nose and fin):
            return
        rl, rr, nose, fin = rl[:2], rr[:2], nose[:2], fin[:2]
        hot = game.boost > 0
        flame = (120, 255, 160) if hot else (90, 180, 255)
        tail = proj(pz - (5.0 if hot else 3.0) - random.random(), a, 0.0, 0.7, True, fl)
        if tail:
            pygame.draw.polygon(scr, flame, (rl, rr, tail[:2]))
        pygame.draw.polygon(scr, (200, 205, 220), (rl, nose, fin))
        pygame.draw.polygon(scr, (120, 125, 150), (rr, nose, fin))
        pygame.draw.polygon(scr, (40, 44, 70), (rl, rr, fin))
        pygame.draw.lines(scr, (255, 80, 160), True, (rl, nose, rr), 2)

    def _sparks(self, game):
        proj = self.proj
        for p in game.sparks:
            q0 = proj(p["z"], 0.0, p["x"], p["h"])
            q1 = proj(p["z"] + 1.6, 0.0, p["x"] + 0.02 * p["vx"], p["h"] + 0.02 * p["vh"])
            if q0 and q1:
                t = p["age"] / p["life"]
                pygame.draw.line(self.screen, mix((255, 250, 200), (255, 110, 20), t), q0[:2], q1[:2],
                                 max(1, int(q0[2] * 0.14 * (1 - 0.5 * t))))
