"""What sits on the sheet rather than on the land: frame, title, compass,
scale, legend, names, the tooltip and the player's mark.

All of it is drawn in screen space each frame, so it stays crisp and the
same size at every zoom level.
"""

import math
from typing import Dict, List, Optional, Tuple

import pygame

from . import glyphs
from .style import (
    FONT_PLAIN, FONT_SCRIPT, FONT_TITLE, FRAME_BAND, FRAME_MARGIN, GOLD_INK, INK,
    INK_FADED, PAPER, RED_INK, ROAD_WASH, ROAD_WASH_ALPHA, SCALE_UNIT, SUBTITLE,
    TITLE, WATER_LINE, WATER_WASH,
)

_fonts: Dict[Tuple[str, int], pygame.font.Font] = {}
_texts: Dict[Tuple, pygame.Surface] = {}
_LIGHT_PAPER = (243, 233, 204)


def font(path: str, size: int) -> pygame.font.Font:
    key = (path, size)
    if key not in _fonts:
        _fonts[key] = pygame.font.Font(path, size)
    return _fonts[key]


def text(content: str, path: str, size: int, color, halo: bool = True, spaced: bool = False) -> pygame.Surface:
    """Rendered text, with a rim of paper around it so it reads over ink."""
    key = (content, path, size, color, halo, spaced)
    if key not in _texts:
        f = font(path, size)
        shown = " ".join(content) if spaced else content
        ink = f.render(shown, True, color)
        if not halo:
            _texts[key] = ink
        else:
            rim = f.render(shown, True, PAPER)
            out = pygame.Surface((ink.get_width() + 4, ink.get_height() + 4), pygame.SRCALPHA)
            for dx in (-2, -1, 0, 1, 2):
                for dy in (-2, -1, 0, 1, 2):
                    if abs(dx) + abs(dy) <= 3 and (dx or dy):
                        out.blit(rim, (2 + dx, 2 + dy))
            out.blit(ink, (2, 2))
            _texts[key] = out
    return _texts[key]


# --- Frame ---------------------------------------------------------------

def frame_inner(rect: pygame.Rect) -> pygame.Rect:
    """The part of the module inside the ruled frame, where the land shows."""
    edge = FRAME_MARGIN + 3 + FRAME_BAND + 1
    return rect.inflate(-2 * edge, -2 * edge)


def frame(screen: pygame.Surface, rect: pygame.Rect) -> None:
    """A heavy rule, a chequered band like a map's degree scale, a fine rule."""
    outer = rect.inflate(-2 * FRAME_MARGIN, -2 * FRAME_MARGIN)
    band = outer.inflate(-6, -6)
    inner = band.inflate(-2 * FRAME_BAND, -2 * FRAME_BAND)
    step = 26
    for i, x in enumerate(range(band.left, band.right, step)):
        if i % 2 == 0:
            w = min(step, band.right - x)
            pygame.draw.rect(screen, INK_FADED, (x, band.top, w, FRAME_BAND))
            pygame.draw.rect(screen, INK_FADED, (x, band.bottom - FRAME_BAND, w, FRAME_BAND))
    for i, y in enumerate(range(band.top, band.bottom, step)):
        if i % 2 == 0:
            h = min(step, band.bottom - y)
            pygame.draw.rect(screen, INK_FADED, (band.left, y, FRAME_BAND, h))
            pygame.draw.rect(screen, INK_FADED, (band.right - FRAME_BAND, y, FRAME_BAND, h))
    pygame.draw.rect(screen, INK, outer, 3)
    pygame.draw.rect(screen, INK, band, 1)
    pygame.draw.rect(screen, INK, inner.inflate(2, 2), 1)


# --- Cartouche -----------------------------------------------------------

def cartouche_rect(topleft: Tuple[int, int]) -> pygame.Rect:
    title = text(TITLE, FONT_TITLE, 36, INK, halo=False)
    sub = text(SUBTITLE, FONT_PLAIN, 17, INK_FADED, halo=False)
    w = max(title.get_width(), sub.get_width()) + 64
    h = title.get_height() + sub.get_height() + 36
    return pygame.Rect(topleft, (w, h))


