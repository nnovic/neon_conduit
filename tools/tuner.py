"""A panel of sliders for the tuning tools (engine_sound.py, sound_mix.py, aim_tuner.py).

Each slider shows one setting: a constant of neon_conduit/config.py, or a value of the tool's
own (not saved). A config setting is changed live in every module of the game that has
imported it, so the game uses the new value at once; save() writes the values back into
config.py, rounded to the slider's step, with the comments kept and lined up.
"""
import math
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from neon_conduit import config  # noqa: E402

CONFIG = os.path.join(ROOT, "neon_conduit", "config.py")
COMMENT_COL = 24            # config.py's comments start at this column, or further if need be
ROW = 44                    # pixels from one slider to the next
LABEL_W = 170               # pixels for the labels, left of the sliders...
VALUE_W = 90                # ...and for the values, right of them
BACK = (12, 14, 30)
TEXT = (230, 235, 255)
DIM = (130, 140, 180)
ACCENT = (255, 50, 170)
NOTE = (120, 230, 140)


class Setting:
    """One slider: label, config constant (None: a value of the tool's own, start value
    given), lowest and highest values, step (Left / Right; Shift: x10), and how to show
    the value: a % format or a function of the value."""

    def __init__(self, label, name, lo, hi, step, fmt="%.2f", value=None):
        self.label, self.name, self.lo, self.hi, self.step, self.fmt = label, name, lo, hi, step, fmt
        self.value = float(getattr(config, name) if name else value)

    def text(self):
        return self.fmt(self.value) if callable(self.fmt) else self.fmt % self.value


def apply(name, value):
    """Change a config constant live: in config itself and in every game module that has
    imported it by name."""
    for mod_name, mod in list(sys.modules.items()):
        if (mod_name == "neon_conduit" or mod_name.startswith("neon_conduit.")) and hasattr(mod, name):
            setattr(mod, name, value)


def decimals(step):
    """Decimals that show a value to the nearest step."""
    return max(1, -math.floor(math.log10(step) + 1e-9))


def save_config(values, steps):
    """Write {name: value} into config.py in place of the numbers there, each rounded to its
    step (with no trailing zeros), the comment after it kept and lined up at COMMENT_COL."""
    lines = open(CONFIG).read().split("\n")
    for name, v in values.items():
        pat = re.compile(r"^(%s\s*=\s*)[-+0-9.eE]+(\s*(#.*))?$" % re.escape(name))
        hits = [i for i, line in enumerate(lines) if pat.match(line)]
        if len(hits) != 1:
            raise RuntimeError("%s: %d lines found in %s" % (name, len(hits), CONFIG))
        m = pat.match(lines[hits[0]])
        num = ("%.*f" % (decimals(steps[name]), round(v / steps[name]) * steps[name])).rstrip("0")
        head = m.group(1) + num + ("0" if num.endswith(".") else "")
        if m.group(3):
            head += " " * max(3, COMMENT_COL - len(head)) + m.group(3)
        lines[hits[0]] = head
    open(CONFIG, "w").write("\n".join(lines))


class Panel:
    """The sliders, drawn in rect (a pygame.Rect) and worked with the mouse (click or drag
    one) and, if keys is on, the keyboard: Up / Down pick, Left / Right move (Shift: x10),
    Home / End to the lowest / highest. on_change(setting) is called after each change."""

    def __init__(self, settings, rect, keys=True, on_change=None):
        self.settings, self.rect, self.keys, self.on_change = settings, rect, keys, on_change
        self.sel, self.dragging = 0, None
        self.saved = {s.name: s.value for s in settings if s.name}     # as in config.py
        self.font = pygame.font.Font(None, 25)

    @property
    def selected(self):
        return self.settings[self.sel]

    def set(self, s, v):
        """Move slider s to value v (kept in its range), and apply it."""
        s.value = max(s.lo, min(s.hi, v))
        if s.name:
            apply(s.name, s.value)
        if self.on_change:
            self.on_change(s)

    def changed(self, s):
        return s.name is not None and abs(s.value - self.saved[s.name]) > 1e-9

    def save(self):
        """Write the changed settings into config.py; afterwards they are the saved ones."""
        changed = [s for s in self.settings if self.changed(s)]
        save_config({s.name: s.value for s in changed}, {s.name: s.step for s in changed})
        for s in self.settings:
            if s.name:
                self.set(s, round(s.value / s.step) * s.step)   # as written
        self.saved = {s.name: s.value for s in self.settings if s.name}

    def revert(self):
        """Put back the settings as last saved."""
        for s in self.settings:
            if s.name:
                self.set(s, self.saved[s.name])

    def _track(self, i):
        """The slider's ends (x) and height (y) for setting i."""
        x0 = self.rect.x + LABEL_W
        return x0, self.rect.right - VALUE_W - 12, self.rect.y + 16 + i * ROW

    def _value_at(self, i, x):
        s, (x0, x1, _) = self.settings[i], self._track(i)
        return s.lo + (x - x0) / (x1 - x0) * (s.hi - s.lo)

    def handle(self, ev):
        """Deal with a pygame event if it is for the panel; True if it was."""
        if ev.type == pygame.KEYDOWN and self.keys:
            s = self.selected
            step = s.step * (10 if ev.mod & pygame.KMOD_SHIFT else 1)
            if ev.key == pygame.K_UP:
                self.sel = (self.sel - 1) % len(self.settings)
            elif ev.key == pygame.K_DOWN:
                self.sel = (self.sel + 1) % len(self.settings)
            elif ev.key == pygame.K_RIGHT:
                self.set(s, s.value + step)
            elif ev.key == pygame.K_LEFT:
                self.set(s, s.value - step)
            elif ev.key == pygame.K_HOME:
                self.set(s, s.lo)
            elif ev.key == pygame.K_END:
                self.set(s, s.hi)
            else:
                return False
            return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for i in range(len(self.settings)):
                x0, x1, y = self._track(i)
                if abs(ev.pos[1] - y) < ROW // 2 - 4 and x0 - 12 <= ev.pos[0] <= x1 + 12:
                    self.sel = self.dragging = i
                    self.set(self.settings[i], self._value_at(i, ev.pos[0]))
                    return True
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and self.dragging is not None:
            self.dragging = None
            return True
        elif ev.type == pygame.MOUSEMOTION and self.dragging is not None:
            self.set(self.settings[self.dragging], self._value_at(self.dragging, ev.pos[0]))
            return True
        return False

    def x_of(self, i, v):
        """The x of value v on slider i (to draw marks on it)."""
        s, (x0, x1, _) = self.settings[i], self._track(i)
        return x0 + int((v - s.lo) / (s.hi - s.lo) * (x1 - x0))

    def y_of(self, i):
        return self._track(i)[2]

    def draw(self, screen):
        for i, s in enumerate(self.settings):
            x0, x1, y = self._track(i)
            on = i == self.sel and self.keys
            col = TEXT if on else DIM
            label = s.label + (" *" if self.changed(s) else "")
            screen.blit(self.font.render(label, True, col), (self.rect.x, y - 8))
            pygame.draw.line(screen, col, (x0, y), (x1, y), 3 if on else 2)
            pygame.draw.circle(screen, ACCENT if on or self.dragging == i else col,
                               (self.x_of(i, s.value), y), 8)
            screen.blit(self.font.render(s.text(), True, col), (x1 + 14, y - 8))


def hints(screen, font, lines, y):
    """Key hints, one line each, from height y down."""
    for k, line in enumerate(lines):
        screen.blit(font.render(line, True, DIM), (20, y + 20 * k))
