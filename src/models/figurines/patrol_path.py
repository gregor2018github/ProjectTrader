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


def signed_area(points: Sequence[Tuple[float, float]]) -> float:
    """Twice the signed area of a polygon, by the shoelace formula.

    Only the sign is used here, to tell which side of an edge the inside is on.

    Args:
        points: The corner points, without a repeated closing point.

    Returns:
        float: Positive or negative depending on the winding order.
    """
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + [points[0]]):
        total += x1 * y2 - x2 * y1
    return total


def inset_polygon(
    points: Sequence[Tuple[float, float]], margin: float
) -> List[Tuple[float, float]]:
    """Pull a polygon's outline inwards, away from its own edges.

    A movement polygon traced along whole tiles runs right up against whatever
    it surrounds, so an NPC walking it brushes the scenery. Insetting moves
    every edge ``margin`` pixels towards the inside — including the edges of a
    concavity, which move away from the thing sitting in it — and each corner to
    where its two shifted edges now cross. On the right-angled corners these
    shapes are drawn with, that is exact.

    Args:
        points: The corner points, without a repeated closing point.
        margin: How far to pull in, in world pixels.

    Returns:
        List: The inset corner points, or the originals when the margin is not
        usable — too small to matter, or large enough to turn the shape inside
        out.
    """
    original = [(float(x), float(y)) for x, y in points]
    if margin <= 0.0 or len(original) < 3:
        return original

    # Which perpendicular of an edge points into the shape depends on the
    # winding order, so settle that once for the whole polygon.
    winding = 1.0 if signed_area(original) > 0.0 else -1.0

    def inward_normal(start: Tuple[float, float], end: Tuple[float, float]) -> Tuple[float, float]:
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        if length <= 0.0:
            return (0.0, 0.0)
        return (-dy / length * winding, dx / length * winding)

    count = len(original)
    result: List[Tuple[float, float]] = []
    for index, corner in enumerate(original):
        n1 = inward_normal(original[index - 1], corner)
        n2 = inward_normal(corner, original[(index + 1) % count])
        # Walk out along the bisector far enough that both edges end up exactly
        # `margin` from where they were. The scale blows up as the corner closes
        # to a spike, so fall back to a plain offset there.
        scale = 1.0 + n1[0] * n2[0] + n1[1] * n2[1]
        if scale < 1e-6:
            result.append((corner[0] + n1[0] * margin, corner[1] + n1[1] * margin))
        else:
            result.append((
                corner[0] + (n1[0] + n2[0]) / scale * margin,
                corner[1] + (n1[1] + n2[1]) / scale * margin,
            ))

    # Too big a margin folds the shape through itself. Pulling edges inwards can
    # only ever shrink a polygon, so a result that kept none of that — reversed
    # winding, or no smaller than it started — is a knot, not an inset, and is
    # better ignored than walked.
    area_before, area_after = signed_area(original), signed_area(result)
    if area_after * winding <= 0.0 or abs(area_after) >= abs(area_before):
        return original
    return result


class PatrolPath:
    """An open or closed polyline addressed by arc length."""

    def __init__(
        self,
        points: Sequence[Tuple[float, float]],
        closed: bool = True,
        margin: float = 0.0,
    ) -> None:
        """Measure the path.

        Args:
            points: The corner points in world coordinates.
            closed: True for a Tiled polygon (the last point joins the first),
                False for a polyline.
            margin: Pull the outline this many world pixels inwards, keeping the
                walker clear of whatever the polygon is drawn around. Closed
                paths only — an open polyline has no inside.
        """
        self.points: List[Tuple[float, float]] = [(float(x), float(y)) for x, y in points]
        # Tiled writes the closing point explicitly in some shapes and leaves it
        # implicit in others, so drop it and re-add it below either way.
        if len(self.points) > 2 and self.points[0] == self.points[-1]:
            self.points.pop()

        self.margin: float = float(margin) if closed else 0.0
        if self.margin > 0.0:
            self.points = inset_polygon(self.points, self.margin)

        if closed and len(self.points) > 2:
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
