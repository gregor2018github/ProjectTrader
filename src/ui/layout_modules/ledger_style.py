"""The depot view's look: the counting house, green baize and brass on parchment.

The guild's records' sheets (``records_window.py``) in a theme of their own, ``COUNTING_HOUSE``:
the frame's band is the chequered cloth of an exchequer's counting table, its strands baize and
brass, in the slimmer, quieter frame (``SLIM_FRAME``) so the figures have the sheet to themselves. Shared by the depot's charts (``depot_view_chart.py``) and its list (``depot_view.py``):
the fonts, the framed sheets (made once per size and title, as they take a while), a parchment
note for tooltips and the small things drawn on the sheets.
"""

import os
from typing import Dict, List, Optional, Sequence, Tuple

import pygame

from ..helper_modules.charter_style import BlockColours
from ..helper_modules.records_window import PageTheme, _divider, _leaf, _tab, _title
from ..paper import draw_paper
from ...config.constants import FONTS_PATH
from ...models.minigames.tutorial_sheet import (
    BRASS, BRASS_DARK, BRASS_LIGHT, CHEQUER, INK, RUBRIC, SLIM_FRAME, SheetTheme, framed_sheet, title_tablet,
)

__all__ = ["COUNTING_HOUSE", "INK", "FAINT_INK", "RULE", "GAIN_INK", "LOSS_INK", "font", "sheet",
           "note", "divider", "leaf", "tab", "small_tab", "faded", "blend", "BRASS", "BRASS_DARK", "BRASS_LIGHT",
           "RUBRIC"]

Colour = Tuple[int, int, int]

FAINT_INK = (120, 104, 84)              # labels, axes, what has no value
RULE = (196, 176, 136)                  # a grid's lines
PAPER = (232, 216, 178)                 # about what the parchment is, for fading marks into it
GAIN_INK, LOSS_INK = (40, 110, 58), (150, 44, 34)

_BAIZE, _BAIZE_DEEP, _BAIZE_RULE = (40, 86, 58), (22, 52, 34), (52, 96, 66)

COUNTING_HOUSE = PageTheme(
    sheet=SheetTheme(edge_dark=_BAIZE_DEEP, edge_light=(104, 146, 106), rule=_BAIZE_RULE,
                     band_wash=(84, 132, 92, 44), strands=(_BAIZE, BRASS_DARK),
                     bead_dark=_BAIZE_DEEP, bead_light=BRASS_LIGHT,
                     block=BlockColours(edge=_BAIZE_DEEP, rule=_BAIZE_RULE, ornament=BRASS, boss=RUBRIC),
                     texture=CHEQUER, texture_colour=(28, 66, 40, 40)),
    title=(BRASS_LIGHT, (126, 88, 26)), accent=BRASS, accent_dark=BRASS_DARK, accent_light=BRASS_LIGHT,
    leaf_fill=(255, 250, 232, 120),
    tab_current=(_BAIZE, BRASS, BRASS_LIGHT),
    tab_other=((222, 204, 160), (238, 222, 182), BRASS_DARK, INK),
    seal=(_BAIZE, BRASS, BRASS_LIGHT), laurel=((104, 140, 74), (48, 72, 36), RUBRIC), glow=BRASS)

# Text set on the sheet's own band reads in the band's light (the title tablet's ends)
BAND_INNER = 26                          # the frame's band and corner blocks end this far in

_fonts: Dict[Tuple[str, int], pygame.font.Font] = {}
_sheets: Dict[Tuple[Tuple[int, int], str], pygame.Surface] = {}


def font(size: int, face: str = "RomanAntique.ttf") -> pygame.font.Font:
    """One of the game's fonts at *size*, loaded once."""
    key = (face, size)
    if key not in _fonts:
        try:
            _fonts[key] = pygame.font.Font(os.path.join(FONTS_PATH, face), size)
        except (OSError, FileNotFoundError):
            _fonts[key] = pygame.font.SysFont("georgia", size)
    return _fonts[key]


