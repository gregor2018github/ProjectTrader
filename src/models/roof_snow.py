"""Snow on the roofs: each building's roofs whitened as the snow on the ground deepens.

A building's roofs are the polygons on the map's `Roofs` layer over its
sprite (models/roofs.py) less their holes, cut to where the sprite is painted. Its snow cap is
the sprite there, turned to grey, lifted towards white and tinted like snow
(make_cap()), so the roof's tiles and the shade of its slopes still show
through. It is drawn just over its building in the render queue (map_view),
as much of it as the snow covers: Weather.snow_cover between SNOW_ROOFS_FROM's
two levels takes a roof from bare to white, so the roofs keep pace with the
ground, a little ahead of it. Like the
ground (snow_flecks.py), a roof first takes scattered flecks in clumps, and
the rest fills in, unevenly, only from ROOF_BLANKET_FROM on.

Made lazily, per building, zoom and one of LEVEL_STEPS levels (baked into the
pixels, as the furrows are: a surface alpha on a per-pixel-alpha surface
makes SDL blit it far slower), within BUILD_BUDGET_S a frame (begin_frame())
while an older look of the cap can stand in; buildings without a roof get none.
"""

import random
import time
from typing import Dict, List, Optional, Sequence, Tuple

import pygame

from ..config.constants import SNOW_ROOFS_FROM
from . import snow_flecks

Point = Tuple[float, float]
SNOW_TINT = (236, 241, 252)   # multiplied into the lifted grey: white with a breath of blue
GREY_KEEP = 0.4               # how much of the roof's own light and shade shows through the snow
LEVEL_STEPS = 24
FLECK_PX = 2                  # world pixels to a pixel of the flecks, as on the ground
NOISE_PX = 48                 # the drifts on a roof, about this many world px apart
ROOF_NOISE_DUST = 0.35        # the drifts move where the flecks lie first by up to this much
ROOF_BLANKET_FROM = 0.4       # the rest of the roof whitens from this level...
ROOF_NOISE_BLANKET = 0.45     # ...and later by up to this much more
BUILD_BUDGET_S = 0.003        # time per frame for making caps while older ones can stand in
MAX_KEPT = 400                # scaled caps kept before the cache is emptied

_FLECKS: Optional[pygame.Surface] = None


def _flecks() -> pygame.Surface:
    global _FLECKS
    if _FLECKS is None:
        tile = snow_flecks.fleck_tile(random.Random(11))
        _FLECKS = pygame.transform.scale(tile, (tile.get_width() * FLECK_PX, tile.get_height() * FLECK_PX))
    return _FLECKS


