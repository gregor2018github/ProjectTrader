"""Where on the screen a sprite of the map lands, in whole pixels."""

import math


def screen_pixel(pos: tuple[float, float]) -> tuple[int, int]:
    """The whole screen pixel a queued sprite is blitted at: halves always rounded up.

    Python's round() takes a half to the even neighbour, so a sprite whose place
    on screen ends in .5 (an object at an odd world pixel, at a zoom of 1.25)
    would land a pixel left or right by turns as the camera moves on, and
    wiggle against everything round it."""
    return math.floor(pos[0] + 0.5), math.floor(pos[1] + 0.5)
