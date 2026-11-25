"""The window, the main loop and the command line."""
import argparse

import pygame

from .audio import Audio
from .config import FOCAL, HORIZON, SCREEN, TITLE_MUSIC, TITLE_MUSIC_FADE, TITLE_MUSIC_VOLUME
from .game import Controls, Game
from .hud import Hud
from .render import Renderer
from .title import TitleFlag, TitleTunnel, ease

LAUNCH_MOVE = 1.6               # seconds the title's tunnel takes to glide into the game's view...
LAUNCH_FADE = 0.8               # ...and the title then takes to fade into the game


def read_controls(keys, fire):
    """Controls from the keyboard state (arrows or A / D); fire: Space was pressed this frame.

    Shots leave along the track's slope; Down raises the guns above it, Up lowers them.
    """
    steer = (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a])
    aim = keys[pygame.K_DOWN] - keys[pygame.K_UP]
    return Controls(steer, fire, aim)


class App:
    def __init__(self, seed=None, size=SCREEN, focal=FOCAL, horizon=HORIZON, fullscreen=False):
        pygame.init()
        pygame.display.set_caption("Neon Conduit")
        # SCALED: the game always draws at size; pygame blows it up to fill the screen in
        # full screen (keeping its shape, with black bars if need be).
        flags = pygame.SCALED | (pygame.FULLSCREEN if fullscreen else 0)
        self.screen = pygame.display.set_mode(size, flags)
        pygame.mouse.set_visible(not fullscreen)
        self.clock = pygame.time.Clock()
        self.audio = Audio()
        self.game = Game(seed, self.audio)
        self.renderer = Renderer(self.screen, focal, horizon)
        self.hud = Hud(self.screen)
        self.title = TitleFlag(self.screen)
        r = self.renderer
        self.title_tunnel = TitleTunnel(self.screen, (r.focal, r.cx, r.cy))
        self.title_t = 0.0          # clock of the title screen's flag and tunnel
        self.launch_t = None        # time since ENTER on the title, while it turns into the game
        self.paused = False

    def start(self, reset=True):
        """Set the racer off; reset: on a fresh track (it already is after the briefing)."""
        if reset:
            self.game.reset()
        self.game.state = "play"
        self.paused = False

    def draw(self):
        game = self.game
        if self.launch_t is not None:
            self.draw_launch()
            return
        if game.state == "title":
            self.title.draw(self.title_t)
            # The tunnel goes over the darkened middle, so it stands out, but under the text.
            self.hud.overlay(game, lambda: self.title_tunnel.draw(self.title_t))
            self.hud.credits(self.title_t)
            return
        self.renderer.draw(game)
        self.hud.draw(game)
        if game.veil > 0:                   # skipping the tutorial: a fade to black and back
            veil = pygame.Surface(self.screen.get_size())
            veil.set_alpha(int(255 * game.veil))
            self.screen.blit(veil, (0, 0))
        if game.state == "brief":
            self.hud.brief()
            return
        if game.state != "play" or self.paused:
            self.hud.overlay(game)

    def draw_launch(self):
        """From the title into the game: the flag darkens and the text fades while the
        tunnel glides into the game's view; then the game fades in under it."""
        s, scr = self.launch_t, self.screen
        u = ease(s / LAUNCH_MOVE)
        self.title.draw(self.title_t)
        self.hud.title_band()
        veil = pygame.Surface(scr.get_size())
        veil.set_alpha(int(235 * u))
        scr.blit(veil, (0, 0))
        self.title_tunnel.draw(self.title_t, u)
        self.hud.title_text(int(255 * (1 - u)))
        self.hud.credits(self.title_t, int(255 * (1 - u)))
        if s > LAUNCH_MOVE:
            title = scr.copy()
            self.renderer.draw(self.game)
            self.hud.draw(self.game)
            title.set_alpha(int(255 * (1 - ease((s - LAUNCH_MOVE) / LAUNCH_FADE))))
            scr.blit(title, (0, 0))

    def toggle_fullscreen(self):
        pygame.display.toggle_fullscreen()
        pygame.mouse.set_visible(not pygame.display.is_fullscreen())

    def run(self, frames=None, screenshot=None):
        """Play until the window closes; with frames, self-play that many frames and stop."""
        game = self.game
        auto = frames is not None
        if auto:
            game.state = "play"
        else:
            self.audio.music(TITLE_MUSIC, TITLE_MUSIC_VOLUME, TITLE_MUSIC_FADE)
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
                    if ev.key == pygame.K_F11:
                        self.toggle_fullscreen()
                        continue
                    if self.launch_t is not None:         # nothing to do while it plays
                        continue
                    if ev.key == pygame.K_TAB and game.state in ("brief", "play"):
                        game.skip_tutorial()               # skip the tutorial (first race, until its door)
                    if game.state == "brief":            # any key sets the racer off...
                        self.start(False)
                        continue                           # ...and does nothing else
                    if ev.key == pygame.K_SPACE:
                        fire = True
                    if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and game.state != "play":
                        if game.state == "title":         # off to the start line
                            game.reset()
                            self.launch_t = 0.0
                            self.title_tunnel.depart(self.title_t)
                            self.audio.stop_music(LAUNCH_MOVE + LAUNCH_FADE)   # gone by the start line
                        else:
                            self.start()
                    elif ev.key == pygame.K_p and game.state == "play":
                        self.paused = not self.paused
            self.title_t += dt
            if self.launch_t is not None:
                self.launch_t += dt
                if self.launch_t >= LAUNCH_MOVE + LAUNCH_FADE:   # there: briefing up
                    self.launch_t = None
                    self.title_tunnel.yaw0 = None
                    game.state = "brief"
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
    ap.add_argument("--fullscreen", action="store_true", help="start in full screen (F11 toggles it)")
    args = ap.parse_args()
    app = App(args.seed, fullscreen=args.fullscreen)
    try:
        app.run(args.frames, args.screenshot)
    finally:
        pygame.quit()
