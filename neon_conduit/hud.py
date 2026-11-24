"""Head-up display and the title, game-over and pause screens."""
import math

import pygame

from .config import GATE_SEGS, SEG
from .speedo import H as SPEEDO_H, W as SPEEDO_W, Speedo

TEXT = (235, 240, 255)
BAND_Y = 110                    # the title screen's dark band leaves this much clear above and below
BRIEF = ["Reach each gate before the clock runs out.",
         "Follow the stars round the outside of bends, or you lose speed.",
         "",
         "Left / Right  steer      Up / Down  aim      Space  fire",
         "P  pause      F11  full screen      Esc  quit",
         "",
         "Press any key to go"]


class Hud:
    def __init__(self, screen):
        self.screen = screen
        self.w, self.h = screen.get_size()
        self.font = pygame.font.Font(None, 30)
        self.big = pygame.font.Font(None, 84)
        self.mid = pygame.font.Font(None, 44)
        self.speedo = Speedo()
        self.band = None            # the title screen's darkened band behind its tunnel
        self.title_layer = None     # the title screen's text, to fade out at launch

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
        tcol = (255, 70, 60) if game.time_left < 6 and int(game.t * 4) % 2 else TEXT
        self.text(self.mid, "%04.1f" % game.time_left, (w // 2, 30), tcol, center=True)
        self.text(self.font, "SCORE %07d" % game.score, (20, 16))
        self.text(self.font, "GATE %d" % game.level, (20, 44))
        self.speedo.draw(self.screen, (w - SPEEDO_W - 8, self.h - SPEEDO_H - 8), game)
        prog = (game.sled_z / SEG % GATE_SEGS) / GATE_SEGS
        pygame.draw.rect(self.screen, (40, 44, 70), (w // 2 - 150, 56, 300, 8))
        pygame.draw.rect(self.screen, (255, 255, 160), (w // 2 - 150, 56, int(300 * prog), 8))
        if game.msg[1] > 0:
            self.text(self.mid, game.msg[0], (w // 2, 120), (255, 255, 160), center=True)

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
        """The title and the prompt to start, alpha from 0 (gone) to 255."""
        if self.title_layer is None:
            self.title_layer = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            screen, self.screen = self.screen, self.title_layer
            mid = self.w // 2
            self.text(self.big, "NEON CONDUIT", (mid, 62), (255, 80, 160), center=True)
            self.text(self.mid, "Press ENTER to start", (mid, self.h - 44), center=True)
            self.screen = screen
        self.title_layer.set_alpha(alpha)
        self.screen.blit(self.title_layer, (0, 0))

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
        else:
            self.text(self.big, "PAUSED", (mid, 250), center=True)
            lines = []
        for i, s in enumerate(lines):
            self.text(self.font, s, (mid, 280 + i * 32), center=True)
