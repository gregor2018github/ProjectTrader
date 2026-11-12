"""The council's sheets drawn as an official charter: browned parchment in ruled borders of
iron-gall ink and sepia, square corner blocks with a quatrefoil in each, tabs and buttons of
dull leather and parchment, a dark ochre for what the records' pages gild, and an oxblood red
for what a clerk would write in red. The town council's window and the session's sheet use it;
the minigames' how-to pages and the records keep their gold (``tutorial_sheet.py``).
"""

from typing import Sequence, Tuple

import pygame

from ..paper import draw_paper

INK = (40, 30, 22)                  # iron-gall ink
FAINT_INK = (112, 96, 76)
OXBLOOD = (120, 42, 34)             # the clerk's red ink, for emphasis and what goes against one
GOOD_INK = (56, 88, 50)             # a dark, settled green
SEPIA = (112, 82, 50)               # the rules
SEPIA_DARK = (74, 52, 32)
OCHRE = (158, 122, 66)              # the ornaments' dull gold
LEATHER = (92, 66, 44)
PAPER_DEEP = (222, 204, 164)        # the ground of the corner blocks and plates
PAPER_LIGHT = (238, 226, 196)

BUTTON_FILL, BUTTON_HOVER = (206, 186, 146), (222, 204, 166)
DISABLED = ((214, 202, 174), (170, 152, 122), (150, 134, 108))   # fill, edge, ink
TAB_FILL, TAB_HOVER = (214, 196, 158), (228, 212, 178)

_OUTER = 5                          # the dark band round the sheet
_HAIRLINE = 9                       # the thin rule inside it
_DOUBLE = (15, 19)                  # the double rule, its heavy line and its light one
_BLOCK = (7, 41)                    # a corner block spans these insets
_SUPERSAMPLE = 4


def _smooth(size: Tuple[int, int], draw) -> pygame.Surface:
    """An ornament drawn large by *draw(surface, k)* and smoothed down to *size*."""
    k = _SUPERSAMPLE
    art = pygame.Surface((size[0] * k, size[1] * k), pygame.SRCALPHA)
    draw(art, k)
    return pygame.transform.smoothscale(art, size)


