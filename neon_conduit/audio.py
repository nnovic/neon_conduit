"""Sound effects, mostly synthesized at start-up, and the music, streamed from assets/."""
import math
import os
import random
from array import array

import pygame

from .config import (BOOST_SOUND, BOOST_SOUND_VOLUME, DOOR_SOUND, DOOR_SOUND_VOLUME,
                     RACE_MUSIC_DIR, RACE_MUSIC_EXTS, RACE_MUSIC_FADE, RACE_MUSIC_VOLUME, STAR_SOUND,
                     STAR_SOUND_VOLUME)


class Audio:
    RATE = 22050

    def __init__(self):
        self.ok = False
        self.sounds = {}
        try:
            pygame.mixer.init(self.RATE, -16, 1, 512)
            self.sounds = {
                "shot": self._sweep(900, 300, 0.09, 0.25),
                "boost": self._file(BOOST_SOUND, BOOST_SOUND_VOLUME)
                         or self._sweep(200, 900, 0.35, 0.3),
                "hit": self._noise(0.3, 0.45),
                "boom": self._noise(0.22, 0.3),
                "gate": self._sweep(500, 1300, 0.45, 0.3),
                "scrape": self._noise(0.14, 0.22),
                "door": self._file(DOOR_SOUND, DOOR_SOUND_VOLUME)
                        or self._sweep(160, 60, 0.6, 0.18),
                "star": self._file(STAR_SOUND, STAR_SOUND_VOLUME)
                        or self._sweep(1400, 2100, 0.07, 0.12),
            }
            self.ok = True
        except pygame.error:
            pass

    def _file(self, path, vol):
        """The sound in the file at path, or None if it can't be loaded."""
        try:
            sound = pygame.mixer.Sound(path)
        except (pygame.error, OSError) as e:
            print("No sound (%s): %s" % (path, e))
            return None
        sound.set_volume(vol)
        return sound

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
        """Play a sound; the Channel it plays on (to change its volume as it plays), or None."""
        if self.ok:
            return self.sounds[name].play()
        return None

    def music(self, path, volume=1.0, fade=0.0):
        """Loop the music file at path, fading in over fade seconds. A file that can't be
        played is skipped: the game goes on without it."""
        if not self.ok:
            return
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(volume)
            pygame.mixer.music.play(loops=-1, fade_ms=int(fade * 1000))
        except (pygame.error, OSError) as e:
            print("No music (%s): %s" % (path, e))

    def race_music(self):
        """Loop one music file picked at random from the race music folder. An empty or
        missing folder means no race music."""
        try:
            names = [n for n in os.listdir(RACE_MUSIC_DIR) if n.lower().endswith(RACE_MUSIC_EXTS)]
        except OSError:
            names = []
        if names:
            self.music(os.path.join(RACE_MUSIC_DIR, random.choice(names)),
                       RACE_MUSIC_VOLUME, RACE_MUSIC_FADE)

    def stop_music(self, fade=0.0):
        """Fade the music out over fade seconds, or stop it at once."""
        if self.ok:
            pygame.mixer.music.fadeout(int(fade * 1000))


class Silent:
    """Stands in for Audio where no sound is wanted (tests, headless rendering)."""

    def play(self, name):
        return None

    def music(self, path, volume=1.0, fade=0.0):
        pass

    def race_music(self):
        pass

    def stop_music(self, fade=0.0):
        pass
