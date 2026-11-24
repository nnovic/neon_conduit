"""Backdrops for the outdoor runs: 360-degree panoramas round the track.

Each backdrop is the image of a theme in outdoor_themes.txt (the sky_*.jpg there are
painted by tools/make_panoramas.py; any image laid out the same way will do). It is a
cylindrical panorama: its width is one full turn, so the view turns right round it as
the track turns a full circle, and the theme's horizon row is the horizon. It lies "at
infinity": it turns with the camera's roll and slides up and down as the track dips and
climbs.
"""
import math

import pygame

from .config import SEG
from .themes import THEMES


class Panorama:
    def __init__(self, name, scale=1.0):
        theme = THEMES[name]
        img = pygame.image.load(theme.image)
        if not 10 <= theme.horizon <= img.get_height() - 10:
            raise ValueError("theme [%s]: horizon %d is outside its image, which is %d pixels high"
                             % (name, theme.horizon, img.get_height()))
        if pygame.display.get_surface():
            img = img.convert()
        if scale != 1.0:
            img = pygame.transform.smoothscale(img, (round(img.get_width() * scale),
                                                     round(img.get_height() * scale)))
        self.name = name
        self.img = img
        self.half = pygame.transform.smoothscale(img, (img.get_width() // 2, img.get_height() // 2))
        self.w, self.h = img.get_size()
        self.horizon = theme.horizon * scale
        self.ppu = self.w / (2 * math.pi * SEG)     # pixels per unit of heading (see Game.heading)
        self.top = pygame.transform.average_color(img, (0, 0, self.w, 2))[:3]
        self.bottom = pygame.transform.average_color(img, (0, self.h - 2, self.w, 2))[:3]
        band = (0, int(self.horizon) - 10, self.w, 20)
        # The haze the track fades into: the theme's, or the image's colour along the horizon.
        self.fog = theme.fog or pygame.transform.average_color(img, band)[:3]


_loaded = {}


def panoramas(names, scale=1.0):
    """The backdrops called names, loaded once and shared."""
    key = (tuple(names), scale)
    if key not in _loaded:
        _loaded[key] = {n: Panorama(n, scale) for n in names}
    return _loaded[key]


def _paint(dst, img, top, bottom, u, v, w, h):
    """Copy the w x h window of the panorama img whose top left is at (u, v) onto dst,
    wrapping round horizontally and padding above and below with the edge colours."""
    pw, ph = img.get_size()
    u, v = int(u) % pw, int(v)
    if v < 0:
        dst.fill(top, (0, 0, w, -v))
    if v + h > ph:
        dst.fill(bottom, (0, ph - v, w, v + h - ph))
    sy = max(0, v)
    rows = min(ph, v + h) - sy
    if rows <= 0:
        return
    x = 0
    while x < w:
        n = min(w - x, pw - u)
        dst.blit(img, (x, sy - v), (u, sy, n, rows))
        x += n
        u = 0


_tmp = {}


def draw(r, pano, heading, rise):
    """Draw pano for renderer r (its screen, vanishing point and roll), looking along
    heading, with the horizon rise pixels below the vanishing point."""
    scr = r.screen
    u = heading * pano.ppu                          # panorama column straight ahead
    tilt = math.atan2(r.sr, r.cr)
    if abs(tilt) < 0.003:
        _paint(scr, pano.img, pano.top, pano.bottom, u - r.pcx, pano.horizon - r.pcy - rise, r.w, r.h)
        return
    # Rolled (only ever in the tube, looking out through its far end): paint a square
    # round the vanishing point at half size, turn it, and blow it back up.
    d = int(math.hypot(r.w, r.h)) // 2 + 2
    tmp = _tmp.get(d)
    if tmp is None:
        tmp = _tmp[d] = pygame.Surface((d, d)).convert() if pygame.display.get_surface() else pygame.Surface((d, d))
    _paint(tmp, pano.half, pano.top, pano.bottom, u / 2 - d / 2, (pano.horizon - rise) / 2 - d / 2, d, d)
    turned = pygame.transform.rotate(tmp, -math.degrees(tilt))
    tw, th = turned.get_size()
    big = pygame.transform.scale(turned, (tw * 2, th * 2))
    scr.blit(big, (r.pcx - tw, r.pcy - th))
