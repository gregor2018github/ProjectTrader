"""A trough in the chicken pen on the map: its picture follows what is in it.

A Tiled point of type "Trough" on the Houses layer, like any building, whose
File_name is its empty picture (troughs/trough_empty.png, painted by
build_tools/Sprite_Manager/trough_painter.py); its other pictures lie beside
it, trough_water_<1..4>.png and trough_feed_<1..4>.png, on the same canvas, so
they swap in place. What is in it is models/chicken_troughs.py's, which Game
keeps and shows here (show()).

The chickens keep out of it (keep_out) and come to peck in front of it while
it holds something (front_spot, chicken.py). The pen's keeper fills it when it
runs dry, standing where keeper_spot says (npcs/pen_keeper.py).
"""

import os
import random
from typing import Dict, Optional, Tuple

import pygame

from .chicken_troughs import FEED, KINDS, LEVELS
from .house import House

#: Around its collision box the chickens keep clear of, px
KEEP_CLEAR_PX = 3
#: Where a chicken stands to peck at it: this far in front of its base, give or take FRONT_SPREAD_PX
FRONT_PX = 5
FRONT_SPREAD_PX = 2
#: ...and no nearer its ends than this
END_CLEAR_PX = 8
#: Where the keeper stands to fill it: this far in front of the chickens' keep-out, px
KEEPER_FRONT_PX = 8


class Trough(House):
    """A trough, with a picture for every fill of water and grain."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The others lie beside the empty one: <stem>water_1.png ... for File_name <stem>empty.png
        folder, base = os.path.split(self.file_name)
        stem = base[:-len("empty.png")] if base.endswith("empty.png") else "trough_"
        self.pictures: Dict[str, Tuple[pygame.Surface, Optional[pygame.Surface]]] = {
            "trough_empty": (self.image, self.source_image)}
        for kind in KINDS:
            for level in range(1, LEVELS + 1):
                name = f"trough_{kind}_{level}"
                picture = self._load_picture(f"{folder}/{stem}{kind}_{level}.png" if folder else f"{stem}{kind}_{level}.png")
                if picture[0] is not None:
                    self.pictures[name] = picture
        self._caches: Dict[str, dict] = {"trough_empty": self.scaled_image_cache}
        self.shown = "trough_empty"
        #: Whether it holds anything: what the chickens come to (set by show())
        self.has_contents = False
        #: What the pen's keeper fills it with when it runs dry and the other kind is held too, or neither
        #: (Tiled ``Keeper_fills``: "feed" or "water"; chicken_troughs.Troughs.keeper_kind)
        self.keeper_fills: str = FEED

    def show(self, picture: str, has_contents: bool) -> None:
        """Show the picture of what is in it (chicken_troughs.TroughState.picture())."""
        self.has_contents = has_contents
        if picture == self.shown or picture not in self.pictures:
            return
        self.shown = picture
        self.image, self.source_image = self.pictures[picture]
        self.scaled_image_cache = self._caches.setdefault(picture, {})

    def hit_box(self) -> Optional[pygame.Rect]:
        """What of its picture is drawn, in sprite pixels: where a click finds it."""
        return self.image.get_bounding_rect() if self.image else None

    @property
    def keep_out(self) -> Tuple[float, float, float, float]:
        """(left, top, right, bottom) the chickens' feet stay out of."""
        box = self.collision_rect
        return (box.left - KEEP_CLEAR_PX, box.top - KEEP_CLEAR_PX,
                box.right + KEEP_CLEAR_PX, box.bottom + KEEP_CLEAR_PX)

    def blocks(self, x: float, y: float) -> bool:
        left, top, right, bottom = self.keep_out
        return left <= x <= right and top <= y <= bottom

    def keeper_spot(self) -> Tuple[float, float]:
        """Where the keeper stands to fill it: in the middle of its front, a little farther out than the
        chickens peck, facing it."""
        box = self.collision_rect
        return box.centerx, box.bottom + KEEP_CLEAR_PX + KEEPER_FRONT_PX

    def front_spot(self, rng: random.Random) -> Tuple[float, float]:
        """Where a chicken stands to peck at it: just in front of it, facing it."""
        box = self.collision_rect
        x = rng.uniform(box.left + END_CLEAR_PX, box.right - END_CLEAR_PX)
        y = box.bottom + KEEP_CLEAR_PX + FRONT_PX + rng.uniform(-FRONT_SPREAD_PX, FRONT_SPREAD_PX)
        return x, max(y, box.bottom + KEEP_CLEAR_PX + 1)
