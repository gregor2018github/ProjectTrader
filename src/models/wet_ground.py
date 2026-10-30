"""The ground darkening as it gets wet, unevenly, and differently for each kind of ground.

A multiply over the ground layers (under the puddles, the bridges and
everyone else), its strength following how wet it is: Weather.wetness, plus
a little of the rain itself, since the surface darkens before anything
collects (wet_level()). What it multiplies by depends on the ground
(WET_TINTS): a dirt road turns a darker, richer brown, cobbles a darker,
cooler grey, sand darker, grass and forest floor only a little deeper; water
is left as it is. The kinds of ground are the Town Plan's own reading of the
map (set_ground()).

Uneven: every spot has a threshold of wetness it darkens at (smooth noise of
two sizes, NOISE_TILES), so a shower first darkens the low patches and the
ground dries in blotches rather than all at once. Round each puddle the
threshold is lowered (a hollow, HOLLOW_GROW times the puddle), so it sits in
a damp patch that is first to darken and last to dry.

Cheap: the whole map's colours are kept at PX_PER_TILE pixels a tile. For
the screen, the part in view is worked out in a few blends on that small
scale and smoothed up to the zoom in one piece (so there are no seams), and
kept: it is only made again once the camera has moved a whole pixel of the
small map (a quarter tile) or the wet level has changed; in between it is
only blitted a little further along. Drawing is one multiply blit.
"""

import random
from typing import Dict, Optional

import pygame

from ..config.constants import TILE_SIZE

PX_PER_TILE = 4           # resolution of the wetness map
NOISE_TILES = (6, 1.5)    # the size of the blotches, large and small, in tiles
NOISE_SPREAD = 0.62       # the thresholds run from 0 to this much wetness
FULL_OVER = 0.25          # wetness over a spot's threshold it takes to look fully wet
HOLLOW_GROW = 2.2         # a puddle's damp patch, as many times its size
RAIN_SHARE = 0.4          # how much the rain itself wets the surface, besides the ground's wetness

# What fully wet ground is multiplied by, per kind (anything else is grass)
WET_TINTS = {
    "grass": (214, 224, 206),
    "wood": (204, 210, 198),
    "road": (178, 156, 140),
    "plaza": (176, 182, 196),
    "sand": (188, 170, 148),
    "water": (255, 255, 255),
}


def wet_level(wetness: float, rain: float) -> float:
    """How wet the ground looks (0 to 1): the ground's wetness, and a little of the rain falling on it."""
    return min(1.0, wetness * 1.2 + rain * RAIN_SHARE)


