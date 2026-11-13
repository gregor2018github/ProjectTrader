"""The view narrowing round the player while worn out (models/drowsiness.py).

The map goes dark from the edges in, leaving a soft-edged oval round the player
clear; when the eyes fall shut the oval closes to a slit and opens again. The
darkness is made at `LOW_RES` of the view's size (a radial falloff stretched to
the oval, `_falloff`) and smoothed up to it, and only made again when the oval
or the player's place on the screen has changed by a low-res pixel, so with the
eyes open it costs one blit a frame.
"""

from typing import Any, Optional, Tuple

import pygame

from ...models.drowsiness import Drowsiness, fatigue

#: The darkness is worked out at this share of the view's size
LOW_RES = 0.25
#: The falloff texture's size, where the dark begins (share of the oval's radius) and how dark it gets
FALLOFF_SIZE = 256
CLEAR_INNER = 0.45
DARKEST = 250
#: How dark the edges are at first (from `drowsiness.TIRED_FROM`), growing to `DARKEST` when worn out
DARK_AT_FIRST = 165

_falloff_surface: Optional[pygame.Surface] = None
_cache: dict = {"key": None, "surface": None}


def _falloff() -> pygame.Surface:
    """Black, clear in the middle and growing dark towards the edge of the circle it fills, dark beyond."""
    global _falloff_surface
    if _falloff_surface is None:
        size = FALLOFF_SIZE
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        surf.fill((0, 0, 0, DARKEST))
        c = size // 2
        # Rings from the edge inwards, each overwriting the middle with a lighter dark
        for radius in range(c, 0, -1):
            t = max(0.0, min(1.0, (radius / c - CLEAR_INNER) / (1.0 - CLEAR_INNER)))
            t = t * t * (3.0 - 2.0 * t)
            pygame.draw.circle(surf, (0, 0, 0, round(DARKEST * t)), (c, c), radius)
        _falloff_surface = surf
    return _falloff_surface


def _darkness(size: Tuple[int, int], centre: Tuple[int, int], half: Tuple[int, int], dark: int) -> pygame.Surface:
    """The darkness over a view of `size`, as dark as `dark` (alpha), the oval of half sizes `half`
    clear round `centre`."""
    low = (max(1, round(size[0] * LOW_RES)), max(1, round(size[1] * LOW_RES)))
    surf = pygame.Surface(low, pygame.SRCALPHA)
    surf.fill((0, 0, 0, dark))
    a, b = max(1, round(half[0] * LOW_RES)), max(1, round(half[1] * LOW_RES))
    cx, cy = round(centre[0] * LOW_RES), round(centre[1] * LOW_RES)
    oval = pygame.transform.smoothscale(_falloff(), (2 * a, 2 * b))
    surf.blit(oval, (cx - a, cy - b), special_flags=pygame.BLEND_RGBA_MIN)
    return pygame.transform.smoothscale(surf, size)


def draw_drowsy_view(screen: pygame.Surface, map_rect: pygame.Rect, centre: Tuple[float, float],
                     drowsiness: Optional[Drowsiness], tiredness: float) -> bool:
    """Darken the map round the player at `centre` (screen coordinates); whether anything was drawn."""
    if drowsiness is None:
        return False
    view = drowsiness.view(tiredness)
    if view is None:
        return False
    half_diagonal = (map_rect.width ** 2 + map_rect.height ** 2) ** 0.5 / 2
    half = (view[0] * half_diagonal, view[1] * half_diagonal)
    local = (centre[0] - map_rect.left, centre[1] - map_rect.top)
    step = 1.0 / LOW_RES
    # Shut, the dark is as deep as it goes whatever the tiredness
    shut = 1.0 - drowsiness.lid
    dark = DARK_AT_FIRST + (DARKEST - DARK_AT_FIRST) * max(fatigue(tiredness), shut)
    key = (map_rect.size, round(local[0] / step), round(local[1] / step), round(half[0] / step),
           round(half[1] / step), round(dark / 5))
    if _cache["key"] != key:
        _cache["key"] = key
        _cache["surface"] = _darkness(map_rect.size, (key[1] * step, key[2] * step), (key[3] * step, key[4] * step),
                                      key[5] * 5)
    screen.blit(_cache["surface"], map_rect.topleft)
    return True


def player_centre(game_map: Any, offset: Tuple[int, int]) -> Tuple[float, float]:
    """Where the middle of the player is on the screen."""
    player = game_map.map_player
    x, y = game_map.camera.apply(player.x + player.width / 2, player.y + player.height / 2)
    return x + offset[0], y + offset[1]
