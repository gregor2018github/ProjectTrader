"""A sheep led on a leash: where it walks behind the player, and how the rope between them hangs.

The sheep keeps to the player's own trail (``Leash.record`` keeps the last few
tiles of where their feet went), walking along it, not across its bends (and
never losing its place on it where it doubles back), to
``FOLLOW_GAP`` behind them, so it only ever goes where the player went: round
the corner of a wall, through a gate, over a bridge. It stands while the player is within ``STAND_WITHIN``,
walks a little faster than them while the rope is slack (``CATCH_UP``) and
faster still once it is taut, and is put straight behind them if it is left
farther than ``SNAP_DISTANCE`` (after a load, a rest, a jump of the clock).

The rope (``rope_points``) runs from the player's hand to the sheep's neck,
``LENGTH`` long: a curve that sags by the slack and sways a little, taut and
straight once they are a rope's length apart.

No pygame; the sheep is moved by Sheep.move_led, the rope drawn by
src/ui/layout_modules/leash_view.py.
"""

import math
from collections import deque
from typing import Deque, List, Optional, Tuple

Point = Tuple[float, float]

#: The rope's length, in world pixels (about 2 tiles)
LENGTH = 66.0
#: How far behind the player's feet, along their trail, the sheep aims
FOLLOW_GAP = 46.0
#: It stands still while its feet are this near the player's
STAND_WITHIN = 40.0
#: Its speed as a share of the player's while the rope is slack, and once it is taut
CATCH_UP = 1.1
TAUT_CATCH_UP = 1.6
#: Farther than this from the player it is put straight behind them
SNAP_DISTANCE = 6 * 32.0
#: Trail points closer together than this are not kept
TRAIL_STEP = 3.0
#: How much trail is kept behind the player, in world pixels
TRAIL_KEEP = 4 * LENGTH
#: More trail points than this (the player wandering round a standing sheep) and it starts afresh
MAX_TRAIL_POINTS = 600
#: Where the trail comes back within this of the sheep, it takes the shortcut
SHORTCUT = 12.0
#: ... if the way round is at least this long (a loop, not the bend of a corner)
LOOP_FROM = 4 * SHORTCUT
#: The rope's sway: its period in seconds and its most, in world pixels
SWAY_PERIOD_S = 2.6
SWAY_MAX = 2.5
#: How many straight pieces the drawn rope is made of
ROPE_SEGMENTS = 14


