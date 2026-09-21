"""A front door townsfolk step out of and disappear into.

Doors are drawn on the Tiled "Doors" object layer as plain points, one per
doorway, sitting on the wall itself. The object's *name* says which way a
person faces walking out of it -- ``down``, ``up``, ``left`` or ``right`` -- and
the object's *id*, which Tiled hands out and never reuses, identifies the door
for as long as it is not deleted and redrawn. That id is what a townsperson
remembers between outings, so they come back out of the door they went into.

A door has two positions. The *threshold* is the point itself: where a figure
is fully faded out, standing in the doorway. The *step* is the first walkable
spot outside it, a tile or two out in the door's own direction -- far enough
that the walker clears the wall, and the place every route to or from this
house begins and ends.
"""

from typing import TYPE_CHECKING, Dict, Optional, Tuple

if TYPE_CHECKING:
    from .navigation import NavGrid

#: Which way a walker moves leaving a door, per Tiled object name.
DOOR_DIRECTIONS: Dict[str, Tuple[int, int]] = {
    "down": (0, 1),
    "up": (0, -1),
    "left": (-1, 0),
    "right": (1, 0),
}

#: Direction assumed for a door whose Tiled name says nothing useful.
DEFAULT_DIRECTION = "down"

#: How many tiles out from the threshold to look for the step, at most. Most
#: doors are clear after one tile; the church and the bank have a porch in the
#: way and need two.
MAX_STEP_TILES = 4


class Door:
    """One doorway on the map, with the spot outside it a walker uses."""

    def __init__(
        self,
        door_id: int,
        direction: str,
        x: float,
        y: float,
        tile_size: int,
        nav: 'NavGrid',
    ) -> None:
        """Place a door and find the walkable spot in front of it.

        Args:
            door_id: The Tiled object id, used to remember this door.
            direction: Which way a person faces walking out, see
                :data:`DOOR_DIRECTIONS`.
            x: World X of the Tiled point.
            y: World Y of the Tiled point.
            tile_size: Base tile size, the unit the step is measured in.
            nav: The walkability grid, to find a step that is actually free.
        """
        self.id: int = int(door_id)
        self.direction: str = direction if direction in DOOR_DIRECTIONS else DEFAULT_DIRECTION
        self.threshold: Tuple[float, float] = (float(x), float(y))
        self.step: Optional[Tuple[float, float]] = self._find_step(tile_size, nav)

    def __repr__(self) -> str:
        return f"<Door {self.id} {self.direction} at {self.threshold}>"

    @property
    def is_usable(self) -> bool:
        """Whether anyone can actually get in and out of this door.

        A door drawn somewhere hemmed in on every side has no step, and is
        skipped rather than left for a walker to get stuck in.
        """
        return self.step is not None

    def _find_step(self, tile_size: int, nav: 'NavGrid') -> Optional[Tuple[float, float]]:
        """The first free spot outside the door, going straight out from it.

        Args:
            tile_size: Base tile size.
            nav: The walkability grid.

        Returns:
            Tuple: World (x, y) to step out onto, or None if the way is blocked
            for :data:`MAX_STEP_TILES` tiles.
        """
        step_x, step_y = DOOR_DIRECTIONS[self.direction]
        for tiles in range(1, MAX_STEP_TILES + 1):
            spot = (
                self.threshold[0] + step_x * tile_size * tiles,
                self.threshold[1] + step_y * tile_size * tiles,
            )
            if nav.is_free_at(*spot):
                return spot
        return None
