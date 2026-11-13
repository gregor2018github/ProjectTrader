"""The minigames' how-to sheets: one parchment page as big as the minigame, framed in gold, with a
title and cards side by side, each a rubric numeral, a heading, a frame waiting for its moving
picture and a few words under it. What moves is each minigame's own (``woodhacking_tutorial.py``,
``fishing_tutorial.py``); the sheet, the mouse and the button are here.

A minigame showing a sheet has ``font``, ``font_small``, ``font_words``, ``font_grade``,
``font_large``, ``font_title`` and ``_inked(text, font, colour)``.
"""

import math
import random
from dataclasses import dataclass
from typing import List, Sequence, Tuple

import pygame

from .woodhacking import draw_divider, draw_flourish
from ...config.colors import GOLD, MUTED_DARK_RED, WHITE
from ...ui.helper_modules.charter_style import BlockColours, draw_corner_blocks
from ...ui.paper import draw_paper

INK = (44, 32, 22)
RUBRIC = MUTED_DARK_RED                 # the red ink of a manuscript's emphasised words
BRASS, BRASS_LIGHT, BRASS_DARK = (196, 154, 64), (236, 204, 120), (120, 86, 30)
GOOD, BAD = (146, 214, 120), (240, 120, 96)
MAX_DT = 0.05                           # a slow frame does not make the pictures jump

BUTTON_SIZE = (176, 44)
MOUSE_SIZE = (40, 60)
SPACE_SIZE = (92, 28)

_FRAME_INSET = 13
_TITLE_Y, _DIVIDER_Y = 52, 84
_CARDS_LEFT, _CARDS_TOP = 30, 98
_CARD_GAP = 12
_CARD_PAD = 12
_HEADING_H = 42
_LINE_H = 27
_SUPERSAMPLE = 4


@dataclass(frozen=True)
class SheetLayout:
    """Where a sheet's cards go, in the minigame's canvas pixels."""
    card_widths: Tuple[int, ...]
    cards_bottom: int
    picture_h: int
    button_y: int

    def card_rects(self) -> List[pygame.Rect]:
        rects, x = [], _CARDS_LEFT
        for width in self.card_widths:
            rects.append(pygame.Rect(x, _CARDS_TOP, width, self.cards_bottom - _CARDS_TOP))
            x += width + _CARD_GAP
        return rects

    def picture_rects(self) -> List[pygame.Rect]:
        return [pygame.Rect(card.left + _CARD_PAD, card.top + _HEADING_H + 8, card.width - 2 * _CARD_PAD, self.picture_h)
                for card in self.card_rects()]


GOLD_BLOCK = BlockColours(edge=BRASS_DARK, rule=(150, 108, 30), ornament=BRASS, boss=RUBRIC)
_FRAME_GOLD = (150, 108, 30)

# The banded frame round a sheet with corner blocks, in pixels in from the sheet's edge: a double
# rule each side of a band of interlaced waves, the band's middle running through the blocks' middles.
_BAND_RULES = ((10, 2), (13, 1), (35, 1), (37, 2))      # (inset, width), the heavy lines outermost
_BAND_MIDDLE, _BAND_HALF = 24, 9                         # the waves' axis and how far they swing
_WAVE_PERIOD = 46                                        # about this long; fitted to each side
_BAND_WASH = (13, 35)                                    # the band's ground lies between these insets


@dataclass(frozen=True)
class SheetTheme:
    """The colours of a framed sheet with corner blocks: its outer edge (a dark band with a lighter
    line in it), the band's rules, a wash over the band's ground, its two strands and their beads,
    and the corner blocks."""
    edge_dark: Tuple[int, int, int]
    edge_light: Tuple[int, int, int]
    rule: Tuple[int, int, int]
    band_wash: Tuple[int, int, int, int]
    strands: Tuple[Tuple[int, int, int], Tuple[int, int, int]]
    bead_dark: Tuple[int, int, int]
    bead_light: Tuple[int, int, int]
    block: BlockColours
    texture: str = ""                                    # "", or the band's ground as GRAIN or RIPPLES
    texture_colour: Tuple[int, int, int, int] = (0, 0, 0, 0)


GRAIN, RIPPLES, WEAVE = "grain", "ripples", "weave"


