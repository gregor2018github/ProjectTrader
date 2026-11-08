"""A place on the map where the player can fish, from the "Fishing" object layer.

A spot is a Tiled point in the water, just off the bank or pier the player
stands on, named as the player is to read it. Standing within
``FISHING_REACH_TILES`` of it, a click on the water offers "Go Fishing"
(``water_click_menu.py``). While the day's fishing is still to be done, golden
rings spread on the water there (``FishingSpot.draw``), as the chopping stump
glows; the Town Plan marks explored spots at all times.
"""

from typing import Dict, List, Tuple, TYPE_CHECKING

import pygame

from ..config.constants import TILE_SIZE

if TYPE_CHECKING:
    from .map import Camera

#: How far from the spot the player may stand and still fish there, in tiles
FISHING_REACH_TILES = 4

_RING_COUNT = 3                     # rings out at a time, evenly apart
_RING_PERIOD_S = 2.7                # a ring's life, in real seconds
_RING_MAX_RADIUS = 34.0             # how wide one grows, in world pixels
_RING_FLATTEN = 0.5                 # lying on the water: half as tall as wide
_RING_ALPHA = 255                   # at its strongest, just after it starts
_RING_COLOUR = (255, 204, 70)       # deeper than the stump's gold, which turns grey over the blue
_ALPHA_STEP = 12                    # the surfaces are kept per radius and step of alpha

_ring_cache: Dict[Tuple[int, int, int], pygame.Surface] = {}


def _ring_surface(radius_px: int, alpha: int, width: int) -> pygame.Surface:
    alpha -= alpha % _ALPHA_STEP
    key = (radius_px, alpha, width)
    surface = _ring_cache.get(key)
    if surface is None:
        height = max(2, round(radius_px * _RING_FLATTEN))
        surface = pygame.Surface((radius_px * 2 + 2, height * 2 + 2), pygame.SRCALPHA)
        pygame.draw.ellipse(surface, (*_RING_COLOUR, alpha), surface.get_rect(), width)
        _ring_cache[key] = surface
    return surface


class FishingSpot:
    """One of the map's fishing spots (see the module)."""

    def __init__(self, name: str, x: float, y: float) -> None:
        self.name = name
        self.x = x
        self.y = y

    def in_reach(self, px: float, py: float) -> bool:
        """Whether someone at this world point can fish here."""
        return (px - self.x) ** 2 + (py - self.y) ** 2 <= (FISHING_REACH_TILES * TILE_SIZE) ** 2

    @staticmethod
    def rings(seconds: float) -> List[Tuple[float, int]]:
        """The rings out at this moment: (radius in world pixels, alpha), growing and fading."""
        out = []
        for number in range(_RING_COUNT):
            age = (seconds / _RING_PERIOD_S + number / _RING_COUNT) % 1.0
            out.append((_RING_MAX_RADIUS * age, round(_RING_ALPHA * (1 - age * age))))   # fades late
        return out

    def draw(self, screen: pygame.Surface, camera: 'Camera', offset_x: int, offset_y: int, seconds: float) -> None:
        """The golden rings, flat on the water, if they are in view."""
        centre_x, centre_y = camera.apply(self.x, self.y)
        reach = _RING_MAX_RADIUS * camera.zoom + 2
        if not (-reach <= centre_x <= camera.screen_width + reach and -reach <= centre_y <= camera.screen_height + reach):
            return
        width = max(2, round(camera.zoom * 1.5))
        for radius, alpha in self.rings(seconds):
            radius_px = round(radius * camera.zoom)
            if radius_px >= 3 and alpha >= _ALPHA_STEP:
                surface = _ring_surface(radius_px, alpha, width)
                screen.blit(surface, surface.get_rect(center=(round(centre_x) + offset_x, round(centre_y) + offset_y)))
