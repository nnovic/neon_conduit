"""Head-up display and the title, game-over and pause screens."""
import math
import os

import pygame

from .nowplaying import NowPlaying
from .speedo import H as SPEEDO_H, W as SPEEDO_W, Speedo

TEXT = (235, 240, 255)
# The title's lettering: Russo One (SIL Open Font License, see assets/RussoOne-OFL.txt).
TITLE_FONT = os.path.join(os.path.dirname(__file__), "assets", "RussoOne-Regular.ttf")
TITLE_WIDTH = 0.86              # the title spans this much of the screen's width
# Its fill, top to bottom: white-hot, pink, a hard step to deep pink, then orange.
TITLE_STOPS = ((0.0, (255, 250, 255)), (0.42, (255, 120, 220)), (0.52, (255, 40, 150)), (1.0, (255, 170, 40)))
TITLE_STROKE = (20, 0, 40)
TITLE_GLOW = (255, 50, 170)
TIP_COL = (255, 255, 160)        # the tutorial's tips (see tutorial.py)...
TIP_Y = 150                     # ...centred this far down the screen
BAND_Y = 110                    # the title screen's dark band leaves this much clear above and below
# The title screen's credits banner, scrolling along the bottom: a summary of CREDITS.md.
CREDITS_LINE = ('Music: "Hero Immortal" by Trevor Lentz (CC BY-SA 3.0, opengameart.org)     \u2022     '
                'Font: Russo One by Jovanny Lemonad (SIL Open Font License 1.1)     \u2022     ')
CREDITS_H = 26                  # height of the banner's strip
CREDITS_SPEED = 70.0            # pixels per second it scrolls to the left
CREDITS_COL = (190, 200, 230)
MENU_H = 100                    # height of the title menu, just above the credits banner
MENU_GAP = 60                   # pixels between two modes' names
MENU_DIM = (150, 160, 200)      # modes not selected, and the keys' hint
MENU_DESC = (255, 220, 150)     # the selected mode's description
MENU_OFF = (75, 78, 95)         # a mode not playable yet: its name and its frame
BRIEF = ["Left / Right  steer      Up / Down  aim      Space  fire",
         "P  pause      F11  full screen      Esc  quit",
         "",
         "Press any key to go"]