def _texture_strip(length: int, theme: SheetTheme) -> pygame.Surface:
    """The band's ground along one side: wood's grain, long wavering lines with a knot now and
    then, water's ripples, short pale curves scattered over it, or a linen's WEAVE. The same for
    the same length."""
    k = 2
    height = _BAND_WASH[1] - _BAND_WASH[0]
    art = pygame.Surface((length * k, height * k), pygame.SRCALPHA)
    rng = random.Random(length)
    colour = theme.texture_colour
    if theme.texture == GRAIN:
        for row in range(6):
            base = (row + 0.5) * height / 6
            a, b = rng.uniform(0.6, 1.6), rng.uniform(0.3, 0.9)
            la, lb = rng.uniform(90, 200), rng.uniform(25, 60)
            pa, pb = rng.uniform(0, 6.3), rng.uniform(0, 6.3)
            points = [(x * k, (base + a * math.sin(x / la + pa) + b * math.sin(x / lb + pb)) * k)
                      for x in range(0, length + 4, 4)]
            pygame.draw.lines(art, colour, False, points, k)
        for _ in range(max(1, length // 260)):                         # knots, the grain swirling round them
            x, y = rng.uniform(20, length - 20), rng.uniform(5, height - 5)
            for r in (2.0, 4.0):
                pygame.draw.ellipse(art, colour, ((x - 3 * r) * k, (y - r) * k, 6 * r * k, 2 * r * k), k)
    elif theme.texture == RIPPLES:
        for _ in range(length // 9):
            x, y = rng.uniform(0, length), rng.uniform(3, height - 3)
            w = rng.uniform(6, 16)
            pygame.draw.arc(art, colour, ((x - w / 2) * k, (y - 1.5) * k, w * k, 4 * k), 0.4, 2.74, k)
    elif theme.texture == WEAVE:                                       # a linen twill: close diagonals, fainter across
        faint = (*colour[:3], colour[3] // 2)
        for x in range(-height, length + height, 3):
            pygame.draw.line(art, colour, (x * k, 0), ((x + height) * k, height * k), k)
        for x in range(-height, length + height, 6):
            pygame.draw.line(art, faint, ((x + height) * k, 0), (x * k, height * k), k)
    return pygame.transform.smoothscale(art, (length, height))


GOLD_SHEET = SheetTheme(edge_dark=_FRAME_GOLD, edge_light=GOLD, rule=_FRAME_GOLD, band_wash=(0, 0, 0, 0),
                        strands=(RUBRIC, BRASS_DARK), bead_dark=BRASS_DARK, bead_light=BRASS, block=GOLD_BLOCK)


def _wave_strip(length: int, theme: SheetTheme) -> pygame.Surface:
    """One side's band of two strands in opposite phase, crossing on the axis: a chain of eyes,
    each with a bead in it, as many whole periods as fit *length*, so the strands meet the
    corner blocks on the axis."""
    k = _SUPERSAMPLE
    height = 2 * _BAND_HALF + 2
    art = pygame.Surface((length * k, height * k), pygame.SRCALPHA)
    periods = max(1, round(length / _WAVE_PERIOD))
    half_period = length / (2 * periods)
    mid = height * k / 2
    steps = length * 2
    for strand, ink in enumerate(theme.strands):
        sign = 1 if strand == 0 else -1
        points = [(i / steps * length * k,
                   mid + sign * _BAND_HALF * k * math.sin(math.pi * i / steps * length / half_period))
                  for i in range(steps + 1)]
        pygame.draw.lines(art, ink, False, points, int(1.6 * k))
    for eye in range(2 * periods):                                     # a bead in every eye
        x = (eye + 0.5) * half_period * k
        pygame.draw.circle(art, theme.bead_dark, (x, mid), 2.4 * k)
        pygame.draw.circle(art, theme.bead_light, (x, mid), 1.6 * k)
    return pygame.transform.smoothscale(art, (length, height))


def _draw_band(page: pygame.Surface, theme: SheetTheme) -> None:
    """The frame's band inside the edge: its ground, its double rules and the waves between them."""
    sheet = page.get_rect()
    if theme.band_wash[3]:
        wash = pygame.Surface(sheet.size, pygame.SRCALPHA)
        outer, inner = _BAND_WASH
        wash.fill(theme.band_wash, sheet.inflate(-2 * outer, -2 * outer))
        wash.fill((0, 0, 0, 0), sheet.inflate(-2 * inner, -2 * inner))
        page.blit(wash, (0, 0))
    if theme.texture:
        outer, inner = _BAND_WASH
        middle = (outer + inner) / 2
        across = _texture_strip(sheet.width - 2 * outer, theme)
        upright = pygame.transform.rotate(_texture_strip(sheet.height - 2 * inner, theme), 90)
        for art, centre in ((across, (sheet.centerx, middle)), (across, (sheet.centerx, sheet.height - middle)),
                            (upright, (middle, sheet.centery)), (upright, (sheet.width - middle, sheet.centery))):
            page.blit(art, art.get_rect(center=(round(centre[0]), round(centre[1]))))
    for inset, width in _BAND_RULES:
        pygame.draw.rect(page, theme.rule, sheet.inflate(-2 * inset, -2 * inset), width)
    block_far = 41                                   # the corner blocks' far edge, as charter_style lays them
    across = _wave_strip(sheet.width - 2 * block_far, theme)
    upright = pygame.transform.rotate(_wave_strip(sheet.height - 2 * block_far, theme), 90)
    for art, centre in ((across, (sheet.centerx, _BAND_MIDDLE)), (across, (sheet.centerx, sheet.height - _BAND_MIDDLE)),
                        (upright, (_BAND_MIDDLE, sheet.centery)), (upright, (sheet.width - _BAND_MIDDLE, sheet.centery))):
        page.blit(art, art.get_rect(center=centre))


_TABLET_TOP, _TABLET_BOTTOM = 10, 84          # a title's tablet: from the band's outer rule to under the title
_TABLET_PAD = 46                              # either side of the title
_TABLET_CUT = 9                               # its corners cut off


def title_tablet(page: pygame.Surface, title: pygame.Surface, centre_x: int, theme: SheetTheme = GOLD_SHEET,
                 title_y: int = None) -> pygame.Rect:
    """Set *title* on a tablet of the sheet's own parchment that stands over the frame's top band,
    so no flourish of its letters runs into the waves: cut corners, edged in the frame's dark
    colour, ruled inside, with a lozenge at each end. Returns the tablet's rect."""
    rect = pygame.Rect(0, _TABLET_TOP, title.get_width() + 2 * _TABLET_PAD, _TABLET_BOTTOM - _TABLET_TOP)
    rect.centerx = centre_x
    c = _TABLET_CUT

    def outline(r: pygame.Rect, cut: int) -> List[Tuple[int, int]]:
        return [(r.left + cut, r.top), (r.right - 1 - cut, r.top), (r.right - 1, r.top + cut),
                (r.right - 1, r.bottom - 1 - cut), (r.right - 1 - cut, r.bottom - 1), (r.left + cut, r.bottom - 1),
                (r.left, r.bottom - 1 - cut), (r.left, r.top + cut)]

    paper = pygame.Surface(rect.size, pygame.SRCALPHA)
    draw_paper(paper, paper.get_rect(), (-rect.left, -rect.top), edge_depth=0)   # the grain carries on from the sheet
    shape = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.polygon(shape, (255, 255, 255, 255), outline(paper.get_rect(), c))
    paper.blit(shape, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    shadow = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.polygon(shadow, (40, 24, 8, 60), outline(shadow.get_rect(), c))
    page.blit(shadow, rect.move(2, 3))
    page.blit(paper, rect)

    pygame.draw.polygon(page, theme.edge_dark, outline(rect, c), 3)
    pygame.draw.polygon(page, theme.rule, outline(rect.inflate(-10, -10), c - 3), 1)
    for x in (rect.left, rect.right - 1):                         # a lozenge on each end, over the edge
        y = rect.centery
        points = [(x, y - 9), (x + 7, y), (x, y + 9), (x - 7, y)]
        pygame.draw.polygon(page, theme.block.ornament, points)
        pygame.draw.polygon(page, theme.edge_dark, points, 1)
        pygame.draw.circle(page, theme.block.boss, (x, y), 2)
    centre_y = rect.centery if title_y is None else title_y
    page.blit(title, title.get_rect(center=(centre_x, centre_y)))
    return rect


def framed_sheet(size: Tuple[int, int], corner_blocks: bool = False,
                 theme: SheetTheme = GOLD_SHEET) -> pygame.Surface:
    """A blank sheet: browned parchment in a gold frame with flourishes in its corners, or with
    *corner_blocks* a broader frame, a band of interlaced waves between double rules, meeting in
    the council's charter's square blocks, in the colours of *theme* (gold by default)."""
    page = pygame.Surface(size)
    sheet = page.get_rect()
    draw_paper(page, sheet, sheet.topleft)
    if corner_blocks:
        pygame.draw.rect(page, theme.edge_dark, sheet, 6)
        pygame.draw.rect(page, theme.edge_light, sheet.inflate(-4, -4), 3)
        _draw_band(page, theme)
        draw_corner_blocks(page, theme.block)
        return page
    pygame.draw.rect(page, _FRAME_GOLD, sheet, 6)
    pygame.draw.rect(page, GOLD, sheet.inflate(-4, -4), 3)
    inner = sheet.inflate(-2 * _FRAME_INSET, -2 * _FRAME_INSET)
    pygame.draw.rect(page, _FRAME_GOLD, inner, 1)
    for sx, sy, corner in ((1, 1, inner.topleft), (-1, 1, inner.topright),
                           (1, -1, inner.bottomleft), (-1, -1, inner.bottomright)):
        draw_flourish(page, corner, sx, sy)
    return page


def inked(text: str, font: pygame.font.Font, colour) -> pygame.Surface:
    """Text with a dark edge, so gold reads on the paper."""
    edge = font.render(text, True, INK)
    label = pygame.Surface((edge.get_width() + 2, edge.get_height() + 2), pygame.SRCALPHA)
    for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
        label.blit(edge, (dx, dy))
    label.blit(font.render(text, True, colour), (1, 1))
    return label


def build_sheet(size: Tuple[int, int], minigame, layout: SheetLayout, title: str,
                cards: Sequence[Tuple[str, str]]) -> pygame.Surface:
    """All of a sheet that does not move. Each card is its heading and its words, *these* in red ink."""
    page = framed_sheet(size)
    sheet = page.get_rect()

    label = minigame._inked(title, minigame.font_title, GOLD)
    page.blit(label, label.get_rect(center=(sheet.centerx, _TITLE_Y)))
    draw_divider(page, (sheet.centerx, _DIVIDER_Y), 170)

    for number, (card, picture, (heading, words)) in enumerate(
            zip(layout.card_rects(), layout.picture_rects(), cards), 1):
        _draw_card(page, minigame, card, picture, number, heading, words)
    return page


def _draw_card(page: pygame.Surface, minigame, card: pygame.Rect, picture: pygame.Rect,
               number: int, heading: str, words: str) -> None:
    """A card: a paler leaf, ruled in brass, with a rubric numeral, a heading, a frame
    waiting for its picture, and the words under it."""
    leaf = pygame.Surface(card.size, pygame.SRCALPHA)
    leaf.fill((255, 248, 226, 96))
    page.blit(leaf, card.topleft)
    pygame.draw.rect(page, BRASS_DARK, card, 2, border_radius=4)
    pygame.draw.rect(page, BRASS, card.inflate(-6, -6), 1, border_radius=3)

    seal = pygame.Rect(card.left + _CARD_PAD, card.top + 10, 32, 32)
    pygame.draw.rect(page, RUBRIC, seal, border_radius=3)
    pygame.draw.rect(page, GOLD, seal, 2, border_radius=3)
    numeral = minigame.font.render("I" * number, True, BRASS_LIGHT)
    page.blit(numeral, numeral.get_rect(center=seal.center))
    title = minigame.font_large.render(heading, True, INK)
    page.blit(title, title.get_rect(midleft=(seal.right + 8, seal.centery)))

    pygame.draw.rect(page, INK, picture.inflate(8, 8), border_radius=3)
    pygame.draw.rect(page, BRASS, picture.inflate(6, 6), 2, border_radius=3)
    pygame.draw.rect(page, BRASS_DARK, picture.inflate(2, 2), 1)

    _draw_words(page, minigame.font_words, words, card.left + _CARD_PAD + 2, picture.bottom + 16,
                card.width - 2 * _CARD_PAD - 4)


def _draw_words(page: pygame.Surface, font: pygame.font.Font, words: str, x: int, y: int, width: int) -> None:
    """The words broken to the width, those between stars in red ink."""
    space = font.size(" ")[0]
    cx = x
    red = False
    for word in words.split():
        opens = word.startswith("*")
        red = red or opens
        bare = word.replace("*", "")
        if cx > x and cx + font.size(bare)[0] > x + width:
            cx, y = x, y + _LINE_H
        page.blit(font.render(bare, True, RUBRIC if red else INK), (cx, y))
        cx += font.size(bare)[0] + space
        if word.rstrip(".,:;!?").endswith("*"):
            red = False


def draw_button(canvas: pygame.Surface, rect: pygame.Rect, label: str, font: pygame.font.Font, hovered: bool) -> None:
    pygame.draw.rect(canvas, BRASS_LIGHT if hovered else BRASS, rect, border_radius=4)
    pygame.draw.line(canvas, WHITE if hovered else BRASS_LIGHT, (rect.left + 4, rect.top + 3),
                     (rect.right - 5, rect.top + 3), 1)
    pygame.draw.rect(canvas, BRASS_DARK, rect, 2, border_radius=4)
    text = font.render(label, True, INK)
    canvas.blit(text, text.get_rect(center=rect.center))


def draw_tab(canvas: pygame.Surface, rect: pygame.Rect, label: str, font: pygame.font.Font, current: bool,
             locked: bool, hovered: bool) -> None:
    """A page's tab: red and gold like the cards' seals on the page shown, faded while it cannot be opened."""
    if current:
        fill, edge, ink = RUBRIC, GOLD, BRASS_LIGHT
    elif locked:
        fill, edge, ink = (214, 196, 158), (160, 138, 100), (140, 120, 90)
    else:
        fill, edge, ink = BRASS_LIGHT if hovered else BRASS, BRASS_DARK, INK
    pygame.draw.rect(canvas, fill, rect, border_radius=4)
    pygame.draw.rect(canvas, edge, rect, 2, border_radius=4)
    text = font.render(label, True, ink)
    canvas.blit(text, text.get_rect(center=rect.center))


def plaque(surf: pygame.Surface, font: pygame.font.Font, text: str, center: Tuple[float, float]) -> pygame.Rect:
    """A small brass plate with engraved text, nailed on."""
    label = font.render(text, True, INK)
    rect = label.get_rect(center=center).inflate(14, 6)
    pygame.draw.rect(surf, BRASS, rect, border_radius=3)
    pygame.draw.line(surf, BRASS_LIGHT, (rect.left + 3, rect.top + 2), (rect.right - 4, rect.top + 2), 1)
    pygame.draw.rect(surf, BRASS_DARK, rect, 2, border_radius=3)
    surf.blit(label, label.get_rect(center=rect.center))
    return rect


def mouse_icon(pressed: bool = False, wheel: bool = False) -> pygame.Surface:
    """A mouse, drawn large and smoothed down: its left button gilded while it is pressed, or its
    wheel, to show that the wheel is what is meant."""
    k = _SUPERSAMPLE
    w, h = MOUSE_SIZE
    art = pygame.Surface((w * k, h * k), pygame.SRCALPHA)
    body = art.get_rect().inflate(-2 * k, -2 * k)
    radius = 17 * k
    pygame.draw.rect(art, (236, 222, 186), body, border_radius=radius)
    split_y = body.top + 25 * k
    if pressed:
        left = pygame.Surface(art.get_size(), pygame.SRCALPHA)
        pygame.draw.rect(left, (*GOLD, 255), body, border_radius=radius)
        left.fill((0, 0, 0, 0), (body.centerx, 0, art.get_width(), art.get_height()))
        left.fill((0, 0, 0, 0), (0, split_y, art.get_width(), art.get_height()))
        art.blit(left, (0, 0))
    pygame.draw.rect(art, INK, body, 2 * k, border_radius=radius)
    pygame.draw.line(art, INK, (body.left, split_y), (body.right, split_y), 2 * k)
    pygame.draw.line(art, INK, (body.centerx, body.top), (body.centerx, split_y), 2 * k)
    if wheel:
        spokes = pygame.Rect(0, 0, 8 * k, 18 * k)
        spokes.center = (body.centerx, body.top + 14 * k)
        pygame.draw.rect(art, GOLD, spokes, border_radius=3 * k)
        pygame.draw.rect(art, INK, spokes, k, border_radius=3 * k)
    return pygame.transform.smoothscale(art, MOUSE_SIZE)


def space_icon(pressed: bool = False) -> pygame.Surface:
    """The space bar, gilded and pushed down a little while it is pressed."""
    w, h = SPACE_SIZE
    art = pygame.Surface(SPACE_SIZE, pygame.SRCALPHA)
    pygame.draw.rect(art, INK, (0, 3, w, h - 3), border_radius=6)
    top = pygame.Rect(2, 2 if pressed else 0, w - 4, h - 7)
    pygame.draw.rect(art, GOLD if pressed else (236, 222, 186), top, border_radius=5)
    pygame.draw.rect(art, INK, top, 2, border_radius=5)
    return art


def hold_sign(surf: pygame.Surface, font: pygame.font.Font, icon: pygame.Surface, text: str,
              center: Tuple[int, int]) -> None:
    """The mouse and what it is doing."""
    rect = icon.get_rect(center=center)
    surf.blit(icon, rect)
    plaque(surf, font, text, (rect.centerx, rect.bottom + 15))
