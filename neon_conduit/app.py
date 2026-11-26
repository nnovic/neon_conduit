"""The window, the main loop and the command line."""
import argparse
import time

import pygame

from .audio import Audio
from .config import FOCAL, HORIZON, SCREEN, TITLE_MUSIC, TITLE_MUSIC_FADE, TITLE_MUSIC_VOLUME
from .game import Controls, Game
from .hud import Hud
from .render import Renderer
from .title import TitleFlag, TitleTunnel, ease

LAUNCH_MOVE = 1.6               # seconds the title's tunnel takes to glide into the game's view...
LAUNCH_FADE = 0.8               # ...and the title then takes to fade into the game
# The title menu's game modes: name and what it is.
MODES = (("VOYAGE", "An endless track, new every race: reach each gate before the clock runs out"),)


def read_controls(keys, fire):
    """Controls from the keyboard state (arrows or A / D); fire: Space was pressed this frame.

    Shots leave along the track's slope; Down raises the guns above it, Up lowers them.
    """
    steer = (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a])
    aim = keys[pygame.K_DOWN] - keys[pygame.K_UP]
    return Controls(steer, fire, aim)


class App:
    def __init__(self, seed=None, size=SCREEN, focal=FOCAL, horizon=HORIZON, fullscreen=False, show_fps=False,
                 course=None, start_seg=0):
        pygame.init()
        pygame.display.set_caption("Neon Conduit")
        # SCALED: the game always draws at size; pygame blows it up to fill the screen in
        # full screen (keeping its shape, with black bars if need be).
        flags = pygame.SCALED | (pygame.FULLSCREEN if fullscreen else 0)
        self.screen = pygame.display.set_mode(size, flags)
        pygame.mouse.set_visible(not fullscreen)
        self.clock = pygame.time.Clock()
        self.audio = Audio()
        self.game = Game(seed, self.audio, course, start_seg)
        self.renderer = Renderer(self.screen, focal, horizon)
        self.hud = Hud(self.screen)
        self.title = TitleFlag(self.screen)
        r = self.renderer
        self.title_tunnel = TitleTunnel(self.screen, (r.focal, r.cx, r.cy))
        self.title_t = 0.0          # clock of the title screen's flag and tunnel
        self.launch_t = None        # time since ENTER on the title, while it turns into the game
        self.mode = 0               # the game mode selected in the title menu, in MODES
        self.paused = False
        self.show_fps = show_fps    # F3: frames per second and the work each frame takes
        self.work_ms = 0.0          # milliseconds of game update and drawing per frame, smoothed
        self.fps_font = pygame.font.Font(None, 24)

    def draw_fps(self):
        """Top right: frames per second, and how many milliseconds of the 16.7 a frame has at
        60 fps go to updating and drawing the game (the rest is spent waiting)."""
        s = "%3.0f fps   %4.1f ms" % (self.clock.get_fps(), self.work_ms)
        col = (120, 255, 160) if self.work_ms < 12 else (255, 200, 60) if self.work_ms < 16.7 else (255, 70, 60)
        img = self.fps_font.render(s, True, col)
        r = img.get_rect(topright=(self.screen.get_width() - 12, 12))
        self.screen.fill((0, 0, 0), r.inflate(10, 6))
        self.screen.blit(img, r)

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
            self.hud.title_menu(MODES, self.mode, self.title_t)
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
        self.hud.title_menu(MODES, self.mode, self.title_t, int(255 * (1 - u)))
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
        elif game.course:                   # a level: straight to its start line
            game.state = "brief"
        else:
            self.audio.music(TITLE_MUSIC, TITLE_MUSIC_VOLUME, TITLE_MUSIC_FADE)
        count = 0
        while True:
            ms = self.clock.tick() if auto else self.clock.tick(60)   # self-play runs flat out
            dt = 1 / 60 if auto else min(0.05, ms / 1000.0)
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
                    if ev.key == pygame.K_F3:
                        self.show_fps = not self.show_fps
                        continue
                    if self.launch_t is not None:         # nothing to do while it plays
                        continue
                    if ev.key == pygame.K_TAB and game.state in ("brief", "play"):
                        game.skip_tutorial()               # skip the tutorial (first race, until its door)
                    if game.state == "brief":            # any key sets the racer off...
                        self.start(False)
                        continue                           # ...and does nothing else
                    if game.state == "title" and ev.key in (pygame.K_LEFT, pygame.K_RIGHT):
                        self.mode = (self.mode + (1 if ev.key == pygame.K_RIGHT else -1)) % len(MODES)
                        continue
                    if ev.key == pygame.K_SPACE:
                        fire = True
                    if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and game.state != "play":
                        if game.state == "title":         # off to the start line (Voyage, the only mode yet)
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
            t0 = time.perf_counter()
            if game.state == "play" and not self.paused:
                game.update(dt, game.autopilot() if auto else read_controls(pygame.key.get_pressed(), fire))
            self.draw()
            self.work_ms += ((time.perf_counter() - t0) * 1000 - self.work_ms) * 0.05
            if self.show_fps:
                self.draw_fps()
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
    ap.add_argument("--fps", action="store_true", help="show frames per second and frame time (F3 toggles it)")
    ap.add_argument("--level", metavar="FILE", help="race a hand-made level (see edit_level.py) to its finish line")
    ap.add_argument("--from", dest="start_seg", type=int, default=0, metavar="SEG",
                    help="with --level, start at this segment of it")
    args = ap.parse_args()
    course = None
    if args.level:
        from .level import LevelError, load
        try:
            course = load(args.level)
        except (OSError, LevelError) as e:
            ap.exit(1, "Can't race %s: %s\n" % (args.level, e))
    app = App(args.seed, fullscreen=args.fullscreen, show_fps=args.fps, course=course, start_seg=args.start_seg)
    try:
        app.run(args.frames, args.screenshot)
    finally:
        pygame.quit()
