"""How a boat lying on the water moves: it bobs up and down and rocks from side to side.

A building on the "Houses" layer floats when its Tiled ``Afloat`` property is
true (``House.afloat``), as the fishing boat at the harbour pier does. The map
view draws it lifted by ``bob`` and turned by ``roll`` about the middle of its
foot, its waterline (``afloat_view.py``); the barge under the cranes bobs the
same way (``crane_view.py``'s ``BOB_PX``, ``BOB_PERIOD_S``). The bob and the
roll have periods that do not divide into each other, so the motion does not
repeat soon, and each boat is put out of step with the others by where it lies.
A longer boat rocks less and slower (``size_factor``: by the square root of its
length against the fishing boat's), so a ship's masthead does not sweep about.

No pygame here: the motion is a function of the time alone.
"""

import math
from typing import Tuple

#: Up and down, world px (as the barge's), and its period in seconds
BOB_PX = 0.8
BOB_PERIOD_S = 3.4
#: Rocking from side to side: at most this many degrees either way, and its period in seconds
ROLL_DEG = 1.2
ROLL_PERIOD_S = 5.3
#: The roll is drawn in steps of this many degrees, so the turned pictures can be kept
ROLL_STEP_DEG = 0.25
#: How far apart, in world px, two boats have to lie to rock a whole period out of step
PHASE_SPREAD_PX = 200.0
#: The length (world px along its waterline, its collision box's width) of a boat moving as above:
#: the fishing boat's; a longer one bobs and rocks less and slower, a shorter one no more than it
REFERENCE_LENGTH_PX = 138.0


def size_factor(length: float) -> float:
    """How much slower and, inversely, how much less a boat this long (world px) moves than the reference one;
    never below 1."""
    return max(1.0, length / REFERENCE_LENGTH_PX) ** 0.5


def motion(seconds: float, x: float, length: float = REFERENCE_LENGTH_PX) -> Tuple[float, float]:
    """(bob, roll) at this time of a boat `length` world px long lying at world x: world px up (negative is
    up, as on the screen) and degrees anticlockwise, in steps of ROLL_STEP_DEG."""
    phase = 2 * math.pi * x / PHASE_SPREAD_PX
    size = size_factor(length)
    bob = -BOB_PX / size * math.sin(2 * math.pi * seconds / (BOB_PERIOD_S * size) + phase)
    roll = ROLL_DEG / size * math.sin(2 * math.pi * seconds / (ROLL_PERIOD_S * size) + phase * 0.7)
    return bob, round(roll / ROLL_STEP_DEG) * ROLL_STEP_DEG
