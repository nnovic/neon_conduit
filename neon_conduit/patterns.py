"""Tunnel wall patterns, read from a text file (conduit_patterns.txt; see its header
for the format)."""
from .config import PATTERNS_FILE
from .geometry import WALL_SIDES

SHADES = {".": 0.0, "#": 1.0, **{str(d): d / 9 for d in range(10)}}
CONTRASTS = ("strong", "soft")


class PatternError(ValueError):
    pass


class Pattern:
    def __init__(self, name, rows, scroll=0.0, contrast="strong"):
        self.name = name
        self.rows = rows            # rows of shades (0 .. 1), one per wall panel
        self.scroll = scroll        # rows per second the pattern slides towards the sled
        self.contrast = contrast

    def shade(self, si, col, t):
        """Shade (0 = dark .. 1 = light) of wall panel col in segment si, at time t."""
        n = len(self.rows)
        if not self.scroll:
            return self.rows[si % n][col]
        f = (si + self.scroll * t) % n
        i = int(f)
        a, b = self.rows[i][col], self.rows[(i + 1) % n][col]
        return a + (b - a) * (f - i)


def load(path=PATTERNS_FILE):
    """All patterns in the file, in order. Raises PatternError, naming the line, if it's malformed."""
    patterns, names = [], set()
    cur = None

    def fail(lineno, msg):
        raise PatternError("%s:%d: %s" % (path, lineno, msg))

    def finish():
        if cur is not None:
            if not cur.rows:
                fail(cur.lineno, "pattern [%s] has no rows" % cur.name)
            patterns.append(cur)

    with open(path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.split(";", 1)[0].strip()
            if not line:
                continue
            if line.startswith("[") and line.endswith("]"):
                finish()
                name = line[1:-1].strip()
                if not name:
                    fail(lineno, "pattern without a name")
                if name in names:
                    fail(lineno, "pattern [%s] defined twice" % name)
                names.add(name)
                cur = Pattern(name, [])
                cur.lineno = lineno
            elif cur is None:
                fail(lineno, "expected a [name] line to start a pattern")
            elif "=" in line:
                if cur.rows:
                    fail(lineno, "settings go before the rows")
                key, value = (s.strip() for s in line.split("=", 1))
                if key == "scroll":
                    try:
                        cur.scroll = float(value)
                    except ValueError:
                        fail(lineno, "scroll must be a number, not %r" % value)
                elif key == "contrast":
                    if value not in CONTRASTS:
                        fail(lineno, "contrast must be one of %s, not %r" % (", ".join(CONTRASTS), value))
                    cur.contrast = value
                else:
                    fail(lineno, "unknown setting %r (expected scroll or contrast)" % key)
            else:
                if len(line) != len(WALL_SIDES):
                    fail(lineno, "a row needs %d characters, one per wall panel; this one has %d"
                         % (len(WALL_SIDES), len(line)))
                bad = sorted(set(line) - set(SHADES))
                if bad:
                    fail(lineno, "unexpected character(s) %s: use . # or 0-9" % " ".join(repr(c) for c in bad))
                cur.rows.append([SHADES[c] for c in line])
    finish()
    if not patterns:
        raise PatternError("%s: no patterns found" % path)
    return patterns


PATTERNS = load()
BY_NAME = {p.name: p for p in PATTERNS}