def title_font(size: int = 40) -> pygame.font.Font:
    return font(size, "Medici Text.ttf")


def sheet(size: Tuple[int, int], title: str = "") -> pygame.Surface:
    """A framed counting-house sheet *size* big, *title* on its tablet over the top band; made once."""
    key = (tuple(size), title)
    if key not in _sheets:
        if len(_sheets) > 24:                    # a few sizes, a dozen titles: never many
            _sheets.clear()
        page = framed_sheet(size, corner_blocks=True, theme=COUNTING_HOUSE.sheet, geometry=SLIM_FRAME)
        if title:
            title_tablet(page, _title(title, title_font(), COUNTING_HOUSE), page.get_width() // 2,
                         COUNTING_HOUSE.sheet)
        _sheets[key] = page
    return _sheets[key]


WHOLE_TITLE = "Depot"                     # the one sheet's title when the depot fills both sides
SEAM = 26                                 # how far each half's content keeps from the rule between them


def draw_depot_sheet(screen: pygame.Surface, rect: pygame.Rect) -> Tuple[pygame.Rect, pygame.Rect]:
    """The depot over both sides: one framed sheet under one title, a brass rule down its middle
    with a lozenge at each end. Returns the rects to lay the charts and the accounts out in, as
    if each were a sheet of its own but reaching to within ``SEAM`` of the middle."""
    screen.blit(sheet(rect.size, WHOLE_TITLE), rect)
    mid = rect.centerx
    top, bottom = rect.top + 100, rect.bottom - 52
    pygame.draw.line(screen, BRASS_DARK, (mid - 2, top), (mid - 2, bottom), 1)
    pygame.draw.line(screen, BRASS, (mid + 1, top), (mid + 1, bottom), 1)
    for y in (top, bottom):
        points = [(mid, y - 8), (mid + 6, y), (mid, y + 8), (mid - 6, y)]
        pygame.draw.polygon(screen, BRASS, points)
        pygame.draw.polygon(screen, BRASS_DARK, points, 1)
    half = rect.width // 2
    left = pygame.Rect(rect.left, rect.top, half + 52 - SEAM, rect.height)
    right = pygame.Rect(rect.left + half - 52 + SEAM, rect.top, rect.width - half + 52 - SEAM, rect.height)
    return left, right


def blend(colour: Colour, toward: Colour, k: float) -> Colour:
    return tuple(round(a + (b - a) * k) for a, b in zip(colour, toward))


def faded(colour: Colour, k: float = 0.65) -> Colour:
    """A mark's colour half gone into the paper, for what is not in focus."""
    return blend(colour, PAPER, k)


def divider(surf: pygame.Surface, centre: Tuple[int, int], half: int) -> None:
    _divider(surf, centre, half, COUNTING_HOUSE)


def leaf(surf: pygame.Surface, rect: pygame.Rect, lit: bool = True) -> None:
    _leaf(surf, rect, lit, COUNTING_HOUSE)


def tab(surf: pygame.Surface, rect: pygame.Rect, label: str, current: bool, hovered: bool,
        size: int = 19) -> None:
    """A tab in the counting house's colours, its label shrunk to fit."""
    face = font(size)
    while face.size(label)[0] > rect.width - 10 and size > 13:
        size -= 1
        face = font(size)
    _tab(surf, rect, label, face, current, hovered, COUNTING_HOUSE, text_shift=0)


def small_tab(surf: pygame.Surface, rect: pygame.Rect, label: str, current: bool, hovered: bool) -> None:
    """A small switch, as for a chart's range: brass when chosen, a paler leaf otherwise."""
    if current:
        fill, edge, ink = BRASS, BRASS_DARK, INK
    else:
        fill, edge, ink = ((246, 234, 204) if hovered else (232, 218, 182)), (176, 150, 100), FAINT_INK
    pygame.draw.rect(surf, fill, rect, border_radius=4)
    if current:
        pygame.draw.line(surf, BRASS_LIGHT, (rect.left + 4, rect.top + 2), (rect.right - 5, rect.top + 2), 1)
    pygame.draw.rect(surf, edge, rect, 1 if not current else 2, border_radius=4)
    text = font(17).render(label, True, ink)
    surf.blit(text, text.get_rect(center=rect.center))