def neon_title(text, width):
    """text set in the title font, width pixels wide: a gradient fill over a dark stroke,
    in a wide glow. Returns the image and the margin left round the letters for the glow."""
    size = 200
    size = int(size * width / pygame.font.Font(TITLE_FONT, size).size(text)[0])
    mask = pygame.font.Font(TITLE_FONT, size).render(text, True, (255, 255, 255))
    mw, mh = mask.get_size()
    pad = size // 2
    w, h = mw + 2 * pad, mh + 2 * pad
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    # Glow: the letters blurred wide, twice over.
    halo = pygame.Surface((w, h), pygame.SRCALPHA)
    tint = mask.copy()
    tint.fill(TITLE_GLOW + (255,), special_flags=pygame.BLEND_RGBA_MULT)
    halo.blit(tint, (pad, pad))
    for k in (4, 10):
        blur = pygame.transform.smoothscale(pygame.transform.smoothscale(halo, (w // k, h // k)), (w, h))
        out.blit(blur, (0, 0))
        out.blit(blur, (0, 0))
    # Dark stroke, a little heavier below, so the letters stand off the glow.
    dark = mask.copy()
    dark.fill(TITLE_STROKE + (255,), special_flags=pygame.BLEND_RGBA_MULT)
    r = max(3, size // 28)
    step = max(1, r // 3)
    for dx in range(-r, r + 1, step):
        for dy in range(-r, r + 1, step):
            if dx * dx + dy * dy <= r * r:
                out.blit(dark, (pad + dx, pad + dy + r // 2))
    # Fill.
    grad = pygame.Surface((mw, mh), pygame.SRCALPHA)
    for y in range(mh):
        t = y / (mh - 1)
        for (t0, c0), (t1, c1) in zip(TITLE_STOPS, TITLE_STOPS[1:]):
            if t <= t1:
                u = (t - t0) / (t1 - t0)
                grad.fill(tuple(int(a + (b - a) * u) for a, b in zip(c0, c1)) + (255,), (0, y, mw, 1))
                break
    mask.blit(grad, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    out.blit(mask, (pad, pad))
    return out, pad


class Hud:
    def __init__(self, screen):
        self.screen = screen
        self.w, self.h = screen.get_size()
        self.font = pygame.font.Font(None, 30)
        self.big = pygame.font.Font(None, 84)
        self.mid = pygame.font.Font(None, 44)
        self.speedo = Speedo()
        self.now_playing = NowPlaying()
        self.band = None            # the title screen's darkened band behind its tunnel
        self.title_layer = None     # the title screen's text, to fade out at launch
        self.credits_strip = None   # the credits banner's strip, and its line of text
        self.credits_text = None
        self.menu_fonts = None      # the title menu's fonts: mode names, descriptions

    def text(self, font, s, pos, col=TEXT, center=False):
        """Text with a drop shadow, at its top-left corner or centred on pos."""
        img = font.render(s, True, col)
        shadow = font.render(s, True, (0, 0, 0))
        r = img.get_rect()
        if center:
            r.center = pos
        else:
            r.topleft = pos
        self.screen.blit(shadow, r.move(2, 2))
        self.screen.blit(img, r)

    def draw(self, game):
        """Clock, score, gate, speed and progress to the next gate."""
        w = self.w
        if game.tutorial.clock:             # hidden while the tutorial holds it back
            tcol = (255, 70, 60) if game.time_left < 6 and int(game.t * 4) % 2 else TEXT
            self.text(self.mid, "%04.1f" % game.time_left, (w // 2, 30), tcol, center=True)
        self.text(self.font, "SCORE %07d" % game.score, (20, 16))
        self.text(self.font, "GATE %d" % game.level, (20, 44))
        self.speedo.draw(self.screen, (w - SPEEDO_W - 8, self.h - SPEEDO_H - 8), game)
        self.now_playing.draw(self.screen, (8, self.h - SPEEDO_H - 8), game.now_playing,
                              game.t - game.music_t)
        if game.tutorial.clock:             # no gates to run for while the tutorial is on
            prog = game.gate_progress
            pygame.draw.rect(self.screen, (40, 44, 70), (w // 2 - 150, 56, 300, 8))
            pygame.draw.rect(self.screen, (255, 255, 160), (w // 2 - 150, 56, int(300 * prog), 8))
        if game.msg[1] > 0:
            self.text(self.mid, game.msg[0], (w // 2, 120), (255, 255, 160), center=True)
        self.tip(game)

    def tip(self, game):
        """The tutorial's tip, if one is up, under the clock; and while it can be skipped,
        how to."""
        if game.can_skip:
            self.text(self.font, "TAB  skip tutorial", (20, self.h - 36), (170, 180, 210))
        up = game.tutorial.current()
        if up is None:
            return
        tip, alpha = up
        img = self.mid.render(tip.text, True, TIP_COL)
        shadow = self.mid.render(tip.text, True, (0, 0, 0))
        r = img.get_rect(center=(self.w // 2, TIP_Y))
        for surf, pos in ((shadow, r.move(2, 2)), (img, r)):
            surf.set_alpha(int(255 * alpha))
            self.screen.blit(surf, pos)

    def brief(self):
        """The briefing, on a dark panel over the race while the racer waits on the start line."""
        mid = self.w // 2
        top = (self.h - len(BRIEF) * 34) // 2
        panel = pygame.Surface((self.w, len(BRIEF) * 34 + 44), pygame.SRCALPHA)
        panel.fill((4, 6, 18, 160))
        self.screen.blit(panel, (0, top - 30))
        for i, s in enumerate(BRIEF):
            self.text(self.font, s, (mid, top + i * 34), center=True)

    def title_band(self):
        """The title screen's darkened band, behind the tunnel."""
        if self.band is None:
            bh = self.h - 2 * BAND_Y
            self.band = pygame.Surface((self.w, bh), pygame.SRCALPHA)
            for y in range(bh):                               # dark in the middle, fading out
                self.band.fill((4, 6, 18, int(170 * math.sin(math.pi * y / (bh - 1)))), (0, y, self.w, 1))
        self.screen.blit(self.band, (0, BAND_Y))

    def title_text(self, alpha=255):
        """The title, alpha from 0 (gone) to 255."""
        if self.title_layer is None:
            self.title_layer = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            screen, self.screen = self.screen, self.title_layer
            mid = self.w // 2
            title, pad = neon_title("NEON CONDUIT", int(self.w * TITLE_WIDTH))
            self.screen.blit(title, title.get_rect(midtop=(mid, 18 - pad)))
            self.screen = screen
        self.title_layer.set_alpha(alpha)
        self.screen.blit(self.title_layer, (0, 0))

    def title_menu(self, modes, sel, t, alpha=255):
        """The game modes in a row under the tunnel, the selected one framed and its
        description below; t pulses the frame, alpha from 0 (gone) to 255."""
        if self.menu_fonts is None:
            self.menu_fonts = (pygame.font.Font(TITLE_FONT, 30), pygame.font.Font(TITLE_FONT, 16))
        name_font, desc_font = self.menu_fonts
        top = self.h - CREDITS_H - MENU_H                 # just above the credits banner
        layer = pygame.Surface((self.w, MENU_H), pygame.SRCALPHA)
        screen, self.screen = self.screen, layer
        y = 26
        imgs = [name_font.render(name, True, TEXT) for name, _, _ in modes]
        x = (self.w - sum(i.get_width() for i in imgs) - MENU_GAP * (len(imgs) - 1)) // 2
        for i, ((name, desc, enabled), img) in enumerate(zip(modes, imgs)):
            r = img.get_rect(midleft=(x, y))
            if not enabled:                               # greyed out, a still frame if selected
                if i == sel:
                    pygame.draw.rect(layer, MENU_OFF, r.inflate(28, 10), 2, border_radius=8)
                self.text(name_font, name, r.center, MENU_OFF, center=True)
            elif i == sel:
                glow = int(170 + 85 * math.sin(t * 4))
                pygame.draw.rect(layer, (255, 50, 170, glow), r.inflate(28, 10), 2, border_radius=8)
                self.text(name_font, name, r.center, TEXT, center=True)
            else:
                self.text(name_font, name, r.center, MENU_DIM, center=True)
            x += img.get_width() + MENU_GAP
        self.text(desc_font, modes[sel][1], (self.w // 2, y + 36),
                  MENU_DESC if modes[sel][2] else MENU_DIM, center=True)
        hint = "ENTER  start" if len(modes) == 1 else "LEFT / RIGHT  choose      ENTER  start"
        self.text(desc_font, hint, (self.w // 2, y + 60), MENU_DIM, center=True)
        self.screen = screen
        layer.set_alpha(alpha)
        self.screen.blit(layer, (0, top))

    def credits(self, t, alpha=255):
        """The credits banner along the bottom of the title screen, scrolled to time t,
        alpha from 0 (gone) to 255."""
        if self.credits_strip is None:
            self.credits_strip = pygame.Surface((self.w, CREDITS_H))
            font = pygame.font.Font(TITLE_FONT, 15)
            self.credits_text = font.render(CREDITS_LINE, True, CREDITS_COL)
        strip, img = self.credits_strip, self.credits_text
        strip.fill((4, 6, 18))
        pygame.draw.line(strip, (255, 50, 170), (0, 0), (self.w, 0))     # a neon edge on top
        tw = img.get_width()
        x = -(t * CREDITS_SPEED % tw)
        y = (CREDITS_H - img.get_height()) // 2 + 1
        while x < self.w:                                                # the line, end to end
            strip.blit(img, (int(x), y))
            x += tw
        strip.set_alpha(int(220 * alpha / 255))
        self.screen.blit(strip, (0, self.h - CREDITS_H))

    def overlay(self, game, backdrop=None):
        """Darkened screen with the title, game-over or pause text, depending on game.state.

        The title screen has its own backdrop (the flag): only a band behind the tunnel is darkened.
        backdrop, if given, is called to draw between that darkening and the text.
        """
        mid = self.w // 2
        if game.state == "title":
            self.title_band()
        else:
            veil = pygame.Surface((self.w, self.h))
            veil.set_alpha(150)
            self.screen.blit(veil, (0, 0))
        if backdrop:
            backdrop()
        if game.state == "title":
            self.title_text()
            return
        if game.state == "over":
            self.text(self.big, "TIME UP", (mid, 190), (255, 70, 60), center=True)
            lines = ["Score %d     Gates %d" % (game.score, game.level),
                     "Best %d" % game.best, "", "Press ENTER to race again"]
        elif game.state == "finished":
            m, s = divmod(game.race_t, 60)
            self.text(self.big, "FINISH", (mid, 190), (120, 255, 160), center=True)
            lines = ["Time %d:%04.1f     %.1f s left on the clock" % (m, s, game.time_left),
                     "Score %d     Best %d" % (game.score, game.best), "", "Press ENTER to race again"]
        else:
            self.text(self.big, "PAUSED", (mid, 250), center=True)
            lines = []
        for i, s in enumerate(lines):
            self.text(self.font, s, (mid, 280 + i * 32), center=True)
