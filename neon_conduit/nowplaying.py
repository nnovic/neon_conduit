"""The race music's tags (title, artist, album, date), and the HUD panel that shows them as
a track starts, and every minute or so after: bottom left, the speedometer's mirror image.

Tags are read here rather than with a library, so the game needs nothing but pygame: ID3v2
and ID3v1 (MP3), and Vorbis comments (FLAC, Ogg Vorbis, Opus). Anything else, or a file
without tags, shows its file name as the title.
"""
import os
import struct

import pygame

from .config import NOW_PLAYING_EVERY, NOW_PLAYING_FADE, NOW_PLAYING_HOLD
from .speedo import FRAME, H, SLANT, W, lean

TITLE_FONT = os.path.join(os.path.dirname(__file__), "assets", "RussoOne-Regular.ttf")
BG = (8, 10, 24, 170)
TITLE_COL = (235, 240, 255)
ARTIST_COL = (255, 120, 220)
ALBUM_COL = (170, 180, 210)
PAD = 14                        # text's left margin inside the frame, along its slant
RIGHT = W - 46                  # text stops short of this, before the frame's right edge


# ------------------------------------------------------------------- tags
def read_tags(path):
    """{"title", "artist", "album", "date"} of the file at path, each "" if unknown; the
    title falls back on the file name."""
    tags = {}
    try:
        with open(path, "rb") as f:
            head = f.read(10)
            if head[:3] == b"ID3":
                tags = _id3v2(head, f)
            elif head[:4] == b"fLaC":
                f.seek(4)
                tags = _flac(f)
            elif head[:4] == b"OggS":
                f.seek(0)
                tags = _ogg(f.read(1 << 18))
            if not tags.get("title"):
                tags = {**_id3v1(f), **{k: v for k, v in tags.items() if v}}
    except (OSError, ValueError, struct.error, IndexError):
        pass
    out = {k: (tags.get(k) or "").strip() for k in ("title", "artist", "album", "date")}
    out["title"] = out["title"] or os.path.splitext(os.path.basename(path))[0]
    return out


def _syncsafe(b):
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def _text(data):
    """An ID3v2 text frame's first value."""
    enc, data = data[0], data[1:]
    if enc == 0:
        s = data.decode("latin-1")
    elif enc == 1:
        s = data.decode("utf-16")
    elif enc == 2:
        s = data.decode("utf-16-be")
    else:
        s = data.decode("utf-8", "replace")
    return s.split("\0")[0]


ID3_FRAMES = {"TIT2": "title", "TT2": "title", "TPE1": "artist", "TP1": "artist",
              "TALB": "album", "TAL": "album", "TDRC": "date", "TYER": "date", "TYE": "date",
              "TDRL": "date"}


def _id3v2(head, f):
    ver, flags, size = head[3], head[5], _syncsafe(head[6:10])
    tag = f.read(size)
    if flags & 0x80 and ver < 4:                    # unsynchronised, the whole tag
        tag = tag.replace(b"\xff\x00", b"\xff")
    pos = 0
    if flags & 0x40:                                # skip the extended header
        pos = _syncsafe(tag[:4]) if ver >= 4 else 4 + struct.unpack(">I", tag[:4])[0]
    idlen, hlen = (3, 6) if ver == 2 else (4, 10)
    out = {}
    while pos + hlen <= len(tag) and tag[pos] != 0:
        fid = tag[pos:pos + idlen].decode("latin-1")
        if ver == 2:
            n = int.from_bytes(tag[pos + 3:pos + 6], "big")
            fflags = 0
        else:
            n = _syncsafe(tag[pos + 4:pos + 8]) if ver >= 4 else struct.unpack(">I", tag[pos + 4:pos + 8])[0]
            fflags = struct.unpack(">H", tag[pos + 8:pos + 10])[0]
        data = tag[pos + hlen:pos + hlen + n]
        pos += hlen + n
        key = ID3_FRAMES.get(fid)
        if not key or not data or key in out:
            continue
        if ver >= 4:
            if fflags & 0x000C:                     # compressed or encrypted: no
                continue
            if fflags & 0x0002:
                data = data.replace(b"\xff\x00", b"\xff")
            if fflags & 0x0001:                     # data length indicator
                data = data[4:]
        elif ver == 3 and fflags & 0x00C0:
            continue
        out[key] = _text(data)
    return out


def _id3v1(f):
    f.seek(-128, os.SEEK_END)
    t = f.read(128)
    if t[:3] != b"TAG":
        return {}
    field = lambda a, b: t[a:b].split(b"\0")[0].decode("latin-1")
    return {"title": field(3, 33), "artist": field(33, 63), "album": field(63, 93),
            "date": field(93, 97)}


