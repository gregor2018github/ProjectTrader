"""A quest marker over a figurine who has news for the player: a gold "!" on a parchment shield.

It bobs gently over their head and breathes a soft glow, drawn after the
lighting (like the petted sheep's hearts) so it shows at night as well. Drawn
with pygame's shapes at four times the size and smoothed down, made once per
size. So far the shepherdess wears it while her sheep is lost
(models/lost_sheep.py) and she has something to tell.
"""

import math
from typing import Dict, Tuple

import pygame

#: Its size at zoom 1, in screen pixels (width; the height follows), and its least
MARKER_WIDTH = 20
MIN_WIDTH = 12
#: Its gap over the figurine's head at zoom 1, how far it bobs and how fast
GAP = 6
BOB_PX = 3.0
BOB_PERIOD_S = 1.4
#: The glow behind it: its strength between breaths
GLOW_ALPHA = (40, 120)
SUPERSAMPLE = 4

INK = (58, 38, 22)
PARCHMENT = (240, 226, 186)
GOLD = (222, 170, 48)
GOLD_LIGHT = (252, 222, 120)
GLOW = (255, 214, 110)

_cache: Dict[int, Tuple[pygame.Surface, pygame.Surface]] = {}


def _marker(width: int) -> Tuple[pygame.Surface, pygame.Surface]:
    """The marker and its glow, `width` pixels wide."""
    cached = _cache.get(width)
    if cached is not None:
        return cached
    height = round(width * 1.3)
    s = SUPERSAMPLE
    big = pygame.Surface((width * s, height * s), pygame.SRCALPHA)
    w, h = big.get_size()
    # A shield of parchment with an ink rim, pointed at the bottom towards the head
    shield = [(0.1 * w, 0.06 * h), (0.9 * w, 0.06 * h), (0.9 * w, 0.62 * h), (0.5 * w, 0.96 * h),
              (0.1 * w, 0.62 * h)]
    pygame.draw.polygon(big, PARCHMENT, shield)
    pygame.draw.polygon(big, INK, shield, max(2, round(0.08 * w)))
    # The "!": a tapering bar and a dot, gold with an ink outline and a light glint
    bar = [(0.38 * w, 0.17 * h), (0.62 * w, 0.17 * h), (0.56 * w, 0.52 * h), (0.44 * w, 0.52 * h)]
    pygame.draw.polygon(big, GOLD, bar)
    pygame.draw.polygon(big, INK, bar, max(2, round(0.05 * w)))
    pygame.draw.line(big, GOLD_LIGHT, (0.45 * w, 0.22 * h), (0.47 * w, 0.44 * h), max(1, round(0.04 * w)))
    dot = (round(0.5 * w), round(0.66 * h))
    radius = round(0.09 * w)
    pygame.draw.circle(big, GOLD, dot, radius)
    pygame.draw.circle(big, INK, dot, radius, max(2, round(0.05 * w)))
    marker = pygame.transform.smoothscale(big, (width, height))

    glow_size = round(width * 2.2)
    glow = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)
    centre = glow_size / 2
    for r in range(int(centre), 0, -1):
        alpha = round(255 * max(0.0, 1 - r / centre) ** 1.6)
        pygame.draw.circle(glow, (*GLOW, alpha), (round(centre), round(centre)), r)
    _cache[width] = (marker, glow)
    return marker, glow


def draw_quest_marker(screen: pygame.Surface, head: Tuple[int, int], zoom: float, seconds: float) -> None:
    """Draw the marker over a head.

    Args:
        screen: The surface to draw on.
        head: The top centre of the figurine's sprite on screen.
        zoom: The map's zoom.
        seconds: Real seconds, for the bob and the glow.
    """
    width = max(MIN_WIDTH, round(MARKER_WIDTH * zoom))
    marker, glow = _marker(width)
    phase = seconds * 2 * math.pi / BOB_PERIOD_S
    bob = math.sin(phase) * BOB_PX * max(zoom, 0.6)
    x = head[0] - marker.get_width() / 2
    y = head[1] - GAP * max(zoom, 0.6) - marker.get_height() + bob
    low, high = GLOW_ALPHA
    glow.set_alpha(round(low + (high - low) * (0.5 + 0.5 * math.sin(phase * 0.5))))
    screen.blit(glow, (round(x + marker.get_width() / 2 - glow.get_width() / 2),
                       round(y + marker.get_height() * 0.4 - glow.get_height() / 2)))
    screen.blit(marker, (round(x), round(y)))
