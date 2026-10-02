"""Reads the kinds of ground off the map's own tiles.

The plan is not drawn by hand: the ground tile layers are averaged down to a
few pixels per tile, and each kind of ground (water, sand, road, cobbles,
forest floor) is picked out by its colour into a ``pygame.Mask``. Whatever
the map's tiles show, the plan therefore shows too, without anyone having to
keep the two in step.
"""

from typing import Dict, Optional, Tuple

import pygame
import pytmx

from .style import (
    GROUND_PLAZA, GROUND_ROAD, GROUND_SAND, GROUND_WATER, GROUND_WOOD,
    IGNORED_GROUND_LAYERS, SAMPLE_PX_PER_TILE,
)


class Ground:
    """The kinds of ground of one map, at any size asked for."""

    def __init__(self, tmx_data: pytmx.TiledMap) -> None:
        self.tiles_wide: int = tmx_data.width
        self.tiles_high: int = tmx_data.height
        self._sample: pygame.Surface = _composite(tmx_data, SAMPLE_PX_PER_TILE)
        # Forest floor is a speckled mix of tiles; one pixel per tile, read
        # before any smoothing, says best where it lies as a whole.
        self._coarse: pygame.Surface = pygame.transform.smoothscale(
            self._sample, (self.tiles_wide, self.tiles_high)
        )
        self._cache: Dict[Tuple[int, int], Dict[str, pygame.Mask]] = {}

    def masks(self, size: Tuple[int, int]) -> Dict[str, pygame.Mask]:
        """Masks of water, sand, road, plaza and wood, ``size`` pixels large."""
        if size not in self._cache:
            self._cache[size] = self._make_masks(size)
        return self._cache[size]

    def _make_masks(self, size: Tuple[int, int]) -> Dict[str, pygame.Mask]:
        scaled = pygame.transform.smoothscale(self._sample, size)
        masks = {
            "water": _rounded(_pick(scaled, GROUND_WATER), (self.tiles_wide, self.tiles_high)),
            "sand": _pick(scaled, GROUND_SAND),
            "road": _pick(scaled, GROUND_ROAD),
            "plaza": _pick(scaled, GROUND_PLAZA),
        }
        masks["wood"] = _smooth_up(_pick(self._coarse, GROUND_WOOD), size)
        # Lone pixels where two kinds of ground blend read as noise, not ground
        for name in ("sand", "road", "plaza"):
            masks[name] = erode(dilate(masks[name], 1), 1)
        masks["sand"].erase(masks["water"], (0, 0))
        return masks


def dilate(mask: pygame.Mask, radius: int) -> pygame.Mask:
    """The mask grown by ``radius`` pixels in every direction."""
    if radius <= 0:
        return mask.copy()
    # Growing by a big disk costs about its area; growing several times by
    # small ones adds up to nearly the same shape for far less
    out = mask
    while radius > 0:
        step = min(radius, _MAX_STEP)
        grown = pygame.Mask(mask.get_size())
        out.convolve(_disk(step), grown, (-step, -step))
        out = grown
        radius -= step
    return out


_MAX_STEP = 4


def erode(mask: pygame.Mask, radius: int) -> pygame.Mask:
    """The mask shrunk by ``radius`` pixels from every edge."""
    if radius <= 0:
        return mask.copy()
    inverse = mask.copy()
    inverse.invert()
    grown = dilate(inverse, radius)
    grown.invert()
    return grown


def rim(mask: pygame.Mask, inner: int, outer: int) -> pygame.Mask:
    """The band from ``inner`` inside the mask's edge to ``outer`` outside it."""
    band = dilate(mask, outer)
    band.erase(erode(mask, inner), (0, 0))
    return band


_disks: Dict[int, pygame.Mask] = {}


def _disk(radius: int) -> pygame.Mask:
    if radius not in _disks:
        side = 2 * radius + 1
        disk = pygame.Mask((side, side))
        for y in range(side):
            for x in range(side):
                if (x - radius) ** 2 + (y - radius) ** 2 <= radius * radius + radius:
                    disk.set_at((x, y))
        _disks[radius] = disk
    return _disks[radius]


def _pick(surface: pygame.Surface, ground: Tuple[Tuple[int, int, int], Tuple[int, int, int]]) -> pygame.Mask:
    color, tolerance = ground
    return pygame.mask.from_threshold(surface, (*color, 255), (*tolerance, 255))


def _rounded(mask: pygame.Mask, via: Tuple[int, int]) -> pygame.Mask:
    """The mask with the tile grid's stair steps rounded off its edges.

    Shrunk to ``via`` (averaging away the steps) and grown back smoothly.
    """
    full = mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 255))
    # Scaling alone keeps a staircase a (softer) staircase; blurring it at
    # the size of one step is what turns it into a slope
    small = _box_blur(pygame.transform.smoothscale(full, via))
    # The blur tops out a little short of white; keep what is over half of it
    return pygame.mask.from_threshold(
        pygame.transform.smoothscale(small, mask.get_size()), (255, 255, 255, 255), (134, 134, 134, 255)
    )


def _box_blur(surface: pygame.Surface) -> pygame.Surface:
    """Each pixel the mean of its 3x3 neighbourhood (to within a few levels)."""
    ninth = surface.copy()
    ninth.fill((28, 28, 28), special_flags=pygame.BLEND_MULT)
    out = pygame.Surface(surface.get_size())
    out.fill((0, 0, 0))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            out.blit(ninth, (dx, dy), special_flags=pygame.BLEND_ADD)
    return out


def _smooth_up(mask: pygame.Mask, size: Tuple[int, int]) -> pygame.Mask:
    """Scale a coarse mask up with rounded rather than stepped edges."""
    small = mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 255))
    big = pygame.transform.smoothscale(small, size)
    return pygame.mask.from_threshold(big, (255, 255, 255, 255), (128, 128, 128, 255))


def _composite(tmx_data: pytmx.TiledMap, px_per_tile: int) -> pygame.Surface:
    """All ground tile layers drawn over one another, ``px_per_tile`` small."""
    surface = pygame.Surface((tmx_data.width * px_per_tile, tmx_data.height * px_per_tile))
    surface.fill((0, 0, 0))
    shrunk: Dict[int, Optional[pygame.Surface]] = {}
    for layer in tmx_data.visible_layers:
        if not isinstance(layer, pytmx.TiledTileLayer):
            continue
        if not layer.name.startswith("Ground") or layer.name in IGNORED_GROUND_LAYERS:
            continue
        for x, y, image in layer.tiles():
            key = id(image)
            if key not in shrunk:
                shrunk[key] = pygame.transform.smoothscale(image, (px_per_tile, px_per_tile))
            surface.blit(shrunk[key], (x * px_per_tile, y * px_per_tile))
    return surface
