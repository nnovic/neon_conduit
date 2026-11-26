"""Visual editor for hand-made levels (see level.py), with a live preview from the game's
renderer.

    python3 edit_level.py [level-file]

Bottom, the map of the course, left to right from the start to the finish line: the
sections (their kind, bend and slope), then the tube unrolled flat, the floor along the
middle and the ceiling at the top and bottom edges, with what is on it. The preview shows
the view from the cursor (the white line): click the ruler or a section to move it.

Click a section to edit it in the panel on the left. Pick a tool (Select, or an object)
and click the unrolled tube to place objects; with Select, click one to edit it, drag it
to move it. Right-click an object to delete it.
"""
import math
import os
import subprocess
import sys
import tempfile

import pygame

from .audio import Silent
from .config import BASE_SPEED, FLOOR_A, FLOOR_HW, FLOOR_Y, PLAYER_D, SEG
from .game import Game
from .geometry import wrap
from .level import (KINDS, OBJECT_KINDS, SECTION_SETTINGS, START_TIME, Level, LevelError, load,
                    new_object, new_section)
from .patterns import PATTERNS
from .render import Renderer
from .themes import of_kind

W, H = 1400, 860
BG, PANEL, LINE = (14, 16, 30), (26, 29, 50), (60, 66, 100)
TEXT, DIM, ACCENT, WARN = (230, 235, 250), (140, 146, 175), (255, 80, 160), (255, 170, 40)
PREVIEW = pygame.Rect(262, 12, 800, 500)
HELP_X = 1080
MAP = pygame.Rect(262, 540, W - 262 - 14, 300)
PROFILE = pygame.Rect(MAP.x, 548, MAP.w, 78)
TUBE = pygame.Rect(MAP.x, 640, MAP.w, 168)
RULER = pygame.Rect(MAP.x, 812, MAP.w, 26)
KIND_COLS = {"tube": (52, 72, 140), "ground": (52, 130, 80), "air": (50, 140, 160)}
BEND_COL, SLOPE_COL = (255, 110, 200), (255, 220, 90)
ANGLE_STEP = math.pi / 16       # objects snap to this round the tube (Shift: free)
ZOOMS = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0)   # pixels per segment on the map
DEFAULT_PATH = os.path.join("levels", "level.json")
HELP = ["Map: click a section to edit it,",
        "click the ruler to move the view",
        "Wheel        scroll the map",
        "Ctrl+wheel   zoom",
        "Left / Right move the view",
        "             (Shift: 10 at a time)",
        "S            Select tool",
        "%s   object tools" % "  ".join(k.key.upper() for k in OBJECT_KINDS.values()),
        "Click        place / select",
        "Drag         move an object",
        "Right-click  delete an object",
        "Shift        don't snap the angle",
        "Del          delete the selection",
        "Space        fly the preview",
        "P / Shift+P  play / play from here",
        "Ctrl+Z undo  Ctrl+S save",
        "Esc          quit"]


