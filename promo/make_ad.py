#!/usr/bin/env python3
"""Render a short vertical promo video (1080x1920, 30 fps) for social networks.

Footage comes straight from the game: its title screen, then the engine driven by
its auto-pilot, and the pattern editor at work; captions and cuts are added on top.
The video is silent. Encoding uses GStreamer (gst-launch-1.0 with x264enc and mp4mux).

    python3 promo/make_ad.py [-o promo/neon_conduit_ad.mp4] [--preview DIR] [--only SCENE ...]
"""
import argparse
import math                       # noqa: F401  (the commented-out call to action uses it)
import os
import random
import subprocess
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import pygame                                                      # noqa: E402
from neon_conduit import Track                                     # noqa: E402
from neon_conduit import patterns as P                             # noqa: E402
from neon_conduit import track as track_module                     # noqa: E402
from neon_conduit.app import App                                   # noqa: E402
from neon_conduit.config import BOOST_MULT, GATE_SEGS, PLAYER_D, SEG   # noqa: E402
from neon_conduit.speedo import H as SPEEDO_H, W as SPEEDO_W       # noqa: E402
from neon_conduit.title import TitleFlag                           # noqa: E402

VW, VH, FPS = 1080, 1920, 30
STEPS = 2                         # physics steps (at 60 Hz) per video frame
SEED = 3
LEVEL = 9                         # ride at a later gate's speed and drone count
BPM = 120                         # the cuts keep to a beat, though the video is silent
BEAT = 60.0 / BPM
# Beats per scene, in order.
SCENES = (("intro", 5), ("hook", 6), ("tunnels", 8), ("outdoors", 6), ("sky", 6), ("door", 5),
          ("drones", 6), ("gate", 7), ("editor", 8), ("end_card", 8))

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-BoldOblique.ttf"
PINK = (255, 60, 170)
CYAN = (70, 230, 255)
GREEN = (110, 255, 150)
WHITE = (255, 255, 255)
PORTRAIT = {"size": (VW, VH), "focal": 760.0, "horizon": 0.5}   # same engine, taller screen


# ------------------------------------------------------------------ world
def world(drones=False):
    """A fresh, fully generated track (each clip gets its own, untouched by the others).
    Drones are cleared unless asked for: a crash would kill the shot."""
    tr = Track(random.Random(SEED))
    tr.ensure(6000, LEVEL)
    if not drones:
        tr.objects = [o for o in tr.objects if o["kind"] != "drone"]
    return tr


def runs_of(tr, want, lo=1, hi=6000):
    """(start, end) segment ranges where want(tr, i) holds all along."""
    out, start = [], None
    for i in range(lo, hi):
        if want(tr, i) and start is None:
            start = i
        elif not want(tr, i) and start is not None:
            out.append((start, i))
            start = None
    return out


def indoor(tr, i):
    return not tr.outdoor(i)


def ground(tr, i):
    return tr.open[i]


def air(tr, i):
    return tr.air[i]


def place(g, tr, seg, speed_mult=1.0):
    """Drop the sled onto track tr with its nose at segment seg, already at speed."""
    g.reset()
    g.state = "play"
    g.track = tr
    g.level = LEVEL
    g.cam_z = seg * SEG - PLAYER_D
    g.theta = g.roll = tr.line(seg)
    g.flat = 1.0 if tr.open[seg] else 0.0
    g.speed = g.max_speed * speed_mult
    g.time_left = 99.0


def step(g, shoot=False):
    for _ in range(STEPS):
        if not shoot:
            g.cooldown = 1e9
            g.bullets = []
        g.update(1.0 / (FPS * STEPS), g.autopilot())


