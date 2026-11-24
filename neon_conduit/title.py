"""The title screen's backdrop: a close-up of a flag rippling in a slow wind.

The flag fills the whole screen, its edges out of sight. Its cloth is woven from the
tunnels' checker pattern, in the first zone's blues: along the flag runs the tunnel's
length (one cell per track segment), across it the wall panels.
"""
import math

import pygame

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