Row = Tuple[Optional[Colour], str, str, str]     # (swatch, label, value, style: "", "total", "faint", "focus", "line")


def note(surf: pygame.Surface, anchor: Tuple[int, int], heading: str, rows: Sequence[Row],
         bounds: pygame.Rect, value_colours: Optional[Dict[int, Colour]] = None) -> pygame.Rect:
    """A slip of parchment pinned beside *anchor* (right of it, or left where that runs out of
    *bounds*): a heading, a rule, and its rows, each a swatch (a square, or a short line for a
    "line" row), a label and a value set to the right. Returns where it was drawn."""
    head_font, body_font = title_font(21), font(18)
    pad, swatch, gap = 12, 12, 14
    label_w = max([body_font.size(label)[0] for _, label, _, _ in rows] + [0])
    value_w = max([body_font.size(value)[0] for _, _, value, _ in rows] + [0])
    width = max(head_font.size(heading)[0], swatch + 8 + label_w + gap + value_w) + 2 * pad
    line_h = body_font.size("Ag")[1] + 2           # this face's own line height is shorter than its letters
    head_h = head_font.size("Ag")[1]
    height = pad + head_h + 8 + len(rows) * line_h + pad - 2
    rect = pygame.Rect(0, 0, width, height)
    rect.midleft = (anchor[0] + 22, anchor[1])
    if rect.right > bounds.right - 4:
        rect.midright = (anchor[0] - 22, anchor[1])
    rect.clamp_ip(bounds)

    shadow = pygame.Surface(rect.size, pygame.SRCALPHA)
    shadow.fill((40, 24, 8, 60))
    surf.blit(shadow, rect.move(3, 4))
    draw_paper(surf, rect, rect.topleft, edge_depth=10)
    pygame.draw.rect(surf, BRASS_DARK, rect, 2)
    pygame.draw.rect(surf, BRASS, rect.inflate(-6, -6), 1)

    y = rect.top + pad - 2
    surf.blit(head_font.render(heading, True, INK), (rect.left + pad, y))
    y += head_h + 2
    pygame.draw.line(surf, BRASS, (rect.left + pad, y), (rect.right - pad, y), 1)
    y += 6
    for n, (colour, label, value, style) in enumerate(rows):
        if style == "total":
            pygame.draw.line(surf, RULE, (rect.left + pad, y), (rect.right - pad, y), 1)
        ink = FAINT_INK if style == "faint" else INK
        cy = y + line_h // 2
        if colour is not None:
            if style == "line":
                pygame.draw.line(surf, colour, (rect.left + pad, cy), (rect.left + pad + swatch, cy), 3)
            else:
                box = pygame.Rect(rect.left + pad, cy - swatch // 2, swatch, swatch)
                pygame.draw.rect(surf, colour, box, border_radius=2)
                pygame.draw.rect(surf, blend(colour, INK, 0.5), box, 1, border_radius=2)
        text_x = rect.left + pad + swatch + 8
        label_s = body_font.render(label, True, ink)
        value_colour = (value_colours or {}).get(n, ink)
        value_s = body_font.render(value, True, value_colour)
        if style in ("total", "focus"):                         # set heavier: printed twice
            surf.blit(label_s, (text_x + 1, y))
            surf.blit(value_s, (rect.right - pad - value_s.get_width() + 1, y))
        surf.blit(label_s, (text_x, y))
        surf.blit(value_s, (rect.right - pad - value_s.get_width(), y))
        y += line_h
    return rect


def leader(surf: pygame.Surface, x0: int, x1: int, y: int, colour: Colour = (190, 164, 110)) -> None:
    """A ledger's dotted line from a label to its value."""
    for x in range(int(x0), int(x1), 6):
        surf.fill(colour, (x, y, 2, 2))
