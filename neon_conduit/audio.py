"""Sound effects, synthesized at start-up: no sound files needed."""
import math
import random
from array import array

import pygame


class Audio:
    RATE = 22050

    def __init__(self):
        self.ok = False
        self.sounds = {}
        try:
            pygame.mixer.init(self.RATE, -16, 1, 512)
            self.sounds = {
                "shot": self._sweep(900, 300, 0.09, 0.25),
                "boost": self._sweep(200, 900, 0.35, 0.3),
                "hit": self._noise(0.3, 0.45),
                "boom": self._noise(0.22, 0.3),
                "gate": self._sweep(500, 1300, 0.45, 0.3),
                "scrape": self._noise(0.14, 0.22),
                "door": self._sweep(160, 60, 0.6, 0.18),
            }
            self.ok = True
        except pygame.error:
            pass

    def _sweep(self, f0, f1, dur, vol):
        """Square-wave pitch sweep from f0 to f1 Hz, fading out."""
        n = int(self.RATE * dur)
        buf, phase = array("h"), 0.0
        for i in range(n):
            t = i / n
            phase += 2 * math.pi * (f0 + (f1 - f0) * t) / self.RATE
            sq = 1.0 if math.sin(phase) > 0 else -1.0
            buf.append(int(32767 * vol * (1 - t) * sq))
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def _noise(self, dur, vol):
        """Crunchy noise burst, fading out."""
        n = int(self.RATE * dur)
        buf, v = array("h"), 0.0
        for i in range(n):
            if i % 6 == 0:
                v = random.uniform(-1, 1)
            buf.append(int(32767 * vol * (1 - i / n) * v))
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def play(self, name):
        if self.ok:
            self.sounds[name].play()


class Silent:
    """Stands in for Audio where no sound is wanted (tests, headless rendering)."""

    def play(self, name):
        pass
