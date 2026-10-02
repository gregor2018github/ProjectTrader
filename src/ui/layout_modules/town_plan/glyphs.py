"""The little drawings a town plan is made of: roofs, trees, fields, stalls.

Each draws at any size into any surface, so the plan's engraving and the
legend's samples are the same drawings. Washes are blended in (they are
watercolour over whatever lies below); strokes are drawn opaque (they are ink).
"""

import math
from typing import Sequence, Tuple

import pygame

from .style import (
    FIELD_WASH, FIELD_WASH_ALPHA, INK, INK_FADED, ROOF_WASH, ROOF_WASH_ALPHA,
    SHADOW, SHADOW_ALPHA, STALL_WASH, TREE_WASH, WATER_LINE, WATER_WASH,
)

Point = Tuple[float, float]


def wash_rect(surface: pygame.Surface, color: Tuple[int, int, int], alpha: int, rect: pygame.Rect) -> None:
    """Lay a translucent wash over ``rect``, blending with what is below."""
    if rect.width <= 0 or rect.height <= 0:
        return
    wash = pygame.Surface(rect.size, pygame.SRCALPHA)
    wash.fill((*color, alpha))
    surface.blit(wash, rect.topleft)


def wash_polygon(surface: pygame.Surface, color: Tuple[int, int, int], alpha: int, points: Sequence[Point]) -> None:
    """Lay a translucent wash over a polygon."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    left, top = int(min(xs)) - 1, int(min(ys)) - 1
    w, h = int(max(xs)) - left + 2, int(max(ys)) - top + 2
    if w <= 0 or h <= 0:
        return
    wash = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.polygon(wash, (*color, alpha), [(x - left, y - top) for x, y in points])
    surface.blit(wash, (left, top))


def roof(surface: pygame.Surface, rect: pygame.Rect, color: Tuple[int, int, int] = ROOF_WASH) -> None:
    """A building seen from above: a hipped roof with its ridge and shadow."""
    if rect.width < 2 or rect.height < 2:
        return
    drop = max(1, round(min(rect.width, rect.height) * 0.14))
    wash_rect(surface, SHADOW, SHADOW_ALPHA, rect.move(drop, drop))
    wash_rect(surface, color, ROOF_WASH_ALPHA, rect)

    # Ridge along the long side, hips running from its ends to the corners
    if rect.width >= rect.height:
        half = rect.height / 2
        a = (rect.left + half, rect.centery)
        b = (max(rect.left + half, rect.right - half), rect.centery)
        hips = ((rect.topleft, a), (rect.bottomleft, a), (rect.topright, b), (rect.bottomright, b))
        shaded = [rect.bottomleft, a, b, rect.bottomright]
    else:
        half = rect.width / 2
        a = (rect.centerx, rect.top + half)
        b = (rect.centerx, max(rect.top + half, rect.bottom - half))
        hips = ((rect.topleft, a), (rect.topright, a), (rect.bottomleft, b), (rect.bottomright, b))
        shaded = [rect.topright, a, b, rect.bottomright]

    # The slope turned from the light is hatched
    if min(rect.width, rect.height) >= 9:
        _hatch_polygon(surface, shaded, spacing=3, color=INK_FADED)
    else:
        wash_polygon(surface, SHADOW, SHADOW_ALPHA, shaded)

    if min(rect.width, rect.height) >= 6:
        pygame.draw.line(surface, INK_FADED, a, b)
        for corner, end in hips:
            pygame.draw.line(surface, INK_FADED, corner, end)
    pygame.draw.rect(surface, INK, rect, 2 if min(rect.width, rect.height) >= 14 else 1)


def conifer(surface: pygame.Surface, x: float, y: float, height: float) -> None:
    """A fir tree standing on its foot at (x, y), as old maps draw woods."""
    height = max(4.0, height)
    width = height * 0.62
    trunk = height * 0.16
    top = y - height
    crown = height - trunk

    _ground_shadow(surface, x, y, width)

    tiers = 3 if height >= 14 else (2 if height >= 8 else 1)
    left_side, right_side = [], []
    for i in range(tiers):
        bottom = top + crown * (i + 1) / tiers
        reach = width / 2 * (0.55 + 0.45 * (i + 1) / tiers)
        left_side.append((x - reach, bottom))
        right_side.append((x + reach, bottom))
        if i < tiers - 1:
            left_side.append((x - reach * 0.5, bottom))
            right_side.append((x + reach * 0.5, bottom))
    outline = [(x, top)] + right_side + [(x, top + crown)] + left_side[::-1]

    pygame.draw.polygon(surface, TREE_WASH, outline)
    shade = [(x, top)] + right_side + [(x, top + crown)]
    pygame.draw.polygon(surface, _darker(TREE_WASH, 0.72), shade)
    pygame.draw.line(surface, INK, (x, top + crown), (x, y), 2 if height >= 16 else 1)
    pygame.draw.polygon(surface, INK, outline, 1)


def broadleaf(surface: pygame.Surface, x: float, y: float, height: float) -> None:
    """A round-crowned tree standing on its foot at (x, y)."""
    height = max(4.0, height)
    radius = max(2, round(height * 0.32))
    cx, cy = x, y - height + radius
    _ground_shadow(surface, x, y, radius * 2)
    pygame.draw.line(surface, INK, (x, cy), (x, y), 2 if height >= 16 else 1)
    pygame.draw.circle(surface, TREE_WASH, (round(cx), round(cy)), radius)
    pygame.draw.circle(surface, _darker(TREE_WASH, 0.72), (round(cx + radius * 0.35), round(cy + radius * 0.3)),
                       max(1, round(radius * 0.6)))
    pygame.draw.circle(surface, INK, (round(cx), round(cy)), radius, 1)


def field(surface: pygame.Surface, rect: pygame.Rect, spacing: int = 4) -> None:
    """A ploughed field: a wash, its furrows and its hedge line."""
    wash_rect(surface, FIELD_WASH, FIELD_WASH_ALPHA, rect)
    old_clip = surface.get_clip()
    surface.set_clip(rect.clip(old_clip) if old_clip else rect)
    for offset in range(-rect.height, rect.width, max(2, spacing)):
        start = (rect.left + offset, rect.bottom)
        end = (rect.left + offset + rect.height * 0.5, rect.top)
        pygame.draw.line(surface, INK_FADED, start, end)
    surface.set_clip(old_clip)
    pygame.draw.rect(surface, INK_FADED, rect, 1)


def stall(surface: pygame.Surface, rect: pygame.Rect) -> None:
    """A market stall: a striped awning."""
    wash_rect(surface, STALL_WASH, 230, rect)
    step = max(2, rect.width // 5)
    for sx in range(rect.left + step, rect.right - 1, step * 2):
        stripe = pygame.Rect(sx, rect.top, step, rect.height)
        wash_rect(surface, ROOF_WASH, 110, stripe.clip(rect))
    pygame.draw.rect(surface, INK, rect, 1)


def well(surface: pygame.Surface, center: Point, radius: float) -> None:
    """A well: a ring of stone with water in it."""
    r = max(2, round(radius))
    c = (round(center[0]), round(center[1]))
    pygame.draw.circle(surface, WATER_WASH, c, r)
    pygame.draw.circle(surface, INK, c, r, 2 if r >= 6 else 1)
    if r >= 5:
        pygame.draw.circle(surface, WATER_LINE, c, max(1, r // 2), 1)


def mill_sails(surface: pygame.Surface, center: Point, length: float) -> None:
    """The four sails of a windmill, turned a little off the square."""
    if length < 3:
        return
    cx, cy = center
    width = 2 if length >= 12 else 1
    for i in range(4):
        angle = math.radians(20 + 90 * i)
        dx, dy = math.cos(angle), math.sin(angle)
        tip = (cx + dx * length, cy + dy * length)
        pygame.draw.line(surface, INK, center, tip, width)
        # The sail cloth along the trailing side of each arm
        nx, ny = -dy * length * 0.22, dx * length * 0.22
        cloth = [
            (cx + dx * length * 0.3, cy + dy * length * 0.3),
            tip,
            (tip[0] + nx, tip[1] + ny),
            (cx + dx * length * 0.3 + nx, cy + dy * length * 0.3 + ny),
        ]
        pygame.draw.polygon(surface, (238, 226, 196), cloth)
        pygame.draw.polygon(surface, INK, cloth, 1)
    pygame.draw.circle(surface, INK, (round(cx), round(cy)), max(2, round(length * 0.12)))


def cross(surface: pygame.Surface, center: Point, size: float, color: Tuple[int, int, int] = INK) -> None:
    """A church cross, ``size`` tall."""
    if size < 4:
        return
    cx, cy = center
    width = max(1, round(size / 6))
    pygame.draw.line(surface, color, (cx, cy - size / 2), (cx, cy + size / 2), width)
    pygame.draw.line(surface, color, (cx - size * 0.32, cy - size * 0.18), (cx + size * 0.32, cy - size * 0.18), width)


def palisade(surface: pygame.Surface, start: Point, end: Point, tick: float) -> None:
    """A fence: a line with short posts across it."""
    pygame.draw.line(surface, INK, start, end, 1)
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    if length < 1 or tick < 1.5:
        return
    dx, dy = (end[0] - start[0]) / length, (end[1] - start[1]) / length
    step = max(3.0, tick * 1.6)
    d = 0.0
    while d <= length:
        px, py = start[0] + dx * d, start[1] + dy * d
        pygame.draw.line(surface, INK, (px + dy * tick, py - dx * tick), (px - dy * tick * 0.4, py + dx * tick * 0.4))
        d += step


def grass_tuft(surface: pygame.Surface, x: float, y: float, size: float) -> None:
    """Three short strokes of grass."""
    for lean in (-0.5, 0.0, 0.5):
        pygame.draw.line(surface, INK_FADED, (x + lean * size * 0.4, y), (x + lean * size, y - size))


def wavelet(surface: pygame.Surface, x: float, y: float, size: float) -> None:
    """A little wave mark on open water."""
    w = max(4, round(size * 2))
    h = max(2, round(size))
    for i in range(2):
        rect = pygame.Rect(round(x - w + i * w), round(y), w, h)
        pygame.draw.arc(surface, WATER_LINE, rect, 0, math.pi, 1)


def ship(surface: pygame.Surface, x: float, y: float, size: float) -> None:
    """A cog under sail, ``size`` long."""
    if size < 8:
        return
    hull = [(x - size / 2, y - size * 0.12), (x + size / 2, y - size * 0.12),
            (x + size * 0.36, y + size * 0.12), (x - size * 0.36, y + size * 0.12)]
    pygame.draw.polygon(surface, (150, 108, 66), hull)
    pygame.draw.polygon(surface, INK, hull, 1)
    mast_top = (x, y - size * 0.75)
    pygame.draw.line(surface, INK, (x, y - size * 0.12), mast_top, 1)
    sail = pygame.Rect(0, 0, round(size * 0.46), round(size * 0.42))
    sail.midtop = (round(x), round(y - size * 0.68))
    pygame.draw.ellipse(surface, (240, 230, 206), sail)
    pygame.draw.ellipse(surface, INK, sail, 1)
    pygame.draw.line(surface, RED_PENNANT, mast_top, (x + size * 0.18, mast_top[1] + size * 0.05), 2)
    for i in range(3):
        wavelet(surface, x - size * 0.5 + i * size * 0.4, y + size * 0.18, size * 0.1)


RED_PENNANT = (150, 40, 30)


def _ground_shadow(surface: pygame.Surface, x: float, y: float, width: float) -> None:
    w = max(3, round(width * 0.9))
    h = max(2, round(width * 0.3))
    shadow = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (*SHADOW, SHADOW_ALPHA), shadow.get_rect())
    surface.blit(shadow, (round(x - w * 0.25), round(y - h * 0.6)))


def _hatch_polygon(surface: pygame.Surface, points: Sequence[Point], spacing: int, color: Tuple[int, int, int]) -> None:
    """Diagonal hatching inside a polygon."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    left, top = int(min(xs)), int(min(ys))
    w, h = int(math.ceil(max(xs))) - left + 1, int(math.ceil(max(ys))) - top + 1
    if w <= 1 or h <= 1:
        return
    shape = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.polygon(shape, (255, 255, 255, 255), [(px - left, py - top) for px, py in points])
    lines = pygame.Surface((w, h), pygame.SRCALPHA)
    for offset in range(-h, w, spacing):
        pygame.draw.line(lines, (*color, 255), (offset, h), (offset + h, 0))
    # Keep the lines only where the polygon is
    lines.blit(shape, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surface.blit(lines, (left, top))


def _darker(color: Tuple[int, int, int], factor: float) -> Tuple[int, int, int]:
    return tuple(int(c * factor) for c in color)
