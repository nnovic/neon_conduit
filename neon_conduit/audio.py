"""Sound effects, mostly synthesized at start-up, and the music, streamed from assets/."""
import math
import os
import random
import time
from array import array

import pygame

from .config import (BOOST_MULT, BOOST_SOUND, BOOST_SOUND_VOLUME, DOOR_SOUND, DOOR_SOUND_VOLUME,
                     ENGINE_FADE, ENGINE_IDLE_HZ, ENGINE_IDLE_VOLUME, ENGINE_LEAD, ENGINE_RING,
                     ENGINE_TOP_HZ, ENGINE_VOLUME, RACE_MUSIC_DIR, RACE_MUSIC_EXTS, RACE_MUSIC_FADE, RACE_MUSIC_VOLUME, STAR_SOUND,
                     SPEED_CAP, STAR_SOUND_VOLUME)
from .nowplaying import read_tags

ENGINE_TOP_SPEED = SPEED_CAP * BOOST_MULT   # the speed at which the engine is at its highest
ENGINE_TABLE = 1024         # samples in the engine's one-cycle waveform
ENGINE_HARMONICS = 12       # overtones in it: a buzzy hum that small speakers still carry
ENGINE_DETUNE = 1.007       # a second voice this much higher: a slow shimmer, the beat of the two
ENGINE_CHUG = 0.3           # how deep the throb at half the pitch is (0: a steady drone)
NOISE_GRAIN = 3675.0        # times a second the noise bursts jump to a new random level: lower
                            # sounds coarser and crunchier


