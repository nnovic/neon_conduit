"""Neon Conduit - an original tunnel racer written with pygame.

Ride a hover sled through an endless, procedurally generated tube.  Bends
have a fast line up the outside wall: stray from it and you lose speed.
Boost pads sit on that line, drones get in the way, and the clock only stops
if you reach the next gate.

Controls
    Left / Right (or A / D)   steer around the tube wall
    Down / Up                 aim higher / lower (shots otherwise leave along the slope)
    S                         brake
    Space                     fire
    P                         pause
    Enter                     start / restart
    Esc                       quit

Modules
    config      every tunable: screen, tube, track, physics, timing
    geometry    shape of the tube: angles, surface positions, distances
    palette     colours, fog and tube wall patterns
    track       the endless, procedurally generated track
    game        game state and rules (no drawing, no keyboard)
    render      3D drawing of the world
    decor       360-degree backdrops of the outdoor runs (images in assets/)
    hud         head-up display and title / game-over / pause screens
    audio       synthesized sound effects
    app         window, main loop and command line
"""
from .game import Controls, Game
from .track import Track

__all__ = ["Controls", "Game", "Track"]
