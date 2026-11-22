"""Visual editor for the tunnel wall patterns, with a live preview from the game's renderer.

    python3 edit_patterns.py [patterns-file]

Left-click (or drag) paints a wall panel with the current brush, right-click paints
it dark. Arrow keys shift the whole pattern: left / right round the tube, up / down
along it. Ctrl+Z undoes, Ctrl+S saves, Space pauses the preview, Esc quits.
"""
import os
import sys

import pygame

from . import patterns as P
from . import track as track_module
from .audio import Silent
from .config import PATTERNS_FILE
from .game import Game
from .palette import PALETTES, mix, tube_palette
from .render import Renderer

W, H = 1400, 840
BG, PANEL, LINE = (14, 16, 30), (26, 29, 50), (60, 66, 100)
TEXT, DIM, ACCENT, WARN = (230, 235, 250), (140, 146, 175), (255, 80, 160), (255, 170, 40)
BRUSHES = ".12345678#"
CELL = 26
GRID = pygame.Rect(240, 160, P.WIDTH * CELL, 24 * CELL)
PREVIEW = pygame.Rect(630, 20, 750, 470)
LIST_Y, LIST_ROWS = 52, 11


class Button:
    def __init__(self, rect, label, action, enabled=lambda: True):
        self.rect, self.label, self.action, self.enabled = pygame.Rect(rect), label, action, enabled

    def draw(self, ed):
        on = self.enabled()
        hover = on and self.rect.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(ed.screen, (48, 54, 88) if hover else (36, 40, 66), self.rect, border_radius=5)
        pygame.draw.rect(ed.screen, LINE, self.rect, 1, border_radius=5)
        label = self.label() if callable(self.label) else self.label
        ed.text(label, self.rect.center, TEXT if on else DIM, center=True)


