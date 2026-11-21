"""Ways across the map that go through gates, for those who open and shut them on their way.

The townsfolk's NavGrid is built with every gate shut, so a fenced field is a
pocket no route leads into. GateWays finds those pockets once: it labels the
grid's free cells by the area they join up into (areas), and for every gate
the spot just outside it on each side; a gate whose sides lie in two areas is
a Crossing between them. A walker who opens gates (a harvest worker) asks for
a way (plan_steps): within one area that is the ordinary route; otherwise the
areas are searched for a chain of crossings, and the way is legs of walking
(routes from the NavGrid) with a gate to go through between each two, which
the walker opens, passes and shuts behind him (harvest_crew.py).

Any gate on the map works so, with nothing to set in Tiled.
"""

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Generator, List, Optional, Sequence, Tuple, Union

if TYPE_CHECKING:
    from .navigation import NavGrid

Point = Tuple[float, float]

#: How far out from a gate's collision box its side spots are looked for, in tiles: the first free cell
SIDE_REACH_TILES = (0.75, 1.25, 1.75, 2.25)


@dataclass(frozen=True)
class Crossing:
    """A gate between two areas: the spot before it on each side."""
    gate: Any
    side_a: Point
    area_a: int
    side_b: Point
    area_b: int

    def towards(self, area: int) -> Tuple[Point, Point]:
        """(the spot to come from, the spot to come out at) going through it into `area`."""
        return (self.side_a, self.side_b) if area == self.area_b else (self.side_b, self.side_a)

    def other(self, area: int) -> int:
        return self.area_b if area == self.area_a else self.area_a


@dataclass
class Walk:
    """A leg walked: world points, the first where the walker is."""
    points: List[Point]


@dataclass
class Through:
    """A gate gone through: from the spot before it to the spot past it."""
    gate: Any
    before: Point
    after: Point


Leg = Union[Walk, Through]


class GateWays:
    """The map's areas, the gates between them and ways through them."""

    def __init__(self, nav: 'NavGrid', gates: Sequence[Any]) -> None:
        """
        Args:
            nav: The townsfolk's grid, built with the gates shut.
            gates: The map's gates (gate.Gate), each with its shut collision boxes in `_blocking`.
        """
        self.nav = nav
        self.areas: List[int] = self._label()
        self.crossings: List[Crossing] = []
        for gate in gates:
            crossing = self._crossing(gate)
            if crossing is not None:
                self.crossings.append(crossing)

    # ------------------------------------------------------------------
    # Areas
    # ------------------------------------------------------------------

    def _label(self) -> List[int]:
        """Each cell's area: free cells joined side by side share a number (from 1), blocked ones 0.

        Joined only along sides, as the grid's routes are: a diagonal step needs both cells beside it free.
        """
        width, height, blocked = self.nav.width, self.nav.height, self.nav.blocked
        areas = [0] * (width * height)
        label = 0
        for start in range(width * height):
            if blocked[start] or areas[start]:
                continue
            label += 1
            areas[start] = label
            queue = deque([start])
            while queue:
                cell = queue.popleft()
                x = cell % width
                for neighbour, ok in ((cell - 1, x > 0), (cell + 1, x < width - 1),
                                      (cell - width, cell >= width), (cell + width, cell < width * (height - 1))):
                    if ok and not blocked[neighbour] and not areas[neighbour]:
                        areas[neighbour] = label
                        queue.append(neighbour)
        return areas

    def area_at(self, point: Point) -> int:
        """The area a point is in (the nearest free cell's, if it is on a blocked one); 0 if none is near."""
        cell = self.nav.nearest_free(*point)
        if cell is None:
            return 0
        return self.areas[cell[1] * self.nav.width + cell[0]]

    def _free_area(self, point: Point) -> int:
        """The area of the cell right under a point, 0 if it is blocked or off the map."""
        x, y = self.nav.cell_of(*point)
        if not self.nav.is_free(x, y):
            return 0
        return self.areas[y * self.nav.width + x]

    def _crossing(self, gate: Any) -> Optional[Crossing]:
        """The two sides of a gate if they are in different areas, the spots straight out from its middle."""
        rects = list(getattr(gate, "_blocking", ()) or getattr(gate, "collision_rects", ()))
        if not rects:
            return None
        left = min(r.left for r in rects)
        right = max(r.right for r in rects)
        top = min(r.top for r in rects)
        bottom = max(r.bottom for r in rects)
        cx, cy = (left + right) / 2, (top + bottom) / 2
        tile = self.nav.tile_size
        sides = {"up": (0, -1, (bottom - top) / 2), "down": (0, 1, (bottom - top) / 2),
                 "left": (-1, 0, (right - left) / 2), "right": (1, 0, (right - left) / 2)}
        found: Dict[str, Tuple[Point, int]] = {}
        for name, (dx, dy, half) in sides.items():
            for reach in SIDE_REACH_TILES:
                spot = (cx + dx * (half + reach * tile), cy + dy * (half + reach * tile))
                area = self._free_area(spot)
                if area:
                    found[name] = (spot, area)
                    break
        for one, two in (("up", "down"), ("left", "right")):
            if one in found and two in found and found[one][1] != found[two][1]:
                (spot_a, area_a), (spot_b, area_b) = found[one], found[two]
                return Crossing(gate, spot_a, area_a, spot_b, area_b)
        return None

    # ------------------------------------------------------------------
    # Ways
    # ------------------------------------------------------------------

    def _chain(self, start: int, goal: int) -> Optional[List[Tuple[Crossing, int]]]:
        """The crossings from one area to another, each with the area it leads into; None if none join them."""
        came: Dict[int, Optional[Tuple[Crossing, int]]] = {start: None}
        queue = deque([start])
        while queue:
            area = queue.popleft()
            if area == goal:
                chain = []
                while came[area] is not None:
                    crossing, before = came[area]
                    chain.append((crossing, area))
                    area = before
                return chain[::-1]
            for crossing in self.crossings:
                if area in (crossing.area_a, crossing.area_b):
                    nxt = crossing.other(area)
                    if nxt not in came:
                        came[nxt] = (crossing, area)
                        queue.append(nxt)
        return None

    def plan_steps(self, start: Point, goal: Point) -> Generator[None, None, Optional[List[Leg]]]:
        """The legs from one point to another, through any gates on the way, a little at a time
        (the routes are searched with NavGrid.route_steps); None if there is no way.
        """
        start_area, goal_area = self.area_at(start), self.area_at(goal)
        if not start_area or not goal_area:
            return None
        chain = self._chain(start_area, goal_area)
        if chain is None:
            return None
        legs: List[Leg] = []
        here = start
        for crossing, into in chain:
            before, after = crossing.towards(into)
            route = yield from self.nav.route_steps(here, before)
            if route is None:
                return None
            legs.append(Walk(list(route)))
            legs.append(Through(crossing.gate, before, after))
            here = after
        route = yield from self.nav.route_steps(here, goal)
        if route is None:
            return None
        legs.append(Walk(list(route)))
        return legs

    def plan(self, start: Point, goal: Point) -> Optional[List[Leg]]:
        """plan_steps in one go."""
        steps = self.plan_steps(start, goal)
        while True:
            try:
                next(steps)
            except StopIteration as done:
                return done.value