def _soft_blob(size: int) -> pygame.Surface:
    """A round grey blob, full in the middle and fading to nothing at its edge."""
    blob = pygame.Surface((size, size))
    blob.fill((0, 0, 0))
    for ring in range(size // 2, 0, -1):
        v = round(255 * (1 - ring / (size / 2)) ** 0.7)
        pygame.draw.circle(blob, (v, v, v), (size // 2, size // 2), ring)
    return blob


class WetGround:
    """The map's wet look, made once from its kinds of ground and redrawn as it gets wetter or drier."""

    def __init__(self, tiles_wide: int, tiles_high: int, rng: Optional[random.Random] = None) -> None:
        self.size = (tiles_wide * PX_PER_TILE, tiles_high * PX_PER_TILE)
        self.rng = rng or random.Random()
        self._dark: Optional[pygame.Surface] = None      # 255 less the wet tint, per pixel
        self._noise = self._make_noise()                 # the threshold per pixel, before the hollows
        self._threshold = self._noise.copy()             # with the hollows of the current puddles
        self._threshold_version = 0
        self._puddles_seen = None
        self._view_key = None                            # what the kept view was made for
        self._view_surface: Optional[pygame.Surface] = None

    def set_ground(self, masks: Dict[str, pygame.Mask]) -> None:
        """Take over the kinds of ground: masks of "water", "sand", "road", "plaza" and "wood", self.size large."""
        tint = pygame.Surface(self.size)
        tint.fill(WET_TINTS["grass"])
        for kind in ("wood", "sand", "road", "plaza", "water"):
            if kind in masks:
                tint.blit(masks[kind].to_surface(setcolor=(*WET_TINTS[kind], 255), unsetcolor=(0, 0, 0, 0)), (0, 0))
        self._dark = pygame.Surface(self.size)
        self._dark.fill((255, 255, 255))
        self._dark.blit(tint, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
        self._view_key = None

    def _make_noise(self) -> pygame.Surface:
        """Smooth blotches of two sizes, scaled to 0..NOISE_SPREAD of full."""
        noise = pygame.Surface(self.size)
        noise.fill((0, 0, 0))
        for tiles, share in zip(NOISE_TILES, (0.65, 0.35)):
            cells = (max(2, round(self.size[0] / PX_PER_TILE / tiles)), max(2, round(self.size[1] / PX_PER_TILE / tiles)))
            small = pygame.Surface(cells)
            for y in range(cells[1]):
                for x in range(cells[0]):
                    v = round(255 * share * self.rng.random())
                    small.set_at((x, y), (v, v, v))
            noise.blit(pygame.transform.smoothscale(small, self.size), (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        spread = round(255 * NOISE_SPREAD)
        noise.fill((spread, spread, spread), special_flags=pygame.BLEND_RGB_MULT)
        return noise

    def _dig_hollows(self, puddles) -> None:
        """Lower the thresholds round each puddle, so the ground there is the first to darken and last to dry."""
        self._threshold = self._noise.copy()
        for puddle in puddles:
            w = max(3, round(puddle.width * HOLLOW_GROW * PX_PER_TILE))
            h = max(3, round(puddle.height * HOLLOW_GROW * PX_PER_TILE))
            blob = pygame.transform.smoothscale(_soft_blob(32), (w, h))
            self._threshold.blit(blob, (round(puddle.x / TILE_SIZE * PX_PER_TILE - w / 2),
                                        round(puddle.y / TILE_SIZE * PX_PER_TILE - h / 2)),
                                 special_flags=pygame.BLEND_RGB_SUB)
        self._threshold_version += 1

    def _view(self, src: pygame.Rect, level: int, per_px: int) -> pygame.Surface:
        """The multiply for the wetness map's pixels *src* at *level* (0-255), *per_px* screen pixels each."""
        # How wet each pixel looks: (level - threshold), steepened to full over FULL_OVER
        amount = pygame.Surface(src.size)
        amount.fill((level, level, level))
        amount.blit(self._threshold, (0, 0), src, special_flags=pygame.BLEND_RGB_SUB)
        for _ in range(2):   # x4: FULL_OVER past its threshold a spot is fully wet
            amount.blit(amount.copy(), (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        # The multiply: white less (255 - tint) * amount
        dark = pygame.Surface(src.size)
        dark.blit(self._dark, (0, 0), src)
        dark.blit(amount, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        small = pygame.Surface(src.size)
        small.fill((255, 255, 255))
        small.blit(dark, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
        return pygame.transform.smoothscale(small, (src.width * per_px, src.height * per_px))

    def draw(self, screen: pygame.Surface, camera, offset_x: int, offset_y: int,
             level: float, puddles=None) -> None:
        """Darken the ground in view by how wet it looks (*level*, see wet_level())."""
        if self._dark is None or level <= 0:
            return
        if puddles is not None and puddles.placed is not self._puddles_seen:
            self._puddles_seen = puddles.placed
            self._dig_hollows(puddles.placed)
        tile_px = round(TILE_SIZE * camera.zoom)
        per_px = max(1, tile_px // PX_PER_TILE)   # tiles are 16 to 56 px: always a whole number
        scale = tile_px / float(TILE_SIZE)
        cam_x, cam_y = round(camera.x * scale), round(camera.y * scale)
        # The wetness map's pixels in view, and one more all round so the smoothing has no edge in sight
        src = pygame.Rect(cam_x // per_px - 1, cam_y // per_px - 1,
                          camera.screen_width // per_px + 3, camera.screen_height // per_px + 3)
        src = src.clip(pygame.Rect((0, 0), self.size))
        if src.width <= 0 or src.height <= 0:
            return
        key = (src.topleft, src.size, round(level * 255), per_px, self._threshold_version)
        if key != self._view_key:
            self._view_key = key
            self._view_surface = self._view(src, round(level * 255), per_px)
        screen.blit(self._view_surface, (src.x * per_px - cam_x + offset_x, src.y * per_px - cam_y + offset_y),
                    special_flags=pygame.BLEND_MULT)
