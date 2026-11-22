"""Every tunable of the game in one place: screen, tube, track, physics and timing."""
import math

DEVELOPER_MODE = False  # True draws the fast line through bends on the track

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

# ----------------------------------------------------------------- camera
PLAYER_D = 12.0         # how far ahead of the camera the sled sits
CAM_H = 3.5             # camera height above the surface the sled is riding on
CAM_LAG = 0.45          # how far the camera lags behind the sled's way round the tube (0 = none)

# ---------------------------------------------------------- open sections
WALL_H = 2.2            # height of the upright kerbs lining open sections
WALL_T = WALL_H         # ...and their thickness
OPEN_CHANCE = 0.12      # chance that the next stretch of track is an open run
OPEN_RUN = (2, 4)       # sections chained into one open run
WIDE_CHANCE = 0.5       # chance that an open run widens out
WIDE_HW = (13.0, 18.0)  # floor half-width of a widened run
WIDE_TAPER = 20         # segments over which the kerbs splay out and back in

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
# Hint stars float above the fast line through bends, showing the way.
STAR_EVERY = 3          # one star every this many segments...
STAR_BEND = 0.5         # ...where the bend is at least this sharp (see Track.bend)
STAR_H = 1.3            # height above the surface
STAR_SCORE = 25         # points for riding through one

# ---------------------------------------------------------------- objects
SLED_HW = 1.5           # half-widths, in world units
BOOST_HW = 2.2
BOOST_CHANCE = 0.375    # chance that a section gets a boost pad (one at most)
SCRAPE_DRAG = 130.0     # speed lost per second while grinding along a kerb
SCRAPE_FLOOR = 0.5      # ...down to this fraction of top speed

# ----------------------------------------------------------- race & speed
GATE_SEGS = 260         # segments between checkpoint gates
START_TIME = 25.0
BASE_SPEED = 100.0      # cruising speed at the first gate
SPEED_CAP = 135.0       # cruising speed stops rising here
BOOST_MULT = 1.65       # speed multiplier while boosting
CRASH_KEEP = 0.2        # fraction of speed kept after hitting a drone