# ------------------------------------------------------------------ text
class Text:
    def __init__(self):
        self.fonts = {}

    def font(self, size):
        if size not in self.fonts:
            self.fonts[size] = pygame.font.Font(FONT, size)
        return self.fonts[size]

    def neon(self, s, size, col, glow=None):
        """Text with a soft coloured glow, as one surface."""
        f = self.font(size)
        core = f.render(s, True, WHITE if glow is None else col)
        glow = glow or col
        pad = size // 2
        w, h = core.get_width() + 2 * pad, core.get_height() + 2 * pad
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        halo = pygame.Surface((w, h), pygame.SRCALPHA)
        halo.blit(f.render(s, True, glow), (pad, pad))
        for k in (6, 12):
            b = pygame.transform.smoothscale(pygame.transform.smoothscale(halo, (w // k, h // k)), (w, h))
            surf.blit(b, (0, 0))
            surf.blit(b, (0, 0))
        shadow = f.render(s, True, (0, 0, 0))
        shadow.set_alpha(160)
        surf.blit(shadow, (pad + 5, pad + 7))
        surf.blit(core, (pad, pad))
        return surf


def ease_out(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def blit_pop(scr, surf, centre, age, life, pop=0.18):
    """Blit surf centred, popping in (scale + fade) and fading out at the end of its life."""
    if age < 0 or age > life:
        return
    k = 1.0 + 0.35 * (1 - ease_out(age / pop))
    a = min(1.0, age / 0.08, (life - age) / 0.12)
    s = surf
    if abs(k - 1.0) > 0.01:
        s = pygame.transform.smoothscale(surf, (int(surf.get_width() * k), int(surf.get_height() * k)))
    s.set_alpha(int(255 * a))
    scr.blit(s, s.get_rect(center=centre))
    surf.set_alpha(255)


# ------------------------------------------------------------------ clips
class Ad:
    def __init__(self, out_pipe, preview):
        pygame.init()
        app = App(SEED, **PORTRAIT)
        self.app = app
        self.g = app.game
        self.renderer = app.renderer            # world only: the ad draws its own overlays
        self.scr = app.screen
        self.speedo_surf = pygame.Surface((SPEEDO_W + 16, SPEEDO_H + 16), pygame.SRCALPHA)
        self.txt = Text()
        self.pipe = out_pipe
        self.preview = preview
        self.frame = 0
        self.flash = 0

    def emit(self):
        if self.flash > 0:
            veil = pygame.Surface((VW, VH))
            veil.fill(WHITE)
            veil.set_alpha(int(150 * self.flash / 3))
            self.scr.blit(veil, (0, 0))
            self.flash -= 1
        if self.pipe:
            self.pipe.write(pygame.image.tobytes(self.scr, "RGB"))
        if self.preview and self.frame % 15 == 7:
            pygame.image.save(self.scr, os.path.join(self.preview, "f%04d.png" % self.frame))
        self.frame += 1

    def cut(self):
        self.flash = 3

    def vignette(self):
        """Darken the top and bottom bands a little so captions read over anything."""
        if not hasattr(self, "_vig"):
            v = pygame.Surface((VW, VH), pygame.SRCALPHA)
            for y in range(VH):
                d = min(y / (VH * 0.32), (VH - y) / (VH * 0.2), 1.0)
                pygame.draw.line(v, (0, 0, 10, int(150 * (1 - d) ** 1.5)), (0, y), (VW, y))
            self._vig = v
        self.scr.blit(self._vig, (0, 0))

    def speedo(self, centre, scale):
        """The game's own speedometer, blown up to read on a phone."""
        s = self.speedo_surf
        s.fill((0, 0, 0, 0))
        self.app.hud.speedo.draw(s, (8, 8), self.g)
        big = pygame.transform.smoothscale(s, (int(s.get_width() * scale), int(s.get_height() * scale)))
        self.scr.blit(big, big.get_rect(center=centre))

    def ride(self, secs, captions=(), shoot=False, overlay=None, clock=False, speedo=True):
        """Play the game for secs; captions are (surface, start, life, y) in clip time."""
        n = int(round(secs * FPS))
        for f in range(n):
            t = f / FPS
            step(self.g, shoot)
            self.g.time_left = max(self.g.time_left, 0.5) if clock else 99.0
            self.renderer.draw(self.g)
            self.vignette()
            if speedo:
                self.speedo((VW // 2, VH - 110), 1.9)
            for surf, start, life, y in captions:
                blit_pop(self.scr, surf, (VW // 2, y), t - start, life)
            if overlay:
                overlay(t)
            self.emit()

    # -------------------------------------------------------------- scenes
    def intro(self, beats):
        """The game's title screen: the waving flag, the wireframe tunnel turning in front
        of it. (How it turns into the race stays a surprise for the game itself.)"""
        app, scr, t = self.app, self.scr, self.txt
        flag = TitleFlag(scr)
        flag.f = 1400.0                         # zoomed in, so the flag fills the tall screen too
        logo1, logo2 = t.neon("NEON", 230, PINK), t.neon("CONDUIT", 170, CYAN)
        enter = t.neon("PRESS ENTER", 80, WHITE, glow=PINK)
        for f in range(int(round(beats * BEAT * FPS))):
            tc = f / FPS
            flag.draw(tc)
            app.hud.title_band()
            app.title_tunnel.draw(tc)
            blit_pop(scr, logo1, (VW // 2, 330), tc - 0.1, 99)
            blit_pop(scr, logo2, (VW // 2, 520), tc - 0.3, 99)
            if tc > 0.9 and int(tc * 2.5) % 2 == 0:
                scr.blit(enter, enter.get_rect(center=(VW // 2, VH - 300)))
            self.emit()

    def hook(self, beats):
        """Off the start line, on boost."""
        g = self.g
        g.reset()
        g.state = "play"
        g.level = LEVEL
        g.track.tube_styles[g.track.stretch[0]] = "checker"    # the title flag's own weave
        g.time_left = 99.0
        g.boost = 99.0
        t = self.txt
        caps = [(t.neon("GAIN", 150, PINK), 0.0, 3.0, 400),
                (t.neon("SPEED", 230, PINK), 0.5, 2.5, 580)]
        self.cut()
        self.ride(beats * BEAT, caps, speedo=False, overlay=lambda _: self.speedo((VW // 2, VH - 150), 2.3))
        g.boost = 0.0

    def tunnels(self, beats):
        cap = self.txt.neon("HYPNOTIC", 150, CYAN)
        cap2 = self.txt.neon("TUNNELS", 150, CYAN)
        tr = world()
        stretches = [r for r in runs_of(tr, indoor, 40) if r[1] - r[0] > 60]
        styles = ("bloom", "tunnel", "chevron", "whirl")
        each = beats / len(styles)
        for k, style in enumerate(styles):
            tr = world()
            a, _ = stretches[k + 1]
            tr.tube_styles[tr.stretch[a]] = style
            place(self.g, tr, a + 6)
            self.cut()
            off = k * each * BEAT
            self.ride(each * BEAT, [(cap, -off, beats * BEAT, 380), (cap2, -off, beats * BEAT, 540)])

    def outdoors(self, beats):
        """Out of the tube on to a wide road, a city panorama all round."""
        tr = world()
        runs = runs_of(tr, ground, 40)
        city = [r for r in runs if tr.outdoor_theme(r[0]) == "metropolis"]
        a, b = max(city or runs, key=lambda r: max(tr.width[r[0]:r[1]]))
        place(self.g, tr, a - 22)
        self.cut()
        t = self.txt
        self.ride(beats * BEAT, [(t.neon("BREAK OUT", 140, GREEN), 0.4, 2.6, 380),
                                 (t.neon("INTO THE OPEN", 120, GREEN), 0.4, 2.6, 530)])

    def sky(self, beats):
        """Into a see-through tube high above a planet."""
        tr = world()
        a, b = max(runs_of(tr, air, 40), key=lambda r: r[1] - r[0])
        place(self.g, tr, a - 12)
        self.cut()
        t = self.txt
        violet = (190, 120, 255)
        self.ride(beats * BEAT, [(t.neon("RIDE", 150, violet), 0.3, 2.7, 380),
                                 (t.neon("THE SKY", 150, violet), 0.3, 2.7, 540)])

    def door(self, beats):
        tr = world()
        doors = [i for i in range(80, 6000) if tr.is_door(i) and all(tr.open[i - 70:i])]
        d = doors[1] if len(doors) > 1 else doors[0]
        tr.tube_styles[tr.stretch[d]] = "whirl"
        place(self.g, tr, d - 50)
        self.cut()
        t = self.txt
        self.ride(beats * BEAT, [(t.neon("THEN DIVE", 140, PINK), 0.0, 2.5, 380),
                                 (t.neon("BACK IN", 140, PINK), 0.0, 2.5, 530)])

    def drones(self, beats):
        best, best_kills = None, -1
        for start in range(60, 3000, 12):
            tr = world(drones=True)
            if any(tr.outdoor(i) for i in range(start, start + 90)):
                continue
            ahead = [o for o in tr.objects if o["kind"] == "drone" and start * SEG < o["z"] < start * SEG + 450]
            if len(ahead) < 3:
                continue
            place(self.g, tr, start)
            kills = 0
            for _ in range(int(beats * BEAT * FPS)):
                s0 = self.g.score
                step(self.g, shoot=True)
                kills += (self.g.score - s0) >= 500
            if kills > best_kills:
                best, best_kills = start, kills
        print("drones clip: %d kills" % best_kills)
        tr = world(drones=True)
        tr.tube_styles[tr.stretch[best]] = "chevron_alt"
        place(self.g, tr, best)
        self.cut()
        t = self.txt
        orange = (255, 150, 40)
        self.ride(beats * BEAT, [(t.neon("BLAST", 160, orange), 0.0, 3.0, 380),
                                 (t.neon("THE DRONES", 130, orange), 0.0, 3.0, 540)], shoot=True)

    def gate(self, beats):
        tr = world()
        gates = [k * GATE_SEGS for k in range(1, 20) if not tr.outdoor(k * GATE_SEGS)]
        gz = gates[1]
        tr.tube_styles[tr.stretch[gz]] = "pulse"
        place(self.g, tr, gz - 44)
        self.g.time_left = 3.9
        lvl0 = self.g.level
        self.cut()
        t = self.txt
        passed = {}

        def clock(tc):
            g = self.g
            if g.level > lvl0 and "t" not in passed:
                passed["t"] = tc
            low = "t" not in passed
            col = (255, 70, 60) if low and int(tc * 6) % 2 else WHITE
            s = t.neon("%04.1f" % g.time_left, 170, col, glow=(255, 70, 60) if low else GREEN)
            self.scr.blit(s, s.get_rect(center=(VW // 2, 760)))
            if not low:
                bonus = max(11.0, 16.0 - 0.6 * g.level)          # as in Game.update
                blit_pop(self.scr, t.neon("+%d s" % bonus, 130, GREEN), (VW // 2, 930), tc - passed["t"], 9.0)

        self.ride(beats * BEAT, [(t.neon("BEAT THE", 140, WHITE, glow=PINK), 0.0, 3.5, 380),
                                 (t.neon("CLOCK", 170, WHITE, glow=PINK), 0.0, 3.5, 540)],
                  overlay=clock, clock=True)

    def editor(self, beats):
        """The pattern editor: a new pattern painted cell by cell, the tunnel in its
        preview taking it on as it goes."""
        from neon_conduit import editor as E
        saved = dict(P.BY_NAME), track_module.OPEN_CHANCE
        set_mode = pygame.display.set_mode
        pygame.display.set_mode = lambda size, *a, **k: pygame.Surface(size)   # keep the ad's screen
        try:
            ed = E.Editor()
        finally:
            pygame.display.set_mode = set_mode
        target = P.BY_NAME["chevron"].texts
        ed.patterns.insert(len(ed.patterns), P.Pattern("my_tunnel", ["." * P.WIDTH] * len(target)))
        ed.register()
        ed.select(len(ed.patterns) - 1)
        ed.zone = 0
        ed.set_zone()                           # the violet zone (set_zone steps to the next)
        ed.new_preview()
        ed.paused = False
        # Paint near rows first, one brush at a time within each row.
        cells = [(r, c, target[r][c]) for r in range(len(target) - 1, -1, -1)
                 for c in sorted(range(P.WIDTH), key=lambda c: target[r][c]) if target[r][c] != "."]
        n = int(round(beats * BEAT * FPS))
        lead, per = 12, 3                         # frames before the first dab, frames per dab
        t = self.txt
        cap1, cap2 = t.neon("DESIGN YOUR", 120, CYAN), t.neon("OWN TUNNELS", 120, CYAN)
        scale = VW / E.W
        ew, eh = VW, int(E.H * scale)
        pv = E.PREVIEW
        pw = 900
        ph = int(pv.h * pw / pv.w)
        bg = E.BG
        cursor = [(0, 0), (0, 22), (6, 17), (11, 27), (15, 25), (10, 16), (17, 16)]
        pos = (E.GRID.centerx, E.GRID.bottom)
        self.cut()
        try:
            for f in range(n):
                tc = f / FPS
                k = (f - lead) // per
                if f >= lead and (f - lead) % per == 0 and k < len(cells):
                    r, c, ch = cells[k]
                    ed.brush = ch
                    ed.paint(r, c, ch)
                if f >= lead and k < len(cells):
                    r, c, _ = cells[min(k + 1, len(cells) - 1)]
                    goal = (E.GRID.x + c * E.CELL + E.CELL // 2, E.GRID.y + (r - ed.grid_top) * E.CELL + E.CELL // 2)
                    pos = (pos[0] + (goal[0] - pos[0]) * 0.5, pos[1] + (goal[1] - pos[1]) * 0.5)
                for _ in range(STEPS):
                    ed.step_preview(1.0 / (FPS * STEPS))
                ed.draw()
                pygame.draw.polygon(ed.screen, WHITE, [(pos[0] + x, pos[1] + y) for x, y in cursor])
                pygame.draw.polygon(ed.screen, (0, 0, 0), [(pos[0] + x, pos[1] + y) for x, y in cursor], 2)
                self.scr.fill(bg)
                y0 = 600
                self.scr.blit(pygame.transform.smoothscale(ed.screen, (ew, eh)), (0, y0))
                big = pygame.transform.smoothscale(ed.preview_surface, (pw, ph))
                box = big.get_rect(midtop=(VW // 2, y0 + eh + 40))
                self.scr.blit(big, box)
                pygame.draw.rect(self.scr, PINK, box.inflate(8, 8), 4, border_radius=6)
                blit_pop(self.scr, cap1, (VW // 2, 300), tc, 99)
                blit_pop(self.scr, cap2, (VW // 2, 440), tc - 0.2, 99)
                self.emit()
        finally:
            P.BY_NAME.clear()
            P.BY_NAME.update(saved[0])
            track_module.OPEN_CHANCE = saved[1]

    def end_card(self, beats):
        t = self.txt
        logo1 = t.neon("NEON", 230, PINK)
        logo2 = t.neon("CONDUIT", 170, CYAN)
        tag = t.neon("How fast can you go?", 70, WHITE, glow=CYAN)
        # cta = t.neon("PLAY NOW", 96, WHITE, glow=PINK)       # call to action: back once there's somewhere to play
        n = int(beats * BEAT * FPS)
        dim = pygame.Surface((VW, VH))
        dim.fill((4, 4, 16))
        self.cut()
        for f in range(n):
            tc = f / FPS
            step(self.g)
            self.g.time_left = 99.0
            self.renderer.draw(self.g)
            dim.set_alpha(int(200 * ease_out(tc / 0.6)))
            self.scr.blit(dim, (0, 0))
            blit_pop(self.scr, logo1, (VW // 2, 720), tc - 0.15, 99)
            blit_pop(self.scr, logo2, (VW // 2, 900), tc - 0.35, 99)
            blit_pop(self.scr, tag, (VW // 2, 1060), tc - 0.8, 99)
            # if tc > 1.4:
            #     pulse = 1.0 + 0.05 * math.sin((tc - 1.4) * math.pi * 2 / BEAT)
            #     w, h = int(560 * pulse), int(150 * pulse)
            #     box = pygame.Rect(0, 0, w, h)
            #     box.center = (VW // 2, 1400)
            #     pygame.draw.rect(self.scr, PINK, box, 6, border_radius=h // 2)
            #     blit_pop(self.scr, cta, box.center, tc - 1.4, 99)
            if tc > n / FPS - 0.5:                         # fade to black
                veil = pygame.Surface((VW, VH))
                veil.set_alpha(int(255 * (tc - (n / FPS - 0.5)) / 0.5))
                self.scr.blit(veil, (0, 0))
            self.emit()

    def run(self, only=None):
        for name, beats in SCENES:
            if only and name not in only:
                continue
            getattr(self, name)(beats)
        return self.frame / FPS


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "neon_conduit_ad.mp4"))
    ap.add_argument("--preview", help="also save every 15th frame as PNG into this folder")
    ap.add_argument("--only", nargs="+", choices=[n for n, _ in SCENES],
                    help="render only these scenes (a draft)")
    args = ap.parse_args()
    out = os.path.abspath(args.out)
    if args.preview:
        os.makedirs(args.preview, exist_ok=True)

    enc = subprocess.Popen(
        ["gst-launch-1.0", "-q", "-e",
         "fdsrc", "fd=0", "!",
         "rawvideoparse", "width=%d" % VW, "height=%d" % VH, "format=rgb", "framerate=%d/1" % FPS, "!",
         "videoconvert", "!", "video/x-raw,format=I420", "!",
         "x264enc", "speed-preset=slow", "bitrate=9000", "key-int-max=60", "!",
         "video/x-h264,profile=high", "!",
         "mp4mux", "faststart=true", "!", "filesink", "location=" + out],
        stdin=subprocess.PIPE)
    random.seed(0)                 # the sled's flame flicker uses the global generator
    secs = Ad(enc.stdin, args.preview).run(args.only)
    enc.stdin.close()
    if enc.wait():
        sys.exit("encoding failed")
    print("wrote %s (%.1f s)" % (out, secs))


if __name__ == "__main__":
    main()