class Audio:
    RATE = 22050                # the mixer format asked for: 16-bit mono at this rate

    def __init__(self):
        self.ok = False
        self.sounds = {}
        try:
            pygame.mixer.init(self.RATE, -16, 1, 512)
            # pygame.init() may have started the mixer already, in a format of its own
            # (44100 Hz stereo, say): the sounds made here are made in whatever it runs.
            self.rate, size, self.channels = pygame.mixer.get_init()
            if size != -16:                  # not 16-bit samples: start it again as asked
                pygame.mixer.quit()
                pygame.mixer.init(self.RATE, -16, 1, 512)
                self.rate, size, self.channels = pygame.mixer.get_init()
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
            # The engine plays on a channel of its own, out of reach of the other sounds: a
            # loop of ENGINE_RING seconds, played over and over, that engine() keeps writing
            # the coming sound into, just ahead of the part playing. (Queueing short sounds one
            # after the other crackles: pygame starts each from the audio thread, which then
            # waits on the game's Python code and misses the sound card's deadline.)
            pygame.mixer.set_reserved(1)
            self.engine_ch = pygame.mixer.Channel(0)
            self.engine_wave = self._engine_wave()
            self.engine_frames = int(self.rate * ENGINE_RING)   # sample frames in the loop
            self.engine_ring = pygame.mixer.Sound(buffer=bytes(2 * self.channels * self.engine_frames))
            self.engine_buf = memoryview(self.engine_ring).cast("B").cast("h")
            self.engine_t0 = None           # perf_counter() as the loop started, None: not playing
            self.engine_done = 0            # sample frames written since then
            self.engine_quiet = None        # frames written when it had faded out, if it has
            self.engine_f = ENGINE_IDLE_HZ  # the engine's pitch (Hz) and loudness at the end
            self.engine_vol = 0.0           # of what has been written...
            self.engine_phase = [0.0, 0.0]  # ...and where its two voices were in their cycles
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

    def _sound(self, buf):
        """A Sound from 16-bit samples made at the mixer's rate: the same in every speaker."""
        ch = self.channels
        if ch > 1:
            out = array("h", bytes(2 * len(buf) * ch))
            for c in range(ch):
                out[c::ch] = buf
            buf = out
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def _sweep(self, f0, f1, dur, vol):
        """Square-wave pitch sweep from f0 to f1 Hz, fading out."""
        n = int(self.rate * dur)
        buf, phase = array("h"), 0.0
        for i in range(n):
            t = i / n
            phase += 2 * math.pi * (f0 + (f1 - f0) * t) / self.rate
            sq = 1.0 if math.sin(phase) > 0 else -1.0
            buf.append(int(32767 * vol * (1 - t) * sq))
        return self._sound(buf)

    def _noise(self, dur, vol):
        """Crunchy noise burst, fading out."""
        n = int(self.rate * dur)
        hold = max(1, round(self.rate / NOISE_GRAIN))   # samples each random level lasts
        buf, v = array("h"), 0.0
        for i in range(n):
            if i % hold == 0:
                v = random.uniform(-1, 1)
            buf.append(int(32767 * vol * (1 - i / n) * v))
        return self._sound(buf)

    def _engine_wave(self):
        """One cycle of the engine's hum, -1 .. 1: a fundamental and its overtones, each
        fainter than the last (between a sawtooth's brightness and a sine's softness)."""
        n = ENGINE_TABLE
        wave = [sum(math.sin(2 * math.pi * k * i / n) / k ** 1.3 for k in range(1, ENGINE_HARMONICS + 1))
                for i in range(n)]
        top = max(abs(v) for v in wave)
        return [v / top for v in wave]

    def engine(self, speed):
        """Keep the engine going at this speed (0: idling at a standstill), or fade it out
        with None. Call it every frame: it writes the sound up to ENGINE_LEAD ahead."""
        if not self.ok:
            return
        if speed is None:
            if self.engine_t0 is None:
                return                       # silent already
            f, vol = self.engine_f, 0.0
        else:
            k = max(0.0, min(1.0, speed / ENGINE_TOP_SPEED))
            f = ENGINE_IDLE_HZ * (ENGINE_TOP_HZ / ENGINE_IDLE_HZ) ** k
            vol = ENGINE_IDLE_VOLUME + (ENGINE_VOLUME - ENGINE_IDLE_VOLUME) * k
            self.engine_quiet = None         # back on before it stopped: it plays on
        if self.engine_t0 is None:          # starting: a silent loop, then sound ahead of it
            self.engine_buf[:] = array("h", bytes(len(self.engine_buf) * 2))
            self.engine_done, self.engine_quiet, self.engine_vol = 0, None, 0.0
            self._engine_write(int(self.rate * ENGINE_LEAD), f, vol)
            self.engine_ch.play(self.engine_ring, loops=-1)
            self.engine_t0 = time.perf_counter()
            return
        now = int((time.perf_counter() - self.engine_t0) * self.rate)   # the frame playing
        if self.engine_quiet is not None and now >= self.engine_quiet:
            self.engine_ch.stop()            # faded out, and that has played: stop the loop
            self.engine_t0 = None
            return
        if self.engine_done < now:           # the game stalled: skip what is too late to write
            self.engine_done = now
        n = min(now + int(self.rate * ENGINE_LEAD), now + self.engine_frames // 2) - self.engine_done
        if n > 0:
            self._engine_write(n, f, vol)

    def _engine_write(self, n, f, vol):
        """Write the next n frames of engine sound into the loop, gliding from the pitch and
        loudness written last to f and vol (the loudness no faster than ENGINE_FADE allows)."""
        rate = self.rate
        step = n / rate / ENGINE_FADE * max(ENGINE_VOLUME, ENGINE_IDLE_VOLUME)
        v0 = self.engine_vol
        v1 = max(v0 - step, min(v0 + step, vol))
        f0 = self.engine_f
        wave, size = self.engine_wave, ENGINE_TABLE
        p1, p2 = self.engine_phase           # in cycles; p1 runs over two, for the throb
        buf = array("h", bytes(2 * n))
        for i in range(n):
            t = i / n
            fi = f0 + (f - f0) * t
            p1 = (p1 + fi / rate) % 2.0
            p2 = (p2 + fi * ENGINE_DETUNE / rate) % 1.0
            throb = 1.0 - ENGINE_CHUG * (0.5 + 0.5 * wave[int(p1 * 0.5 * size)])
            s = (wave[int(p1 * size) % size] + wave[int(p2 * size)]) * 0.5 * throb
            buf[i] = int(32767 * (v0 + (v1 - v0) * t) * s)
        self.engine_f, self.engine_vol, self.engine_phase = f, v1, [p1, p2]
        if v1 == 0.0 and vol == 0.0 and self.engine_quiet is None:
            self.engine_quiet = self.engine_done + n
        ch, frames = self.channels, self.engine_frames
        start = self.engine_done % frames    # where it goes in the loop, wrapping round its end
        first = min(n, frames - start)
        for c in range(ch):
            self.engine_buf[start * ch + c:(start + first) * ch:ch] = buf[:first]
            if first < n:
                self.engine_buf[c:(n - first) * ch:ch] = buf[first:]
        self.engine_done += n

    def play(self, name):
        """Play a sound; the Channel it plays on (to change its volume as it plays), or None."""
        if self.ok:
            return self.sounds[name].play()
        return None

    def music(self, path, volume=1.0, fade=0.0):
        """Loop the music file at path, fading in over fade seconds. A file that can't be
        played is skipped: the game goes on without it. True if it plays."""
        if not self.ok:
            return False
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(volume)
            pygame.mixer.music.play(loops=-1, fade_ms=int(fade * 1000))
        except (pygame.error, OSError) as e:
            print("No music (%s): %s" % (path, e))
            return False
        return True

    def race_music(self):
        """Loop one music file picked at random from the race music folder, and return its
        tags (see nowplaying.read_tags); None if none plays (an empty or missing folder)."""
        try:
            names = [n for n in os.listdir(RACE_MUSIC_DIR) if n.lower().endswith(RACE_MUSIC_EXTS)]
        except OSError:
            names = []
        if not names:
            return None
        path = os.path.join(RACE_MUSIC_DIR, random.choice(names))
        if not self.music(path, RACE_MUSIC_VOLUME, RACE_MUSIC_FADE):
            return None
        return read_tags(path)

    def stop_music(self, fade=0.0):
        """Fade the music out over fade seconds, or stop it at once."""
        if self.ok:
            pygame.mixer.music.fadeout(int(fade * 1000))


class Silent:
    """Stands in for Audio where no sound is wanted (tests, headless rendering)."""

    def engine(self, speed):
        pass

    def play(self, name):
        return None

    def music(self, path, volume=1.0, fade=0.0):
        return False

    def race_music(self):
        return None

    def stop_music(self, fade=0.0):
        pass
