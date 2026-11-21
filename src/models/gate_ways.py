"""The harvest's workers' ways across the map, a little at a time.

The townsfolk's NavGrid takes no notice of gates, so a route into a fenced
field runs through its gate like anywhere else; the worker opens and shuts it
on his way as every NPC does (gate_passing.py). A way is a list of legs to
walk, one leg so far: the route from the NavGrid.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Generator, List, Optional, Tuple

if TYPE_CHECKING:
    from .navigation import NavGrid

Point = Tuple[float, float]


@dataclass
class Walk:
    """A leg walked: world points, the first where the walker is."""
    points: List[Point]


Leg = Walk


class GateWays:
    """Ways for the harvest's workers, through any gates on them."""

    def __init__(self, nav: 'NavGrid') -> None:
        self.nav = nav

    def plan_steps(self, start: Point, goal: Point) -> Generator[None, None, Optional[List[Leg]]]:
        """The legs from one point to another, a little at a time (NavGrid.route_steps); None if there is
        no way."""
        route = yield from self.nav.route_steps(start, goal)
        if route is None:
            return None
        return [Walk(list(route))]

    def plan(self, start: Point, goal: Point) -> Optional[List[Leg]]:
        """plan_steps in one go."""
        steps = self.plan_steps(start, goal)
        while True:
            try:
                next(steps)
            except StopIteration as done:
                return done.value
