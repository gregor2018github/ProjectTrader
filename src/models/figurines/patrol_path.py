"""A polyline an NPC walks along, parametrized by distance travelled.

Tiled polygons and polylines come in as a list of corner points. Walking
straight at a corner and turning on arrival is fiddly and drifts off the line,
so instead the path is measured once and every position is addressed by how far
along it is. Moving is then just "advance my distance and ask where that puts
me", which stays exactly on the line no matter the frame rate.
"""

import math
import random
from typing import List, Sequence, Tuple


class PatrolPath:
    """An open or closed polyline addressed by arc length."""

    def __init__(self, points: Sequence[Tuple[float, float]], closed: bool = True) -> None:
        """Measure the path.

        Args:
            points: The corner points in world coordinates.
            closed: True for a Tiled polygon (the last point joins the first),
                False for a polyline.
        """
        self.points: List[Tuple[float, float]] = [(float(x), float(y)) for x, y in points]
        # Tiled writes the closing point explicitly in some shapes and leaves it
        # implicit in others, so only add it when it is genuinely missing.
        if closed and len(self.points) > 2 and self.points[0] != self.points[-1]:
            self.points.append(self.points[0])
        self.closed: bool = bool(closed)

        # Cumulative distance from the start to each corner, so that a lookup is
        # a walk over the segments rather than a re-measure of the whole path.
        self.segment_ends: List[float] = []
        total = 0.0
        for start, end in zip(self.points, self.points[1:]):
            total += math.dist(start, end)
            self.segment_ends.append(total)
        self.length: float = total

    def __bool__(self) -> bool:
        """A path with no length cannot be walked."""
        return self.length > 0.0

    def normalize(self, distance: float) -> float:
        """Wrap or clamp a distance into the path's range.

        Args:
            distance: Distance along the path, possibly out of range.

        Returns:
            float: A distance inside ``[0, length]``.
        """
        if self.length <= 0.0:
            return 0.0
        if self.closed:
            return distance % self.length
        return max(0.0, min(self.length, distance))

    def position_at(self, distance: float) -> Tuple[float, float]:
        """The world position that far along the path.

        Args:
            distance: Distance along the path.

        Returns:
            Tuple: World (x, y).
        """
        if not self.points:
            return (0.0, 0.0)
        if self.length <= 0.0:
            return self.points[0]

        distance = self.normalize(distance)
        previous_end = 0.0
        for index, end in enumerate(self.segment_ends):
            if distance <= end or index == len(self.segment_ends) - 1:
                start = self.points[index]
                finish = self.points[index + 1]
                span = end - previous_end
                t = 0.0 if span <= 0.0 else (distance - previous_end) / span
                return (
                    start[0] + (finish[0] - start[0]) * t,
                    start[1] + (finish[1] - start[1]) * t,
                )
            previous_end = end
        return self.points[-1]

    def random_distance(self) -> float:
        """A uniformly random point along the path.

        Returns:
            float: Distance along the path.
        """
        return random.uniform(0.0, self.length)

    def signed_gap(self, start: float, target: float) -> float:
        """How far to walk from one distance to another, and in which direction.

        On a closed path this takes whichever way round is shorter, so the NPC
        never loops the long way for a step it could take backwards.

        Args:
            start: Current distance along the path.
            target: Wanted distance along the path.

        Returns:
            float: Signed distance — negative means walk backwards.
        """
        gap = target - start
        if self.closed and self.length > 0.0:
            gap = (gap + self.length / 2.0) % self.length - self.length / 2.0
        return gap
