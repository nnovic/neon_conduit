"""The window, the main loop and the command line."""
import argparse

import pygame

from .audio import Audio
from .config import FOCAL, HORIZON, SCREEN
from .game import Controls, Game
from .hud import Hud
from .render import Renderer


def read_controls(keys, fire):
    """Controls from the keyboard state (arrows or A / D / S); fire: Space was pressed this frame."""
    steer = (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a])
    return Controls(steer, keys[pygame.K_DOWN] or keys[pygame.K_s], fire)


class App:
    def __init__(self, seed=None, size=SCREEN, focal=FOCAL, horizon=HORIZON):
        pygame.init()
        pygame.display.set_caption("Neon Conduit")
        self.screen = pygame.display.set_mode(size)
        self.clock = pygame.time.Clock()
        self.game = Game(seed, Audio())
        self.renderer = Renderer(self.screen, focal, horizon)
        self.hud = Hud(self.screen)
        self.paused = False

    def draw(self):
        game = self.game
        self.renderer.draw(game)
        self.hud.draw(game)
        if game.state != "play" or self.paused:
            self.hud.overlay(game)

    def run(self, frames=None, screenshot=None):
        """Play until the window closes; with frames, self-play that many frames and stop."""
        game = self.game
        auto = frames is not None
        if auto:
            game.state = "play"
        count = 0
        while True:
            dt = 1 / 60 if auto else min(0.05, self.clock.tick(60) / 1000.0)
            fire = False                # one shot per Space press, holding it does not auto-fire
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    return
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        return
                    if ev.key == pygame.K_SPACE:
                        fire = True
                    if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and game.state != "play":
                        game.reset()
                        game.state = "play"
                        self.paused = False
                    elif ev.key == pygame.K_p and game.state == "play":
                        self.paused = not self.paused
            if game.state == "play" and not self.paused:
                game.update(dt, game.autopilot() if auto else read_controls(pygame.key.get_pressed(), fire))
            self.draw()
            pygame.display.flip()
            count += 1
            if frames is not None and count >= frames:
                if screenshot:
                    pygame.image.save(self.screen, screenshot)
                return


def main():
    ap = argparse.ArgumentParser(description="Neon Conduit - tunnel racer")
    ap.add_argument("--seed", type=int, help="fixed track seed")
    ap.add_argument("--frames", type=int, help="self-play this many frames, then exit (for testing)")
    ap.add_argument("--screenshot", help="with --frames, save the last frame to this file")
    args = ap.parse_args()
    app = App(args.seed)
    try:
        app.run(args.frames, args.screenshot)
    finally:
        pygame.quit()
