"""The speedometer: slanted segment digits, a rising bar of speed and a boost strip."""
import pygame

from .config import BOOST_MULT, BOOST_TIME, SPEED_CAP

KMH = 4.0                       # game speed to km/h on the display
TOP = SPEED_CAP * BOOST_MULT    # the bar is full at the fastest boost

# Which of the seven segments each digit lights: top, upper right, lower right,
# bottom, lower left, upper left, middle.
DIGITS = {"0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg",
          "5": "acdfg", "6": "acdefg", "7": "abc", "8": "abcdefg", "9": "abcdfg"}

W, H = 420, 84                  # panel size
SLANT = 0.22                    # how far everything leans right, per pixel of height
DW, DH, DT = 18, 32, 6          # digit width, height, stroke
DX, DY, DSTEP = 16, 9, 27      # first digit's corner and the step from one digit to the next
BARS = 20
BX0, BX1, BBOT = 108, 380, 64   # the speed bar's left / right ends and baseline

RAMP = [(40, 220, 255), (150, 90, 255), (255, 60, 190), (255, 120, 40), (255, 40, 30)]
FRAME = (255, 150, 40)


def ramp(t):
    """Colour along the cool-to-hot speed ramp, t in 0 .. 1."""
    t = max(0.0, min(1.0, t)) * (len(RAMP) - 1)
    i = min(int(t), len(RAMP) - 2)
    f = t - i
    return tuple(int(a + (b - a) * f) for a, b in zip(RAMP[i], RAMP[i + 1]))


def lean(pts):
    """Lean points right by SLANT, measured from the panel's bottom edge."""
    return [(x + (H - y) * SLANT, y) for x, y in pts]


def segment(x0, y0, x1, y1, t):
    """Hexagonal segment from (x0, y0) to (x1, y1), either horizontal or vertical, t thick."""
    h, g = t / 2, 1.5                                     # half thickness, gap at the ends
    if y0 == y1:
        x0, x1 = x0 + g, x1 - g
        return [(x0, y0), (x0 + h, y0 - h), (x1 - h, y0 - h), (x1, y0), (x1 - h, y0 + h), (x0 + h, y0 + h)]
    y0, y1 = y0 + g, y1 - g
    return [(x0, y0), (x0 + h, y0 + h), (x0 + h, y1 - h), (x0, y1), (x0 - h, y1 - h), (x0 - h, y0 + h)]


def digit_segments(x, y):
    """The seven segment polygons of a digit with its top-left corner at x, y."""
    m, b, r = y + DH / 2, y + DH, x + DW
    return {"a": segment(x, y, r, y, DT), "b": segment(r, y, r, m, DT), "c": segment(r, m, r, b, DT),
            "d": segment(x, b, r, b, DT), "e": segment(x, m, x, b, DT), "f": segment(x, y, x, m, DT),
            "g": segment(x, m, r, m, DT)}


class Speedo:
    def __init__(self):
        self.small = pygame.font.Font(None, 19)
        self.surf = pygame.Surface((W, H), pygame.SRCALPHA)
        self.digits = [{k: lean(p) for k, p in digit_segments(DX + i * DSTEP, DY).items()}
                       for i in range(3)]
        self.bars = []
        step = (BX1 - BX0) / BARS
        for i in range(BARS):
            x = BX0 + i * step
            top = BBOT - 8 - 48 * (i + 1) / BARS                # each bar a little taller
            self.bars.append(lean([(x, BBOT), (x + step - 3, BBOT), (x + step - 3, top), (x, top)]))
        self.frame = lean([(2, 2), (W - 86, 2), (W - 74, 0), (W - 30, 0), (W - 30, H - 2),
                           (12, H - 2), (0, H - 12)])

    def draw(self, screen, pos, game):
        s = self.surf
        s.fill((0, 0, 0, 0))
        pygame.draw.polygon(s, (8, 10, 24, 170), self.frame)
        pygame.draw.lines(s, FRAME, True, self.frame, 2)

        kmh = int(game.speed * KMH)
        frac = game.speed / TOP
        if game.boost > 0:
            col = (120, 255, 160)
        elif game.off_line > 0.05:
            col = (255, 170, 40)
        else:
            col = (235, 240, 255)
        text = "%3d" % min(kmh, 999)
        for ch, segs in zip(text, self.digits):
            lit = DIGITS.get(ch, "")
            for k, poly in segs.items():
                if k not in lit:
                    pygame.draw.polygon(s, (40, 44, 70, 90), poly)   # unlit ghost segments
            for k in lit:
                pygame.draw.polygon(s, col, segs[k])

        # Unit tag under the digits, in a slanted outline.
        ty = DY + DH + 6
        tag = lean([(DX - 4, ty), (DX + 2 * DSTEP + DW, ty), (DX + 2 * DSTEP + DW, ty + 16), (DX - 4, ty + 16)])
        pygame.draw.polygon(s, FRAME, tag, 2)
        img = self.small.render("KM/H", True, FRAME)
        s.blit(img, img.get_rect(center=(sum(x for x, _ in tag) / 4, ty + 9)))

        # Speed bar: one bar per 1/BARS of top speed, the last one fading in.
        for i, poly in enumerate(self.bars):
            f = max(0.0, min(1.0, frac * BARS - i))
            c = ramp(i / (BARS - 1))
            pygame.draw.polygon(s, (c[0] // 6, c[1] // 6, c[2] // 6, 220), poly)
            if f > 0:
                pygame.draw.polygon(s, c + (int(255 * f),), poly)

        # Boost strip along the bottom, draining as the boost runs out.
        b = game.boost / BOOST_TIME
        y0, y1 = H - 13, H - 8
        strip = lean([(DX, y0), (BX1, y0), (BX1, y1), (DX, y1)])
        pygame.draw.polygon(s, (20, 50, 35, 220), strip)
        if b > 0:
            x1 = DX + (BX1 - DX) * b
            pulse = 0.75 + 0.25 * (int(game.t * 12) % 2)
            pygame.draw.polygon(s, tuple(int(v * pulse) for v in (120, 255, 160)),
                                lean([(DX, y0), (x1, y0), (x1, y1), (DX, y1)]))
        screen.blit(s, pos)