def cartouche(screen: pygame.Surface, rect: pygame.Rect) -> None:
    """The title panel: a framed tablet with curled corners."""
    _panel(screen, rect)
    title = text(TITLE, FONT_TITLE, 36, INK, halo=False)
    sub = text(SUBTITLE, FONT_PLAIN, 17, INK_FADED, halo=False)
    y = rect.top + 12
    screen.blit(title, title.get_rect(midtop=(rect.centerx, y)))
    y += title.get_height() + 3
    # A rule with a lozenge in the middle between title and subtitle
    half = rect.width // 2 - 40
    pygame.draw.line(screen, INK_FADED, (rect.centerx - half, y), (rect.centerx - 8, y))
    pygame.draw.line(screen, INK_FADED, (rect.centerx + 8, y), (rect.centerx + half, y))
    pygame.draw.polygon(screen, INK, [(rect.centerx - 6, y), (rect.centerx, y - 4), (rect.centerx + 6, y), (rect.centerx, y + 4)])
    screen.blit(sub, sub.get_rect(midtop=(rect.centerx, y + 6)))


def _panel(screen: pygame.Surface, rect: pygame.Rect) -> None:
    """A tablet of lighter paper with a double rule and curled corners."""
    shadow = pygame.Surface(rect.size, pygame.SRCALPHA)
    shadow.fill((60, 40, 20, 50))
    screen.blit(shadow, rect.move(4, 4))
    pygame.draw.rect(screen, _LIGHT_PAPER, rect)
    pygame.draw.rect(screen, INK, rect, 2)
    pygame.draw.rect(screen, INK_FADED, rect.inflate(-10, -10), 1)
    for corner in (rect.topleft, rect.topright, rect.bottomleft, rect.bottomright):
        cx = corner[0] + (9 if corner[0] == rect.left else -9)
        cy = corner[1] + (9 if corner[1] == rect.top else -9)
        pygame.draw.circle(screen, _LIGHT_PAPER, (cx, cy), 7)
        pygame.draw.circle(screen, INK, (cx, cy), 7, 1)
        pygame.draw.circle(screen, INK, (cx, cy), 2)


# --- Compass rose --------------------------------------------------------

