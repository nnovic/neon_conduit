"""Themes of the outdoor runs, read from a text file: outdoor_themes.txt, whose header
describes the format. A theme is a backdrop image plus how it is used and drawn."""
import os

from .config import THEMES_FILE

KINDS = ("ground", "air")
HORIZON = 760               # default horizon row (see tools/make_panoramas.py)


class ThemeError(ValueError):
    pass


class Theme:
    def __init__(self, name):
        self.name = name
        self.kinds = ()         # "ground" and/or "air": the outdoor runs it can show on
        self.image = None       # path of its panorama
        self.horizon = HORIZON  # row of the horizon in the image
        self.fog = None         # (r, g, b) of the haze, or None: averaged from the image
        self.weight = 1.0       # how often it is picked, against the other themes of its kind
        self.kerbs = None       # (bright, dark) kerb colours, or None: random per run


def _colour(text, where):
    t = text.lstrip("#")
    if len(t) != 6 or not all(c in "0123456789abcdefABCDEF" for c in t):
        raise ThemeError("%s: expected a colour like #ff8040, got %r" % (where, text))
    return tuple(int(t[k:k + 2], 16) for k in (0, 2, 4))


def _number(text, where, kind=float):
    try:
        v = kind(text)
    except ValueError:
        raise ThemeError("%s: expected a number, got %r" % (where, text)) from None
    if v < 0:
        raise ThemeError("%s: expected a number of 0 or more, got %r" % (where, text))
    return v


def _set(theme, key, value, where, assets):
    if key == "kind":
        kinds = tuple(dict.fromkeys(value.lower().split()))
        if not kinds or any(k not in KINDS for k in kinds):
            raise ThemeError("%s: kind is ground, air, or both (ground air), not %r" % (where, value))
        theme.kinds = kinds
    elif key == "image":
        path = os.path.join(assets, value)
        if not os.path.isfile(path):
            raise ThemeError("%s: no image %s" % (where, os.path.relpath(path, os.path.dirname(assets))))
        theme.image = path
    elif key == "horizon":
        theme.horizon = _number(value, where, int)
    elif key == "fog":
        theme.fog = _colour(value, where)
    elif key == "weight":
        theme.weight = _number(value, where)
    elif key == "kerbs":
        cols = value.split()
        if len(cols) != 2:
            raise ThemeError("%s: kerbs takes two colours, bright then dark, e.g. #ffb040 #a0501c" % where)
        theme.kerbs = tuple(_colour(c, where) for c in cols)
    else:
        raise ThemeError("%s: unknown setting %r (kind, image, horizon, fog, weight or kerbs)" % (where, key))


def load(path=THEMES_FILE):
    """The themes in the file at path, by name, in file order."""
    themes, cur = {}, None
    assets = os.path.join(os.path.dirname(path), "assets")
    base = os.path.basename(path)
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.split(";", 1)[0].strip()
            if not line:
                continue
            where = "%s:%d" % (base, n)
            if line.startswith("[") and line.endswith("]"):
                name = line[1:-1].strip()
                if not name or name in themes:
                    raise ThemeError("%s: %s theme name [%s]" % (where, "duplicate" if name else "empty", name))
                cur = themes[name] = Theme(name)
                continue
            if cur is None:
                raise ThemeError("%s: %r before any [theme]" % (where, line))
            key, eq, value = (s.strip() for s in line.partition("="))
            if not eq or not key or not value:
                raise ThemeError("%s: expected key = value, got %r" % (where, line))
            _set(cur, key.lower(), value, where, assets)
    for t in themes.values():
        for key in ("kinds", "image"):
            if not getattr(t, key):
                raise ThemeError("%s: theme [%s] has no %s" % (base, t.name, key.rstrip("s")))
    for kind in KINDS:
        if not any(kind in t.kinds and t.weight > 0 for t in themes.values()):
            raise ThemeError("%s: no theme of kind %s (with a weight above 0)" % (base, kind))
    return themes


THEMES = load()


def of_kind(kind):
    """The themes that can show on outdoor runs of kind, and their weights."""
    ts = [t for t in THEMES.values() if kind in t.kinds and t.weight > 0]
    return [t.name for t in ts], [t.weight for t in ts]
