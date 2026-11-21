"""A shock (stook) of sheaves on a field, standing only from the harvest until it is cleared.

A Tiled point of type "Shock" on the Houses layer, like any decoration (its
File_name, Scale and collision box). It belongs to the field it stands on, or
the nearest one, and shows only while the harvest has reached it (harvest.py,
shock_thresholds; the shocks stand a few days after the harvest's end and are
then gone). While hidden it has no picture and no collision, so nothing draws
it, clicks it or bumps into it, and the townsfolk's NavGrid, built while all
are hidden, never routes round it.
"""

from typing import Optional, Tuple

from .house import House


class Shock(House):
    """A shock of sheaves, shown or not."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.picture = self.image
        self._standing_rects = list(self.collision_rects)
        #: The Tiled id of the field it belongs to, and how many of its plants must be cut first
        self.field_id: Optional[int] = None
        self.threshold: int = 1
        self.shown = True
        self.set_shown(False)

    def picture_box(self) -> Tuple[float, float, float, float]:
        """(left, top, right, bottom) of its picture in world px, shown or not."""
        height = self.picture.get_height() if self.picture is not None else 0
        width = self.picture.get_width() if self.picture is not None else 0
        return float(self.x), float(self.y - height), float(self.x + width), float(self.y)

    def set_collision_gap(self, left_pixel: float, width_pixel: float) -> None:
        """As a house's (the map calls it for every one); kept for while it stands."""
        super().set_collision_gap(left_pixel, width_pixel)
        self._standing_rects = list(self.collision_rects)
        if not self.shown:
            self.collision_rects = []

    def set_shown(self, shown: bool) -> None:
        shown = bool(shown)
        if shown == self.shown:
            return
        self.shown = shown
        self.image = self.picture if shown else None
        self.collision_rects = list(self._standing_rects) if shown else []