def compass(screen: pygame.Surface, center: Tuple[int, int], radius: int) -> None:
    """An eight-pointed rose with a ring of ticks, north marked."""
    cx, cy = center
    disc = pygame.Surface((2 * radius + 4, 2 * radius + 4), pygame.SRCALPHA)
    pygame.draw.circle(disc, (*_LIGHT_PAPER, 200), (radius + 2, radius + 2), radius)
    screen.blit(disc, (cx - radius - 2, cy - radius - 2))
    pygame.draw.circle(screen, INK, center, radius, 2)
    pygame.draw.circle(screen, INK_FADED, center, round(radius * 0.84), 1)
    for i in range(32):
        a = math.radians(i * 360 / 32)
        r0 = radius * (0.84 if i % 4 == 0 else 0.9)
        pygame.draw.line(screen, INK_FADED, (cx + math.cos(a) * r0, cy + math.sin(a) * r0),
                         (cx + math.cos(a) * radius, cy + math.sin(a) * radius))

    def point(angle_deg: float, length: float, width: float, north: bool = False) -> None:
        a = math.radians(angle_deg)
        tip = (cx + math.cos(a) * length, cy + math.sin(a) * length)
        left = (cx + math.cos(a - math.pi / 2) * width, cy + math.sin(a - math.pi / 2) * width)
        right = (cx + math.cos(a + math.pi / 2) * width, cy + math.sin(a + math.pi / 2) * width)
        pygame.draw.polygon(screen, RED_INK if north else INK, [center, tip, left])
        pygame.draw.polygon(screen, _LIGHT_PAPER, [center, tip, right])
        pygame.draw.polygon(screen, INK, [left, tip, right, center], 1)

    for angle in (45, 135, 225, 315):
        point(angle, radius * 0.62, radius * 0.11)
    for angle in (0, 90, 180, 270):
        point(angle, radius * 0.96, radius * 0.17, north=(angle == 270))
    pygame.draw.circle(screen, _LIGHT_PAPER, center, max(2, radius // 12))
    pygame.draw.circle(screen, INK, center, max(2, radius // 12), 1)

    letter = text("N", FONT_PLAIN, max(16, radius // 2), INK)
    screen.blit(letter, letter.get_rect(midbottom=(cx, cy - radius + 1)))


# --- Scale bar -----------------------------------------------------------

def scale_bar_rect(bottomleft: Tuple[int, int], px_per_tile: float) -> pygame.Rect:
    paces, _ = _scale_length(px_per_tile)
    return pygame.Rect(bottomleft[0], bottomleft[1] - 40, round(paces * px_per_tile) + 70, 40)


def scale_bar(screen: pygame.Surface, bottomleft: Tuple[int, int], px_per_tile: float) -> None:
    """Alternating black and white segments, labelled in paces."""
    paces, parts = _scale_length(px_per_tile)
    length = paces * px_per_tile
    x0, y0 = bottomleft[0] + 6, bottomleft[1] - 14
    bar_h = 6
    seg = length / parts
    for i in range(parts):
        r = pygame.Rect(round(x0 + i * seg), y0, round(seg), bar_h)
        if i % 2 == 0:
            pygame.draw.rect(screen, INK, r)
        else:
            pygame.draw.rect(screen, _LIGHT_PAPER, r)
    pygame.draw.rect(screen, INK, (x0, y0, round(length), bar_h), 1)
    for i, value in ((0, 0), (parts // 2, paces // 2), (parts, paces)):
        x = round(x0 + i * seg)
        pygame.draw.line(screen, INK, (x, y0 - 3), (x, y0 + bar_h))
        label = text(str(value), FONT_PLAIN, 15, INK)
        screen.blit(label, label.get_rect(midbottom=(x, y0 - 2)))
    unit = text(SCALE_UNIT, FONT_PLAIN, 15, INK)
    screen.blit(unit, unit.get_rect(midleft=(x0 + round(length) + 8, y0 + bar_h // 2)))


def _scale_length(px_per_tile: float) -> Tuple[int, int]:
    """A round number of paces that makes a bar of a sensible length."""
    for paces in (10, 20, 40, 50, 100, 200):
        if paces * px_per_tile >= 110:
            return paces, 4
    return 200, 4


# --- Legend --------------------------------------------------------------

LEGEND_ROWS = ("Dwelling", "Market stall", "Your property", "Road", "Water", "Wood", "Field", "You are here")


def legend_size() -> Tuple[int, int]:
    return 210, 50 + 26 * len(LEGEND_ROWS)


def legend(screen: pygame.Surface, rect: pygame.Rect) -> None:
    """The key to the plan's symbols, each drawn the way the plan draws it."""
    _panel(screen, rect)
    heading = text("Legend", FONT_SCRIPT, 26, INK, halo=False)
    screen.blit(heading, heading.get_rect(midtop=(rect.centerx, rect.top + 8)))
    y = rect.top + 46
    for row in LEGEND_ROWS:
        sample = pygame.Rect(rect.left + 18, y + 3, 40, 16)
        _legend_sample(screen, row, sample)
        label = text(row, FONT_PLAIN, 17, INK, halo=False)
        screen.blit(label, label.get_rect(midleft=(sample.right + 14, sample.centery)))
        y += 26


def _legend_sample(screen: pygame.Surface, row: str, r: pygame.Rect) -> None:
    if row == "Dwelling":
        glyphs.roof(screen, r)
    elif row == "Market stall":
        glyphs.stall(screen, r.inflate(-8, -2))
    elif row == "Your property":
        glyphs.roof(screen, r, color=(150, 104, 70))
        pygame.draw.rect(screen, GOLD_INK, r.inflate(6, 6), 2)
    elif row == "Road":
        glyphs.wash_rect(screen, ROAD_WASH, ROAD_WASH_ALPHA, r)
        pygame.draw.line(screen, INK_FADED, r.topleft, r.topright)
        pygame.draw.line(screen, INK_FADED, r.bottomleft, r.bottomright)
    elif row == "Water":
        glyphs.wash_rect(screen, WATER_WASH, 160, r)
        for yy in range(r.top + 3, r.bottom, 4):
            pygame.draw.line(screen, WATER_LINE, (r.left + 2, yy), (r.right - 3, yy))
        pygame.draw.rect(screen, INK, r, 1)
    elif row == "Wood":
        for i, x in enumerate((r.left + 7, r.centerx, r.right - 7)):
            glyphs.conifer(screen, x, r.bottom + 2, 18 if i == 1 else 14)
    elif row == "Field":
        glyphs.field(screen, r, spacing=4)
    elif row == "You are here":
        player_mark(screen, r.center, 0.0)


# --- Marks and labels ----------------------------------------------------

def player_mark(screen: pygame.Surface, pos: Tuple[float, float], seconds: float) -> None:
    """A red dot in a ring that slowly widens, so the eye finds it at once."""
    x, y = round(pos[0]), round(pos[1])
    phase = (seconds % 1.8) / 1.8
    ring_r = 6 + phase * 14
    ring = pygame.Surface((48, 48), pygame.SRCALPHA)
    pygame.draw.circle(ring, (*RED_INK, int(200 * (1 - phase))), (24, 24), round(ring_r), 2)
    screen.blit(ring, (x - 24, y - 24))
    pygame.draw.circle(screen, _LIGHT_PAPER, (x, y), 7)
    pygame.draw.circle(screen, RED_INK, (x, y), 5)
    pygame.draw.circle(screen, INK, (x, y), 7, 1)


def neat_line(screen: pygame.Surface, land: pygame.Rect) -> None:
    """The ruled line round the surveyed land, where the plan's knowledge ends."""
    pygame.draw.rect(screen, INK_FADED, land.inflate(8, 8), 1)
    pygame.draw.rect(screen, INK, land.inflate(2, 2), 1)


def dashed_rect(screen: pygame.Surface, rect: pygame.Rect, color, dash: int = 6) -> None:
    for x in range(rect.left, rect.right, dash * 2):
        end = min(x + dash, rect.right)
        pygame.draw.line(screen, color, (x, rect.top), (end, rect.top), 2)
        pygame.draw.line(screen, color, (x, rect.bottom), (end, rect.bottom), 2)
    for y in range(rect.top, rect.bottom, dash * 2):
        end = min(y + dash, rect.bottom)
        pygame.draw.line(screen, color, (rect.left, y), (rect.left, end), 2)
        pygame.draw.line(screen, color, (rect.right, y), (rect.right, end), 2)


def place_label(screen: pygame.Surface, surface: pygame.Surface, anchors: List[Tuple[str, Tuple[float, float]]],
                taken: List[pygame.Rect], bounds: pygame.Rect) -> Optional[pygame.Rect]:
    """Write a name at the first of its anchor spots where it overlaps nothing.

    Args:
        anchors: (rect attribute, point) pairs to try in turn, e.g. ("midtop", (x, y)).
        taken: Rects already written on; the placed label is added.
        bounds: The label must lie wholly inside this.
    """
    for attribute, point in anchors:
        r = surface.get_rect(**{attribute: (round(point[0]), round(point[1]))})
        if bounds.contains(r) and r.collidelist(taken) < 0:
            screen.blit(surface, r)
            taken.append(r.inflate(4, 2))
            return r
    return None


def tooltip(screen: pygame.Surface, pos: Tuple[int, int], title: str, detail: str, bounds: pygame.Rect) -> None:
    """A small slip of paper by the cursor naming what is under it."""
    head = text(title, FONT_PLAIN, 19, INK, halo=False)
    lines = [head]
    if detail:
        lines.append(text(detail, FONT_PLAIN, 15, INK_FADED, halo=False))
    w = max(s.get_width() for s in lines) + 20
    h = sum(s.get_height() for s in lines) + 12
    r = pygame.Rect(pos[0] + 18, pos[1] + 14, w, h)
    if r.right > bounds.right:
        r.right = pos[0] - 10
    if r.bottom > bounds.bottom:
        r.bottom = pos[1] - 10
    shadow = pygame.Surface(r.size, pygame.SRCALPHA)
    shadow.fill((60, 40, 20, 60))
    screen.blit(shadow, r.move(3, 3))
    pygame.draw.rect(screen, _LIGHT_PAPER, r)
    pygame.draw.rect(screen, INK, r, 1)
    y = r.top + 6
    for s in lines:
        screen.blit(s, (r.left + 10, y))
        y += s.get_height()


def hint(screen: pygame.Surface, inner: pygame.Rect) -> pygame.Rect:
    """How to work the plan, in small faded letters along its foot."""
    s = text("Mouse wheel: zoom      Drag: move", FONT_PLAIN, 15, INK_FADED)
    r = s.get_rect(midbottom=(inner.centerx, inner.bottom - 4))
    screen.blit(s, r)
    return r
