"""Head-up display and the title, game-over and pause screens."""
import pygame

from .config import GATE_SEGS, SEG
from .speedo import H as SPEEDO_H, W as SPEEDO_W, Speedo

TEXT = (235, 240, 255)


class Hud:
    def __init__(self, screen):
        self.screen = screen
        self.w, self.h = screen.get_size()
        self.font = pygame.font.Font(None, 30)
        self.big = pygame.font.Font(None, 84)
        self.mid = pygame.font.Font(None, 44)
        self.speedo = Speedo()

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

    def overlay(self, game):
        """Darkened screen with the title, game-over or pause text, depending on game.state."""
        veil = pygame.Surface((self.w, self.h))
        veil.set_alpha(150)
        self.screen.blit(veil, (0, 0))
        mid = self.w // 2
        if game.state == "title":
            self.text(self.big, "NEON CONDUIT", (mid, 190), (255, 80, 160), center=True)
            lines = ["Reach each gate before the clock runs out.",
                     "Follow the stars round the outside of bends, or you lose speed.",
                     "",
                     "Left / Right  steer      Up / Down  aim      S  brake      Space  fire",
                     "P  pause      Esc  quit",
                     "",
                     "Press ENTER to start"]
        elif game.state == "over":
            self.text(self.big, "TIME UP", (mid, 190), (255, 70, 60), center=True)
            lines = ["Score %d     Gates %d" % (game.score, game.level),
                     "Best %d" % game.best, "", "Press ENTER to race again"]
        else:
            self.text(self.big, "PAUSED", (mid, 250), center=True)
            lines = []
        for i, s in enumerate(lines):
            self.text(self.font, s, (mid, 280 + i * 32), center=True)
