"""Every tunable of the game in one place: screen, tube, track, physics and timing."""
import math
import os

DEVELOPER_MODE = False  # True draws the fast line through bends on the track, and the guns' lock-on

# ----------------------------------------------------------------- screen
SCREEN = (1024, 640)
FOCAL = 600.0           # projection scale: larger zooms in
HORIZON = 0.47          # height of the vanishing point, as a fraction of the screen
NEAR = 0.8              # nothing closer to the camera than this is drawn

# ------------------------------------------------------------------- tube
R = 10.0                # tube radius
SEG = 5.0               # length of one track segment
SIDES = 16              # polygon sides of the tube
DRAW = 60               # rings drawn ahead of the camera
FLOOR_A = math.pi / 4   # the tube is flat below this angle either side of the bottom
FLOOR_Y = R * math.cos(FLOOR_A)
FLOOR_HW = FLOOR_Y * math.tan(FLOOR_A)   # half-width of the flat floor
FLAT_MAX = 1.4          # angles are clamped here when mapped onto an open section's flat floor
PATTERNS_FILE = os.path.join(os.path.dirname(__file__), "conduit_patterns.txt")   # tunnel wall patterns

# ------------------------------------------------------------------ music
TITLE_MUSIC = os.path.join(os.path.dirname(__file__), "assets", "Hero_Immortal.mp3")   # see CREDITS.md
TITLE_MUSIC_VOLUME = 0.6
TITLE_MUSIC_FADE = 1.0  # seconds the title music takes to fade in
# The race music: any one file from this folder, picked at random as the real game starts
# (just past the race's first door). The folder is git-ignored: whatever is in it stays local.
RACE_MUSIC_DIR = os.path.join(os.path.dirname(__file__), "music")
RACE_MUSIC_EXTS = (".mp3", ".ogg", ".wav", ".flac", ".opus", ".mod", ".xm", ".it", ".s3m")
RACE_MUSIC_VOLUME = 0.6
RACE_MUSIC_DELAY = 1.0  # seconds after the sled passes the race's first door that the race music starts
RACE_MUSIC_FADE = 1.5   # seconds the race music takes to fade in, and out at game over
NOW_PLAYING_FADE = 0.6  # seconds the HUD's track panel (title, artist, album) takes to fade in or out...
NOW_PLAYING_HOLD = 8.0  # ...and stays up in between, as the race music starts...
NOW_PLAYING_EVERY = 60.0  # ...and again this many seconds later, and so on while it plays
STAR_SOUND = os.path.join(os.path.dirname(__file__), "assets", "completetask_0.wav")   # see CREDITS.md
STAR_SOUND_VOLUME = 0.5
BOOST_SOUND = os.path.join(os.path.dirname(__file__), "assets", "Sequence_SciFi Pack Vol 1_Energy BuildUp to LOOP_Med_Start_var 1.wav")   # see CREDITS.md
BOOST_SOUND_VOLUME = 0.6
DOOR_SOUND = os.path.join(os.path.dirname(__file__), "assets", "rock_metal_slide_2.wav")   # see CREDITS.md
DOOR_SOUND_VOLUME = 1.0   # the recording itself is quiet (peaks near -14 dBFS)
# The sled's engine: a synthesized hum whose pitch follows the speed, from a low idle while
# standing still up to its highest at full boost on top cruising speed (SPEED_CAP x BOOST_MULT).
ENGINE_IDLE_HZ = 73.106   # its pitch at a standstill, in Hz...
ENGINE_TOP_HZ = 257.617   # ...and at full speed, rising evenly in musical steps in between
ENGINE_VOLUME = 0.6    # its loudness at full speed, 0 .. 1...
ENGINE_IDLE_VOLUME = 0.425   # ...and at a standstill
ENGINE_BUZZ = 0.8      # its tone, 0 .. 1: 0 a soft, round hum, 1 a harsh buzz (more overtones)
ENGINE_SHIMMER = 3.0    # a second voice this many percent higher: the two beat, a slow shimmer
                        # (0: one plain voice)
ENGINE_THROB = 0.502      # how deep it pulses, at half its pitch, 0 .. 1 (0: a steady drone)
# Those can be tuned by ear with tools/engine_sound.py, which writes them back here.
ENGINE_FADE = 0.4       # seconds it takes to fade in (at the start line) and out (pause, game over)
ENGINE_LEAD = 0.12      # seconds of engine sound made ahead of what is playing: a slow frame
                        # shorter than this goes unheard; a pitch change is heard this late
ENGINE_RING = 1.0       # seconds of sound in the loop the engine is written into, as it plays

# ----------------------------------------------------------------- camera
PLAYER_D = 12.0         # how far ahead of the camera the sled sits
CAM_H = 3.5             # camera height above the surface the sled is riding on
CAM_LAG = 0.45          # how far the camera lags behind the sled's way round the tube (0 = none)

SKY_RISE_MAX = 140.0    # pixels the horizon moves up or down at most as the track dips or climbs
SKY_RISE_GAIN = 40.0    # ...and how many pixels per unit of dive (see Game.dive) below that
DIVE_SETTLE = 2.0       # seconds for the horizon to settle back after a dip or a climb

