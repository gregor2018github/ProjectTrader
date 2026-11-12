"""Coats of arms: a shield in a house's colour with one plain charge in gold or silver.

The council's notables have no portraits; their arms stand for them (and will for the
dynasties to come). Arms are a dict as `assets/data/council.json` has them: a ``field``
colour, a ``charge`` of `CHARGES` and its ``metal``. A shield is drawn large and smoothed
down once per size, then kept.
"""

from typing import Any, Callable, Dict, List, Mapping, Tuple

import pygame

INK = (44, 32, 22)
METALS = {"gold": (226, 184, 72), "silver": (232, 228, 214)}
PLAYER_ARMS = {"field": (154, 48, 38), "charge": "bezants", "metal": "gold"}   # three gold coins on red
_SUPERSAMPLE = 4
_shields: Dict[Tuple, pygame.Surface] = {}

Point = Tuple[float, float]


def _outline(w: int, h: int) -> List[Point]:
    """A heater shield: a flat top, straight sides and a curve down to the point."""
    shoulder = 0.48 * h
    points: List[Point] = [(0, 0), (w - 1, 0), (w - 1, shoulder)]
    steps = 14
    for i in range(1, steps + 1):                       # right side down to the point
        t = i / steps
        x = (1 - t) ** 2 * (w - 1) + 2 * (1 - t) * t * (w - 1) + t ** 2 * (w / 2)
        y = (1 - t) ** 2 * shoulder + 2 * (1 - t) * t * (0.86 * h) + t ** 2 * (h - 1)
        points.append((x, y))
    for i in range(1, steps + 1):                       # and up the left
        t = i / steps
        x = (1 - t) ** 2 * (w / 2) + 2 * (1 - t) * t * 0 + t ** 2 * 0
        y = (1 - t) ** 2 * (h - 1) + 2 * (1 - t) * t * (0.86 * h) + t ** 2 * shoulder
        points.append((x, y))
    return points


def _band(art: pygame.Surface, colour, start: Point, end: Point, width: float) -> None:
    """A straight band between two points, as a polygon (thick lines leave notched ends)."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = max(1e-6, (dx * dx + dy * dy) ** 0.5)
    nx, ny = -dy / length * width / 2, dx / length * width / 2
    pygame.draw.polygon(art, colour, [(start[0] + nx, start[1] + ny), (end[0] + nx, end[1] + ny),
                                      (end[0] - nx, end[1] - ny), (start[0] - nx, start[1] - ny)])


def _pale(art, c, w, h):
    art.fill(c, (0.36 * w, 0, 0.28 * w, h))


def _fess(art, c, w, h):
    art.fill(c, (0, 0.27 * h, w, 0.22 * h))


def _bend(art, c, w, h):
    _band(art, c, (-0.1 * w, -0.08 * h), (1.05 * w, 0.92 * h), 0.26 * w)


def _chevron(art, c, w, h):
    _band(art, c, (0.5 * w, 0.26 * h), (-0.05 * w, 0.66 * h), 0.2 * w)
    _band(art, c, (0.5 * w, 0.26 * h), (1.05 * w, 0.66 * h), 0.2 * w)


def _cross(art, c, w, h):
    art.fill(c, (0.39 * w, 0, 0.22 * w, h))
    art.fill(c, (0, 0.27 * h, w, 0.18 * h))


def _saltire(art, c, w, h):
    _band(art, c, (-0.1 * w, -0.08 * h), (1.1 * w, 0.84 * h), 0.2 * w)
    _band(art, c, (1.1 * w, -0.08 * h), (-0.1 * w, 0.84 * h), 0.2 * w)


def _chief(art, c, w, h):
    art.fill(c, (0, 0, w, 0.3 * h))


def _roundel(art, c, w, h):
    pygame.draw.circle(art, c, (w / 2, 0.4 * h), 0.25 * w)


def _lozenge(art, c, w, h):
    cx, cy = w / 2, 0.42 * h
    pygame.draw.polygon(art, c, [(cx, cy - 0.27 * h), (cx + 0.26 * w, cy), (cx, cy + 0.27 * h), (cx - 0.26 * w, cy)])


def _bars(art, c, w, h):
    art.fill(c, (0, 0.18 * h, w, 0.13 * h))
    art.fill(c, (0, 0.44 * h, w, 0.13 * h))


def _quarterly(art, c, w, h):
    art.fill(c, (0, 0, w / 2, 0.45 * h))
    art.fill(c, (w / 2, 0.45 * h, w / 2, h))


def _bezants(art, c, w, h):
    for x, y in ((0.3, 0.24), (0.7, 0.24), (0.5, 0.56)):
        pygame.draw.circle(art, c, (x * w, y * h), 0.145 * w)
        pygame.draw.circle(art, INK, (x * w, y * h), 0.145 * w, max(1, round(0.02 * w)))


CHARGES: Dict[str, Callable] = {
    "pale": _pale, "fess": _fess, "bend": _bend, "chevron": _chevron, "cross": _cross,
    "saltire": _saltire, "chief": _chief, "roundel": _roundel, "lozenge": _lozenge,
    "bars": _bars, "quarterly": _quarterly, "bezants": _bezants,
}


def shield(size: Tuple[int, int], arms: Mapping[str, Any], lit: bool = True) -> pygame.Surface:
    """The arms on a shield of that size; greyed if not *lit* (somebody not there)."""
    key = (size, tuple(arms["field"]), arms["charge"], arms["metal"], lit)
    cached = _shields.get(key)
    if cached is not None:
        return cached
    k = _SUPERSAMPLE
    w, h = size[0] * k, size[1] * k
    outline = _outline(w, h)
    art = pygame.Surface((w, h), pygame.SRCALPHA)
    art.fill((*arms["field"], 255))
    CHARGES[arms["charge"]](art, (*METALS[arms["metal"]], 255), w, h)
    # A little light from the top left, as on a painted board
    shade = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.polygon(shade, (0, 0, 0, 46), [(w, 0), (w, h), (0.35 * w, h)])
    art.blit(shade, (0, 0))
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255), outline)
    art.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    pygame.draw.polygon(art, INK, outline, 2 * k)
    small = pygame.transform.smoothscale(art, size)
    if not lit:
        small = pygame.transform.grayscale(small)
        small.fill((255, 255, 255, 150), special_flags=pygame.BLEND_RGBA_MULT)
    _shields[key] = small
    return small


def draw_arms(surf: pygame.Surface, rect: pygame.Rect, arms: Mapping[str, Any], lit: bool = True) -> None:
    surf.blit(shield(rect.size, arms, lit), rect)
