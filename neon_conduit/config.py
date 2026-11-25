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
CRASH_KEEP = 0.2        # fraction of speed kept after hitting a drone
INVINCIBLE_TIME = BOOST_TIME   # seconds a boost pad also makes the sled ram through drones unharmed
