"""A gate in a wall that the player opens and shuts with a click, as the churchyard's two iron gates.

A Tiled point of type "Gate" on the Houses layer, like any building: its
File_name is the shut gate's picture and Open_file_name the open one's, both on
the same canvas, and Opens says which way its leaves swing, "down" the
picture (towards the viewer) or "up" it. Its collision box is the gateway;
it blocks only while the gate is shut.

The gate is drawn y-sorted where the wall it stands in is (Sort_up_pixel above
its point, the walls' own base line), and open towards the viewer a little
lower, as its leaves then reach out in front of the wall.

Nothing of it is saved: the gates are shut when a game starts or is loaded.
The townsfolk's ways (NavGrid) are worked out once with the gates shut, so
they never walk through one.
"""

import random
from collections.abc import Iterable

import pygame

from .house import House

#: Its sounds: any in assets/sound/ whose name starts with these (gate_open.ogg, gate_open_1.ogg, ...),
#: a take picked at random; none there yet, so it opens and shuts silently
OPEN_SOUND = "gate_open"
CLOSE_SOUND = "gate_close"
GATE_VOLUME = 0.55
#: How much lower an open gate whose leaves swing towards the viewer is sorted, in px
OPEN_DOWN_SORT = 12


class Gate(House):
    """A gate: shut or open, its picture, collision and drawing order following."""

    def __init__(self, *args, open_file_name: str = "", opens: str = "down",
                 sort_up_pixel: float = 0.0, **kwargs):
        """Args as House's, and:

        Args:
            open_file_name: The open gate's picture, in houses/ like File_name.
            opens: "down" if its leaves swing down the picture (towards the viewer), else "up".
            sort_up_pixel: How far above its point it is drawn in order, as the wall it stands in.
        """
        super().__init__(*args, **kwargs)
        self.opens = "up" if str(opens).strip().lower() == "up" else "down"
        self.sort_up_pixel = float(sort_up_pixel)
        self.is_open = False
        self.closed_image = self.image
        self._closed_source = self.source_image
        self._closed_cache = self.scaled_image_cache
        self._open_cache: dict = {}
        self.open_image: pygame.Surface | None = None
        self._open_source: pygame.Surface | None = None
        if open_file_name:
            # At its Scale like the shut one, each with its own full-resolution source
            self.open_image, self._open_source = self._load_picture(open_file_name)
        self._blocking = list(self.collision_rects)

    @property
    def y_sort(self) -> float:
        lower = OPEN_DOWN_SORT if self.is_open and self.opens == "down" else 0
        return self.y - self.sort_up_pixel + lower

    def hit_box(self) -> pygame.Rect | None:
        """What of its picture is drawn, in sprite pixels: where a click finds it."""
        return self.image.get_bounding_rect() if self.image else None

    def can_close(self, bodies: Iterable[pygame.Rect]) -> bool:
        """Whether it can swing shut: nobody's feet (`bodies`, world rects) in the gateway."""
        return not any(body.collidelist(self._blocking) >= 0 for body in bodies)

    def set_open(self, is_open: bool) -> None:
        self.is_open = bool(is_open)
        if self.is_open and self.open_image is not None:
            self.image, self.source_image = self.open_image, self._open_source
            self.scaled_image_cache = self._open_cache
        else:
            self.image, self.source_image = self.closed_image, self._closed_source
            self.scaled_image_cache = self._closed_cache
        if self.is_open:
            self.collision_rects = []
        else:
            self.collision_rects = list(self._blocking)

    def toggle(self, bodies: Iterable[pygame.Rect] = ()) -> bool:
        """Open it, or shut it if nobody stands in the way.

        Args:
            bodies: The feet boxes (world rects) of those who could be in the gateway.

        Returns:
            True if it moved.
        """
        if self.is_open and not self.can_close(bodies):
            return False
        self.set_open(not self.is_open)
        return True

    def sound(self, available: Iterable[str], rng: random.Random | None = None) -> str | None:
        """The sound of it having just opened or shut, of the sounds `available`; None if there is none."""
        family = OPEN_SOUND if self.is_open else CLOSE_SOUND
        takes = sorted(name for name in available if name == family or name.startswith(family + "_"))
        return (rng or random).choice(takes) if takes else None


def feet_box(figure, tile_size: int) -> pygame.Rect:
    """The feet box (world rect) a figure stands on, as TMXMap.is_standable() tests it: who is in a gateway."""
    half = tile_size / 2
    feet_height = tile_size / 2 - 2
    x, y = figure.feet
    return pygame.Rect(round(x - half), round(y - feet_height), round(2 * half), round(feet_height))
