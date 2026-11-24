"""Tunnel wall patterns, read from (and written back to) a text file: conduit_patterns.txt,
whose header describes the format."""
import os

from .config import PATTERNS_FILE
from .geometry import WALL_SIDES

WIDTH = len(WALL_SIDES)             # characters in a row: one per wall panel
SHADES = {".": 0.0, "#": 1.0, **{str(d): d / 9 for d in range(10)}}
CONTRASTS = ("strong", "soft")


class PatternError(ValueError):
    pass


class Pattern:
    def __init__(self, name, texts=(), scroll=0.0, contrast="strong"):
        self.name = name
        self.scroll = scroll        # rows per second the pattern slides towards the sled
        self.contrast = contrast
        # Where it came from in the file, so saving can rewrite it in place.
        self.header_line = None     # line number of its [name] line
        self.lines = []             # line numbers of its header, settings and rows
        self.comment = ""           # comment after its [name]
        self.set_rows(texts)

    def set_rows(self, texts):
        """Set the rows from their text (strings of . # 0-9, WIDTH long), in file order:
        the first row is the furthest ahead, the last the closest."""
        self.texts = list(texts)
        # Shades (0 .. 1), nearest row first: rows[i] is i segments further ahead.
        self.rows = [[SHADES[c] for c in t] for t in reversed(self.texts)]

    def shade(self, si, col, t):
        """Shade (0 = dark .. 1 = light) of wall panel col in segment si, at time t."""
        n = len(self.rows)
        if not self.scroll:
            return self.rows[si % n][col]
        f = (si + self.scroll * t) % n
        i = int(f)
        a, b = self.rows[i][col], self.rows[(i + 1) % n][col]
        return a + (b - a) * (f - i)

    def block(self):
        """The pattern as lines of the file: header (with its comment), settings, rows."""
        head = "[%s]" % self.name
        if self.comment:
            head = "%-23s ; %s" % (head, self.comment)
        out = [head]
        if self.scroll:
            out.append("scroll = %g" % self.scroll)
        if self.contrast != "strong":
            out.append("contrast = %s" % self.contrast)
        return out + self.texts


def check_name(name, taken=()):
    """Why name can't be a pattern name, or None if it's fine."""
    if not name.strip():
        return "a pattern needs a name"
    if any(c in name for c in "[];"):
        return "a name can't contain [ ] or ;"
    if name.strip() != name:
        return "a name can't start or end with spaces"
    if name in taken:
        return "there's already a pattern called [%s]" % name
    return None


def load(path=PATTERNS_FILE):
    """All patterns in the file, in order. Raises PatternError, naming the line, if it's malformed."""
    patterns, names = [], set()
    cur = None

    def fail(lineno, msg):
        raise PatternError("%s:%d: %s" % (path, lineno, msg))

    def finish():
        if cur is not None:
            if not cur.texts:
                fail(cur.header_line, "pattern [%s] has no rows" % cur.name)
            cur.set_rows(cur.texts)
            patterns.append(cur)

    with open(path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line, _, comment = raw.partition(";")
            line = line.strip()
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
                cur = Pattern(name)
                cur.header_line = lineno
                cur.comment = comment.strip()
            elif cur is None:
                fail(lineno, "expected a [name] line to start a pattern")
            elif "=" in line:
                if cur.texts:
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
                if len(line) != WIDTH:
                    fail(lineno, "a row needs %d characters, one per wall panel; this one has %d"
                         % (WIDTH, len(line)))
                bad = sorted(set(line) - set(SHADES))
                if bad:
                    fail(lineno, "unexpected character(s) %s: use . # or 0-9" % " ".join(repr(c) for c in bad))
                cur.texts.append(line)
            if cur is not None:
                cur.lines.append(lineno)
    finish()
    if not patterns:
        raise PatternError("%s: no patterns found" % path)
    return patterns


def save(patterns, path=PATTERNS_FILE):
    """Write patterns to the file, keeping everything else in it (comments, blank lines).

    Each pattern loaded from the file is rewritten where it was; patterns that are no
    longer in the list disappear; new ones (never loaded) are added at the end.
    """
    old = load(path) if os.path.exists(path) else []
    lines = open(path, encoding="utf-8").read().splitlines() if old else []
    owned = {n for p in old for n in p.lines}
    here = {p.header_line: p for p in patterns if p.header_line is not None}
    out = []
    for n, text in enumerate(lines, 1):
        if n in here:
            out.extend(here[n].block())
        elif n not in owned:
            out.append(text)
    for p in patterns:
        if p.header_line is None:
            if out and out[-1].strip():
                out.append("")
            out.extend(p.block())
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


PATTERNS = load()
BY_NAME = {p.name: p for p in PATTERNS}
