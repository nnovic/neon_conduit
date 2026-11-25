"""The tutorial at the start of the first race: tips shown one after the other as the
racer goes down the opening straight (see START_STRAIGHT in config.py) and the fixed
course after it."""
from .config import DRAW, START_STRAIGHT

FADE = 0.3                  # seconds a tip takes to fade in, and to fade out


class Tip:
    def __init__(self, at, text, secs=4.0, then=None, clock=False):
        self.at = at            # segment the racer reaches when the tip comes up
        self.text = text
        self.secs = secs        # seconds it stays up
        self.then = then        # what happens as it goes (see Game._tutorial_event), or None
        self.clock = clock      # True: the race clock shows and starts running as it comes up


# The course the tutorial runs on, after the opening straight: the same every time, with
# nothing on it. Sections of (length in segments, peak curvature, peak pitch); the random
# track carries on after them.
BEND = 48                   # segments in each bend, and in each slope
BOOST_RUN = 134             # segments of straight between the bends and the slopes
LAST_RUN = 100              # segments of the last straight, up to the door
COURSE = [
    (BEND, 0.3, 0.0),       # a bend to the right, with hint stars round its outside...
    (BEND, -0.3, 0.0),      # ...then one to the left
    (BOOST_RUN, 0.0, 0.0),  # a straight, with the ring of boost pads
    (BEND, 0.0, 0.2),       # up...
    (BEND, 0.0, -0.2),      # ...and down
    (LAST_RUN, 0.0, 0.0),   # a straight for the rest of the tutorial, while the clock comes in,
                            # ending at a door into the real game (see Track)
]
BENDS_AT = START_STRAIGHT               # segment where the first bend begins
BOOSTS_AT = BENDS_AT + 2 * BEND         # ...the straight after the bends
SLOPES_AT = BOOSTS_AT + BOOST_RUN       # ...the slopes
STRAIGHT_AT = SLOPES_AT + 2 * BEND      # ...the last straight
DOOR_AT = STRAIGHT_AT + LAST_RUN        # ...and the door at its end
SKIP_UNTIL = DOOR_AT - DRAW             # the tutorial can be skipped until the door comes into view
SKIP_TO = DOOR_AT - 35                  # skipping it takes the racer here, just short of the door...
SKIP_FADE = 0.35                        # ...under a fade to black and back, this many seconds each way

# Until the tip that starts the clock, there is none: it is hidden and stands still.
TIPS = [
    Tip(18, "Destroy the drones before they hit you.", 3.0, then="drone_ring"),   # about 1.5 s in
    Tip(BENDS_AT - 10, "Stars show the optimal path.", 4.0),   # going into the bends
    Tip(BOOSTS_AT, "Boosts also make you invincible.", 3.0, then="boost_ring"),   # out of the bends
    Tip(STRAIGHT_AT, "Do not run out of time.", 4.0, clock=True),   # past the slopes
    Tip(DOOR_AT, "Good luck!", 2.5),                    # through the door, into the real game
]


class Tutorial:
    """Which tip is up, and for how long: one at a time, in order, each once its segment
    is reached and the tip before it has gone."""

    def __init__(self, tips=TIPS):
        self.tips = tips
        self.i = 0              # the tip up, or next to come up
        self.t = None           # seconds it has been up, or None while it waits for its segment
        self.started = False    # True once the race it belongs to is under way
        self.clock = not any(t.clock for t in tips)   # whether the race clock runs yet
        self.seg = 0            # the racer's segment

    def update(self, dt, seg):
        """Move on dt seconds, the racer being in segment seg. Returns the tip that has
        just gone, if one has."""
        self.started = True
        self.seg = seg
        if self.i >= len(self.tips):
            return None
        tip = self.tips[self.i]
        if self.t is None:
            if seg < tip.at:
                return None
            self.t = 0.0
            self.clock = self.clock or tip.clock
        self.t += dt
        if self.t >= tip.secs:
            self.i, self.t = self.i + 1, None
            return tip
        return None

    @property
    def done(self):
        """True once every tip has been shown, or the tutorial skipped."""
        return self.i >= len(self.tips)

    @property
    def can_skip(self):
        """True while the tutorial runs and its door is not yet in view."""
        return not self.done and self.seg < SKIP_UNTIL

    def skip(self):
        """Drop the tip up and every one still to come, but for those at the door; and
        start the clock."""
        self.i = next((k for k, tip in enumerate(self.tips) if tip.at >= DOOR_AT), len(self.tips))
        self.t = None
        self.clock = True

    def current(self):
        """The tip up and its opacity (0 .. 1), or None."""
        if self.t is None:
            return None
        tip = self.tips[self.i]
        return tip, max(0.0, min(1.0, self.t / FADE, (tip.secs - self.t) / FADE))