# ---------------------------------------------------------- open sections
WALL_H = 2.2            # height of the upright kerbs lining open sections
WALL_T = WALL_H         # ...and their thickness
OPEN_CHANCE = 0.12      # chance that the next stretch of track is an open run
OPEN_RUN = (2, 4)       # sections chained into one open run
TUNNEL_MIN = 100        # segments of tube at least between two open runs (about 4 s at cruising speed)
START_STRAIGHT = 160    # segments of straight, empty tube the track starts with: room for the drone ring
START_PATTERN = "original"   # wall pattern of the first tunnel (see conduit_patterns.txt)
WIDE_CHANCE = 0.5       # chance that an open run widens out
WIDE_HW = (13.0, 18.0)  # floor half-width of a widened run
WIDE_TAPER = 20         # segments over which the kerbs splay out and back in
THEMES_FILE = os.path.join(os.path.dirname(__file__), "outdoor_themes.txt")   # outdoor themes (themes.py)
AIR_CHANCE = 0.25       # chance that an open run is in the air rather than ground-level

# ------------------------------------------------------------------ doors
DOOR_OPEN_AT = 115.0    # distance ahead of the sled at which a tube door starts to open
DOOR_HEAR_NEAR = 12.0   # the door's slide is at full volume at the door, half as loud this far
                        # from it, a tenth as loud at DOOR_OPEN_AT (smaller: a sharper swell)
DOOR_SLIDE = 70.0       # distance over which it slides fully open

# -------------------------------------------------------------- fast line
# The fast line through a bend runs up the outside, further out the tighter the bend.
LINE_GAIN = 4.5         # wall angle of the line per unit of curvature
LINE_MAX = 1.8          # ...up to this angle
LINE_BEND = 0.12        # curvature at which straying from the line costs full price
LINE_TOL = 2.5          # sideways distance from the line that is still free
LINE_FALLOFF = 8.0      # further distance over which the penalty grows to its maximum
LINE_SLOW = 0.35        # fraction of top speed lost when far off the line in a bend
LINE_HW = 0.35          # half-width of the line as drawn in developer mode
# Hint stars are painted on the fast line through bends, showing the way.
STAR_EVERY = 6          # one star every this many segments...
STAR_BEND = 0.5         # ...where the bend is at least this sharp (see Track.bend)
STAR_R = 2.2            # radius, on the surface
STAR_STRETCH = 2.5      # stretched along the track, like road markings, so it reads from a low camera
STAR_REACH = STAR_STRETCH * STAR_R * 1.4   # how far a star (with its glow) extends along the track
STAR_SCORE = 25         # points for riding through one

# ---------------------------------------------------------------- objects
SLED_HW = 1.5           # half-widths, in world units
BOOST_HW = 2.2
AIM_SLOPE = 0.08        # full aim lifts (Down) or drops (Up) shots this many units per unit forward
AIM_RATE = 4.0          # how fast the aim swings, in full ranges per second
GUN_SPREAD = 1.2        # each twin gun sits this far left / right of the sled's middle
BULLET_SPEED = 260.0    # shots fly this much faster than the sled was going when they left
BULLET_LIFE = 0.9       # seconds before a shot fizzles out
LOCK_RANGE = 60.0       # drones up to this far ahead can be locked on to (near ones only)
LOCK_ANGLE = 0.14       # ...if a straight shot reaches them within this angle (radians, 8 deg)
                        # of the sled's heading: the target must be roughly in front
DRONE_SPEED = 0.5       # drones fly forward at this fraction of top speed
RING_DRONES = 12        # the tutorial's ring of drones: this many, evenly round the tube
                        # (closer than a sled's width apart: no way through but to shoot one)
RING_AHEAD = 200.0      # ...this far ahead of the racer when it appears, hanging still
                        # (and so is its ring of boost pads, as many, with no way to miss one)
BOOST_CHANCE = 0.375    # chance that a section gets a boost pad (one at most)
SCRAPE_DRAG = 130.0     # speed lost per second while grinding along a kerb
SCRAPE_FLOOR = 0.5      # ...down to this fraction of top speed

# ----------------------------------------------------------- race & speed
GATE_SEGS = 260         # segments between checkpoint gates
START_TIME = 25.0
BASE_SPEED = 100.0      # cruising speed at the first gate
SPEED_CAP = 135.0       # cruising speed stops rising here
BOOST_MULT = 1.65       # speed multiplier while boosting
BOOST_TIME = 3.5        # seconds a boost pad keeps it going
BOOST_FOCAL = 0.8       # the camera's focal length at full boost speed, times its usual one: a
                        # wider view, the tube rushing past; eased in and out with the speed...
BOOST_WARP = 0.5        # ...and the perspective bent, as much more at full boost: sizes fall
                        # off as 1 / depth ** (1 + this), the sled's depth keeping its size, so
                        # near walls swell and the far tube is squeezed towards the middle.
# Both at full strength only for a chain of boosts (pads hit one after the other, each
# before the last has worn off): this much of it for the 1st pad of a chain, the 2nd, the
# 3rd and on. Eased from one to the next over BOOST_CHAIN_EASE seconds.
BOOST_CHAIN = (0.15, 0.55, 1.0)
BOOST_CHAIN_EASE = 0.6
CRASH_KEEP = 0.2        # fraction of speed kept after hitting a drone
INVINCIBLE_TIME = BOOST_TIME   # seconds a boost pad also makes the sled ram through drones unharmed
