"""Snow on the roofs: each building's roofs whitened as the snow on the ground deepens.

A building's roofs are the polygons on the map's `Roofs` layer over its
sprite (models/roofs.py), cut to where the sprite is painted. Its snow cap is
the sprite there, turned to grey, lifted towards white and tinted like snow
(make_cap()), so the roof's tiles and the shade of its slopes still show
through. It is drawn just over its building in the render queue (map_view),
at an opacity following Weather.snow_cover between SNOW_ROOFS_FROM's two
levels: the roofs whiten with the first snow that lies and are white well
before the ground is.

Made lazily, per building, zoom and one of OPACITY_STEPS opacities (baked
into the pixels, as the furrows are: a surface alpha on a per-pixel-alpha
surface makes SDL blit it far slower); buildings without a roof get none.
"""

from typing import Dict, List, Optional, Sequence, Tuple

import pygame

from ..config.constants import SNOW_ROOFS_FROM

Point = Tuple[float, float]
SNOW_TINT = (236, 241, 252)   # multiplied into the lifted grey: white with a breath of blue
GREY_KEEP = 0.4               # how much of the roof's own light and shade shows through the snow
OPACITY_STEPS = 8
MAX_KEPT = 400                # scaled caps kept before the cache is emptied


def roof_snow_level(cover: float) -> float:
    """How white the roofs are (0 to 1) for *cover* of snow on the ground."""
    low, high = SNOW_ROOFS_FROM
    if cover <= low:
        return 0.0
    return min(1.0, (cover - low) / (high - low))


def make_cap(image: pygame.Surface, rect: pygame.Rect, roofs: Sequence[Sequence[Point]]) -> Optional[pygame.Surface]:
    """The snow cap of a building drawn as *image* over world *rect*, or None if none of *roofs* is on it."""
    outline = pygame.Surface(rect.size, pygame.SRCALPHA)
    drawn = False
    for points in roofs:
        local = [(x - rect.x, y - rect.y) for x, y in points]
        xs, ys = [p[0] for p in local], [p[1] for p in local]
        if max(xs) < 0 or max(ys) < 0 or min(xs) >= rect.width or min(ys) >= rect.height:
            continue
        pygame.draw.polygon(outline, (255, 255, 255, 255), local)
        drawn = True
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

    def __init__(self, roofs: List[List[Point]]) -> None:
        self.roofs = roofs
        self._caps: Dict[int, Optional[pygame.Surface]] = {}          # id(house) -> its cap at world size
        self._scaled: Dict[Tuple[int, float, int], pygame.Surface] = {}

    def _cap_of(self, house) -> Optional[pygame.Surface]:
        key = id(house)
        if key not in self._caps:
            image = getattr(house, 'image', None)
            cap = None
            if image is not None and self.roofs:
                rect = pygame.Rect(round(house.x), round(house.y) - image.get_height(), *image.get_size())
                cap = make_cap(image, rect, self.roofs)
            self._caps[key] = cap
        return self._caps[key]

    def sprite(self, house, size: Tuple[int, int], level: float) -> Optional[pygame.Surface]:
        """*house*'s snow cap at *size* (its sprite's on screen) for roofs *level* white, or None."""
        step = round(level * OPACITY_STEPS)
        if step <= 0:
            return None
        cap = self._cap_of(house)
        if cap is None:
            return None
        key = (id(house), size, step)
        scaled = self._scaled.get(key)
        if scaled is None:
            if len(self._scaled) > MAX_KEPT:
                self._scaled.clear()
            scaled = pygame.transform.smoothscale(cap, size) if size != cap.get_size() else cap.copy()
            if step < OPACITY_STEPS:
                alpha = round(255 * step / OPACITY_STEPS)
                scaled.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
            self._scaled[key] = scaled
        return scaled
