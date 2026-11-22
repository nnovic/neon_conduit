#!/usr/bin/env python3
"""Paint the 360-degree backdrops of the outdoor runs.

    python3 tools/make_panoramas.py [name ...]

Writes neon_conduit/assets/sky_<name>.jpg for each theme (all of them by default).
Needs numpy, which the game itself doesn't.

Each image is a cylindrical panorama: its width is a full turn round the viewer, so
the left and right edges join up, and its scale is FOCAL pixels per radian at the
game's default focal length. Row HZ is the horizon. The track floats high above
the ground, so the bottom part (below the horizon) is the ground far below.
Any image laid out the same way can replace these.
"""
import math
import os
import sys

import numpy as np

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

W, H, HZ = 4400, 1400, 760          # must match neon_conduit/decor.py
F = W / (2 * math.pi)               # pixels per radian
OUT = os.path.join(os.path.dirname(__file__), "..", "neon_conduit", "assets")

Y = np.arange(H, dtype=np.float32)[:, None]
X = np.arange(W, dtype=np.float32)[None, :]
UP = HZ - Y                         # height above the horizon, per row
DOWN = Y - HZ                       # depth below it


# ------------------------------------------------------------------ helpers
def rgb(r, g, b):
    return np.array((r, g, b), np.float32) / 255


