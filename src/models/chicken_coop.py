"""The chickens' coop: where they go in for the night and how many it holds.

A building on the Houses layer is a coop when its Tiled object has a
`Chicken_capacity` (how many chickens sleep in it) and `Ladder_foot` /
`Ladder_top` ("SX,SY", in its sprite's own pixels, scaled with its `Scale`
like the rest of it): the foot of the hen ladder on the ground and its top at
the pop hole. The Chicken_Coop in the pen holds 20.

At dusk (by the daylight, `sun_hour`, from GO_IN_SUN_HOUR, each chicken up to
BED_SPREAD_HOURS later) a chicken walks to the ladder's foot, climbs it and goes
in; at dawn (from COME_OUT_SUN_HOUR, likewise spread) it comes out and down
again. The first `capacity` chickens of the flock have a place in it; the rest
stay outside and settle down for the night near it, ROOST_TILES at most from
its ladder (chicken.py). No pygame.
"""

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple

#: When the chickens go in, the sun hour of a Spring or Autumn day (night falls at 21)
GO_IN_SUN_HOUR = 19.0
#: When they come out (full daylight from 8)
COME_OUT_SUN_HOUR = 5.5
#: Each chicken goes in and comes out up to this much later than the hour
BED_SPREAD_HOURS = 1.0
#: The chickens that find no room in the coop sleep this near its ladder
ROOST_TILES = 2.5
#: Around the coop's collision box the chickens keep clear of by day, px
KEEP_CLEAR_PX = 6

Point = Tuple[float, float]


def _sprite_point(text: Any) -> Optional[Point]:
    try:
        x, y = (float(v) for v in str(text).split(","))
    except ValueError:
        return None
    return x, y


def is_bedtime(sun: float, bed_offset: float = 0.0, wake_offset: float = 0.0) -> bool:
    """Whether a chicken whose own hours are put off by these offsets is meant to be in for the night."""
    return sun >= GO_IN_SUN_HOUR + bed_offset or sun < COME_OUT_SUN_HOUR + wake_offset


@dataclass(frozen=True)
class Coop:
    name: str
    capacity: int
    foot: Point                                   # the ladder's foot, world px
    hole: Point                                   # its top, at the pop hole
    base_y: float                                 # the building's base line, which it is drawn in order by
    keep_out: Tuple[float, float, float, float]   # (left, top, right, bottom) the chickens stay out of by day

    @classmethod
    def from_house(cls, house: Any, properties: Mapping[str, Any]) -> Optional["Coop"]:
        """The coop a building is, by its Tiled properties, or None if it is none.

        Args:
            house: The House, placed and scaled (its x, y, image, scale, collision_rect).
            properties: Its Tiled object's properties.
        """
        try:
            capacity = int(properties.get("Chicken_capacity", 0))
        except (TypeError, ValueError):
            return None
        foot = _sprite_point(properties.get("Ladder_foot", ""))
        top = _sprite_point(properties.get("Ladder_top", ""))
        if capacity <= 0 or foot is None or top is None or house.image is None:
            return None
        height = house.image.get_height()

        def world(point: Point) -> Point:
            return house.x + point[0] * house.scale, house.y - height + point[1] * house.scale

        box = house.collision_rect
        return cls(house.name, capacity, world(foot), world(top), float(house.y),
                   (box.left - KEEP_CLEAR_PX, box.top - KEEP_CLEAR_PX, box.right + KEEP_CLEAR_PX,
                    box.bottom + KEEP_CLEAR_PX))

    def blocks(self, x: float, y: float) -> bool:
        """Whether a chicken's feet at (x, y) would stand in the coop."""
        left, top, right, bottom = self.keep_out
        return left <= x <= right and top <= y <= bottom
