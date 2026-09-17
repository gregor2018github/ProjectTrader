"""Abstract base class for animal figurines (sheep, and whatever follows).

Animals differ from humans in that their artwork is wider than a tile, they
usually only face left and right, and their collision box is a small strip at
the feet rather than the full sprite footprint.
"""

import os
from abc import abstractmethod
from typing import Any, Dict

import pygame

from ..figurine import Figurine, FIGURINE_SPRITE_ROOT

# Artwork root shared by every animal figurine.
ANIMAL_SPRITE_ROOT = os.path.join(FIGURINE_SPRITE_ROOT, 'animals')


class Animal(Figurine):
    """A non-human figurine that roams the map on its own."""

    def __init__(self, x: float, y: float, tile_size: int) -> None:
        """Initialize shared animal state.

        Args:
            x: World X of the sprite's top-left corner.
            y: World Y of the sprite's top-left corner.
            tile_size: Base tile size, used for scaling sprites and speeds.
        """
        super().__init__(x, y, tile_size)

        # Collision strip at the feet; subclasses size it for their artwork.
        self.collision_width: int = tile_size
        self.collision_height: int = tile_size // 2

        self.direction: str = "right"
        self.is_moving: bool = False

    @property
    def collision_rect(self) -> pygame.Rect:
        """Collision strip, centred horizontally at the sprite bottom."""
        col_x = int(self.x + (self.sprite_width - self.collision_width) / 2)
        col_y = int(self.y + self.sprite_height - self.collision_height)
        return pygame.Rect(col_x, col_y, self.collision_width, self.collision_height)

    @abstractmethod
    def update(self, dt: float, *args: Any, **kwargs: Any) -> None:
        """Advance behaviour and animation by ``dt`` seconds."""
