"""Tile-grid pathfinding for NPCs who walk the town on their own.

Traders walk polylines drawn for them in Tiled, which is enough when the route
never changes. Townsfolk stroll from any front door to any other, so their
route has to be worked out at the moment they set off. This module rasterizes
the map's collision once at load time and answers "how do I get from here to
there" with a list of world points, each reachable from the one before in a
straight line.

The grid is one cell per tile. A cell counts as walkable when a figurine
standing in it would not touch a house, a tree or the water -- the same
blockers :meth:`TMXMap.check_object_collision` tests, minus the sheep, who
wander and would only make the grid lie.

It blocks one thing collision does not: the cells a walker would be *invisible*
in. A house is drawn from its own base upwards and sorts on that base, so the
band of ground behind a tall building is walkable but hidden. The player never
minds, being steered by someone who can see where they are going, but a
townsperson routed through it simply disappears into the wall and comes out the
other side. Those cells are blocked too, so a route goes round what you can
see, not merely round what you can bump into.
"""

import heapq
import math
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

import pygame

if TYPE_CHECKING:
    from .map import TMXMap

#: Cost of a diagonal step relative to a straight one.
DIAGONAL_COST = math.sqrt(2.0)

#: The eight neighbours of a cell, as (dx, dy, cost).
NEIGHBOURS: Tuple[Tuple[int, int, float], ...] = (
    (1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
    (1, 1, DIAGONAL_COST), (1, -1, DIAGONAL_COST),
    (-1, 1, DIAGONAL_COST), (-1, -1, DIAGONAL_COST),
)

#: How far apart, in world pixels, the line-of-sight test samples a straight
#: line. A quarter of a tile, so that no corner can hide between two samples.
LINE_SAMPLE_STEP = 8.0

#: How much room the line-of-sight test leaves around the walker, in world
#: pixels. A walker is a figure, not a point: a line that only just misses the
#: corner of a house is one the walker's shoulder would still scrape along, so
#: the test asks whether a box this big fits, rather than a single point.
LINE_CLEARANCE = 8.0

#: Cells settled before A* gives up. The town is a few thousand cells across,
#: so a search that runs past this is looking for somewhere unreachable and is
#: better stopped than left to sweep the whole map.
MAX_SEARCH_CELLS = 20000

#: How far out from a blocked cell to look for a walkable one, in cells.
NEAREST_FREE_RADIUS = 6

#: How much of a walker's sprite has to be hidden behind a building before the
#: ground they stand on counts as no place to walk. Well short of all of it:
#: passing behind the corner of a house is ordinary, vanishing is not.
OCCLUSION_COVER = 0.7

#: Figure size assumed when no walker is on hand to measure, as multiples of a
#: tile: one tile wide and a good head taller.
DEFAULT_FIGURE_SIZE = (1.0, 1.7)


class NavGrid:
    """A walkability grid over the map, with A* routing on top of it."""

    def __init__(
        self, tmx_map: 'TMXMap', figure_size: Optional[Tuple[int, int]] = None
    ) -> None:
        """Rasterize the map's static collision into a grid of tiles.

        Args:
            tmx_map: The loaded map. Its houses, trees and waters must already
                be parsed.
            figure_size: Width and height of the sprite of whoever walks this
                grid, in world pixels, for working out where they would be
                hidden. Defaults to :data:`DEFAULT_FIGURE_SIZE`.
        """
        self.tile_size: int = tmx_map.tile_size
        self.width: int = tmx_map.width
        self.height: int = tmx_map.height
        self.blocked: bytearray = bytearray(self.width * self.height)
        self.figure_size: Tuple[int, int] = figure_size or (
            int(DEFAULT_FIGURE_SIZE[0] * self.tile_size),
            int(DEFAULT_FIGURE_SIZE[1] * self.tile_size),
        )
        self._rasterize(tmx_map)

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def _rasterize(self, tmx_map: 'TMXMap') -> None:
        """Mark every cell a figurine could not stand in.

        Houses and trees are axis-aligned rectangles, so they are stamped
        straight into the grid. Water is a polygon and is sampled cell by cell,
        but only inside its own bounding box.

        Args:
            tmx_map: The loaded map.
        """
        for house in tmx_map.houses:
            self._block_rect(house.collision_rect)
        for tree in tmx_map.trees:
            self._block_rect(tree.collision_rect)

        for water in tmx_map.waters:
            self._block_polygon(water.points)
        # The hand-placed shoreline tiles are only partly water, so their cell
        # centres can fall outside the polygon while the tile is still drawn as
        # water. Blocking those too keeps walkers off the bank.
        for cell_x, cell_y in tmx_map.water_tiles:
            if 0 <= cell_x < self.width and 0 <= cell_y < self.height:
                self.blocked[cell_y * self.width + cell_x] = 1

        # Last, because it only ever looks at cells the collision left free
        self._block_occluders(list(tmx_map.houses) + list(tmx_map.trees))

    def _block_occluders(self, occluders: Sequence[Any]) -> None:
        """Block the cells a walker would stand all but hidden in.

        Args:
            occluders: Everything drawn from a ground baseline and sorted on
                it -- houses and trees. Each needs ``x``, ``y`` (the bottom
                left of its sprite), ``y_sort`` and ``image``.
        """
        figure_width, figure_height = self.figure_size
        half_width = figure_width / 2.0
        # A solid stand-in for the walker, to count how much of them is covered
        figure_mask = pygame.mask.Mask((figure_width, figure_height), fill=True)

        for occluder in occluders:
            image = getattr(occluder, "image", None)
            if image is None:
                continue
            art_width, art_height = image.get_width(), image.get_height()
            art_left, art_top = float(occluder.x), float(occluder.y) - art_height
            art_box = pygame.Rect(int(art_left), int(art_top), art_width, art_height)
            mask = pygame.mask.from_surface(image)

            # Every cell whose figure could meet this sprite at all
            first_x, first_y = self._clamped_cell(art_left - figure_width,
                                                  art_top - figure_height)
            last_x, last_y = self._clamped_cell(art_left + art_width + figure_width,
                                                occluder.y)
            for cell_y in range(first_y, last_y + 1):
                feet_y = cell_y * self.tile_size + self.tile_size / 2.0
                # Standing level with the baseline or below it puts the walker
                # in front of the sprite, where nothing can hide them.
                if occluder.y_sort <= feet_y:
                    continue
                row = cell_y * self.width
                for cell_x in range(first_x, last_x + 1):
                    if self.blocked[row + cell_x]:
                        continue
                    feet_x = cell_x * self.tile_size + self.tile_size / 2.0
                    figure = pygame.Rect(int(feet_x - half_width),
                                         int(feet_y - figure_height),
                                         figure_width, figure_height)
                    if not figure.colliderect(art_box):
                        continue
                    # Painted pixels of the sprite falling inside the figure's
                    # own box. Counting pixels rather than taking the overlap
                    # whole is what tells a wall from a fence: a fence covers
                    # the same ground and hides nobody.
                    hidden = mask.overlap_area(
                        figure_mask, (figure.x - art_box.x, figure.y - art_box.y)
                    )
                    if hidden >= OCCLUSION_COVER * figure_width * figure_height:
                        self.blocked[row + cell_x] = 1

    def _block_polygon(self, points: Sequence[Tuple[float, float]]) -> None:
        """Mark every cell whose centre falls inside a polygon.

        Testing each cell of the bounding box in turn is far too slow for the
        water, whose box is the whole map. This walks the polygon row by row
        instead, working out where its edges cross the middle of the row and
        filling the spans between them -- the same inside/outside rule as
        :meth:`Water.contains_point`, at a fraction of the cost.

        Args:
            points: The polygon's corner points, in world pixels.
        """
        if len(points) < 3:
            return
        half = self.tile_size / 2.0
        edges = list(zip(points, points[1:] + [points[0]]))
        first_row = max(0, int(min(y for _, y in points)) // self.tile_size)
        last_row = min(self.height - 1, int(max(y for _, y in points)) // self.tile_size)

        for cell_y in range(first_row, last_row + 1):
            centre_y = cell_y * self.tile_size + half
            crossings = []
            for (x1, y1), (x2, y2) in edges:
                if (y1 > centre_y) != (y2 > centre_y):
                    crossings.append(x1 + (centre_y - y1) * (x2 - x1) / (y2 - y1))
            crossings.sort()
            row = cell_y * self.width
            for left, right in zip(crossings[0::2], crossings[1::2]):
                # Cells whose centre lies between the two crossings
                first_x = max(0, math.ceil((left - half) / self.tile_size))
                last_x = min(self.width - 1, math.floor((right - half) / self.tile_size))
                for cell_x in range(first_x, last_x + 1):
                    self.blocked[row + cell_x] = 1

    def _block_rect(self, rect: pygame.Rect) -> None:
        """Mark every cell the given world rectangle touches.

        Args:
            rect: A blocker's collision rectangle in world pixels.
        """
        first_x, first_y = self._clamped_cell(rect.left, rect.top)
        # A rectangle ending exactly on a tile boundary does not reach into the
        # next tile, so step back off the edge before converting.
        last_x, last_y = self._clamped_cell(rect.right - 1, rect.bottom - 1)
        for cell_y in range(first_y, last_y + 1):
            row = cell_y * self.width
            for cell_x in range(first_x, last_x + 1):
                self.blocked[row + cell_x] = 1

    def _clamped_cell(self, world_x: float, world_y: float) -> Tuple[int, int]:
        """The grid cell holding a world point, pulled inside the map.

        Args:
            world_x: World X in pixels.
            world_y: World Y in pixels.

        Returns:
            Tuple: Cell coordinates, guaranteed to be on the grid.
        """
        cell_x = max(0, min(self.width - 1, int(world_x) // self.tile_size))
        cell_y = max(0, min(self.height - 1, int(world_y) // self.tile_size))
        return cell_x, cell_y

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def cell_of(self, world_x: float, world_y: float) -> Tuple[int, int]:
        """The grid cell holding a world point.

        Args:
            world_x: World X in pixels.
            world_y: World Y in pixels.
        """
        return int(world_x) // self.tile_size, int(world_y) // self.tile_size

    def cell_centre(self, cell_x: int, cell_y: int) -> Tuple[float, float]:
        """The world position at the middle of a cell.

        Args:
            cell_x: Cell X.
            cell_y: Cell Y.
        """
        half = self.tile_size / 2.0
        return cell_x * self.tile_size + half, cell_y * self.tile_size + half

    def is_free(self, cell_x: int, cell_y: int) -> bool:
        """Whether a figurine could stand in the given cell.

        Args:
            cell_x: Cell X.
            cell_y: Cell Y.
        """
        if not (0 <= cell_x < self.width and 0 <= cell_y < self.height):
            return False
        return not self.blocked[cell_y * self.width + cell_x]

    def is_free_at(self, world_x: float, world_y: float) -> bool:
        """Whether a figurine could stand at the given world position.

        Args:
            world_x: World X in pixels.
            world_y: World Y in pixels.
        """
        return self.is_free(*self.cell_of(world_x, world_y))

    def nearest_free(
        self, world_x: float, world_y: float, radius: int = NEAREST_FREE_RADIUS
    ) -> Optional[Tuple[int, int]]:
        """The walkable cell closest to a world point.

        Used to rescue a position that sits inside a blocker -- a door point,
        for instance, is drawn on the wall itself.

        Args:
            world_x: World X in pixels.
            world_y: World Y in pixels.
            radius: How many cells out to look.

        Returns:
            Tuple: Cell coordinates, or None if everything nearby is blocked.
        """
        start_x, start_y = self.cell_of(world_x, world_y)
        if self.is_free(start_x, start_y):
            return start_x, start_y
        for ring in range(1, radius + 1):
            best: Optional[Tuple[float, Tuple[int, int]]] = None
            for offset_y in range(-ring, ring + 1):
                for offset_x in range(-ring, ring + 1):
                    # Only the outermost ring is new; the rest was tried already
                    if max(abs(offset_x), abs(offset_y)) != ring:
                        continue
                    cell = (start_x + offset_x, start_y + offset_y)
                    if not self.is_free(*cell):
                        continue
                    gap = math.dist(self.cell_centre(*cell), (world_x, world_y))
                    if best is None or gap < best[0]:
                        best = (gap, cell)
            if best is not None:
                return best[1]
        return None

    def _has_clearance(self, world_x: float, world_y: float) -> bool:
        """Whether a walker standing here would keep clear of every blocker.

        Args:
            world_x: World X in pixels.
            world_y: World Y in pixels.
        """
        for offset_x in (-LINE_CLEARANCE, LINE_CLEARANCE):
            for offset_y in (-LINE_CLEARANCE, LINE_CLEARANCE):
                if not self.is_free_at(world_x + offset_x, world_y + offset_y):
                    return False
        return True

    def has_line_of_sight(
        self, start: Tuple[float, float], end: Tuple[float, float]
    ) -> bool:
        """Whether a walker can go straight from one world point to another.

        Stricter than the grid A* searches: it asks for room around the line,
        not just a free cell under it. That only ever keeps a corner in a route
        that :meth:`_smooth` would otherwise have cut off, never makes a route
        impossible, because the cell path it smooths is walkable by
        construction.

        Args:
            start: World (x, y) to set off from.
            end: World (x, y) to arrive at.
        """
        span = math.dist(start, end)
        if span <= 0.0:
            return self._has_clearance(*start)
        steps = int(span / LINE_SAMPLE_STEP) + 1
        for step in range(steps + 1):
            t = step / steps
            if not self._has_clearance(
                start[0] + (end[0] - start[0]) * t,
                start[1] + (end[1] - start[1]) * t,
            ):
                return False
        return True

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def find_route(
        self, start: Tuple[float, float], goal: Tuple[float, float]
    ) -> Optional[List[Tuple[float, float]]]:
        """Work out a walkable route between two world points.

        The cell path A* returns runs along tile centres and turns in steps of
        45 degrees, which reads as a walker following the paving rather than
        crossing a square. :meth:`_smooth` pulls it straight again.

        Args:
            start: World (x, y) to set off from.
            goal: World (x, y) to arrive at.

        Returns:
            List: World points, beginning at ``start`` and ending at ``goal``,
            each reachable from the one before in a straight line. None if
            there is no way through.
        """
        start_cell = self.nearest_free(*start)
        goal_cell = self.nearest_free(*goal)
        if start_cell is None or goal_cell is None:
            return None
        if start_cell == goal_cell:
            return [start, goal]

        cells = self._search(start_cell, goal_cell)
        if cells is None:
            return None
        points = [start] + [self.cell_centre(*cell) for cell in cells] + [goal]
        return self._smooth(points)

    def _search(
        self, start: Tuple[int, int], goal: Tuple[int, int]
    ) -> Optional[List[Tuple[int, int]]]:
        """A* over the grid.

        Args:
            start: Cell to set off from; must be walkable.
            goal: Cell to arrive at; must be walkable.

        Returns:
            List: The cells walked through, or None if the goal is cut off.
        """
        def heuristic(cell: Tuple[int, int]) -> float:
            # Octile distance: the exact cost of an unobstructed eight-way walk
            gap_x, gap_y = abs(cell[0] - goal[0]), abs(cell[1] - goal[1])
            return (gap_x + gap_y) + (DIAGONAL_COST - 2.0) * min(gap_x, gap_y)

        came_from: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {start: None}
        best_cost: Dict[Tuple[int, int], float] = {start: 0.0}
        # The counter breaks ties, so the heap never compares two cells directly
        counter = 0
        queue: List[Tuple[float, int, Tuple[int, int]]] = [(heuristic(start), 0, start)]

        while queue:
            _, _, cell = heapq.heappop(queue)
            if cell == goal:
                route: List[Tuple[int, int]] = []
                step: Optional[Tuple[int, int]] = cell
                while step is not None:
                    route.append(step)
                    step = came_from[step]
                route.reverse()
                return route
            if len(best_cost) > MAX_SEARCH_CELLS:
                return None

            cost = best_cost[cell]
            for step_x, step_y, step_cost in NEIGHBOURS:
                neighbour = (cell[0] + step_x, cell[1] + step_y)
                if not self.is_free(*neighbour):
                    continue
                # Cutting a corner diagonally would clip whatever sits on it
                if step_x and step_y and not (
                    self.is_free(cell[0] + step_x, cell[1])
                    and self.is_free(cell[0], cell[1] + step_y)
                ):
                    continue
                new_cost = cost + step_cost
                if new_cost < best_cost.get(neighbour, math.inf):
                    best_cost[neighbour] = new_cost
                    came_from[neighbour] = cell
                    counter += 1
                    heapq.heappush(
                        queue, (new_cost + heuristic(neighbour), counter, neighbour)
                    )
        return None

    def _smooth(self, points: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Drop every point that can be walked past in a straight line.

        Args:
            points: The route as it came out of the search.

        Returns:
            List: The same route with its needless corners removed.
        """
        route = [points[0]]
        index = 0
        while index < len(points) - 1:
            # Reach as far ahead as the walker can see, then go straight there
            furthest = index + 1
            for candidate in range(len(points) - 1, index, -1):
                if self.has_line_of_sight(points[index], points[candidate]):
                    furthest = candidate
                    break
            route.append(points[furthest])
            index = furthest
        return route