def _quatrefoil(art: pygame.Surface, k: int, centre: Tuple[float, float], reach: float) -> None:
    """Four round lobes about a point, reaching *reach* from it, in ochre ruled with sepia, a red
    boss in the middle."""
    cx, cy = centre
    offset = reach / 1.7
    radius = offset * 0.7
    lobes = [(cx + dx * offset, cy + dy * offset) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
    for x, y in lobes:
        pygame.draw.circle(art, SEPIA_DARK, (x, y), radius + k)
    for x, y in lobes:
        pygame.draw.circle(art, OCHRE, (x, y), radius)
    pygame.draw.circle(art, SEPIA_DARK, (cx, cy), radius * 0.72 + k)
    pygame.draw.circle(art, OXBLOOD, (cx, cy), radius * 0.72)


def _corner_block(side: int) -> pygame.Surface:
    """A square block where the borders meet: two ruled squares, a lozenge and a quatrefoil in it."""
    def draw(art: pygame.Surface, k: int) -> None:
        s = side * k
        art.fill(PAPER_DEEP)
        pygame.draw.rect(art, SEPIA_DARK, (0, 0, s, s), 2 * k)
        pygame.draw.rect(art, SEPIA, (4 * k, 4 * k, s - 8 * k, s - 8 * k), k)
        inner, spur = 4 * k, 7 * k          # a small sepia spandrel in each corner of the inner square
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            x = inner if sx > 0 else s - inner
            y = inner if sy > 0 else s - inner
            pygame.draw.polygon(art, SEPIA, [(x, y), (x + sx * spur, y), (x, y + sy * spur)])
        c = s / 2
        r = s / 2 - 6 * k
        pygame.draw.polygon(art, PAPER_LIGHT, [(c, c - r), (c + r, c), (c, c + r), (c - r, c)])
        pygame.draw.polygon(art, SEPIA_DARK, [(c, c - r), (c + r, c), (c, c + r), (c - r, c)], k)
        _quatrefoil(art, k, (c, c), r * 0.74)
    return _smooth((side, side), draw)


def _side_boss(width: int, height: int) -> pygame.Surface:
    """The ornament in the middle of each side: a lozenge with a red boss, a smaller one each side."""
    def draw(art: pygame.Surface, k: int) -> None:
        w, h = width * k, height * k
        cx, cy = w / 2, h / 2
        for x, r in ((cx, h * 0.46), (cx - w * 0.3, h * 0.24), (cx + w * 0.3, h * 0.24)):
            points = [(x, cy - r), (x + r, cy), (x, cy + r), (x - r, cy)]
            pygame.draw.polygon(art, OCHRE, points)
            pygame.draw.polygon(art, SEPIA_DARK, points, k)
        pygame.draw.circle(art, SEPIA_DARK, (cx, cy), h * 0.15 + k)
        pygame.draw.circle(art, OXBLOOD, (cx, cy), h * 0.15)
    return _smooth((width, height), draw)


def charter_sheet(size: Tuple[int, int]) -> pygame.Surface:
    """A blank sheet: parchment in a dark band, a hairline and a double rule, the rules meeting in
    corner blocks, and an ornament in the middle of each side."""
    page = pygame.Surface(size)
    sheet = page.get_rect()
    draw_paper(page, sheet, sheet.topleft)
    pygame.draw.rect(page, SEPIA_DARK, sheet, _OUTER)
    pygame.draw.rect(page, SEPIA, sheet.inflate(-2 * _HAIRLINE, -2 * _HAIRLINE), 1)
    heavy, light = _DOUBLE
    pygame.draw.rect(page, SEPIA_DARK, sheet.inflate(-2 * heavy, -2 * heavy), 2)
    pygame.draw.rect(page, SEPIA, sheet.inflate(-2 * light, -2 * light), 1)

    side = _BLOCK[1] - _BLOCK[0]
    block = _corner_block(side)
    near, far_x, far_y = _BLOCK[0], sheet.width - _BLOCK[1], sheet.height - _BLOCK[1]
    for x, y in ((near, near), (far_x, near), (near, far_y), (far_x, far_y)):
        page.blit(block, (x, y))

    middle = (heavy + light) / 2
    across = _side_boss(54, 18)
    upright = pygame.transform.rotate(across, 90)
    for x, y, art in ((sheet.centerx, middle, across), (sheet.centerx, sheet.height - middle, across),
                      (middle, sheet.centery, upright), (sheet.width - middle, sheet.centery, upright)):
        page.blit(art, art.get_rect(center=(round(x), round(y))))
    return page


def charter_title(text: str, font: pygame.font.Font) -> pygame.Surface:
    """A sheet's title in ink, its first letter in red as a clerk would write it."""
    first, rest = text[:1], text[1:]
    initial = font.render(first, True, OXBLOOD)
    tail = font.render(rest, True, INK)
    label = pygame.Surface((initial.get_width() + tail.get_width(), max(initial.get_height(), tail.get_height())),
                           pygame.SRCALPHA)
    label.blit(initial, (0, 0))
    label.blit(tail, (initial.get_width(), 0))
    return label


def draw_rule(surf: pygame.Surface, centre: Tuple[int, int], half: int) -> None:
    """A double rule with a small lozenge in its middle and a dot at each end, under a title."""
    x, y = centre
    for dy, colour in ((-1, SEPIA_DARK), (2, SEPIA)):
        pygame.draw.line(surf, colour, (x - half, y + dy), (x - 11, y + dy), 1)
        pygame.draw.line(surf, colour, (x + 11, y + dy), (x + half, y + dy), 1)
    points = [(x, y - 6), (x + 7, y), (x, y + 6), (x - 7, y)]
    pygame.draw.polygon(surf, OCHRE, points)
    pygame.draw.polygon(surf, SEPIA_DARK, points, 1)
    pygame.draw.circle(surf, OXBLOOD, (x, y), 2)
    for dx in (-half - 4, half + 4):
        pygame.draw.circle(surf, SEPIA_DARK, (x + dx, y), 2)


def draw_leaf(surf: pygame.Surface, rect: pygame.Rect) -> None:
    """A paler panel on the sheet, ruled with a line and a hairline inside it."""
    wash = pygame.Surface(rect.size, pygame.SRCALPHA)
    wash.fill((250, 242, 220, 84))
    surf.blit(wash, rect)
    pygame.draw.rect(surf, SEPIA, rect, 1)
    pygame.draw.rect(surf, (178, 154, 114), rect.inflate(-6, -6), 1)


def draw_button(surf: pygame.Surface, rect: pygame.Rect, label: str, font: pygame.font.Font, hovered: bool,
                enabled: bool = True) -> None:
    """A parchment plate ruled in sepia; faded while it cannot be pressed."""
    if enabled:
        fill, edge, ink = BUTTON_HOVER if hovered else BUTTON_FILL, SEPIA_DARK, INK
    else:
        fill, edge, ink = DISABLED
    pygame.draw.rect(surf, fill, rect, border_radius=2)
    pygame.draw.rect(surf, edge, rect, 2, border_radius=2)
    if enabled:
        pygame.draw.rect(surf, (170, 142, 100), rect.inflate(-8, -8), 1)
    text = font.render(label, True, ink)
    surf.blit(text, text.get_rect(center=rect.center))


def draw_tab(surf: pygame.Surface, rect: pygame.Rect, label: str, font: pygame.font.Font, current: bool,
             hovered: bool) -> None:
    """A page's tab: dark leather for the page shown, parchment for the others."""
    if current:
        fill, edge, ink = LEATHER, SEPIA_DARK, PAPER_LIGHT
    else:
        fill, edge, ink = TAB_HOVER if hovered else TAB_FILL, SEPIA, INK
    pygame.draw.rect(surf, fill, rect, border_radius=2)
    pygame.draw.rect(surf, edge, rect, 2, border_radius=2)
    if current:
        pygame.draw.rect(surf, OCHRE, rect.inflate(-6, -6), 1)
    text = font.render(label, True, ink)
    surf.blit(text, text.get_rect(center=rect.center))


def cartouche(surf: pygame.Surface, font: pygame.font.Font, text: str, center: Tuple[float, float],
              colour=INK) -> pygame.Rect:
    """A small ruled plate with a line of text, a lozenge at each end."""
    label = font.render(text, True, colour)
    rect = label.get_rect(center=center).inflate(38, 8)
    pygame.draw.rect(surf, PAPER_DEEP, rect)
    pygame.draw.rect(surf, SEPIA, rect, 1)
    pygame.draw.rect(surf, (178, 154, 114), rect.inflate(-4, -4), 1)
    for x in (rect.left + 9, rect.right - 10):
        y = rect.centery
        pygame.draw.polygon(surf, OCHRE, [(x, y - 4), (x + 4, y), (x, y + 4), (x - 4, y)])
    surf.blit(label, label.get_rect(center=rect.center))
    return rect


def draw_lozenges(surf: pygame.Surface, centre: Tuple[int, int], count: int) -> None:
    """A tier as ochre lozenges in a row."""
    x = centre[0] - (count - 1) * 8
    for i in range(count):
        cx = x + i * 16
        points: Sequence[Tuple[int, int]] = [(cx, centre[1] - 7), (cx + 6, centre[1]), (cx, centre[1] + 7),
                                             (cx - 6, centre[1])]
        pygame.draw.polygon(surf, OCHRE, points)
        pygame.draw.polygon(surf, SEPIA_DARK, points, 1)


def draw_close(surf: pygame.Surface, rect: pygame.Rect, hovered: bool) -> None:
    """The close button: a leather square with a parchment cross."""
    pygame.draw.rect(surf, (122, 90, 60) if hovered else LEATHER, rect, border_radius=2)
    pygame.draw.rect(surf, SEPIA_DARK, rect, 2, border_radius=2)
    inset = 9
    for start, end in (((rect.left + inset, rect.top + inset), (rect.right - inset - 1, rect.bottom - inset - 1)),
                       ((rect.left + inset, rect.bottom - inset - 1), (rect.right - inset - 1, rect.top + inset))):
        pygame.draw.line(surf, PAPER_LIGHT, start, end, 3)
