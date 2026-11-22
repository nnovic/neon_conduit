#!/usr/bin/env python3
"""Render a short vertical promo video (1080x1920, 30 fps) for social networks.

Footage comes straight from the game engine, driven by its auto-pilot; captions,
cuts and a synthwave soundtrack are added on top. Encoding uses GStreamer
(gst-launch-1.0 with x264enc, avenc_aac and mp4mux).

    python3 promo/make_ad.py [-o promo/neon_conduit_ad.mp4] [--preview DIR]
"""
import argparse
import math
import os
import random
import struct
import subprocess
import sys
import wave

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import pygame                                                      # noqa: E402
from neon_conduit import Track                                     # noqa: E402
from neon_conduit.app import App                                   # noqa: E402
from neon_conduit.config import BOOST_MULT, GATE_SEGS, PLAYER_D, SEG   # noqa: E402

VW, VH, FPS = 1080, 1920, 30
STEPS = 2                         # physics steps (at 60 Hz) per video frame
SEED = 3
LEVEL = 9                         # ride at a later gate's speed and drone count
BPM = 120
BEAT = 60.0 / BPM
TOTAL_BEATS = 6 + 8 + 6 + 5 + 6 + 7 + 8      # hook, tunnels, outdoors, door, drones, gate, end card

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