def roof_threshold(rect: pygame.Rect, seed: int) -> pygame.Surface:
    """The level (alpha, 0-255) each pixel of a building over world *rect* turns white at (snow_flecks.py)."""
    noise = snow_flecks.smooth_noise(rect.size, NOISE_PX, random.Random(seed))
    threshold = snow_flecks.tiled(_flecks(), rect.size, rect.topleft)
    dust = noise.copy()
    dust.fill((255, 255, 255, round(255 * ROOF_NOISE_DUST)), special_flags=pygame.BLEND_RGBA_MULT)
    threshold.blit(dust, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
    noise.fill((255, 255, 255, round(255 * ROOF_NOISE_BLANKET)), special_flags=pygame.BLEND_RGBA_MULT)
    noise.fill((0, 0, 0, round(255 * ROOF_BLANKET_FROM)), special_flags=pygame.BLEND_RGBA_ADD)
    threshold.blit(noise, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return threshold


def roof_snow_level(cover: float) -> float:
    """How white the roofs are (0 to 1) for *cover* of snow on the ground."""
    low, high = SNOW_ROOFS_FROM
    if cover <= low:
        return 0.0
    return min(1.0, (cover - low) / (high - low))


def make_cap(image: pygame.Surface, rect: pygame.Rect,
             roofs: Sequence[Tuple[Sequence[Point], Sequence[Sequence[Point]]]]) -> Optional[pygame.Surface]:
    """The snow cap of a building drawn as *image* over world *rect*, or None if none of *roofs* is on it.

    *roofs* are each roof's points and its holes (roofs.match_holes()).
    """
    outline = pygame.Surface(rect.size, pygame.SRCALPHA)
    drawn = False
    holes = []
    for points, cut in roofs:
        local = [(x - rect.x, y - rect.y) for x, y in points]
        xs, ys = [p[0] for p in local], [p[1] for p in local]
        if max(xs) < 0 or max(ys) < 0 or min(xs) >= rect.width or min(ys) >= rect.height:
            continue
        pygame.draw.polygon(outline, (255, 255, 255, 255), local)
        drawn = True
        holes += cut
    for hole in holes:   # after all the roofs, so a hole is open whichever of them it lies on
        pygame.draw.polygon(outline, (0, 0, 0, 0), [(x - rect.x, y - rect.y) for x, y in hole])
    if not drawn:
        return None
    on_roof = pygame.mask.from_surface(outline).overlap_mask(pygame.mask.from_surface(image), (0, 0))
    if not on_roof.count():
        return None
    cap = pygame.transform.grayscale(image)
    keep = round(255 * GREY_KEEP)
    cap.fill((keep, keep, keep), special_flags=pygame.BLEND_RGB_MULT)
    lift = 255 - keep
    cap.fill((lift, lift, lift), special_flags=pygame.BLEND_RGB_ADD)
    cap.fill(SNOW_TINT, special_flags=pygame.BLEND_RGB_MULT)
    cap.blit(on_roof.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0)), (0, 0),
             special_flags=pygame.BLEND_RGBA_MULT)
    return cap


class RoofSnow:
    """The snow caps of the map's buildings, made as they are first needed."""

    def __init__(self, roofs: List[Tuple[List[Point], List[List[Point]]]]) -> None:
        """*roofs*: each roof's points and its holes (roofs.match_holes())."""
        self.roofs = roofs
        # id(house) -> its cap at world size and the level each of its pixels whitens at, or None
        self._caps: Dict[int, Optional[Tuple[pygame.Surface, pygame.Surface]]] = {}
        self._scaled: Dict[Tuple[int, Tuple[int, int]], Tuple[int, pygame.Surface]] = {}   # -> (step, cap)
        self._spent = 0.0

    def begin_frame(self) -> None:
        """A new frame: caps may be made again for BUILD_BUDGET_S."""
        self._spent = 0.0

    def _cap_of(self, house) -> Optional[Tuple[pygame.Surface, pygame.Surface]]:
        key = id(house)
        if key not in self._caps:
            image = getattr(house, 'image', None)
            made = None
            if image is not None and self.roofs:
                rect = pygame.Rect(round(house.x), round(house.y) - image.get_height(), *image.get_size())
                cap = make_cap(image, rect, self.roofs)
                if cap is not None:
                    made = (cap, roof_threshold(rect, rect.x * 7919 + rect.y))
            self._caps[key] = made
        return self._caps[key]

    def sprite(self, house, size: Tuple[int, int], level: float) -> Optional[pygame.Surface]:
        """*house*'s snow cap at *size* (its sprite's on screen) for roofs *level* white, or None."""
        step = round(level * LEVEL_STEPS)
        if step <= 0:
            return None
        made = self._cap_of(house)
        if made is None:
            return None
        key = (id(house), size)
        kept = self._scaled.get(key)
        if kept is not None and (kept[0] == step or self._spent > BUILD_BUDGET_S):
            return kept[1]   # as it is, or as it was while this frame's time for making caps is spent
        start = time.perf_counter()
        cap, threshold = made
        white = snow_flecks.whiteness(threshold, round(255 * step / LEVEL_STEPS))
        white.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGBA_ADD)
        covered = cap.copy()
        covered.blit(white, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        scaled = pygame.transform.smoothscale(covered, size) if size != covered.get_size() else covered
        if len(self._scaled) > MAX_KEPT:
            self._scaled.clear()
        self._scaled[key] = (step, scaled)
        self._spent += time.perf_counter() - start
        return scaled
