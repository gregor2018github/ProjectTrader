"""Mill institution — extends House with rotating blade animation."""

import os
import pygame
from typing import Optional, Tuple, Dict
from ..house import House

BLADE_SPEED_DEG_PER_SEC = 22.0   # rotation speed in degrees per second


class Mill(House):
    """A mill building with animated rotating blades.

    The blade pivot point (world coordinates) is set after the TMX
    'Special' layer has been parsed, via ``set_blade_pivot()``.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.blade_angle: float = 0.0
        self.blade_pivot: Optional[Tuple[float, float]] = None
        self._blade_orig: Optional[pygame.Surface] = None
        self._blade_scaled_cache: Dict[float, pygame.Surface] = {}
        self._load_blade_image()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _load_blade_image(self) -> None:
        path = os.path.join('assets', 'map_sprites', 'houses', 'Mill_Blades.png')
        if os.path.exists(path):
            try:
                self._blade_orig = pygame.image.load(path).convert_alpha()
            except Exception as e:
                print(f"Failed to load Mill_Blades.png: {e}")

    def set_blade_pivot(self, world_x: float, world_y: float) -> None:
        """Set the world-space center point around which the blades rotate."""
        self.blade_pivot = (world_x, world_y)

    # ------------------------------------------------------------------
    # Animation
    # ------------------------------------------------------------------

    def update_blades(self, dt: float) -> None:
        """Advance blade rotation by dt seconds."""
        self.blade_angle = (self.blade_angle + BLADE_SPEED_DEG_PER_SEC * dt) % 360.0

    def get_blade_sprite(self, zoom: float) -> Optional[pygame.Surface]:
        """Return the rotated blade surface for the current angle and zoom.

        The returned surface is centred on the blade pivot — the caller
        should blit it at ``(pivot_screen_x - w/2, pivot_screen_y - h/2)``.
        """
        if self._blade_orig is None or self.blade_pivot is None:
            return None

        zoom_key = round(zoom, 3)
        if zoom_key not in self._blade_scaled_cache:
            w = round(self._blade_orig.get_width() * zoom)
            h = round(self._blade_orig.get_height() * zoom)
            if w > 0 and h > 0:
                self._blade_scaled_cache[zoom_key] = pygame.transform.smoothscale(
                    self._blade_orig, (w, h)
                )
            else:
                return None

        scaled = self._blade_scaled_cache[zoom_key]
        return pygame.transform.rotate(scaled, self.blade_angle)