def runs_of(tr, want_open, lo=1, hi=6000):
    """(start, end) segment ranges that are all open (want_open) or all tube."""
    out, start = [], None
    for i in range(lo, hi):
        if tr.open[i] == want_open and start is None:
            start = i
        elif tr.open[i] != want_open and start is not None:
            out.append((start, i))
            start = None
    return out


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
        self.g = app.game
        self.renderer = app.renderer            # world only: the ad draws its own overlays
        self.scr = app.screen
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

    def ride(self, secs, captions=(), shoot=False, overlay=None, clock=False):
        """Play the game for secs; captions are (surface, start, life, y) in clip time."""
        n = int(round(secs * FPS))
        for f in range(n):
            t = f / FPS
            step(self.g, shoot)
            self.g.time_left = max(self.g.time_left, 0.5) if clock else 99.0
            self.renderer.draw(self.g)
            self.vignette()
            for surf, start, life, y in captions:
                blit_pop(self.scr, surf, (VW // 2, y), t - start, life)
            if overlay:
                overlay(t)
            self.emit()

    # -------------------------------------------------------------- scenes
    def hook(self):
        tr = world()
        a, b = max(runs_of(tr, False, 40), key=lambda r: r[1] - r[0])
        tr.tube_styles[tr.stretch[a]] = "whirl"
        place(self.g, tr, a + 8, BOOST_MULT)
        self.g.boost = 99.0
        t = self.txt
        caps = [(t.neon("HOW FAST", 150, PINK), 0.0, 1.5, 420),
                (t.neon("CAN YOU", 150, PINK), 1.5, 1.5, 380),
                (t.neon("GO?", 230, PINK), 1.5, 1.5, 560)]

        def speedo(_):
            s = t.neon("%d km/h" % int(self.g.speed * 4), 96, CYAN)
            self.scr.blit(s, s.get_rect(center=(VW // 2, 1330)))
        self.ride(6 * BEAT, caps, overlay=speedo)
        self.g.boost = 0.0

    def tunnels(self):
        cap = self.txt.neon("HYPNOTIC", 150, CYAN)
        cap2 = self.txt.neon("TUNNELS", 150, CYAN)
        tr = world()
        stretches = [r for r in runs_of(tr, False, 40) if r[1] - r[0] > 60]
        for k, style in enumerate(("rings", "pulse", "chevrons", "stripes")):
            tr = world()
            a, _ = stretches[k + 1]
            tr.tube_styles[tr.stretch[a]] = style
            place(self.g, tr, a + 6)
            self.cut()
            off = k * 2 * BEAT
            self.ride(2 * BEAT, [(cap, -off, 8 * BEAT, 380), (cap2, -off, 8 * BEAT, 540)])

    def outdoors(self):
        tr = world()
        runs = runs_of(tr, True, 40)
        a, b = max(runs, key=lambda r: max(tr.width[r[0]:r[1]]))
        place(self.g, tr, a - 22)
        self.cut()
        t = self.txt
        self.ride(6 * BEAT, [(t.neon("BREAK OUT", 140, GREEN), 0.4, 2.6, 380),
                             (t.neon("INTO THE OPEN", 120, GREEN), 0.4, 2.6, 530)])

    def door(self):
        tr = world()
        doors = [i for i in range(80, 6000) if tr.is_door(i) and all(tr.open[i - 70:i])]
        d = doors[1] if len(doors) > 1 else doors[0]
        tr.tube_styles[tr.stretch[d]] = "whirl"
        place(self.g, tr, d - 50)
        self.cut()
        t = self.txt
        self.ride(5 * BEAT, [(t.neon("THEN DIVE", 140, PINK), 0.0, 2.5, 380),
                             (t.neon("BACK IN", 140, PINK), 0.0, 2.5, 530)])

    def drones(self):
        best, best_kills = None, -1
        for start in range(60, 3000, 12):
            tr = world(drones=True)
            if any(tr.open[start:start + 90]):
                continue
            ahead = [o for o in tr.objects if o["kind"] == "drone" and start * SEG < o["z"] < start * SEG + 450]
            if len(ahead) < 3:
                continue
            place(self.g, tr, start)
            kills = 0
            for _ in range(int(6 * BEAT * FPS)):
                s0 = self.g.score
                step(self.g, shoot=True)
                kills += (self.g.score - s0) >= 500
            if kills > best_kills:
                best, best_kills = start, kills
        print("drones clip: %d kills" % best_kills)
        tr = world(drones=True)
        tr.tube_styles[tr.stretch[best]] = "chevrons"
        place(self.g, tr, best)
        self.cut()
        t = self.txt
        self.ride(6 * BEAT, [(t.neon("BLAST", 160, (255, 150, 40)), 0.0, 3.0, 380),
                             (t.neon("THE DRONES", 130, (255, 150, 40)), 0.0, 3.0, 540)], shoot=True)

    def gate(self):
        tr = world()
        gates = [k * GATE_SEGS for k in range(1, 20) if not tr.open[k * GATE_SEGS]]
        gz = gates[1]
        tr.tube_styles[tr.stretch[gz]] = "rings"
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

        self.ride(7 * BEAT, [(t.neon("BEAT THE", 140, WHITE, glow=PINK), 0.0, 3.5, 380),
                             (t.neon("CLOCK", 170, WHITE, glow=PINK), 0.0, 3.5, 540)], overlay=clock, clock=True)

    def end_card(self):
        t = self.txt
        logo1 = t.neon("NEON", 230, PINK)
        logo2 = t.neon("CONDUIT", 170, CYAN)
        tag = t.neon("Ride the light.", 70, WHITE, glow=CYAN)
        cta = t.neon("PLAY NOW", 96, WHITE, glow=PINK)
        n = int(8 * BEAT * FPS)
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
            if tc > 1.4:
                pulse = 1.0 + 0.05 * math.sin((tc - 1.4) * math.pi * 2 / BEAT)
                w, h = int(560 * pulse), int(150 * pulse)
                box = pygame.Rect(0, 0, w, h)
                box.center = (VW // 2, 1400)
                pygame.draw.rect(self.scr, PINK, box, 6, border_radius=h // 2)
                blit_pop(self.scr, cta, box.center, tc - 1.4, 99)
            if tc > n / FPS - 0.5:                         # fade to black
                veil = pygame.Surface((VW, VH))
                veil.set_alpha(int(255 * (tc - (n / FPS - 0.5)) / 0.5))
                self.scr.blit(veil, (0, 0))
            self.emit()

    def run(self):
        self.hook()
        self.tunnels()
        self.outdoors()
        self.door()
        self.drones()
        self.gate()
        self.end_card()
        return self.frame / FPS


# ------------------------------------------------------------------ music
def music(path, secs, rate=44100):
    """Synthwave loop in A minor: kick, clap, hats, pulsing bass and an arpeggio."""
    n = int(secs * rate)
    buf = [0.0] * n

    def add(start, samples):
        i0 = int(start * rate)
        for j, v in enumerate(samples):
            if 0 <= i0 + j < n:
                buf[i0 + j] += v

    def midi(m):
        return 440.0 * 2 ** ((m - 69) / 12)

    rnd = random.Random(1)
    bar = 4 * BEAT
    chords = [(57, (69, 72, 76, 81)), (53, (65, 69, 72, 77)), (48, (67, 72, 76, 79)), (55, (67, 71, 74, 79))]
    end_drums = secs - 8 * BEAT                       # the end card gets a breakdown

    # drums
    kick = [0.9 * math.sin(2 * math.pi * (45 * j / rate + 105 * (1 - math.exp(-j / rate / 0.03)) * 0.03))
            * math.exp(-j / rate / 0.16) for j in range(int(0.35 * rate))]
    clap = [rnd.uniform(-1, 1) * 0.35 * math.exp(-j / rate / 0.07) for j in range(int(0.25 * rate))]
    hat, prev = [], 0.0
    for j in range(int(0.06 * rate)):
        x = rnd.uniform(-1, 1)
        hat.append(0.18 * (x - prev) * math.exp(-j / rate / 0.018))
        prev = x
    b = 0
    while b * BEAT < secs:
        tb = b * BEAT
        if tb < end_drums or tb >= secs - 2 * BEAT:
            add(tb, kick)
            if tb < end_drums:
                if b % 2 == 1:
                    add(tb, clap)
                add(tb + BEAT / 2, hat)
                add(tb + BEAT / 4 * 3, [v * 0.5 for v in hat])
        b += 1

    # bass: eighth notes, root and octave, filtered saw
    e = 0
    while e * BEAT / 2 < secs:
        te = e * BEAT / 2
        root = chords[int(te // bar) % 4][0] - 12
        f = midi(root + (12 if e % 2 else 0))
        ln = int(BEAT / 2 * rate * 0.92)
        lp, out = 0.0, []
        for j in range(ln):
            saw = 2 * ((f * j / rate) % 1.0) - 1
            lp += (saw - lp) * 0.08
            out.append(0.45 * lp * min(1.0, j / 200) * math.exp(-j / rate / 0.22))
        add(te, out)
        e += 1

    # arpeggio: sixteenths through the chord, square wave with a quick decay
    s = 0
    while s * BEAT / 4 < secs:
        ts = s * BEAT / 4
        notes = chords[int(ts // bar) % 4][1]
        f = midi(notes[s % 4] + (12 if (s // 4) % 2 else 0))
        ln = int(BEAT / 4 * rate)
        out = []
        for j in range(ln):
            sq = 1.0 if (f * j / rate) % 1.0 < 0.5 else -1.0
            out.append(0.09 * sq * math.exp(-j / rate / 0.06))
        add(ts, out)
        s += 1

    # pad under the end card
    for c in range(int(end_drums // bar), int(secs // bar) + 1):
        tc = c * bar
        for m in chords[c % 4][1][:3]:
            f = midi(m - 12)
            out = [0.07 * math.sin(2 * math.pi * f * j / rate) * min(1.0, j / (0.3 * rate))
                   * min(1.0, (bar * rate - j) / (0.3 * rate)) for j in range(int(bar * rate))]
            add(tc, out)

    # master: soft clip, fade out
    peak = max(abs(v) for v in buf) or 1.0
    data = bytearray()
    for i, v in enumerate(buf):
        fade = min(1.0, (n - i) / (0.6 * rate))
        x = math.tanh(1.4 * v / peak) * 0.9 * fade
        data += struct.pack("<hh", int(32767 * x), int(32767 * x))
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(data))


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "neon_conduit_ad.mp4"))
    ap.add_argument("--preview", help="also save every 15th frame as PNG into this folder")
    args = ap.parse_args()
    out = os.path.abspath(args.out)
    wav = out + ".music.wav"
    if args.preview:
        os.makedirs(args.preview, exist_ok=True)

    music(wav, TOTAL_BEATS * BEAT)
    unbounded = ["max-size-time=0", "max-size-buffers=0", "max-size-bytes=0"]
    enc = subprocess.Popen(
        ["gst-launch-1.0", "-q", "-e",
         "fdsrc", "fd=0", "!",
         "rawvideoparse", "width=%d" % VW, "height=%d" % VH, "format=rgb", "framerate=%d/1" % FPS, "!",
         "videoconvert", "!", "video/x-raw,format=I420", "!",
         "x264enc", "speed-preset=slow", "bitrate=9000", "key-int-max=60", "!",
         "video/x-h264,profile=high", "!", "queue", "!", "m.",
         "filesrc", "location=" + wav, "!", "wavparse", "!", "audioconvert", "!",
         "avenc_aac", "bitrate=192000", "!", "queue", *unbounded, "!", "m.",
         "mp4mux", "name=m", "faststart=true", "!", "filesink", "location=" + out],
        stdin=subprocess.PIPE)
    random.seed(0)                 # the sled's flame flicker uses the global generator
    secs = Ad(enc.stdin, args.preview).run()
    enc.stdin.close()
    if enc.wait():
        sys.exit("encoding failed")
    os.remove(wav)
    print("wrote %s (%.1f s)" % (out, secs))


if __name__ == "__main__":
    main()