class Editor:
    def __init__(self, path=PATTERNS_FILE):
        pygame.init()
        pygame.display.set_caption("Neon Conduit - pattern editor")
        self.screen = pygame.display.set_mode((W, H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 24)
        self.small = pygame.font.Font(None, 19)
        self.big = pygame.font.Font(None, 32)
        self.mono = pygame.font.SysFont("dejavusansmono,liberationmono,monospace", 16)
        self.path = path
        self.patterns, self.sel = [], 0
        self.undo_stack = []
        self.dirty = False
        self.brush = "#"
        self.painting = None            # mouse button held down over the grid
        self.grid_top = 0               # first row shown, when a pattern is taller than the grid
        self.list_top = 0
        self.prompt = None              # text being typed: dict(label, text, done)
        self.note, self.note_t = "", 0.0
        self.quit_armed = 0.0
        self.zone, self.straight, self.paused = 0, False, False
        self.load()
        self.preview_surface = pygame.Surface(PREVIEW.size)
        self.renderer = Renderer(self.preview_surface)
        self.new_preview()
        self.buttons = self.make_buttons()

    # ------------------------------------------------------------- patterns
    @property
    def cur(self):
        return self.patterns[self.sel]

    def load(self):
        name = self.patterns[self.sel].name if self.patterns else None
        self.patterns = P.load(self.path)
        self.mtime = os.path.getmtime(self.path)
        names = [p.name for p in self.patterns]
        self.sel = names.index(name) if name in names else 0
        self.register()

    def register(self):
        """Let the renderer find the patterns being edited by name."""
        P.BY_NAME.clear()
        P.BY_NAME.update((p.name, p) for p in self.patterns)

    def snapshot(self):
        return ([(p.name, list(p.texts), p.scroll, p.contrast, p.header_line, list(p.lines), p.comment)
                 for p in self.patterns], self.sel)

    def restore(self, snap):
        items, self.sel = snap
        self.patterns = []
        for name, texts, scroll, contrast, header_line, lines, comment in items:
            p = P.Pattern(name, texts, scroll, contrast)
            p.header_line, p.lines, p.comment = header_line, lines, comment
            self.patterns.append(p)
        self.register()

    def change(self):
        """Call before every edit: remembers the state for undo."""
        self.undo_stack.append(self.snapshot())
        del self.undo_stack[:-200]
        self.dirty = True

    def undo(self):
        if self.undo_stack:
            self.restore(self.undo_stack.pop())
            self.dirty = True
            self.say("Undone")

    def say(self, msg, secs=3.0):
        self.note, self.note_t = msg, secs

    def select(self, i):
        self.sel = max(0, min(len(self.patterns) - 1, i))
        self.grid_top = 0
        self.list_top = min(self.list_top, self.sel)
        self.list_top = max(self.list_top, self.sel - LIST_ROWS + 1)

    def set_rows(self, texts):
        self.cur.set_rows(texts)

    # ---------------------------------------------------------------- edits
    def paint(self, row, col, ch):
        texts = list(self.cur.texts)
        if texts[row][col] != ch:
            texts[row] = texts[row][:col] + ch + texts[row][col + 1:]
            self.set_rows(texts)

    def shift(self, dcol, drow):
        self.change()
        texts = self.cur.texts
        if drow:
            texts = texts[drow:] + texts[:drow]
        if dcol:
            texts = [t[-dcol:] + t[:-dcol] for t in texts]
        self.set_rows(texts)

    def add_row(self):
        if len(self.cur.texts) < 64:
            self.change()
            self.set_rows(self.cur.texts + [self.cur.texts[-1]])

    def remove_row(self):
        if len(self.cur.texts) > 1:
            self.change()
            self.set_rows(self.cur.texts[:-1])

    def ask(self, label, text, done, keep=None):
        """Prompt for a pattern name; keep: a name that may be reused (renaming to itself)."""
        self.prompt = {"label": label, "text": text, "done": done, "keep": keep}

    def new_pattern(self):
        def done(name):
            self.change()
            self.patterns.insert(self.sel + 1, P.Pattern(name, ["." * P.WIDTH] * 4))
            self.register()
            self.select(self.sel + 1)
        self.ask("Name of the new pattern", "", done)

    def duplicate(self):
        base = self.cur
        name = base.name + " copy"
        while name in P.BY_NAME:
            name += "'"

        def done(name):
            self.change()
            self.patterns.insert(self.sel + 1, P.Pattern(name, base.texts, base.scroll, base.contrast))
            self.register()
            self.select(self.sel + 1)
        self.ask("Name of the copy", name, done)

    def rename(self):
        def done(name):
            self.change()
            self.cur.name = name
            self.register()
        self.ask("New name for [%s]" % self.cur.name, self.cur.name, done, keep=self.cur.name)

    def delete(self):
        if len(self.patterns) > 1:
            self.change()
            name = self.patterns.pop(self.sel).name
            self.register()
            self.select(self.sel)
            self.say("Deleted [%s] (Ctrl+Z to undo)" % name)

    def set_scroll(self, d):
        self.change()
        self.cur.scroll = round(self.cur.scroll + d, 1)

    def toggle_contrast(self):
        self.change()
        self.cur.contrast = "soft" if self.cur.contrast == "strong" else "strong"

    # ------------------------------------------------------------- file
    def save(self):
        if os.path.getmtime(self.path) != self.mtime:
            self.say("The file changed on disk since it was loaded: Reload first (your edits would be lost)", 6)
            return
        P.save(self.patterns, self.path)
        self.load()
        self.dirty = False
        self.say("Saved to %s" % os.path.basename(self.path))

    def reload(self):
        try:
            self.load()
        except P.PatternError as e:
            self.say(str(e), 8)
            return
        self.undo_stack.clear()
        self.dirty = False
        self.say("Reloaded from disk")

    # ---------------------------------------------------------- preview
    def new_preview(self):
        """A fresh tunnel flight: no open sections and no drones, painted with the pattern
        being edited."""
        track_module.OPEN_CHANCE = 0.0
        self.game = Game(1, Silent())
        self.game.state = "play"
        self.game.track.tube_style = lambda i: self.cur.name
        self.game.speed = self.game.max_speed
        self.prepared = 0

    def step_preview(self, dt):
        g = self.game
        if not self.paused:
            g.update(dt, g.autopilot()._replace(fire=False))
            g.time_left = 99.0
        tr = g.track
        tr.objects = [o for o in tr.objects if o["kind"] != "drone"]
        for i in range(self.prepared, len(tr.curv)):      # newly generated segments
            tr.stretch[i] = self.zone
            if self.straight:
                tr.curv[i] = tr.pitch[i] = 0.0
        self.prepared = len(tr.curv)
        tr.runs = self.zone

    def set_zone(self):
        self.zone = (self.zone + 1) % len(PALETTES)
        tr = self.game.track
        tr.stretch[:] = [self.zone] * len(tr.stretch)

    def toggle_straight(self):
        self.straight = not self.straight
        self.new_preview()

    # ------------------------------------------------------------- input
    def make_buttons(self):
        y = LIST_Y + LIST_ROWS * 26 + 12
        b = [Button((20, y, 98, 28), "New", self.new_pattern),
             Button((122, y, 98, 28), "Duplicate", self.duplicate),
             Button((20, y + 32, 98, 28), "Rename", self.rename),
             Button((122, y + 32, 98, 28), "Delete", self.delete, lambda: len(self.patterns) > 1)]
        y += 100
        b += [Button((20, y, 30, 28), "-", lambda: self.set_scroll(-0.5)),
              Button((190, y, 30, 28), "+", lambda: self.set_scroll(0.5)),
              Button((20, y + 34, 200, 28), lambda: "contrast: %s" % self.cur.contrast, self.toggle_contrast)]
        y += 110
        b += [Button((20, y, 200, 28), lambda: "colours: zone %d of %d" % (self.zone + 1, len(PALETTES)),
                     self.set_zone),
              Button((20, y + 32, 200, 28), lambda: "track: straight" if self.straight else "track: bends",
                     self.toggle_straight),
              Button((20, y + 64, 200, 28), lambda: "preview: paused" if self.paused else "preview: running",
                     lambda: setattr(self, "paused", not self.paused))]
        y += 136
        b += [Button((20, y, 98, 32), lambda: "Save*" if self.dirty else "Save", self.save),
              Button((122, y, 98, 32), "Reload", self.reload)]
        gx = GRID.x
        b += [Button((gx + GRID.w - 132, 112, 64, 26), "+ row", self.add_row, lambda: len(self.cur.texts) < 64),
              Button((gx + GRID.w - 64, 112, 64, 26), "- row", self.remove_row, lambda: len(self.cur.texts) > 1)]
        return b

    def grid_cell(self, pos):
        x, y = pos
        if not GRID.collidepoint(pos):
            return None
        row = self.grid_top + (y - GRID.y) // CELL
        col = (x - GRID.x) // CELL
        if row < len(self.cur.texts):
            return row, col
        return None

    def on_key(self, ev):
        if self.prompt:
            p = self.prompt
            if ev.key == pygame.K_ESCAPE:
                self.prompt = None
            elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                err = P.check_name(p["text"], set(P.BY_NAME) - {p["keep"]})
                if err:
                    self.say(err)
                else:
                    self.prompt = None
                    p["done"](p["text"])
            elif ev.key == pygame.K_BACKSPACE:
                p["text"] = p["text"][:-1]
            elif ev.unicode and ev.unicode.isprintable() and len(p["text"]) < 40:
                p["text"] += ev.unicode
            return
        ctrl = ev.mod & pygame.KMOD_CTRL
        if ev.key == pygame.K_ESCAPE:
            return self.try_quit()
        if ctrl and ev.key == pygame.K_s:
            self.save()
        elif ctrl and ev.key == pygame.K_z:
            self.undo()
        elif ev.key == pygame.K_SPACE:
            self.paused = not self.paused
        elif ev.key in (pygame.K_LEFT, pygame.K_RIGHT):
            self.shift(-1 if ev.key == pygame.K_LEFT else 1, 0)
        elif ev.key in (pygame.K_UP, pygame.K_DOWN):
            self.shift(0, 1 if ev.key == pygame.K_UP else -1)
        elif ev.key == pygame.K_PAGEUP:
            self.select(self.sel - 1)
        elif ev.key == pygame.K_PAGEDOWN:
            self.select(self.sel + 1)
        elif ev.unicode and ev.unicode in BRUSHES + "09":
            self.brush = {"0": ".", "9": "#"}.get(ev.unicode, ev.unicode)

    def on_mouse_down(self, ev):
        if self.prompt:
            return
        if ev.button in (4, 5):                                   # wheel
            d = -1 if ev.button == 4 else 1
            if GRID.collidepoint(ev.pos):
                self.grid_top = max(0, min(len(self.cur.texts) - 1, self.grid_top + d))
            elif ev.pos[0] < 230 and ev.pos[1] < LIST_Y + LIST_ROWS * 26:
                self.list_top = max(0, min(len(self.patterns) - LIST_ROWS, self.list_top + d))
            return
        for b in self.buttons:
            if b.rect.collidepoint(ev.pos) and b.enabled():
                b.action()
                return
        for i, ch in enumerate(BRUSHES):
            if self.brush_rect(i).collidepoint(ev.pos):
                self.brush = ch
                return
        if 20 <= ev.pos[0] < 220 and LIST_Y <= ev.pos[1] < LIST_Y + LIST_ROWS * 26:
            i = self.list_top + (ev.pos[1] - LIST_Y) // 26
            if i < len(self.patterns):
                self.select(i)
            return
        cell = self.grid_cell(ev.pos)
        if cell and ev.button in (1, 3):
            self.change()
            self.painting = ev.button
            self.paint(*cell, self.brush if ev.button == 1 else ".")

    def on_mouse_move(self, ev):
        cell = self.grid_cell(ev.pos)
        if self.painting and cell:
            self.paint(*cell, self.brush if self.painting == 1 else ".")

    def try_quit(self):
        if not self.dirty or self.quit_armed > 0:
            return True
        self.quit_armed = 3.0
        self.say("Unsaved changes: press Esc again to quit without saving, or Ctrl+S to save", 3)

    # ------------------------------------------------------------- draw
    def text(self, s, pos, col=TEXT, center=False, font=None):
        img = (font or self.font).render(s, True, col)
        r = img.get_rect(center=pos) if center else img.get_rect(topleft=pos)
        self.screen.blit(img, r)
        return r

    def brush_rect(self, i):
        return pygame.Rect(GRID.x + i * 32, 52, 28, 28)

    def colour(self, ch, pat=None):
        pal = tube_palette(self.zone, (pat or self.cur).contrast)
        return mix(pal[0], pal[1], P.SHADES[ch])

    def draw(self):
        scr = self.screen
        scr.fill(BG)
        pygame.draw.rect(scr, PANEL, (0, 0, 230, H))

        # pattern list and settings
        self.text("Patterns", (20, 18), font=self.big)
        for k in range(LIST_ROWS):
            i = self.list_top + k
            if i >= len(self.patterns):
                break
            r = pygame.Rect(20, LIST_Y + k * 26, 200, 24)
            if i == self.sel:
                pygame.draw.rect(scr, (60, 40, 90), r, border_radius=4)
            self.text(self.patterns[i].name, (r.x + 8, r.y + 4), ACCENT if i == self.sel else TEXT)
        y = LIST_Y + LIST_ROWS * 26 + 12
        self.text("Settings of [%s]" % self.cur.name, (20, y + 76), DIM, font=self.small)
        self.text("scroll %g rows/s" % self.cur.scroll, (120, y + 114), center=True)
        self.text("Preview", (20, y + 190), DIM, font=self.small)
        self.text("File: %s" % os.path.basename(self.path), (20, y + 326), DIM, font=self.small)
        for b in self.buttons:
            b.draw(self)

        # brushes
        self.text("Brush", (GRID.x, 18), font=self.big)
        for i, ch in enumerate(BRUSHES):
            r = self.brush_rect(i)
            pygame.draw.rect(scr, self.colour(ch), r)
            pygame.draw.rect(scr, ACCENT if ch == self.brush else LINE, r, 3 if ch == self.brush else 1)
            self.text(ch, (r.centerx, r.bottom + 9), DIM, center=True, font=self.small)

        # grid
        self.text("[%s]  %d rows" % (self.cur.name, len(self.cur.texts)), (GRID.x, 114), font=self.big)
        self.text("left wall", (GRID.x, GRID.y - 16), DIM, font=self.small)
        self.text("ceiling", (GRID.centerx, GRID.y - 9), DIM, center=True, font=self.small)
        self.text("right wall", (GRID.right - self.small.size("right wall")[0], GRID.y - 16), DIM, font=self.small)
        texts = self.cur.texts
        n = len(texts)
        visible = GRID.h // CELL
        for k in range(visible):
            row = self.grid_top + k
            ghost = row >= n                              # how the pattern repeats further on
            text = texts[row % n]
            for col, ch in enumerate(text):
                cell = pygame.Rect(GRID.x + col * CELL, GRID.y + k * CELL, CELL - 1, CELL - 1)
                c = self.colour(ch)
                if ghost:
                    c = mix(c, BG, 0.65)
                pygame.draw.rect(scr, c, cell)
                if not ghost and ch not in ".#":
                    self.text(ch, cell.center, (0, 0, 0), center=True, font=self.small)
            if not ghost:
                self.text(str(row + 1), (GRID.x - 8 - self.small.size(str(row + 1))[0], GRID.y + k * CELL + 6),
                          DIM, font=self.small)
            elif row == n:
                pygame.draw.line(scr, ACCENT, (GRID.x - 4, GRID.y + k * CELL - 1),
                                 (GRID.right + 4, GRID.y + k * CELL - 1), 2)
                self.text("repeats", (GRID.right + 8, GRID.y + k * CELL - 8), ACCENT, font=self.small)
        pygame.draw.line(scr, LINE, (GRID.centerx - 1, GRID.y - 2), (GRID.centerx - 1, GRID.bottom), 1)
        self.text("ahead", (GRID.right + 8, GRID.bottom - 34), DIM, font=self.small)
        ax, ay = GRID.right + 24, GRID.bottom - 16
        pygame.draw.line(scr, DIM, (ax, ay - 6), (ax, ay + 2), 2)
        pygame.draw.polygon(scr, DIM, ((ax - 5, ay + 1), (ax + 5, ay + 1), (ax, ay + 8)))

        # live preview
        self.renderer.draw(self.game)
        scr.blit(self.preview_surface, PREVIEW)
        pygame.draw.rect(scr, LINE, PREVIEW, 1)

        # the pattern as it will be written to the file
        x, y = PREVIEW.x, PREVIEW.bottom + 16
        self.text("In %s:" % os.path.basename(self.path), (x, y), DIM, font=self.small)
        block = self.cur.block()
        for i, line in enumerate(block[:15]):
            if i == 0 and self.cur.comment:
                line = "[%s] ; %s" % (self.cur.name, self.cur.comment)
            if len(line) > 28:
                line = line[:27] + "…"
            self.text(line, (x, y + 20 + i * 19), TEXT, font=self.mono)
        if len(block) > 15:
            self.text("... %d more rows" % (len(block) - 15), (x, y + 20 + 15 * 19), DIM, font=self.mono)
        help_x = x + 300
        for i, line in enumerate(["Click / drag   paint with the brush",
                                  "Right-click    paint dark (.)",
                                  ". 1-8 # (0 9)  choose the brush",
                                  "Arrows         shift the pattern:",
                                  "               round the tube / along it",
                                  "PgUp / PgDn    previous / next pattern",
                                  "Ctrl+Z undo    Ctrl+S save",
                                  "Space pause    Esc quit"]):
            self.text(line, (help_x, y + 20 + i * 22), DIM, font=self.mono)

        # messages and the name prompt
        if self.note_t > 0:
            self.text(self.note, (PREVIEW.x, H - 30), WARN)
        if self.prompt:
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, 160))
            scr.blit(veil, (0, 0))
            box = pygame.Rect(0, 0, 520, 120)
            box.center = (W // 2, H // 2)
            pygame.draw.rect(scr, PANEL, box, border_radius=8)
            pygame.draw.rect(scr, ACCENT, box, 2, border_radius=8)
            self.text(self.prompt["label"], (box.x + 20, box.y + 18))
            field = pygame.Rect(box.x + 20, box.y + 50, box.w - 40, 32)
            pygame.draw.rect(scr, BG, field)
            self.text(self.prompt["text"] + "_", (field.x + 8, field.y + 7), ACCENT)
            self.text("Enter to confirm, Esc to cancel", (box.x + 20, box.bottom - 26), DIM, font=self.small)

    # ------------------------------------------------------------- loop
    def run(self, frames=None, screenshot=None):
        count = 0
        while True:
            dt = 1 / 60 if frames else min(0.05, self.clock.tick(60) / 1000.0)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT and self.try_quit():
                    return
                if ev.type == pygame.KEYDOWN and self.on_key(ev):
                    return
                if ev.type == pygame.MOUSEBUTTONDOWN:
                    self.on_mouse_down(ev)
                elif ev.type == pygame.MOUSEBUTTONUP:
                    self.painting = None
                elif ev.type == pygame.MOUSEMOTION:
                    self.on_mouse_move(ev)
            self.note_t -= dt
            self.quit_armed = max(0.0, self.quit_armed - dt)
            self.step_preview(dt)
            self.draw()
            pygame.display.flip()
            count += 1
            if frames and count >= frames:
                if screenshot:
                    pygame.image.save(self.screen, screenshot)
                return


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else PATTERNS_FILE
    try:
        editor = Editor(path)
    except P.PatternError as e:
        sys.exit("Can't edit the patterns: %s" % e)
    try:
        editor.run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