class LevelEditor:
    def __init__(self, path=DEFAULT_PATH):
        pygame.init()
        pygame.display.set_caption("Neon Conduit - level editor")
        self.screen = pygame.display.set_mode((W, H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 24)
        self.small = pygame.font.Font(None, 19)
        self.big = pygame.font.Font(None, 32)
        self.mono = pygame.font.SysFont("dejavusansmono,liberationmono,monospace", 15)
        self.path = path
        self.undo_stack = []
        self.dirty = False
        self.note, self.note_t = "", 0.0
        self.quit_armed = 0.0
        self.prompt = None
        self.tool = "select"
        self.sec = 0                # the section selected (always one)...
        self.obj = None             # ...and the object, if one is
        self.drag = None            # the object being dragged
        self.scrub = False          # dragging the cursor along the ruler
        self.pan = None             # (mouse x, view0) while panning with the middle button
        self.cursor = 0.0           # segment the preview's racer is at
        self.view0 = 0.0            # segment at the map's left edge...
        self.zoom = 3.0             # ...and pixels per segment
        self.flying = False
        self.hot = []               # (rect, action) of the buttons drawn last frame
        self.preview_surface = pygame.Surface(PREVIEW.size)
        self.renderer = Renderer(self.preview_surface)
        self.level = self.load()
        self.rebuild()

    # --------------------------------------------------------------- file
    def load(self):
        if os.path.exists(self.path):
            lv = load(self.path)
            self.say("Loaded %s" % os.path.basename(self.path))
        else:
            name = os.path.splitext(os.path.basename(self.path))[0].replace("_", " ").title()
            lv = Level(name, sections=[new_section(length=60)])
            self.say("New level: %s (not saved yet)" % os.path.basename(self.path))
        return lv

    def save(self):
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        self.level.save(self.path)
        self.dirty = False
        self.say("Saved to %s" % os.path.basename(self.path))

    def reload(self):
        try:
            self.level = self.load()
        except (OSError, LevelError) as e:
            self.say("Can't reload: %s" % e, 8)
            return
        self.undo_stack.clear()
        self.dirty = False
        self.sec, self.obj = 0, None
        self.rebuild()

    def play(self, from_cursor):
        """Race the level as it is now (saved or not) in the game, in its own window."""
        tmp = os.path.join(tempfile.gettempdir(), "neon_conduit_level_test.json")
        self.level.save(tmp)
        cmd = [sys.executable, "-m", "neon_conduit", "--level", tmp]
        if from_cursor:
            cmd += ["--from", str(int(self.cursor))]
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        subprocess.Popen(cmd, cwd=root)
        self.say("Racing it in the game window%s" % (" from segment %d" % self.cursor if from_cursor else ""))

    # -------------------------------------------------------------- edits
    def say(self, msg, secs=3.0):
        self.note, self.note_t = msg, secs

    def change(self):
        """Call before every edit: remembers the level for undo."""
        self.undo_stack.append(self.level.to_dict())
        del self.undo_stack[:-200]
        self.dirty = True

    def undo(self):
        if not self.undo_stack:
            return
        from .level import from_dict
        self.level = from_dict(self.undo_stack.pop())
        self.obj = self.drag = None
        self.sec = min(self.sec, len(self.level.sections) - 1)
        self.dirty = True
        self.rebuild()
        self.say("Undone")

    def rebuild(self):
        """The track again, after an edit: for the map and the preview."""
        lv = self.level
        self.cursor = max(0.0, min(lv.length - 1, self.cursor))
        self.track = lv.build()
        if not self.flying:
            self.game = Game(None, Silent(), lv)
            self.game.state = "play"
            self.place_camera()

    def place_camera(self):
        """The preview's racer at the cursor, on the floor, at cruising speed."""
        g = self.game
        g.cam_z = self.cursor * SEG - PLAYER_D
        g.prev_z = g.sled_z
        g.speed = g.max_speed
        seg = int(g.sled_z // SEG)
        g.flat = 1.0 if g.track.open[seg] else 0.0
        g.theta = g.roll = g.omega = 0.0

    def shift_objects(self, at, d):
        """Objects at or past segment at move d segments along: track was inserted there
        (d > 0) or the d segments before it removed (d < 0). Those on a removed stretch go to
        the segment just before it."""
        for o in self.level.objects:
            if o["seg"] >= at:
                o["seg"] += d
            elif d < 0 and o["seg"] >= at + d:
                o["seg"] = max(0, at + d - 1)

    def clamp_objects(self):
        end = self.level.length - 1
        for o in self.level.objects:
            o["seg"] = max(0, min(end, o["seg"]))

    def set_section(self, key, delta):
        s = self.level.sections[self.sec]
        _, lo, hi, _ = SECTION_SETTINGS[key]
        v = max(lo, min(hi, s[key] + delta))
        if key == "length":
            v = int(v)
        else:
            v = round(v, 3)
        if v == s[key]:
            return
        self.change()
        if key == "length":
            self.shift_objects(self.level.section_start(self.sec) + s["length"], v - s["length"])
        s[key] = v
        self.clamp_objects()
        self.rebuild()

    def cycle_kind(self):
        s = self.level.sections[self.sec]
        self.change()
        s["kind"] = KINDS[(KINDS.index(s["kind"]) + 1) % len(KINDS)]
        s["theme"] = None                       # themes are for one kind of outdoor run
        self.rebuild()

    def cycle_look(self, d):
        """The wall pattern of a tube section, or the theme of an outdoor one: random, then
        each in turn."""
        s = self.level.sections[self.sec]
        if s["kind"] == "tube":
            key, names = "pattern", [None] + [p.name for p in PATTERNS]
        else:
            key, names = "theme", [None] + of_kind(s["kind"])[0]
        cur = s.get(key)
        i = names.index(cur) if cur in names else 0
        self.change()
        s[key] = names[(i + d) % len(names)]
        self.rebuild()

    def insert_section(self, after=True, copy=False):
        self.change()
        i = self.sec + 1 if after else self.sec
        new = dict(self.level.sections[self.sec]) if copy else new_section(length=40)
        self.shift_objects(self.level.section_start(i), new["length"])
        self.level.sections.insert(i, new)
        self.sec = i
        self.rebuild()

    def delete_section(self):
        if len(self.level.sections) < 2:
            self.say("A level needs at least one section")
            return
        self.change()
        start = self.level.section_start(self.sec)
        n = self.level.sections[self.sec]["length"]
        self.level.objects = [o for o in self.level.objects if not start <= o["seg"] < start + n]
        self.shift_objects(start + n, -n)
        del self.level.sections[self.sec]
        self.sec = min(self.sec, len(self.level.sections) - 1)
        self.obj = None
        self.rebuild()

    def add_object(self, kind, seg, angle):
        self.change()
        o = new_object(kind, seg, angle)
        self.level.objects.append(o)
        self.obj = o
        self.rebuild()

    def delete_object(self, o):
        self.change()
        self.level.objects.remove(o)
        if self.obj is o:
            self.obj = None
        self.rebuild()

    def nudge(self, key, delta, lo, hi):
        o = self.obj
        self.change()
        o[key] = max(lo, min(hi, round(o[key] + delta, 3)))
        if key == "angle":
            o[key] = round(wrap(o[key]), 3)
        self.rebuild()

    def set_start_time(self, d):
        _, lo, hi, _ = START_TIME
        self.change()
        self.level.start_time = max(lo, min(hi, self.level.start_time + d))

    def rename(self):
        def done(name):
            self.change()
            self.level.name = name
        self.prompt = {"label": "Name of the level", "text": self.level.name, "done": done}

    # ---------------------------------------------------------- map maths
    def x_of(self, seg):
        return MAP.x + (seg - self.view0) * self.zoom

    def seg_of(self, x):
        return self.view0 + (x - MAP.x) / self.zoom

    def y_of(self, a):
        return TUBE.centery + a / math.pi * (TUBE.h / 2)

    def a_of(self, y, snap=True):
        a = (y - TUBE.centery) / (TUBE.h / 2) * math.pi
        a = max(-math.pi, min(math.pi, a))
        return round(a / ANGLE_STEP) * ANGLE_STEP if snap else a

    def obj_pos(self, o):
        k = OBJECT_KINDS[o["kind"]]
        x = self.x_of(o["seg"] + k.length / SEG / 2)
        return x, self.y_of(o["angle"]) if k.angle else TUBE.centery

    def object_at(self, pos):
        best, bd = None, 10.0
        for o in self.level.objects:
            x, y = self.obj_pos(o)
            if OBJECT_KINDS[o["kind"]].angle:
                d = math.hypot(pos[0] - x, pos[1] - y)
            else:
                d = abs(pos[0] - x)
            if d < bd:
                best, bd = o, d
        return best

    def scroll(self, dseg):
        self.view0 = max(-20.0, min(self.level.length, self.view0 + dseg))

    def zoom_at(self, x, d):
        seg = self.seg_of(x)
        i = min(range(len(ZOOMS)), key=lambda k: abs(ZOOMS[k] - self.zoom))
        self.zoom = ZOOMS[max(0, min(len(ZOOMS) - 1, i + d))]
        self.view0 = seg - (x - MAP.x) / self.zoom

    def set_cursor(self, seg):
        self.cursor = max(0.0, min(self.level.length - 1, seg))
        if not self.flying:
            self.place_camera()

    def follow_cursor(self):
        """Keep the cursor on the map while it moves."""
        span = MAP.w / self.zoom
        if self.cursor < self.view0 + span * 0.1:
            self.view0 = self.cursor - span * 0.1
        elif self.cursor > self.view0 + span * 0.8:
            self.view0 = self.cursor - span * 0.8

    # ------------------------------------------------------------- input
    def on_key(self, ev):
        if self.prompt:
            p = self.prompt
            if ev.key == pygame.K_ESCAPE:
                self.prompt = None
            elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if p["text"].strip():
                    self.prompt = None
                    p["done"](p["text"].strip())
            elif ev.key == pygame.K_BACKSPACE:
                p["text"] = p["text"][:-1]
            elif ev.unicode and ev.unicode.isprintable() and len(p["text"]) < 40:
                p["text"] += ev.unicode
            return
        ctrl, shift = ev.mod & pygame.KMOD_CTRL, ev.mod & pygame.KMOD_SHIFT
        if ev.key == pygame.K_ESCAPE:
            return self.try_quit()
        if ctrl and ev.key == pygame.K_s:
            self.save()
        elif ctrl and ev.key == pygame.K_z:
            self.undo()
        elif ev.key == pygame.K_SPACE:
            self.toggle_flying()
        elif ev.key == pygame.K_p:
            self.play(bool(shift))
        elif ev.key in (pygame.K_LEFT, pygame.K_RIGHT):
            step = (10 if shift else 1) * (1 if ev.key == pygame.K_RIGHT else -1)
            self.set_cursor(int(self.cursor) + step)
            self.follow_cursor()
        elif ev.key in (pygame.K_HOME, pygame.K_END):
            self.set_cursor(0 if ev.key == pygame.K_HOME else self.level.length - 1)
            self.follow_cursor()
        elif ev.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
            if self.obj is not None:
                self.delete_object(self.obj)
            else:
                self.delete_section()
        elif ev.key == pygame.K_s:
            self.tool = "select"
        else:
            for name, k in OBJECT_KINDS.items():
                if ev.unicode == k.key:
                    self.tool = name

    def on_mouse_down(self, ev):
        if self.prompt:
            return
        pos = ev.pos
        mods = pygame.key.get_mods()
        if ev.button in (4, 5):                                   # wheel
            d = 1 if ev.button == 4 else -1
            if MAP.collidepoint(pos):
                if mods & pygame.KMOD_CTRL:
                    self.zoom_at(pos[0], d)
                else:
                    self.scroll(-d * 60 / self.zoom)
            return
        if ev.button == 2 and MAP.collidepoint(pos):
            self.pan = (pos[0], self.view0)
            return
        if ev.button == 1:
            for rect, action in self.hot:
                if rect.collidepoint(pos):
                    action()
                    return
        if RULER.collidepoint(pos) and ev.button == 1:
            self.scrub = True
            self.set_cursor(self.seg_of(pos[0]))
        elif PROFILE.collidepoint(pos) and ev.button == 1:
            seg = self.seg_of(pos[0])
            if 0 <= seg < self.level.length:
                self.sec, _ = self.level.section_at(int(seg))
                self.obj = None
                self.set_cursor(seg)
        elif TUBE.collidepoint(pos):
            hit = self.object_at(pos)
            if ev.button == 3:
                if hit:
                    self.delete_object(hit)
                return
            if ev.button != 1:
                return
            seg = int(self.seg_of(pos[0]))
            if self.tool == "select":
                self.obj = hit
                if hit:
                    self.change()
                    self.drag = hit
                    self.sec, _ = self.level.section_at(hit["seg"])
            elif 0 <= seg < self.level.length:
                self.add_object(self.tool, seg, self.a_of(pos[1], not mods & pygame.KMOD_SHIFT))

    def on_mouse_move(self, ev):
        if self.pan:
            x0, v0 = self.pan
            self.view0 = v0 - (ev.pos[0] - x0) / self.zoom
        elif self.scrub:
            self.set_cursor(self.seg_of(ev.pos[0]))
        elif self.drag:
            o = self.drag
            o["seg"] = max(0, min(self.level.length - 1, int(self.seg_of(ev.pos[0]))))
            if OBJECT_KINDS[o["kind"]].angle:
                o["angle"] = self.a_of(ev.pos[1], not pygame.key.get_mods() & pygame.KMOD_SHIFT)
            self.sec, _ = self.level.section_at(o["seg"])
            self.rebuild()

    def on_mouse_up(self, ev):
        self.drag, self.scrub, self.pan = None, False, None

    def toggle_flying(self):
        self.flying = not self.flying
        if not self.flying:
            self.rebuild()                  # drones flown off, gates passed: as they were

    def try_quit(self):
        if not self.dirty or self.quit_armed > 0:
            return True
        self.quit_armed = 3.0
        self.say("Unsaved changes: press Esc again to quit without saving, or Ctrl+S to save", 3)

    def step(self, dt):
        g = self.game
        g.t += dt
        if self.flying:
            g.update(dt, g.autopilot()._replace(fire=False))
            g.time_left = 99.0
            self.cursor = g.sled_z / SEG
            if g.state != "play" or self.cursor >= self.level.length - 1:
                self.flying = False
                self.cursor = min(self.cursor, self.level.length - 1)
                self.rebuild()
            self.follow_cursor()

    # -------------------------------------------------------------- draw
    def text(self, s, pos, col=TEXT, center=False, font=None):
        img = (font or self.font).render(s, True, col)
        r = img.get_rect(center=pos) if center else img.get_rect(topleft=pos)
        self.screen.blit(img, r)
        return r

    def button(self, rect, label, action, active=False, enabled=True):
        rect = pygame.Rect(rect)
        hover = enabled and rect.collidepoint(pygame.mouse.get_pos())
        fill = (90, 40, 110) if active else (48, 54, 88) if hover else (36, 40, 66)
        pygame.draw.rect(self.screen, fill, rect, border_radius=5)
        pygame.draw.rect(self.screen, ACCENT if active else LINE, rect, 1, border_radius=5)
        self.text(label, rect.center, TEXT if enabled else DIM, center=True, font=self.small)
        if enabled:
            self.hot.append((rect, action))

    def stepper(self, y, label, value, dec, inc):
        """A setting: its name, its value between - and + buttons."""
        self.text(label, (16, y + 6), DIM, font=self.small)
        self.button((96, y, 28, 24), "-", dec)
        self.text(value, (172, y + 12), center=True, font=self.small)
        self.button((220, y, 28, 24), "+", inc)

    def draw_panel(self):
        scr, lv = self.screen, self.level
        pygame.draw.rect(scr, PANEL, (0, 0, 256, H))
        self.text("Level", (16, 14), font=self.big)
        self.button((16, 44, 232, 26), lv.name, self.rename)
        self.text(os.path.basename(self.path) + (" *" if self.dirty else ""), (16, 76), DIM, font=self.small)
        st = START_TIME[3]
        self.stepper(96, "start time", "%g s" % lv.start_time,
                     lambda: self.set_start_time(-st), lambda: self.set_start_time(st))
        secs = lv.length * SEG / BASE_SPEED
        self.text("%d segments, about %.0f s" % (lv.length, secs), (16, 126), DIM, font=self.small)
        self.text("at cruising speed", (16, 142), DIM, font=self.small)

        self.text("Tools", (16, 168), font=self.big)
        tools = [("select", "Select (S)")] + [(n, "%s (%s)" % (k.label, k.key.upper()))
                                              for n, k in OBJECT_KINDS.items()]
        for i, (name, label) in enumerate(tools):
            x, y = 16 + (i % 2) * 118, 198 + (i // 2) * 30
            self.button((x, y, 114, 26), label, lambda n=name: setattr(self, "tool", n),
                        active=self.tool == name)
        y = 198 + ((len(tools) + 1) // 2) * 30 + 14
        if self.obj is not None:
            self.draw_object_panel(y)
        else:
            self.draw_section_panel(y)

        y = H - 112
        self.button((16, y, 114, 30), "Save" + ("*" if self.dirty else ""), self.save)
        self.button((134, y, 114, 30), "Reload", self.reload)
        self.button((16, y + 36, 114, 30), "Play (P)", lambda: self.play(False))
        self.button((134, y + 36, 114, 30), "From here", lambda: self.play(True))
        self.button((16, y + 72, 232, 26), "Preview: flying" if self.flying else "Preview: still (Space)",
                    self.toggle_flying, active=self.flying)

    def draw_section_panel(self, y):
        lv = self.level
        s = lv.sections[self.sec]
        start = lv.section_start(self.sec)
        self.text("Section %d of %d" % (self.sec + 1, len(lv.sections)), (16, y), font=self.big)
        self.text("segments %d to %d" % (start, start + s["length"] - 1), (16, y + 28), DIM, font=self.small)
        y += 48
        self.button((16, y, 232, 26), "kind: %s" % s["kind"], self.cycle_kind)
        y += 34
        rows = [("length", "%d" % s["length"]), ("bend", "%+.2f" % s["bend"]), ("slope", "%+.2f" % s["slope"])]
        if s["kind"] == "ground":
            rows.append(("width", "%.0f" % s["width"]))
        for key, value in rows:
            step = SECTION_SETTINGS[key][3]
            self.stepper(y, key, value, lambda k=key, d=step: self.set_section(k, -d),
                         lambda k=key, d=step: self.set_section(k, d))
            y += 30
        look = s.get("pattern") if s["kind"] == "tube" else s.get("theme")
        self.text("pattern" if s["kind"] == "tube" else "theme", (16, y + 6), DIM, font=self.small)
        self.button((96, y, 28, 24), "<", lambda: self.cycle_look(-1))
        self.text(look or "random", (172, y + 12), center=True, font=self.small)
        self.button((220, y, 28, 24), ">", lambda: self.cycle_look(1))
        y += 40
        self.button((16, y, 114, 26), "Insert before", lambda: self.insert_section(False))
        self.button((134, y, 114, 26), "Insert after", lambda: self.insert_section(True))
        self.button((16, y + 30, 114, 26), "Duplicate", lambda: self.insert_section(True, True))
        self.button((134, y + 30, 114, 26), "Delete", self.delete_section, enabled=len(lv.sections) > 1)

    def draw_object_panel(self, y):
        o = self.obj
        k = OBJECT_KINDS[o["kind"]]
        self.text(k.label, (16, y), font=self.big)
        y += 34
        end = self.level.length - 1
        self.stepper(y, "segment", "%d" % o["seg"], lambda: self.nudge("seg", -1, 0, end),
                     lambda: self.nudge("seg", 1, 0, end))
        y += 30
        if k.angle:
            deg = math.degrees(o["angle"])
            self.stepper(y, "angle", "%+.0f deg" % deg, lambda: self.nudge("angle", -ANGLE_STEP, -9, 9),
                         lambda: self.nudge("angle", ANGLE_STEP, -9, 9))
            y += 30
        for name, (_, lo, hi, step) in k.settings.items():
            self.stepper(y, name, "%.2f" % o[name], lambda n=name, s=step, a=lo, b=hi: self.nudge(n, -s, a, b),
                         lambda n=name, s=step, a=lo, b=hi: self.nudge(n, s, a, b))
            y += 30
        y += 10
        self.button((16, y, 114, 26), "Delete", lambda: self.delete_object(o))
        self.button((134, y, 114, 26), "Done", lambda: setattr(self, "obj", None))

    def draw_map(self):
        scr, lv, tr = self.screen, self.level, self.track
        pygame.draw.rect(scr, (10, 12, 22), MAP)
        clip = scr.get_clip()
        scr.set_clip(MAP)
        first, last = max(0, int(self.view0)), min(lv.length, int(self.seg_of(MAP.right)) + 2)

        # sections: kind as the colour, bend and slope as curves
        start = 0
        for i, s in enumerate(lv.sections):
            x0, x1 = self.x_of(start), self.x_of(start + s["length"])
            if x1 >= MAP.x and x0 <= MAP.right:
                r = pygame.Rect(int(x0), PROFILE.y, max(1, int(x1) - int(x0)), PROFILE.h)
                col = KIND_COLS[s["kind"]]
                pygame.draw.rect(scr, tuple(c // 2 for c in col), r)
                pygame.draw.rect(scr, col, r, 1)
                if i == self.sec and self.obj is None:
                    pygame.draw.rect(scr, ACCENT, r.inflate(-2, -2), 3)
                if r.w > 46:
                    self.text("%s %d" % (s["kind"], s["length"]), (r.x + 5, r.y + 4), TEXT, font=self.small)
            start += s["length"]
        # Right bends dip, like the right wall on the unrolled tube below; climbs rise.
        mid = PROFILE.centery + 8
        for curve, col, sign in ((tr.curv, BEND_COL, -1), (tr.pitch, SLOPE_COL, 1)):
            pts = [(self.x_of(i + 0.5), mid - sign * curve[i] / 0.6 * (PROFILE.h / 2 - 12))
                   for i in range(first, last)]
            if len(pts) > 1:
                pygame.draw.lines(scr, col, False, pts, 2)

        # the unrolled tube: floor along the middle, ceiling at the edges
        step = 2
        for px in range(TUBE.x, TUBE.right, step):
            seg = int(self.seg_of(px))
            if not 0 <= seg < lv.length:
                pygame.draw.rect(scr, (18, 18, 26), (px, TUBE.y, step, TUBE.h))
                continue
            if tr.open[seg]:
                wall, floor = (20, 44, 28), (66, 70, 80)
                edge = math.atan(tr.width[seg] / FLOOR_Y)
            elif tr.air[seg]:
                wall, floor, edge = (22, 52, 62), (44, 86, 98), FLOOR_A
            else:
                wall, floor, edge = (32, 40, 76), (58, 62, 78), FLOOR_A
            pygame.draw.rect(scr, wall, (px, TUBE.y, step, TUBE.h))
            y0, y1 = self.y_of(-edge), self.y_of(edge)
            pygame.draw.rect(scr, floor, (px, y0, step, y1 - y0))
        pygame.draw.line(scr, (90, 94, 120), (TUBE.x, TUBE.centery), (TUBE.right, TUBE.centery), 1)
        for label, a in (("ceiling", -math.pi), ("left wall", -math.pi / 2), ("floor", 0.0),
                         ("right wall", math.pi / 2), ("ceiling", math.pi)):
            y = max(TUBE.y + 1, min(TUBE.bottom - 15, self.y_of(a) - 7))
            self.text(label, (TUBE.right - 4 - self.small.size(label)[0], y), DIM, font=self.small)
        # the fast line and its hint stars
        pts = [(self.x_of(i + 0.5), self.y_of(tr.line(i))) for i in range(first, last)]
        for a, b in zip(pts, pts[1:]):
            pygame.draw.line(scr, (150, 70, 120), a, b, 1)
        for i in range(first, last):
            if tr.has_star(i):
                pygame.draw.circle(scr, (255, 220, 90), (self.x_of(i), self.y_of(tr.line(i))), 3)
        # doors and the finish line
        for i in range(first, last + 1):
            if tr.is_door(i):
                x = self.x_of(i)
                pygame.draw.line(scr, (200, 200, 220), (x, TUBE.y), (x, TUBE.bottom), 3)
                self.text("door", (x + 4, TUBE.y + 3), DIM, font=self.small)
        fx = self.x_of(lv.length)
        for k in range(0, TUBE.h + PROFILE.h + 20, 8):
            col = (240, 240, 250) if (k // 8) % 2 else (20, 20, 30)
            pygame.draw.rect(scr, col, (fx - 3, PROFILE.y + k, 6, 8))
        self.text("finish", (fx + 6, PROFILE.y + 4), TEXT, font=self.small)

        # objects
        for o in lv.objects:
            self.draw_object(o, o is self.obj)
        # what the tool would place, under the mouse
        mp = pygame.mouse.get_pos()
        if self.tool != "select" and TUBE.collidepoint(mp) and not self.prompt:
            seg = int(self.seg_of(mp[0]))
            if 0 <= seg < lv.length:
                ghost = new_object(self.tool, seg, self.a_of(mp[1], not pygame.key.get_mods() & pygame.KMOD_SHIFT))
                self.draw_object(ghost, False, ghost=True)

        # the cursor: where the preview looks from
        cx = self.x_of(self.cursor)
        pygame.draw.line(scr, (255, 255, 255), (cx, PROFILE.y), (cx, RULER.bottom), 1)
        scr.set_clip(clip)

        # ruler: segments, and seconds at cruising speed
        pygame.draw.rect(scr, PANEL, RULER)
        scr.set_clip(RULER)
        span = MAP.w / self.zoom
        tick = next(t for t in (10, 20, 50, 100, 200, 500, 1000) if span / t <= 14)
        for i in range(int(self.view0 // tick) * tick, int(self.seg_of(MAP.right)) + 1, tick):
            x = self.x_of(i)
            if MAP.x <= x <= MAP.right and i >= 0:
                pygame.draw.line(scr, DIM, (x, RULER.y), (x, RULER.y + 6), 1)
                self.text("%d  %.0fs" % (i, i * SEG / BASE_SPEED), (x + 3, RULER.y + 8), DIM, font=self.small)
        pygame.draw.polygon(scr, (255, 255, 255), ((cx - 6, RULER.y), (cx + 6, RULER.y), (cx, RULER.y + 8)))
        scr.set_clip(clip)
        pygame.draw.rect(scr, LINE, MAP.union(RULER), 1)
        self.text("course: kind, bend (pink, down = to the right), slope (yellow, up = climbing)",
                  (MAP.x, PROFILE.y - 18), DIM, font=self.small)
        self.text("tube unrolled, as seen from above: the fast line (pink) and its stars",
                  (MAP.x, TUBE.y - 15), DIM, font=self.small)

    def draw_object(self, o, selected, ghost=False):
        scr = self.screen
        k = OBJECT_KINDS[o["kind"]]
        col = k.colour if not ghost else tuple(c // 2 for c in k.colour)
        x, y = self.obj_pos(o)
        if o["kind"] == "boost":
            x0, x1 = self.x_of(o["seg"]), self.x_of(o["seg"] + k.length / SEG)
            h = 2.2 / 10.0 / math.pi * TUBE.h                # its width round the tube
            r = pygame.Rect(int(x0), int(y - h / 2), max(4, int(x1 - x0)), max(6, int(h)))
            pygame.draw.rect(scr, col, r)
            if selected:
                pygame.draw.rect(scr, (255, 255, 255), r.inflate(6, 6), 2)
        elif o["kind"] == "drone":
            sway = o["sway"] / math.pi * (TUBE.h / 2)
            if sway > 1:
                pygame.draw.line(scr, col, (x, y - sway), (x, y + sway), 1)
            if o["speed"] > 0:
                pygame.draw.line(scr, col, (x, y), (x + 10 + 20 * o["speed"], y), 1)
            pygame.draw.polygon(scr, col, ((x - 7, y), (x, y - 5), (x + 7, y), (x, y + 5)))
            if selected:
                pygame.draw.circle(scr, (255, 255, 255), (x, y), 11, 2)
        elif o["kind"] == "gate":
            pygame.draw.line(scr, col, (x, TUBE.y), (x, TUBE.bottom), 3)
            if selected:
                pygame.draw.rect(scr, (255, 255, 255), (x - 6, TUBE.y, 12, TUBE.h), 2)
        else:                                                # a kind without a look of its own
            pygame.draw.circle(scr, col, (x, y), 6)
            if selected:
                pygame.draw.circle(scr, (255, 255, 255), (x, y), 10, 2)

    def draw(self):
        scr = self.screen
        scr.fill(BG)
        self.hot = []
        self.renderer.draw(self.game)
        scr.blit(self.preview_surface, PREVIEW)
        pygame.draw.rect(scr, LINE, PREVIEW, 1)
        seg = int(self.cursor)
        self.text("segment %d   %.0f s in at cruising speed" % (seg, seg * SEG / BASE_SPEED),
                  (PREVIEW.x + 8, PREVIEW.bottom - 22), TEXT, font=self.small)
        self.draw_map()
        self.draw_panel()
        self.text("Keys", (HELP_X, 14), font=self.big)
        for i, line in enumerate(HELP):
            self.text(line, (HELP_X, 48 + i * 22), DIM, font=self.mono)
        if self.note_t > 0:
            self.text(self.note, (HELP_X, PREVIEW.bottom - 22), WARN, font=self.small)
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

    # -------------------------------------------------------------- loop
    def run(self, frames=None, screenshot=None, script=None):
        """script: {frame: function(editor)} to drive it in tests."""
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
                    self.on_mouse_up(ev)
                elif ev.type == pygame.MOUSEMOTION:
                    self.on_mouse_move(ev)
            if script and count in script:
                script[count](self)
            self.note_t -= dt
            self.quit_armed = max(0.0, self.quit_armed - dt)
            self.step(dt)
            self.draw()
            pygame.display.flip()
            count += 1
            if frames and count >= frames:
                if screenshot:
                    pygame.image.save(self.screen, screenshot)
                return


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH
    try:
        editor = LevelEditor(path)
    except (OSError, LevelError) as e:
        sys.exit("Can't edit %s: %s" % (path, e))
    try:
        editor.run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