VORBIS_KEYS = {"TITLE": "title", "ARTIST": "artist", "ALBUM": "album", "DATE": "date"}


def _vorbis(data):
    """Vorbis comments, from the vendor string's length on."""
    n = struct.unpack("<I", data[:4])[0]
    pos = 4 + n
    count = struct.unpack("<I", data[pos:pos + 4])[0]
    pos += 4
    out = {}
    for _ in range(count):
        n = struct.unpack("<I", data[pos:pos + 4])[0]
        k, _, v = data[pos + 4:pos + 4 + n].decode("utf-8", "replace").partition("=")
        pos += 4 + n
        key = VORBIS_KEYS.get(k.upper())
        if key and key not in out:
            out[key] = v
    return out


def _flac(f):
    while True:
        h = f.read(4)
        if len(h) < 4:
            return {}
        n = int.from_bytes(h[1:4], "big")
        if h[0] & 0x7F == 4:
            return _vorbis(f.read(n))
        if h[0] & 0x80:                             # that was the last block
            return {}
        f.seek(n, os.SEEK_CUR)


def _ogg(data):
    """The comment header from the first pages: page headers in its way are cut out first."""
    body, pos = bytearray(), 0
    while data[pos:pos + 4] == b"OggS":
        nseg = data[pos + 26]
        size = sum(data[pos + 27:pos + 27 + nseg])
        start = pos + 27 + nseg
        body += data[start:start + size]
        pos = start + size
    body = bytes(body)
    for magic in (b"\x03vorbis", b"OpusTags"):
        i = body.find(magic)
        if i >= 0:
            return _vorbis(body[i + len(magic):])
    return {}


# ------------------------------------------------------------------ panel
def _fit(font, s, width, col, form="%s"):
    """s set in form (e.g. in quotes) and rendered in font, s cut short with an ellipsis so
    that it all fits in width."""
    if font.size(form % s)[0] > width:
        while s and font.size(form % (s + "…"))[0] > width:
            s = s[:-1]
        s = s.rstrip() + "…"
    s = form % s
    return font.render(s, True, col), font.render(s, True, (0, 0, 0))


class NowPlaying:
    """The panel naming the track that has just started: title, artist, then album and date."""

    def __init__(self):
        self.big = pygame.font.Font(TITLE_FONT, 24)
        self.mid = pygame.font.Font(None, 26)
        self.small = pygame.font.Font(None, 19)
        # The speedometer's frame, mirrored left to right (before it is leaned, so it leans the
        # same way): the tab on top is at the left.
        edge = W - 30
        self.frame = lean([(edge - x, y) for x, y in
                           [(2, 2), (W - 86, 2), (W - 74, 0), (W - 30, 0), (W - 30, H - 2),
                            (12, H - 2), (0, H - 12)]])
        self.tags = None
        self.plain = None           # the panel for self.tags...
        self.framed = None          # ...and the same in the speedometer's orange frame

    def _build(self, tags):
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        pygame.draw.polygon(s, BG, self.frame)
        album = "  •  ".join(v for v in (tags["album"], tags["date"]) if v)
        for font, text, col, y, form in ((self.big, tags["title"], TITLE_COL, 7, "“%s”"),
                                         (self.mid, tags["artist"], ARTIST_COL, 40, "%s"),
                                         (self.small, album, ALBUM_COL, 62, "%s")):
            if not text:
                continue
            x = PAD + (H - y - font.get_height() / 2) * SLANT   # each line set in along the slant
            img, shadow = _fit(font, text, RIGHT - x, col, form)
            s.blit(shadow, (x + 2, y + 2))
            s.blit(img, (x, y))
        return s

    def draw(self, screen, pos, tags, age):
        """The panel for tags at pos, age seconds after its track started: it fades in, stays
        a while and fades out; and comes back every NOW_PLAYING_EVERY seconds. Only the first
        time is it framed in orange, like the speedometer: after that it has no border."""
        if tags is None:
            return
        fade, hold = NOW_PLAYING_FADE, NOW_PLAYING_HOLD
        first = age < NOW_PLAYING_EVERY
        age %= NOW_PLAYING_EVERY
        if age >= 2 * fade + hold:
            return
        if tags is not self.tags:
            self.tags, self.plain = tags, self._build(tags)
            self.framed = self.plain.copy()
            pygame.draw.lines(self.framed, FRAME, True, self.frame, 2)
        surf = self.framed if first else self.plain
        alpha = min(1.0, age / fade, (2 * fade + hold - age) / fade)
        surf.set_alpha(int(255 * max(0.0, alpha)))
        screen.blit(surf, pos)
