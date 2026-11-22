"""How a boat lying on the water moves: it bobs up and down and rocks from side to side.

A building on the "Houses" layer floats when its Tiled ``Afloat`` property is
true (``House.afloat``), as the fishing boat at the harbour pier does. The map
view draws it lifted by ``bob`` and turned by ``roll`` about the middle of its
foot, its waterline (``afloat_view.py``); the barge under the cranes bobs the
same way (``crane_view.py``'s ``BOB_PX``, ``BOB_PERIOD_S``). The bob and the
roll have periods that do not divide into each other, so the motion does not
repeat soon, and each boat is put out of step with the others by where it lies.

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


def motion(seconds: float, x: float) -> Tuple[float, float]:
    """(bob, roll) at this time of a boat lying at world x: world px up (negative is up, as on the
    screen) and degrees anticlockwise, in steps of ROLL_STEP_DEG."""
    phase = 2 * math.pi * x / PHASE_SPREAD_PX
    bob = -BOB_PX * math.sin(2 * math.pi * seconds / BOB_PERIOD_S + phase)
    roll = ROLL_DEG * math.sin(2 * math.pi * seconds / ROLL_PERIOD_S + phase * 0.7)
    return bob, round(roll / ROLL_STEP_DEG) * ROLL_STEP_DEG