class Leash:
    """The player's trail, which the sheep on the leash follows, and how far along it the sheep is.

    Each trail point keeps its distance from the trail's start (``reach``), and the
    sheep its own distance (``progress``), which only ever grows: it is never
    worked out again from where the sheep stands, so where the trail doubles back
    or crosses itself the sheep cannot jump between its parts. If the trail comes
    back past the sheep (the player turned round), it takes that shortcut
    (``SHORTCUT``) rather than walking the loop.
    """

    def __init__(self) -> None:
        self.trail: Deque[Point] = deque()
        #: Each trail point's distance along the trail from where it was begun
        self.reach: Deque[float] = deque()
        #: How far along the trail the sheep is, on the same measure
        self.progress: float = 0.0

    def reset(self, player_feet: Point, sheep_feet: Optional[Point] = None) -> None:
        """Start a new trail: from the sheep (if given) to the player, the sheep at its start."""
        self.trail.clear()
        self.reach.clear()
        self.progress = 0.0
        if sheep_feet is not None:
            self.trail.append(sheep_feet)
            self.reach.append(0.0)
        self._append(player_feet)

    def _append(self, point: Point) -> None:
        last = self.reach[-1] + math.dist(self.trail[-1], point) if self.trail else 0.0
        self.trail.append(point)
        self.reach.append(last)

    def record(self, player_feet: Point) -> None:
        """Add where the player's feet are now, and forget the trail beyond TRAIL_KEEP behind them
        (never the part the sheep still has to walk)."""
        if not self.trail:
            self._append(player_feet)
            return
        if math.dist(self.trail[-1], player_feet) < TRAIL_STEP:
            return
        self._append(player_feet)
        keep_from = min(self.reach[-1] - TRAIL_KEEP, self.progress)
        while len(self.trail) > 2 and self.reach[1] <= keep_from:
            self.trail.popleft()
            self.reach.popleft()
        if len(self.trail) > MAX_TRAIL_POINTS:
            # The player has wandered round the standing sheep for long: start afresh from it
            self.reset(player_feet, self._point_at(self.progress))

    def target(self, gap: float = FOLLOW_GAP) -> Optional[Point]:
        """The point `gap` behind the player along their trail (its start if it is shorter)."""
        if not self.trail:
            return None
        return self._point_at(self.reach[-1] - gap)

    def _point_at(self, distance: float) -> Point:
        """The point of the trail `distance` along it (clamped to its ends)."""
        points, reach = self.trail, self.reach
        if distance <= reach[0]:
            return points[0]
        for index in range(1, len(points)):
            if reach[index] >= distance:
                span = reach[index] - reach[index - 1]
                t = (distance - reach[index - 1]) / span if span else 0.0
                a, b = points[index - 1], points[index]
                return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        return points[-1]

    def _shortcut(self, sheep_feet: Point) -> None:
        """Where the trail comes back past the sheep (the player turned round), cut out the loop:
        the trail then runs from the sheep straight to the latest point of it within SHORTCUT."""
        for index in range(len(self.trail) - 1, 0, -1):
            if self.reach[index] <= self.progress + LOOP_FROM:
                return
            if math.dist(self.trail[index], sheep_feet) <= SHORTCUT:
                rest = list(self.trail)[index:]
                self.trail.clear()
                self.reach.clear()
                self.trail.append(sheep_feet)
                self.reach.append(self.progress)
                for point in rest:
                    self._append(point)
                return

    def step(self, sheep_feet: Point, player_feet: Point, player_speed: float, dt: float) -> Tuple[Point, bool]:
        """Where the sheep's feet go this frame, and whether it walked.

        Args:
            sheep_feet: Where its feet are.
            player_feet: Where the player's are.
            player_speed: The player's walking speed now, world px a second.
            dt: Seconds of the frame.
        """
        apart = math.dist(sheep_feet, player_feet)
        if apart > SNAP_DISTANCE or not self.trail:
            spot = self.target() if self.trail else player_feet
            self.reset(player_feet, spot)
            return spot, False
        self.progress = max(self.progress, self.reach[0])
        self._shortcut(sheep_feet)
        if apart <= STAND_WITHIN or len(self.trail) < 2:
            return sheep_feet, False
        goal = self.reach[-1] - FOLLOW_GAP
        if self.progress >= goal - 0.5:
            return sheep_feet, False
        pace = TAUT_CATCH_UP if apart >= LENGTH else CATCH_UP
        self.progress = min(goal, self.progress + max(player_speed, 1.0) * pace * dt)
        spot = self._point_at(self.progress)
        return spot, math.dist(spot, sheep_feet) > 0.05


def _sag_for(span: float, length: float) -> float:
    """How deep a parabola over `span` hangs to be `length` long (found by halving)."""
    if span >= length:
        return 0.0
    low, high = 0.0, length / 2.0
    for _ in range(30):
        sag = (low + high) / 2.0
        if _parabola_length(max(span, 1e-6), sag) < length:
            low = sag
        else:
            high = sag
    return (low + high) / 2.0


def _parabola_length(span: float, sag: float) -> float:
    """The length of a parabola over `span` hanging `sag` deep at its middle."""
    if sag <= 0:
        return span
    k = 4.0 * sag / span            # the slope at either end
    root = math.sqrt(1.0 + k * k)
    return span / 2.0 * (root + math.asinh(k) / k)


def rope_points(hand: Point, neck: Point, seconds: float, length: float = LENGTH,
                segments: int = ROPE_SEGMENTS) -> List[Point]:
    """The rope from the player's hand to the sheep's neck, as points along it.

    It hangs in a curve as deep as the slack allows (a parabola about as long as
    the rope), swaying a little from side to side, and runs straight once taut.

    Args:
        hand: Where it is held, world pixels.
        neck: Where it is tied, world pixels.
        seconds: Real seconds, for the sway.
        length: The rope's length.
        segments: Pieces of the curve.
    """
    span = math.dist(hand, neck)
    sag = _sag_for(span, length)
    sway = SWAY_MAX * min(1.0, sag / 10.0) * math.sin(seconds * 2.0 * math.pi / SWAY_PERIOD_S)
    points = []
    for index in range(segments + 1):
        t = index / segments
        bulge = 4.0 * t * (1.0 - t)
        points.append((hand[0] + (neck[0] - hand[0]) * t + sway * bulge,
                       hand[1] + (neck[1] - hand[1]) * t + sag * bulge))
    return points