def smooth(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def sstep(a, b, x):
    return smooth((x - a) / (b - a))


def noise(rng, cx, cy, w=W, h=H):
    """Smooth value noise 0 .. 1, cx by cy cells over w by h pixels, wrapping across x."""
    g = rng.random((cy + 2, cx)).astype(np.float32)
    fx = np.arange(w, dtype=np.float32) * cx / w
    x0 = fx.astype(int)
    tx = smooth(fx - x0)
    x1 = (x0 + 1) % cx
    fy = np.arange(h, dtype=np.float32) * cy / h
    y0 = fy.astype(int)
    ty = smooth(fy - y0)[:, None]
    top = g[y0][:, x0] + (g[y0][:, x1] - g[y0][:, x0]) * tx
    bot = g[y0 + 1][:, x0] + (g[y0 + 1][:, x1] - g[y0 + 1][:, x0]) * tx
    return top + (bot - top) * ty


def fbm(rng, cx, cy, octaves=5, w=W, h=H, gain=0.5):
    total, amp, norm = 0, 1.0, 0.0
    for k in range(octaves):
        total = total + amp * noise(rng, cx << k, cy << k, w, h)
        norm += amp
        amp *= gain
    return total / norm


def fbm1(rng, cells, octaves=5, n=W, gain=0.5):
    """1D fbm across the width (wrapping), 0 .. 1."""
    return fbm(rng, cells, 1, octaves, n, 1, gain)[0]


def box_x(a, r):
    pad = np.concatenate([a[:, -r - 1:], a, a[:, :r]], axis=1)
    c = np.cumsum(pad, axis=1, dtype=np.float32)
    return (c[:, 2 * r + 1:] - c[:, :-2 * r - 1]) / (2 * r + 1)


def box_y(a, r):
    pad = np.concatenate([np.repeat(a[:1], r + 1, axis=0), a, np.repeat(a[-1:], r, axis=0)], axis=0)
    c = np.cumsum(pad, axis=0, dtype=np.float32)
    return (c[2 * r + 1:] - c[:-2 * r - 1]) / (2 * r + 1)


def blur(a, r):
    """Roughly gaussian blur of radius r (three box passes)."""
    r = max(1, int(r / 1.7))
    for _ in range(3):
        a = box_y(box_x(a, r), r)
    return a


def glow(a, r):
    """Wide blur, done at a quarter of the size for speed."""
    if r < 12:
        return blur(a, r)
    k = 4
    h, w = a.shape[:2]
    small = a.reshape(h // k, k, w // k, k, *a.shape[2:]).mean(axis=(1, 3))
    small = blur(small, r / k)
    big = np.repeat(np.repeat(small, k, axis=0), k, axis=1)
    return blur(big, k)


def over(img, mask, colour):
    """Paint colour over img where mask (0 .. 1) says."""
    m = mask[..., None] if mask.ndim == 2 else mask
    img *= 1 - m
    img += m * colour


def silhouette(top):
    """Coverage mask below a per-column top edge (row numbers), anti-aliased vertically."""
    return np.clip(Y - top[None, :] + 0.5, 0, 1)


def sky(stops):
    """Vertical gradient from [(height above the horizon, colour)], as a (H, 1, 3) column."""
    hs = np.array([s[0] for s in stops], np.float32)
    up = UP[:, 0]
    return np.stack([np.interp(up, hs, [s[1][c] / 255 for s in stops]) for c in range(3)], -1)[:, None, :].astype(np.float32)


def stars(rng, img, count, low, high, tint=0.25):
    """Scatter stars between heights low and high above the horizon."""
    ys = (HZ - rng.uniform(low, high, count)).astype(int)
    xs = rng.integers(0, W, count)
    b = rng.random(count) ** 4 * 1.6 + 0.08
    hue = rng.random(count)
    cols = np.stack([1 - tint * hue, 1 - tint * 0.5 * abs(hue - 0.5), 1 - tint * (1 - hue)], -1) * b[:, None]
    fade = sstep(low, low + 120, HZ - ys)[:, None]
    np.add.at(img, (ys, xs), cols * fade)
    big = b > 1.2                                       # the brightest get a small cross
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        np.add.at(img, (ys[big] + dy, (xs[big] + dx) % W), cols[big] * 0.35 * fade[big])


def blob(img, cx, cy, r, colour, power=2.0):
    """Add a soft round glow (r = its radius, roughly) centred on cx, cy."""
    x0, x1 = int(cx - 3 * r), int(cx + 3 * r) + 1
    y0, y1 = max(0, int(cy - 3 * r)), min(H, int(cy + 3 * r) + 1)
    xs = np.arange(x0, x1)
    d = np.hypot((xs[None, :] - cx), (np.arange(y0, y1)[:, None] - cy)) / r
    g = np.exp(-d ** power)[..., None] * colour
    img[y0:y1, xs % W] += g


def disc(cx, cy, r, w=W, h=H):
    """Anti-aliased disc mask, and the local coordinates (-1 .. 1) inside it."""
    dx = (X - cx) / r
    dy = (Y - cy) / r
    d = np.hypot(dx, dy)
    return np.clip((1 - d) * r + 0.5, 0, 1), dx, dy


def shape_mask(draw):
    """Mask from pygame drawing calls: draw(surface) paints white on black."""
    s = pygame.Surface((W, H))
    draw(s)
    return pygame.surfarray.array_red(s).T.astype(np.float32) / 255


def ground_lights(rng, img, height, spacing, cols, density_cells, keep):
    """City lights far below: a street grid round the viewer, projected onto the panorama.

    height is how high above the ground the track runs, spacing the street block size.
    """
    pts = []
    reach = height * 60
    lines = np.arange(-reach, reach, spacing) + spacing * 0.37
    step = spacing / 7
    along = np.arange(-reach, reach, step)
    for horiz in (0, 1):
        a = np.repeat(lines, len(along))
        b = np.tile(along, len(lines))
        a = a + rng.normal(0, spacing * 0.04, a.shape)
        x, z = (a, b) if horiz else (b, a)
        pts.append((x, z))
    x = np.concatenate([p[0] for p in pts])
    z = np.concatenate([p[1] for p in pts])
    rho = np.hypot(x, z)
    ok = rho > height * 1.2
    x, z, rho = x[ok], z[ok], rho[ok]
    theta = np.arctan2(x, z)
    u = ((theta / (2 * math.pi)) % 1.0) * W
    v = HZ + F * height / rho
    on = v < H - 1
    u, v, rho = u[on], v[on], rho[on]
    # Districts: lights cluster where a noise map is high.
    dens = fbm(rng, density_cells, density_cells // 2, 4, 256, 128)
    di = (dens[(np.log(rho / height) / np.log(60) * 127).clip(0, 127).astype(int), (u / W * 256).astype(int) % 256])
    keep_p = sstep(keep - 0.15, keep + 0.15, di) * (0.15 + 0.85 * rng.random(len(u)))
    sel = rng.random(len(u)) < keep_p
    u, v, rho = u[sel], v[sel], rho[sel]
    pick = rng.integers(0, len(cols), len(u))
    c = np.array(cols, np.float32)[pick]
    far = np.clip(np.log(rho / height) / np.log(60), 0, 1)
    c *= (1.4 - far)[:, None] * (0.5 + rng.random(len(u)))[:, None]
    iu, iv = u.astype(int) % W, v.astype(int)
    np.add.at(img, (iv, iu), c)
    near = rho < height * 6                             # close lights cover more than a pixel
    for dy, dx in ((0, 1), (1, 0), (1, 1)):
        np.add.at(img, (np.minimum(iv[near] + dy, H - 1), (iu[near] + dx) % W), c[near] * 0.8)


def bloom(img, emit, strength=1.0):
    """Light spilling round bright things: emit plus whatever in img is very bright."""
    hot = emit + np.clip(img - 0.85, 0, None)
    return img + emit + strength * (0.55 * blur(hot, 3) + 0.35 * glow(hot, 18) + 0.3 * glow(hot, 70))


def save(img, name):
    soft = np.where(img < 0.8, img, 0.8 + 0.2 * np.tanh((img - 0.8) / 0.2))
    arr = (np.clip(soft, 0, 1) * 255 + 0.5).astype(np.uint8)
    surf = pygame.surfarray.make_surface(arr.transpose(1, 0, 2))
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"sky_{name}.jpg")
    pygame.image.save(surf, path)
    print("wrote", os.path.normpath(path))


# ------------------------------------------------------------------ metropolis
def towers(rng, lo, hi, wmin, wmax, gap=0.3, tall=0.0):
    """Building tops per column (row numbers), plus the id and left edge of each column's tower."""
    top = np.full(W, float(H))
    bid = np.full(W, -1)
    left = np.zeros(W, int)
    x, k = 0, 0
    info = []
    while x < W:
        w = int(rng.uniform(wmin, wmax))
        h = rng.uniform(lo, hi) * (rng.uniform(1.4, 2.0) if rng.random() < tall else 1.0)
        top[x:x + w] = HZ - h
        bid[x:x + w] = k
        left[x:x + w] = x
        info.append((x, w, h))
        k += 1
        x += w + (int(rng.uniform(4, 30)) if rng.random() < gap else 0)
    return top, bid, left, info


def windows(rng, bid, left, top, pitch_x, pitch_y, wx, wy, density, cols):
    """Lit window grid inside towers: an emission layer."""
    col = (X - left[None, :]).astype(int)
    row = (Y - top[None, :]).astype(int)
    inside = (row > 3) & (bid[None, :] >= 0) & (col >= 2)
    cell = (col % pitch_x < wx) & (row % pitch_y < wy)
    table = rng.random(1 << 16).astype(np.float32)
    h = (bid[None, :] * 7919 + (col // pitch_x) * 131 + (row // pitch_y) * 31337) & 0xFFFF
    lit = inside & cell & (table[h] < density)
    pick = (table[(h * 3 + 7) & 0xFFFF] * len(cols)).astype(int).clip(0, len(cols) - 1)
    out = np.array(cols, np.float32)[pick] * lit[..., None]
    return out * (0.5 + table[(h * 5 + 1) & 0xFFFF])[..., None]


def metropolis():
    rng = np.random.default_rng(101)
    haze = rgb(255, 92, 150)
    img = sky([(0, (255, 110, 160)), (70, (190, 50, 140)), (220, (70, 18, 96)),
               (480, (18, 6, 40)), (HZ, (5, 2, 14))]) * np.ones((1, W, 1), np.float32)
    emit = np.zeros_like(img)

    # Low clouds, lit from below by the city.
    cl = fbm(rng, 14, 6, 6)
    cloud = sstep(0.5, 0.78, cl) * sstep(110, 260, UP) * (1 - sstep(520, 700, UP))
    over(img, cloud * 0.55, (rgb(150, 40, 120) * (1 - sstep(150, 600, UP))[..., None] + rgb(30, 10, 50)))
    stars(rng, img, 900, 330, HZ, 0.3)

    # A huge ringed moon, half hidden in the haze, and sky lanes of flying traffic.
    m, dx, dy = disc(3000, HZ - 430, 120)
    shade = np.clip(0.35 - 0.75 * dx - 0.4 * dy, 0, 1)
    tex = fbm(rng, 60, 20, 4)
    over(img, m, (rgb(255, 170, 210) * shade[..., None] * (0.7 + 0.5 * tex[..., None]) + rgb(40, 10, 50)))
    blob(img, 3000, HZ - 430, 160, rgb(120, 30, 90))
    ring = shape_mask(lambda s: pygame.draw.ellipse(s, (255, 255, 255), (2700, HZ - 470, 600, 80), 3))
    ring[:HZ - 430] *= 1 - m[:HZ - 430]                 # the back half goes behind the moon
    emit += ring[..., None] * rgb(255, 120, 210) * 0.7
    for lane in range(6):
        base = rng.uniform(140, 320)
        amp, ph, fr = rng.uniform(10, 50), rng.uniform(0, 6.3), rng.integers(1, 4)
        x0 = rng.uniform(0, W)
        span = rng.uniform(900, 2200)
        n = int(span / rng.uniform(5, 11))
        xs = (x0 + np.sort(rng.uniform(0, span, n))) % W
        for side, c in ((0, rgb(255, 240, 210)), (5, rgb(255, 60, 60))):
            ys = HZ - base - amp * np.sin(2 * math.pi * fr * xs / W + ph) + side
            dist = np.abs(xs - (x0 + span / 2) % W) / (span / 2)
            np.add.at(emit, (ys.astype(int), xs.astype(int)), c * (1.4 - dist)[:, None])

    # Searchlights sweeping up from the city.
    beams = np.zeros((H, W), np.float32)
    for _ in range(9):
        bx = rng.uniform(0, W)
        lean = rng.uniform(-0.5, 0.5)
        width = rng.uniform(0.03, 0.06)
        ang = np.arctan2(X - bx, np.maximum(UP, 1)) - lean
        beams += np.exp(-(ang / width) ** 2) * sstep(0, 60, UP) * np.exp(-UP / 650) * (UP > 0)
    emit += beams[..., None] * rgb(120, 200, 255) * 0.18

    # Far megastructures, hazy, with stepped crowns and spires.
    top, bid, left, info = towers(rng, 120, 330, 40, 150, gap=0.6, tall=0.25)
    for x, w, h in info:
        if rng.random() < 0.5:                          # a stepped crown
            c = x + w // 2
            for step in range(1, 4):
                half = max(3, int(w * (0.5 - 0.13 * step)))
                top[c - half:c + half] = HZ - h - 18 * step
        if rng.random() < 0.4:                          # an antenna with a red light on it
            c = x + w // 2 + int(rng.uniform(-w / 4, w / 4))
            tip = HZ - h - 60 - rng.uniform(20, 120)
            top[c - 1:c + 1] = np.minimum(top[c - 1:c + 1], tip)
            blob(emit, c, tip, 2.5, rgb(255, 40, 40) * 1.5)
    far = silhouette(top) * (UP > -40)
    fc = rgb(110, 40, 110) * (0.6 + 0.4 * sstep(0, 300, UP))[..., None]
    over(img, far, fc)
    emit += windows(rng, bid, left, top, 7, 10, 2, 3, 0.18, [rgb(255, 170, 230), rgb(180, 160, 255)]) * far[..., None] * 0.6

    # Mid towers: dense windows, neon trims and billboards.
    top, bid, left, info = towers(rng, 60, 240, 30, 95, gap=0.35, tall=0.15)
    mid = silhouette(top) * (UP > -40)
    over(img, mid, rgb(26, 10, 40) + rgb(40, 10, 50) * sstep(-20, 150, -UP)[..., None])
    emit += windows(rng, bid, left, top, 6, 9, 3, 4, 0.33,
                    [rgb(255, 210, 140), rgb(255, 240, 210), rgb(130, 230, 255), rgb(255, 120, 210)]) * mid[..., None]
    neon = pygame.Surface((W, H))
    palette = [(0, 255, 240), (255, 40, 200), (255, 220, 60), (120, 120, 255)]
    for x, w, h in info:
        c = palette[rng.integers(0, 4)]
        y = int(HZ - h)
        if rng.random() < 0.5:                          # trim up the corners
            pygame.draw.line(neon, c, (x, y), (x, HZ + 40))
            pygame.draw.line(neon, c, (x + w - 1, y), (x + w - 1, HZ + 40))
        if rng.random() < 0.6:                          # trim round the roof
            pygame.draw.line(neon, c, (x, y), (x + w - 1, y), 2)
        if rng.random() < 0.3 and w > 40 and h > 110:   # a billboard
            bw, bh = int(w * 0.7), int(rng.uniform(40, 70))
            bx, by = x + (w - bw) // 2, y + int(rng.uniform(20, h - bh - 10))
            c2 = palette[rng.integers(0, 4)]
            for k in range(bh):
                t = k / bh
                pygame.draw.line(neon, [int(a * (1 - t) + b * t) for a, b in zip(c, c2)], (bx, by + k), (bx + bw, by + k))
            motif = rng.integers(0, 3)
            dark = (20, 0, 30)
            if motif == 0:
                pygame.draw.circle(neon, dark, (bx + bw // 2, by + bh // 2), bh // 3, 3)
            elif motif == 1:
                for k in range(4):
                    pygame.draw.line(neon, dark, (bx + 4, by + 8 + k * bh // 5), (bx + bw - 4, by + 8 + k * bh // 5), 2)
            else:
                pygame.draw.polygon(neon, dark, [(bx + bw // 4, by + bh - 8), (bx + bw // 2, by + 8),
                                                 (bx + 3 * bw // 4, by + bh - 8)], 3)
    nv = pygame.surfarray.array3d(neon).transpose(1, 0, 2).astype(np.float32) / 255
    emit += nv * mid[..., None] * 0.9

    # Near low blocks, almost black, and the glow of the streets behind them.
    top, bid, left, info = towers(rng, 15, 80, 40, 130, gap=0.2)
    near = silhouette(top) * (UP > -60)
    blob_line = np.exp(-((UP - 4) / 22) ** 2)
    img += blob_line[..., None] * haze * 0.35
    over(img, near, rgb(10, 4, 18))
    emit += windows(rng, bid, left, top, 8, 10, 4, 3, 0.18, [rgb(255, 200, 120), rgb(120, 255, 230)]) * near[..., None]

    # The city far below.
    below = DOWN > 0
    ground = (rgb(60, 14, 50) * np.exp(-DOWN / 40)[..., None] + rgb(8, 3, 14)) * below[..., None]
    img = img * (~below)[..., None] + ground
    ground_lights(rng, emit, 260.0, 90.0,
                  [rgb(255, 180, 90), rgb(255, 230, 200), rgb(90, 220, 255), rgb(255, 80, 200)], 12, 0.45)
    hz = np.exp(-np.abs(DOWN) / 26)[..., None] * (DOWN > -60)[..., None]
    img = img * (1 - 0.6 * hz) + haze * 0.6 * hz * 0.8
    return bloom(img, emit, 1.0)


# ------------------------------------------------------------------ dunes
def dunes():
    rng = np.random.default_rng(202)
    img = sky([(0, (255, 214, 150)), (35, (255, 160, 90)), (140, (210, 90, 90)), (320, (100, 40, 100)),
               (560, (26, 14, 52)), (HZ, (8, 5, 22))]) * np.ones((1, W, 1), np.float32)
    emit = np.zeros_like(img)
    stars(rng, img, 700, 380, HZ, 0.2)
    sun_x = 1100

    # Thin high streaks of cloud, lit by the low sun.
    cl = fbm(rng, 8, 30, 5)
    streak = sstep(0.55, 0.8, cl) * sstep(60, 180, UP) * (1 - sstep(330, 460, UP))
    lit = np.exp(-((X - sun_x + W / 2) % W - W / 2) ** 2 / (2 * 900 ** 2))
    over(img, streak * 0.5, rgb(255, 150, 110) * (0.4 + 0.8 * lit)[..., None] + rgb(60, 20, 60))

    # A gas giant with rings, lit from the low sun's side.
    gx, gy, gr = 2900, HZ - 400, 260
    m, dx, dy = disc(gx, gy, gr)
    nz = np.sqrt(np.clip(1 - dx * dx - dy * dy, 0, 1))
    light = np.clip(-0.85 * dx + 0.15 * dy + 0.35 * nz, 0, 1) ** 0.8
    bands = 0.5 + 0.5 * np.sin(dy * 22 + 3 * fbm(rng, 30, 60, 4))
    surf = (rgb(240, 190, 150) * bands[..., None] + rgb(120, 170, 190) * (1 - bands)[..., None])
    over(img, m, surf * light[..., None] + rgb(30, 14, 40))
    rim = m * np.clip(1 - nz * 3, 0, 1) * np.clip(-dx, 0, 1)
    emit += rim[..., None] * rgb(255, 170, 120) * 0.6

    cos, sin = math.cos(-0.22), math.sin(-0.22)
    rxr = (X - gx) * cos - (Y - gy) * sin
    ryr = (X - gx) * sin + (Y - gy) * cos
    rr = np.hypot(rxr / (gr * 2.1), ryr / (gr * 2.1 * 0.2))
    rings = sstep(0.62, 0.66, rr) * (1 - sstep(0.97, 1.0, rr)) * (0.55 + 0.45 * np.sin(rr * 90))
    rings *= 1 - (m * (ryr < 0))                        # the back of the ring is behind the planet
    shadow = (ryr > 0) & (np.abs(rxr) < gr * 0.95) & (rxr > -gr * 0.3)  # the planet's shadow on it
    rings *= np.where(shadow, 0.3, 1.0)
    over(img, rings * 0.8, rgb(255, 220, 190) * 0.9)

    # A small moon, a crescent.
    m2, dx2, dy2 = disc(3700, HZ - 560, 24)
    over(img, m2, rgb(255, 230, 210) * np.clip(-dx2 * 1.6, 0, 1)[..., None] + rgb(30, 20, 50))

    # The sun, low over the dunes, with a long anamorphic streak.
    blob(emit, sun_x, HZ - 34, 16, rgb(255, 250, 220) * 3.0, 6)
    blob(emit, sun_x, HZ - 34, 120, rgb(255, 150, 70) * 0.7)
    blob(emit, sun_x, HZ - 34, 420, rgb(255, 120, 60) * 0.35)
    streak = np.exp(-(((X - sun_x + W / 2) % W - W / 2) / 700) ** 2 - ((Y - HZ + 34) / 3) ** 2)
    emit += streak[..., None] * rgb(255, 200, 150) * 0.8

    # Arcologies on the horizon: pyramids with lit tiers, domes, a needle tower.
    arch = pygame.Surface((W, H))
    lights = pygame.Surface((W, H))
    for k in range(6):
        cx = rng.uniform(1500, 4300) if k < 4 else rng.uniform(200, 900)
        hw = rng.uniform(70, 170)
        hgt = hw * rng.uniform(0.9, 1.3)
        pygame.draw.polygon(arch, (255, 255, 255), [(cx - hw, HZ + 5), (cx, HZ - hgt), (cx + hw, HZ + 5)])
        for t in np.arange(0.15, 0.95, 0.09):
            y = HZ - hgt * t
            half = hw * (1 - t)
            for xx in np.arange(cx - half + 4, cx + half - 4, 7):
                if rng.random() < 0.55:
                    lights.set_at((int(xx), int(y)), (255, 200, 120))
        pygame.draw.line(lights, (120, 255, 255), (cx, HZ - hgt), (cx, HZ - hgt - 180), 1)
    for k in range(5):
        cx, r = rng.uniform(1600, 4300), rng.uniform(30, 70)
        pygame.draw.circle(arch, (255, 255, 255), (int(cx), HZ + 4), int(r))
        for a in np.linspace(0.2, math.pi - 0.2, 7):
            pygame.draw.line(lights, (80, 230, 255), (cx + r * math.cos(a), HZ - r * math.sin(a) + 4), (cx, HZ + 4))
    nx = 2200
    pygame.draw.polygon(arch, (255, 255, 255), [(nx - 9, HZ + 5), (nx - 2, HZ - 340), (nx + 2, HZ - 340), (nx + 9, HZ + 5)])
    pygame.draw.circle(lights, (255, 80, 60), (nx, HZ - 342), 2)
    am = pygame.surfarray.array_red(arch).T.astype(np.float32) / 255
    lm = pygame.surfarray.array3d(lights).transpose(1, 0, 2).astype(np.float32) / 255
    archcol = rgb(120, 60, 80) + rgb(120, 60, 40) * sstep(0, 300, UP)[..., None] * 0.3
    over(img, am * 0.92, archcol)
    emit += lm * 0.9

    # Dunes in three bands, rim-lit on the side facing the sun.
    toward = ((sun_x - X[0] + W / 2) % W - W / 2) / (W / 2)      # -1 .. 1, sun to the right or left
    for k, (base, amp, cells, dark, haze_amt) in enumerate(((0, 34, 9, (150, 70, 60), 0.55),
                                                            (-8, 52, 6, (110, 46, 44), 0.3),
                                                            (-20, 64, 4, (70, 28, 32), 0.1))):
        h = base + amp * (fbm1(rng, cells, 4) * 1.4 - 0.2)
        top = HZ - h
        slope = np.gradient(h)
        mask = silhouette(top)
        face = np.clip(0.5 + 6 * slope * np.sign(toward), 0, 1)
        depth = np.clip((Y - top[None, :]) / 60, 0, 1)
        lit_col = rgb(255, 170, 110) * (0.4 + 0.6 * face)[None, :, None] * (1 - 0.6 * depth)[..., None]
        col = rgb(*dark) + lit_col * 0.6
        col = col * (1 - haze_amt) + rgb(240, 140, 110) * haze_amt
        over(img, mask, col)
        edge = np.exp(-((Y - top[None, :]) / 1.5) ** 2) * (face > 0.7)[None, :]
        emit += edge[..., None] * rgb(255, 200, 140) * 0.35

    # The desert floor far below: rippled sand and runway lights going off to the horizon.
    below = DOWN > 0
    dist = F * 200.0 / np.maximum(DOWN, 1)                     # distance of each row, track 200 up
    ripple = 0.5 + 0.5 * np.sin(dist / 9 + 4 * fbm(rng, 40, 20, 3))
    ripple = ripple * (1 - sstep(4000, 12000, dist)) + 0.5 * sstep(4000, 12000, dist)
    sand = rgb(80, 34, 34) + rgb(140, 70, 50) * (0.6 + 0.4 * ripple)[..., None] * np.exp(-DOWN / 300)[..., None]
    img = img * (~below)[..., None] + sand * below[..., None]
    for _ in range(7):
        u = rng.uniform(0, W)
        d = np.geomspace(260, 30000, 70)
        rows = (HZ + F * 200.0 / d).astype(int)
        ok = rows < H
        np.add.at(emit, (rows[ok], np.full(ok.sum(), int(u))), rgb(90, 255, 255) * (1.2 - np.log(d[ok]) / 12)[:, None])
    hz = np.exp(-np.abs(DOWN) / 30)[..., None] * (DOWN > -30)[..., None]
    img = img * (1 - 0.7 * hz) + rgb(250, 160, 120) * 0.7 * hz
    return bloom(img, emit, 1.0)


# ------------------------------------------------------------------ glacier
def glacier():
    rng = np.random.default_rng(303)
    img = sky([(0, (150, 200, 220)), (60, (80, 130, 170)), (200, (24, 52, 96)), (450, (6, 16, 42)),
               (HZ, (2, 4, 14))]) * np.ones((1, W, 1), np.float32)
    emit = np.zeros_like(img)
    stars(rng, img, 2600, 160, HZ, 0.4)

    # Aurora curtains: rays along a wavy base line, fading upwards.
    for k in range(3):
        base = 230 + 60 * k + 60 * (fbm1(rng, 5, 3) - 0.5) * 2
        span = sstep(0.3, 0.6, fbm1(rng, 4, 3))
        rays = fbm1(rng, 220, 3) ** 3 * 2.2
        hgt = UP - base[None, :]
        vert = sstep(-12, 6, hgt) * np.exp(-np.maximum(hgt, 0) / (110 + 40 * k))
        inten = vert * (span * (0.4 + rays))[None, :]
        green, cyan, violet = rgb(60, 255, 150), rgb(60, 200, 255), rgb(170, 80, 255)
        t = np.clip(hgt / 200, 0, 1)[..., None]
        colour = green * (1 - t) + violet * t * 0.8 + cyan * 0.2
        emit += inten[..., None] * colour * (0.35 - 0.08 * k)

    # An orbital ring arcing across the sky, half in the planet's shadow, with stations.
    xa, xb, top = 300, 3900, 520
    t = (X[0] - xa) / (xb - xa)
    arc_y = HZ - top * np.maximum(np.sin(math.pi * np.clip(t, 0, 1)), 0) ** 0.8
    inside = (t > 0) & (t < 1)
    thick = 1.2 + 2.5 * np.sin(math.pi * np.clip(t, 0, 1))
    band = np.exp(-((Y - arc_y[None, :]) / thick[None, :]) ** 2) * inside[None, :]
    sunlit = np.where(t < 0.62, 1.0, 0.25)
    emit += band[..., None] * rgb(200, 230, 255) * (0.5 * sunlit)[None, :, None]
    for s in np.linspace(0.08, 0.92, 9):
        sx = xa + s * (xb - xa)
        sy = HZ - top * math.sin(math.pi * s) ** 0.8
        blob(emit, sx, sy, 2.5, rgb(255, 255, 255) * (1.5 if s < 0.62 else 0.4))

    # A space elevator: a hair-thin tether from the peaks to the sky, with climbers on it.
    ex = 3350
    tether = np.exp(-((X - ex) / 0.7) ** 2) * (UP > 0) * np.exp(-UP / 900)
    emit += tether[..., None] * rgb(160, 200, 255) * 0.5
    for h in (210, 390, 610):
        blob(emit, ex, HZ - h, 2.0, rgb(255, 220, 120) * 1.5)

    # Mountain ranges: ridged noise, lit from the left, snow on the upper slopes.
    tex = fbm(rng, 90, 40, 5)
    facets = np.gradient(fbm(rng, 160, 60, 4), axis=1)  # rocky facets, lit from the left
    facets = blur(facets / (facets.std() * 4), 1)
    ranges = ((260, 160, 7, (110, 140, 185), 0.45), (190, 120, 11, (60, 76, 110), 0.25),
              (90, 70, 16, (26, 32, 48), 0.06))
    for k, (hmax, var, cells, rock, haze_amt) in enumerate(ranges):
        n = fbm1(rng, cells, 6, gain=0.55)
        ridged = 1 - np.abs(2 * n - 1)
        h = hmax * 0.35 + var * (ridged ** 1.6) * 1.3 + 25 * fbm1(rng, cells * 6, 3)
        if k == 2:
            h = h * 0.6
        top = HZ - h
        mask = silhouette(top)
        slope = np.convolve(np.concatenate([h[-20:], h, h[:20]]), np.ones(41) / 41, "valid")
        slope = np.gradient(slope)                      # the broad lie of each face, not every notch
        lit = np.clip(0.55 + 0.55 * np.tanh(slope * 1.2)[None, :] + 0.9 * facets, 0, 1.2)
        below_top = np.clip((Y - top[None, :]) / 140, 0, 1)
        line = (150, 120, 75)[k]                        # snow line, height above the horizon
        snow = sstep(-12, 12, UP - line + 70 * (tex - 0.5) - 25 * np.abs(np.tanh(slope * 1.2))[None, :])
        rock_c = rgb(*rock) * (0.5 + 0.6 * lit)[..., None]
        snow_c = rgb(220, 235, 255) * (0.55 + 0.5 * lit)[..., None]
        col = rock_c * (1 - snow[..., None]) + snow_c * snow[..., None]
        col = col * (1 - 0.4 * below_top[..., None])
        col = col * (1 - haze_amt) + rgb(140, 185, 215) * haze_amt
        over(img, mask * (UP > -30), col)
        if k == 2:                                      # a research base at the foot of the range
            for bx in (900, 2500, 3340):
                for _ in range(26):
                    px, py = bx + rng.normal(0, 25), HZ - rng.uniform(2, 40)
                    blob(emit, px, py, 1.2, rgb(255, 200, 120) if rng.random() < 0.6 else rgb(120, 230, 255))
                dome, _, _ = disc(bx, HZ, 30)
                over(img, dome * (UP > 0), rgb(40, 70, 100))
                emit += (dome * (UP > 0) * (1 - dome) * 4)[..., None] * rgb(120, 230, 255) * 0.3
                blob(emit, bx, HZ - 10, 40, rgb(80, 180, 255) * 0.25)

    # Below: a frozen lake mirroring it all, streaked and darker underfoot.
    up = img[HZ - (H - HZ):HZ][::-1]
    upe = emit[HZ - (H - HZ):HZ][::-1]
    ice = fbm(rng, 6, 80, 4, W, H - HZ)
    smear = 0.55 + 0.25 * ice[..., None]
    fall = np.exp(-np.arange(H - HZ, dtype=np.float32) / 380)[:, None, None]
    img[HZ:] = up * smear * (0.3 + 0.5 * fall) + rgb(10, 20, 36)
    emit[HZ:] = upe * smear * 0.5 * fall
    cracks = sstep(0.0, 0.015, np.abs(fbm(rng, 50, 30, 4, W, H - HZ) - 0.5)) < 0.5
    img[HZ:] += cracks[..., None] * rgb(80, 120, 160) * 0.25 * fall
    hz = np.exp(-np.abs(DOWN) / 20)[..., None]
    img = img * (1 - 0.5 * hz) + rgb(150, 195, 220) * 0.5 * hz
    return bloom(img, emit, 1.0)


# ------------------------------------------------------------------ orbit
def orbit():
    rng = np.random.default_rng(404)
    img = np.zeros((H, W, 3), np.float32) + rgb(2, 2, 8)
    emit = np.zeros_like(img)
    limb = 46                                           # the planet's edge, below the horizon
    sun_x = 1500

    # The galaxy: a broad band of glow with dark dust lanes, and nebulae.
    centre = 380 + 220 * np.sin(2 * math.pi * X[0] / W + 1.1)
    d = (UP - centre[None, :]) / 140
    band = np.exp(-d * d) * (0.4 + 0.6 * fbm(rng, 40, 16, 6))
    dust = sstep(0.45, 0.7, fbm(rng, 60, 30, 5)) * np.exp(-(d / 0.7) ** 2)
    img += (band * (1 - 0.85 * dust))[..., None] * rgb(110, 105, 140) * 0.9
    neb = fbm(rng, 18, 8, 6)
    for cx, cy, r, c in ((700, 450, 380, (255, 60, 140)), (2400, 600, 450, (40, 200, 220)),
                         (3600, 300, 330, (160, 60, 255))):
        dd = np.hypot(((X - cx + W / 2) % W - W / 2) / r, (UP - cy) / (r * 0.6))
        img += (np.exp(-dd * dd) * sstep(0.45, 0.85, neb))[..., None] * rgb(*c) * 0.5
    stars(rng, img, 7000, -limb + 4, HZ, 0.5)
    n_band = 9000
    sx = rng.integers(0, W, n_band)
    sy = (HZ - centre[sx] - rng.normal(0, 70, n_band)).astype(int).clip(0, HZ - limb)
    np.add.at(img, (sy, sx), (rng.random(n_band) ** 3 * 0.8)[:, None] * rgb(230, 230, 255))

    # A ring station hanging in the distance, and a far moon.
    st = pygame.Surface((W, H))
    cx, cy = 3150, HZ - 230
    pygame.draw.ellipse(st, (200, 210, 230), (cx - 90, cy - 26, 180, 52), 4)
    for a in range(0, 360, 45):
        r = math.radians(a)
        pygame.draw.line(st, (120, 130, 150), (cx, cy), (cx + 88 * math.cos(r), cy + 25 * math.sin(r)), 1)
    pygame.draw.rect(st, (220, 220, 240), (cx - 8, cy - 40, 16, 80))
    pygame.draw.rect(st, (70, 90, 140), (cx - 70, cy - 60, 40, 14))
    pygame.draw.rect(st, (70, 90, 140), (cx + 30, cy - 60, 40, 14))
    sm = pygame.surfarray.array3d(st).transpose(1, 0, 2).astype(np.float32) / 255
    img = np.where(sm.max(-1, keepdims=True) > 0, sm * 0.7, img)
    for a in range(0, 360, 20):
        r = math.radians(a)
        blob(emit, cx + 90 * math.cos(r), cy + 26 * math.sin(r), 1.3, rgb(255, 220, 140) * 1.2)
    blob(emit, cx, cy - 40, 2, rgb(255, 60, 60) * 2)
    m, dx, dy = disc(500, HZ - 470, 46)
    over(img, m, rgb(190, 180, 170) * np.clip(0.2 - dx * 0.9, 0, 1)[..., None] * (0.7 + 0.5 * fbm(rng, 200, 60, 3))[..., None])

    # The planet below: a lit day side towards the sun, cities on the night side.
    below = Y > HZ + limb
    depth = np.maximum(Y - HZ - limb, 0)
    t = np.log1p(depth / 6)                             # squeezes the surface towards the limb
    ti = (t / t.max() * 1023).astype(int)[:, 0]
    land = fbm(rng, 30, 30, 7, W, 1024)[ti]
    cloud = fbm(rng, 50, 40, 7, W, 1024)[ti]
    city = fbm(rng, 200, 120, 3, W, 1024)[ti]
    az = ((X - sun_x + W / 2) % W - W / 2) / (W / 2)    # -1 .. 1 round from the sun
    day = sstep(0.55, 0.15, np.abs(az))
    sea = sstep(0.52, 0.5, land)
    ground = rgb(10, 30, 70) * sea[..., None] + rgb(60, 80, 40) * (1 - sea)[..., None]
    ground = ground * (1 - sstep(0.6, 0.75, land))[..., None] + rgb(160, 140, 110) * sstep(0.6, 0.75, land)[..., None]
    clouds = sstep(0.55, 0.75, cloud)
    surf = (ground * (1 - clouds[..., None]) + rgb(240, 245, 255) * clouds[..., None]) * day[..., None] * 0.9
    night = (1 - day) * (1 - sea) * (1 - clouds * 0.8)
    lights = sstep(0.62, 0.75, city) * night
    sparkle = rng.random((H, W)).astype(np.float32)
    emit += (lights * (sparkle > 0.7) * sparkle)[..., None] * rgb(255, 190, 100) * 0.9 * below[..., None]
    img = np.where(below[..., None], surf + rgb(3, 5, 12), img)

    # Atmosphere: a bright thin shell along the limb, blue on the day side, orange at
    # the terminator; and the sun just rising over the edge.
    h = Y - HZ - limb
    shell = np.exp(-np.abs(h + 6) / np.where(h < 0, 7, 22))
    tint = rgb(90, 170, 255) * day[..., None] + rgb(255, 120, 60) * (sstep(0.15, 0.3, np.abs(az)) * sstep(0.6, 0.35, np.abs(az)))[..., None]
    emit += shell[..., None] * tint * 0.9
    emit += (np.exp(-np.abs(h + 2) / 60) * (h < 0))[..., None] * tint * 0.15
    blob(emit, sun_x, HZ + limb - 6, 10, rgb(255, 255, 240) * 4, 4)
    blob(emit, sun_x, HZ + limb - 6, 90, rgb(255, 230, 190) * 0.8)
    streak = np.exp(-((X - sun_x) / 900) ** 2 - ((Y - HZ - limb + 6) / 2.5) ** 2)
    emit += streak[..., None] * rgb(255, 240, 220) * 1.0
    return bloom(img, emit, 1.1)


THEMES = {"metropolis": metropolis, "dunes": dunes, "glacier": glacier, "orbit": orbit}

if __name__ == "__main__":
    pygame.init()
    for name in sys.argv[1:] or THEMES:
        save(THEMES[name](), name)
