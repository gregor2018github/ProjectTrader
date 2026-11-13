"""The guild's records of the player's successes, opened at the guildhall.

So far the minigames', a page each, on browned parchment in a broad frame of interlaced
waves meeting in square corner blocks, each page in colours of its own (``PageTheme``):
the fishing's woad blue and pewter, the woodhacking's walnut, oak and leaf green.

Fishing: a card for every kind of fish with its portrait in a framed bit of water, its
name, how many were landed, their weight together and the biggest one; a kind never
caught is greyed out with a question mark for its name. Woodhacking: the top scores with
their dates, the best in a laurel wreath, what the player has done over all sessions, and
when a score is hovered what its session made up. Whatever was not tracked yet when a
session was played, as in an older save, shows as ``NOT_TRACKED``.

A page does not change while the window is open, so each is drawn once onto its own sheet
(``_build_page``); only the tabs and the hover are drawn every frame.
"""

import datetime
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

import pygame

from .loan_dialog import _BaseDialog
from .statistics_view import _fmt_woodhacking_score
from ..layout_modules.town_plan import glyphs
from ...config.colors import GOLD, GRAY, PARCHMENT
from ...config.constants import FONTS_PATH
from ...models.minigames.fishing_pond import SPECIES, Species, format_kg
from ...models.minigames.fishing_scene import fish_sprite
from .charter_style import BlockColours
from ...models.minigames.tutorial_sheet import (
    BRASS, BRASS_DARK, BRASS_LIGHT, GOLD_SHEET, GRAIN, INK, RIPPLES, RUBRIC, SheetTheme, framed_sheet, title_tablet,
)
from ...models.minigames.woodhacking import draw_laurel
from ...models.statistics import Statistics, WOODHACKING_TOP_SCORES
from ...sim.calendar import format_date

if TYPE_CHECKING:
    from ...game_state import GameState

UNKNOWN_NAME = "?"
NOT_TRACKED = "-"
PORTRAIT_LENGTH = 30             # low pixels long, whatever its kind's size: one drawn small would show nothing
PORTRAIT_SCALE = 4
_GREY_ALPHA = 170                # how faint the portrait of a kind not caught yet is

PAGE_FISHING, PAGE_WOODHACKING = "Fishing", "Woodhacking"
PAGES = (PAGE_FISHING, PAGE_WOODHACKING)

ROMAN = ("I", "II", "III", "IV", "V")
STREAK, PERFECT, BLOCKS = "streak", "perfect", "blocks"   # the little pictures beside the woodhacking's figures
_OVERALL_ICONS = (STREAK, PERFECT, PERFECT, BLOCKS, BLOCKS)
_DETAIL_ICONS = (STREAK, PERFECT, BLOCKS)
_HOVER_HINT = "Hover over a score to see that round's details"

_FAINT_INK = (120, 104, 84)      # labels and what has no value yet
_GOLD_DARK = (150, 108, 30)      # the frame's outer edge, as on the minigames' sheets
_WATER = ((104, 142, 140), (36, 66, 80))      # a caught fish's bit of water, top and bottom
_NO_WATER = ((158, 152, 140), (112, 106, 98))  # a kind not caught yet


# ----------------------------------------------------------------------
# Each page's colours
# ----------------------------------------------------------------------

Colour = Tuple[int, int, int]


@dataclass(frozen=True)
class PageTheme:
    """A page's colours: its frame, its title (a gradient, top to bottom), the metal of its rules,
    plaques and dots (``accent`` with a dark and a light shade), its leaves' wash, its tab (the
    page shown, and otherwise), its seals, its wreath and the glow over a hovered row."""
    sheet: SheetTheme
    title: Tuple[Colour, Colour]
    accent: Colour
    accent_dark: Colour
    accent_light: Colour
    leaf_fill: Tuple[int, int, int, int]
    tab_current: Tuple[Colour, Colour, Colour]              # fill, edge, ink
    tab_other: Tuple[Colour, Colour, Colour, Colour]        # fill, hovered fill, edge, ink
    seal: Tuple[Colour, Colour, Colour]                     # fill, edge, ink
    laurel: Tuple[Colour, Colour, Colour]                   # leaves, their edge, the bow
    glow: Colour


GOLD_PAGE = PageTheme(
    sheet=GOLD_SHEET, title=(BRASS_LIGHT, (170, 118, 30)), accent=BRASS, accent_dark=BRASS_DARK,
    accent_light=BRASS_LIGHT, leaf_fill=(255, 248, 226, 110),
    tab_current=(RUBRIC, GOLD, BRASS_LIGHT), tab_other=(BRASS, BRASS_LIGHT, BRASS_DARK, INK),
    seal=(RUBRIC, GOLD, BRASS_LIGHT), laurel=(GOLD, _GOLD_DARK, RUBRIC), glow=GOLD)

# Woad and indigo, pewter and a touch of verdigris: the river's page.
_INDIGO, _INDIGO_DEEP, _PEWTER, _PEWTER_LIGHT = (44, 68, 100), (30, 46, 70), (112, 142, 166), (204, 218, 228)
_LAPIS, _VERDIGRIS = (38, 76, 140), (66, 132, 128)
FISHING_PAGE = PageTheme(
    sheet=SheetTheme(edge_dark=_INDIGO_DEEP, edge_light=(128, 158, 182), rule=(52, 78, 108),
                     band_wash=(140, 176, 202, 84), strands=(_LAPIS, _VERDIGRIS),
                     bead_dark=_INDIGO, bead_light=_PEWTER_LIGHT,
                     block=BlockColours(edge=_INDIGO_DEEP, rule=(74, 102, 132), ornament=(140, 170, 194), boss=_LAPIS),
                     texture=RIPPLES, texture_colour=(246, 252, 255, 150)),
    title=((150, 192, 222), (34, 66, 112)), accent=_PEWTER, accent_dark=_INDIGO, accent_light=_PEWTER_LIGHT,
    leaf_fill=(242, 248, 248, 120),
    tab_current=(_INDIGO, (140, 170, 194), (226, 236, 242)),
    tab_other=((178, 198, 212), (200, 216, 228), (52, 78, 108), INK),
    seal=(_LAPIS, _PEWTER_LIGHT, (226, 236, 242)), laurel=((150, 180, 202), _INDIGO, _LAPIS), glow=(120, 170, 214))

# Walnut and oak and the green of the wood: the woodcutter's page.
_WALNUT, _WALNUT_DEEP, _OAK, _OAK_LIGHT = (96, 60, 32), (62, 38, 20), (162, 114, 64), (218, 178, 122)
_LEAF_GREEN, _WAX = (70, 104, 58), (124, 40, 32)
WOODHACKING_PAGE = PageTheme(
    sheet=SheetTheme(edge_dark=_WALNUT_DEEP, edge_light=(170, 120, 68), rule=(98, 62, 34),
                     band_wash=(178, 126, 72, 92), strands=(_WALNUT, _LEAF_GREEN),
                     bead_dark=_WALNUT, bead_light=_OAK_LIGHT,
                     block=BlockColours(edge=_WALNUT_DEEP, rule=(116, 76, 42), ornament=(188, 140, 84), boss=_LEAF_GREEN),
                     texture=GRAIN, texture_colour=(110, 70, 36, 70)),
    title=((226, 176, 108), (104, 60, 28)), accent=_OAK, accent_dark=_WALNUT, accent_light=_OAK_LIGHT,
    leaf_fill=(252, 240, 216, 120),
    tab_current=(_WALNUT, (188, 140, 84), (242, 224, 190)),
    tab_other=((200, 164, 114), (218, 186, 138), (98, 62, 34), INK),
    seal=(_WAX, _WALNUT_DEEP, (242, 224, 190)), laurel=((104, 140, 74), (48, 72, 36), _WAX), glow=(204, 156, 96))

PAGE_THEMES = {PAGE_FISHING: FISHING_PAGE, PAGE_WOODHACKING: WOODHACKING_PAGE}

_portraits = {}                  # (species key, caught) -> the portrait
_waters = {}                     # (size, caught) -> the water behind it


# ----------------------------------------------------------------------
# What the fishing page shows
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class FishRecord:
    """One card: what the player has of a kind of fish."""
    species: Species
    count: int
    kg: float
    biggest_cm: Optional[float]

    @property
    def caught(self) -> bool:
        return self.count > 0

    @property
    def name(self) -> str:
        return self.species.name if self.caught else UNKNOWN_NAME

    def rows(self) -> List[Tuple[str, str]]:
        if not self.caught:
            return [("Caught", NOT_TRACKED), ("Total", NOT_TRACKED), ("Biggest", NOT_TRACKED)]
        biggest = f"{self.biggest_cm:.0f} cm, {format_kg(self.species.kg(self.biggest_cm))}"
        return [("Caught", f"{self.count:,}"), ("Total", format_kg(self.kg)), ("Biggest", biggest)]


def fish_records(stats: Statistics) -> List[FishRecord]:
    """Every kind that can be landed, in the order of ``SPECIES``; minnows never take the hook."""
    records = []
    for key, species in SPECIES.items():
        if species.minnow:
            continue
        tally = stats.fish_tally.get(key, {})
        records.append(FishRecord(species, int(tally.get("count", 0)), tally.get("kg", 0.0),
                                  stats.fishing_records.get(key)))
    return records


def portrait(species: Species, caught: bool) -> pygame.Surface:
    cached = _portraits.get((species.key, caught))
    if cached is not None:
        return cached
    sprite = fish_sprite(species, PORTRAIT_LENGTH)
    big = pygame.transform.scale(sprite, (sprite.get_width() * PORTRAIT_SCALE, sprite.get_height() * PORTRAIT_SCALE))
    if not caught:
        big = pygame.transform.grayscale(big)
        big.fill((255, 255, 255, _GREY_ALPHA), special_flags=pygame.BLEND_RGBA_MULT)
    _portraits[(species.key, caught)] = big
    return big


def _water(size: Tuple[int, int], caught: bool) -> pygame.Surface:
    """The water a portrait hangs in: darker towards the bottom, a few pale ripples near the top."""
    cached = _waters.get((size, caught))
    if cached is not None:
        return cached
    top, bottom = _WATER if caught else _NO_WATER
    width, height = size
    water = pygame.Surface(size)
    for y in range(height):
        k = y / max(1, height - 1)
        pygame.draw.line(water, tuple(round(a + (b - a) * k) for a, b in zip(top, bottom)), (0, y), (width, y))
    ripple = tuple(min(255, c + 34) for c in top)
    for i, (x0, x1, y) in enumerate(((10, 44, 8), (70, 118, 13), (28, 62, 20), (92, 128, 27))):
        pygame.draw.line(water, ripple, (x0, y), (min(x1, width - 4), y), 1 if i % 2 else 2)
    _waters[(size, caught)] = water
    return water


# ----------------------------------------------------------------------
# What the woodhacking page shows
# ----------------------------------------------------------------------

def _number(value: Optional[int]) -> str:
    return NOT_TRACKED if value is None else f"{value:,}"


def score_text(entry: Dict[str, Any]) -> str:
    return _fmt_woodhacking_score(entry["score"])


def date_text(entry: Dict[str, Any]) -> str:
    """The session's day on the game's calendar."""
    date = entry.get("date")
    return format_date(datetime.date.fromisoformat(date)) if date else NOT_TRACKED


def score_details(entry: Dict[str, Any]) -> List[Tuple[str, str]]:
    """What a session in the top scores made up, shown when it is hovered."""
    return [("Best streak", _number(entry.get("streak"))),
            ("Perfect hits", _number(entry.get("perfects"))),
            ("Blocks chopped", _number(entry.get("blocks")))]


def overall_lines(stats: Statistics) -> List[Tuple[str, str]]:
    bests = stats.woodhacking_bests
    return [("Best streak", _number(bests.get("best_streak"))),
            ("Most perfect hits in one round", _number(bests.get("most_perfects"))),
            ("Total perfect hits", _number(bests.get("total_perfects"))),
            ("Most blocks chopped in one game", _number(bests.get("most_blocks"))),
            ("Total blocks chopped", _number(bests.get("total_blocks")))]


# ----------------------------------------------------------------------
# Small things drawn
# ----------------------------------------------------------------------

_FAINT_RULE = (168, 150, 120)


def _leaf(surf: pygame.Surface, rect: pygame.Rect, lit: bool = True, theme: PageTheme = GOLD_PAGE) -> None:
    """A paler leaf ruled twice in the page's metal, with a bracket in each corner on a themed
    page; a duller, bare one for what is still to come."""
    leaf = pygame.Surface(rect.size, pygame.SRCALPHA)
    leaf.fill(theme.leaf_fill if lit else (120, 104, 84, 38))
    surf.blit(leaf, rect)
    pygame.draw.rect(surf, theme.accent_dark if lit else _FAINT_INK, rect, 2, border_radius=4)
    pygame.draw.rect(surf, theme.accent if lit else _FAINT_RULE, rect.inflate(-6, -6), 1, border_radius=3)
    if not lit or theme is GOLD_PAGE:
        return
    inner = rect.inflate(-6, -6)
    arm = 9
    for (x, y), (sx, sy) in ((inner.topleft, (1, 1)), ((inner.right - 1, inner.top), (-1, 1)),
                             ((inner.left, inner.bottom - 1), (1, -1)),
                             ((inner.right - 1, inner.bottom - 1), (-1, -1))):
        pygame.draw.line(surf, theme.accent_dark, (x, y), (x + sx * arm, y), 2)
        pygame.draw.line(surf, theme.accent_dark, (x, y), (x, y + sy * arm), 2)
        pygame.draw.rect(surf, theme.accent_dark, (x + sx * 4 - 1, y + sy * 4 - 1, 3, 3))


def _picture_frame(surf: pygame.Surface, picture: pygame.Rect, lit: bool = True,
                   theme: PageTheme = GOLD_PAGE) -> None:
    """The frame round a picture, as on the how-to pages, in the page's metal."""
    pygame.draw.rect(surf, INK if lit else _FAINT_INK, picture.inflate(8, 8), border_radius=3)
    pygame.draw.rect(surf, theme.accent if lit else _FAINT_RULE, picture.inflate(6, 6), 2, border_radius=3)
    pygame.draw.rect(surf, theme.accent_dark if lit else _FAINT_INK, picture.inflate(2, 2), 1)


def _seal(surf: pygame.Surface, rect: pygame.Rect, text: str, font: pygame.font.Font, lit: bool = True,
          theme: PageTheme = GOLD_PAGE) -> None:
    """A seal with a numeral on it, in the page's wax; a pale one for a place not taken yet."""
    fill, edge, ink = theme.seal if lit else ((206, 190, 156), _FAINT_RULE, _FAINT_INK)
    pygame.draw.rect(surf, fill, rect, border_radius=5)
    pygame.draw.rect(surf, edge, rect, 2, border_radius=5)
    if lit:
        pygame.draw.rect(surf, edge, rect.inflate(-8, -8), 1, border_radius=3)
    label = font.render(text, True, ink)
    surf.blit(label, label.get_rect(center=rect.center))


def _leader(surf: pygame.Surface, x0: int, x1: int, y: int, theme: PageTheme = GOLD_PAGE) -> None:
    """A ledger's dotted line from a label to its value."""
    for x in range(x0, x1, 7):
        surf.fill(theme.accent, (x, y, 2, 2))


def _divider(surf: pygame.Surface, centre: Tuple[int, int], half: int, theme: PageTheme) -> None:
    """A double rule with a lozenge in its middle and a smaller one at each end, under a heading."""
    x, y = centre
    for dy, colour, inset in ((-1, theme.accent_dark, 12), (2, theme.accent, 16)):
        pygame.draw.line(surf, colour, (x - half, y + dy), (x - inset, y + dy), 1)
        pygame.draw.line(surf, colour, (x + inset, y + dy), (x + half, y + dy), 1)
    for cx, r in ((x, 7), (x - half - 6, 4), (x + half + 6, 4)):
        points = [(cx, y + 1 - r), (cx + r, y + 1), (cx, y + 1 + r), (cx - r, y + 1)]
        pygame.draw.polygon(surf, theme.accent, points)
        pygame.draw.polygon(surf, theme.accent_dark, points, 1)
    pygame.draw.circle(surf, theme.seal[0], (x, y + 1), 2)


def _title(text: str, font: pygame.font.Font, theme: PageTheme) -> pygame.Surface:
    """A title in a metal running from light at its top to dark at its foot, edged in ink and
    standing a little off the page on its shadow."""
    mask = font.render(text, True, (255, 255, 255))
    w, h = mask.get_size()
    top, bottom = theme.title
    gradient = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        k = min(1.0, max(0.0, (y - h * 0.18) / (h * 0.64)))     # the font's own space above and below kept flat
        gradient.fill(tuple(round(a + (b - a) * k) for a, b in zip(top, bottom)) + (255,), (0, y, w, 1))
    face = mask.copy()
    face.blit(gradient, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    edge = font.render(text, True, INK)
    shadow = font.render(text, True, (0, 0, 0))
    shadow.set_alpha(70)
    label = pygame.Surface((w + 4, h + 5), pygame.SRCALPHA)
    label.blit(shadow, (3, 4))
    for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
        label.blit(edge, (dx, dy))
    label.blit(face, (1, 1))
    return label


def _plaque(surf: pygame.Surface, font: pygame.font.Font, text: str, center: Tuple[float, float],
            theme: PageTheme) -> pygame.Rect:
    """A small plate of the page's metal with engraved text, a nail at each end."""
    label = font.render(text, True, INK)
    rect = label.get_rect(center=center).inflate(36, 8)
    pygame.draw.rect(surf, theme.accent_light, rect, border_radius=3)
    pygame.draw.line(surf, (250, 246, 236), (rect.left + 4, rect.top + 2), (rect.right - 5, rect.top + 2), 1)
    pygame.draw.rect(surf, theme.accent_dark, rect, 2, border_radius=3)
    pygame.draw.rect(surf, theme.accent, rect.inflate(-6, -6), 1, border_radius=2)
    for x in (rect.left + 10, rect.right - 11):
        pygame.draw.circle(surf, theme.accent_dark, (x, rect.centery), 3)
        pygame.draw.circle(surf, theme.accent_light, (x - 1, rect.centery - 1), 1)
    surf.blit(label, label.get_rect(center=rect.center))
    return rect


def _tab(surf: pygame.Surface, rect: pygame.Rect, label: str, font: pygame.font.Font, current: bool,
         hovered: bool, theme: PageTheme, text_shift: int = 10) -> None:
    """A page's tab in its own page's colours: dark and edged twice for the page shown. Its label
    sits *text_shift* right of the middle, clear of a picture at its left."""
    if current:
        fill, edge, ink = theme.tab_current
    else:
        fill, hover, edge, ink = theme.tab_other
        fill = hover if hovered else fill
    pygame.draw.rect(surf, fill, rect, border_radius=4)
    pygame.draw.rect(surf, edge, rect, 2, border_radius=4)
    if current:
        pygame.draw.rect(surf, edge, rect.inflate(-8, -8), 1, border_radius=3)
    text = font.render(label, True, ink)
    surf.blit(text, text.get_rect(center=(rect.centerx + text_shift, rect.centery)))


def _icon(surf: pygame.Surface, kind: str, center: Tuple[int, int], theme: PageTheme = GOLD_PAGE) -> None:
    """A streak's notches in the page's metal, a perfect hit's gold lozenge, or a sawn log's end."""
    x, y = center
    if kind == STREAK:
        for i, height in enumerate((8, 13, 18)):
            rect = pygame.Rect(x - 10 + i * 8, y + 9 - height, 5, height)
            pygame.draw.rect(surf, theme.accent, rect, border_radius=1)
            pygame.draw.rect(surf, theme.accent_dark, rect, 1, border_radius=1)
    elif kind == PERFECT:
        points = [(x, y - 10), (x + 9, y), (x, y + 10), (x - 9, y)]
        pygame.draw.polygon(surf, GOLD, points)
        pygame.draw.polygon(surf, _GOLD_DARK, points, 1)
        pygame.draw.line(surf, BRASS_LIGHT, (x - 3, y - 2), (x, y - 6), 2)
    else:
        pygame.draw.circle(surf, (214, 178, 122), (x, y), 10)
        pygame.draw.circle(surf, (138, 96, 56), (x, y), 6, 1)
        pygame.draw.circle(surf, (138, 96, 56), (x, y), 2, 1)
        pygame.draw.circle(surf, (92, 62, 36), (x, y), 10, 2)


# ----------------------------------------------------------------------
# The window
# ----------------------------------------------------------------------

def open_records_window(game_state: 'GameState') -> None:
    game_state.info_window = RecordsWindow(game_state.screen, game_state)


class RecordsWindow(_BaseDialog):
    COLUMNS = 3
    CARD_W, CARD_H = 392, 132
    GAP = 10
    MARGIN = 44                  # the page's sides and foot, clear of the corner blocks
    FRAME_INSET = 13
    TITLE_Y = 49                 # on its tablet, which stands over the frame's band
    TAB_TOP = 100
    TAB_W, TAB_H = 200, 38
    BODY_TOP = 152
    PLAQUES_H = 46               # the fishing page's plaques, over the cards
    BODY_H = PLAQUES_H + 3 * CARD_H + 2 * GAP
    FOOT_H = 24                  # under the body, clear of the frame's band: the woodhacking's hint
    W = COLUMNS * CARD_W + (COLUMNS - 1) * GAP + 2 * MARGIN
    H = BODY_TOP + BODY_H + FOOT_H + MARGIN

    PICTURE_W, PICTURE_H = 140, 108
    SCORES_W = 540               # the top scores' leaf; the overall figures have the rest
    HEAD_H = 52                  # a leaf's heading
    BEST_ROW_H = 120             # the best score, in its wreath
    SCORE_ROW_H = (BODY_H - HEAD_H - BEST_ROW_H) // (WOODHACKING_TOP_SCORES - 1)
    OVERALL_ROW_H = (BODY_H - HEAD_H) // 5
    TOOLTIP_W, TOOLTIP_LINE_H, TOOLTIP_PAD = 270, 30, 12

    def __init__(self, screen: pygame.Surface, game_state: 'GameState') -> None:
        super().__init__(screen, game_state, self.W, self.H)
        self.sheet_title_font = self._medici(46, 36)
        self.name_font = self._medici(26, 24)
        self.score_font = self._medici(32, 28)
        self.best_font = self._medici(42, 36)
        self.page = PAGE_FISHING
        self._pages: Dict[str, pygame.Surface] = {}
        self.close_rect = pygame.Rect(0, 0, 30, 30)
        self.close_rect.center = (self.panel.right - 64, self.panel.top + 60)   # below the frame's band

        tabs_w = len(PAGES) * self.TAB_W + (len(PAGES) - 1) * self.GAP
        left = self.panel.centerx - tabs_w // 2
        self.tab_rects = {page: pygame.Rect(left + i * (self.TAB_W + self.GAP), self.panel.top + self.TAB_TOP,
                                            self.TAB_W, self.TAB_H)
                          for i, page in enumerate(PAGES)}
        self.body = pygame.Rect(self.panel.left + self.MARGIN, self.panel.top + self.BODY_TOP,
                                self.W - 2 * self.MARGIN, self.BODY_H)
        self.scores_rect = pygame.Rect(self.body.topleft, (self.SCORES_W, self.BODY_H))
        self.overall_rect = pygame.Rect(self.scores_rect.right + self.GAP, self.body.top,
                                        self.body.width - self.SCORES_W - self.GAP, self.BODY_H)

    @staticmethod
    def _medici(size: int, fallback: int) -> pygame.font.Font:
        try:
            return pygame.font.Font(os.path.join(FONTS_PATH, "Medici Text.ttf"), size)
        except Exception:
            return pygame.font.SysFont("arial", fallback)

    @property
    def _stats(self) -> Statistics:
        return self.game_state.game.depot.stats

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        for page, rect in self.tab_rects.items():
            if rect.collidepoint(pos):
                self.page = page
                return True
        return super().handle_click(pos)

    def score_row_rect(self, index: int) -> pygame.Rect:
        """Where a row of the top scores lies on the screen; the first, the best, is the tallest."""
        top = self.scores_rect.top + self.HEAD_H
        if index == 0:
            return pygame.Rect(self.scores_rect.left, top, self.scores_rect.width, self.BEST_ROW_H)
        return pygame.Rect(self.scores_rect.left, top + self.BEST_ROW_H + (index - 1) * self.SCORE_ROW_H,
                           self.scores_rect.width, self.SCORE_ROW_H)

    def hovered_score(self, pos: Tuple[int, int]) -> Optional[int]:
        """Which of the top scores the pointer is over, if it is on their page and that row holds one."""
        if self.page != PAGE_WOODHACKING:
            return None
        for index in range(len(self._stats.woodhacking_scores)):
            if self.score_row_rect(index).collidepoint(pos):
                return index
        return None

    @property
    def theme(self) -> PageTheme:
        return PAGE_THEMES[self.page]

    def _local(self, rect: pygame.Rect) -> pygame.Rect:
        """A rect on the screen, as it lies on the page's own sheet."""
        return rect.move(-self.panel.left, -self.panel.top)

    # -- the sheet ---------------------------------------------------------

    def _build_sheet(self) -> pygame.Surface:
        """What every page has, in its own colours: the paper, the frame, its corner blocks and the title."""
        theme = self.theme
        sheet = framed_sheet((self.W, self.H), corner_blocks=True, theme=theme.sheet)
        whole = sheet.get_rect()
        title = _title("Records", self.sheet_title_font, theme)
        title_tablet(sheet, title, whole.centerx, theme.sheet, self.TITLE_Y)   # over the band, clear of its waves
        return sheet

    def _build_page(self, page: str) -> pygame.Surface:
        sheet = self._build_sheet()
        if page == PAGE_FISHING:
            self._draw_fishing(sheet)
        else:
            self._draw_woodhacking(sheet)
        return sheet

    def _rows(self, surf: pygame.Surface, rows: Sequence[Tuple[str, str]], x0: int, x1: int, y: int, step: int,
              lit: bool) -> None:
        """Label, dotted line, value, one under the other."""
        for label, value in rows:
            name = self.body_font.render(label, True, _FAINT_INK if not lit else INK)
            shown = self.body_font.render(value, True, _FAINT_INK if not lit else INK)
            surf.blit(name, (x0, y))
            right = shown.get_rect(topright=(x1, y))
            surf.blit(shown, right)
            _leader(surf, x0 + name.get_width() + 6, right.left - 5, y + name.get_height() - 7, self.theme)
            y += step

    # -- the fishing page --------------------------------------------------

    def _draw_card(self, surf: pygame.Surface, rect: pygame.Rect, record: FishRecord) -> None:
        theme = self.theme
        _leaf(surf, rect, record.caught, theme)
        picture = pygame.Rect(rect.left + 12, 0, self.PICTURE_W, self.PICTURE_H)
        picture.centery = rect.centery
        _picture_frame(surf, picture, record.caught, theme)
        surf.blit(_water(picture.size, record.caught), picture)
        fish = portrait(record.species, record.caught)
        surf.blit(fish, fish.get_rect(center=picture.center))

        x0, x1 = picture.right + 16, rect.right - 14
        font = self.name_font if record.caught else self.score_font   # a lone question mark is small
        name = font.render(record.name, True, INK if record.caught else _FAINT_INK)
        surf.blit(name, name.get_rect(midleft=(x0, rect.top + 26)))
        pygame.draw.line(surf, theme.accent if record.caught else _FAINT_RULE, (x0, rect.top + 44), (x1, rect.top + 44), 1)
        self._rows(surf, record.rows(), x0, x1, rect.top + 50, 25, record.caught)

    def _draw_fishing(self, surf: pygame.Surface) -> None:
        stats = self._stats
        records = fish_records(stats)
        known = sum(record.caught for record in records)
        body = self._local(self.body)
        for dx, text in ((-320, f"Fish caught: {stats.fish_caught:,}"),
                         (0, f"Kinds found: {known} of {len(records)}"),
                         (320, f"Best day's fishing: {stats.fishing_highscore:,.2f} coins")):
            _plaque(surf, self.body_font, text, (body.centerx + dx, body.top + 16), self.theme)
        y = body.top + self.PLAQUES_H
        for index, record in enumerate(records):
            row, column = divmod(index, self.COLUMNS)
            rect = pygame.Rect(body.left + column * (self.CARD_W + self.GAP), y + row * (self.CARD_H + self.GAP),
                               self.CARD_W, self.CARD_H)
            self._draw_card(surf, rect, record)

    # -- the woodhacking page ----------------------------------------------

    def _heading(self, surf: pygame.Surface, rect: pygame.Rect, text: str) -> None:
        label = self.name_font.render(text, True, INK)
        surf.blit(label, label.get_rect(center=(rect.centerx, rect.top + 24)))
        _divider(surf, (rect.centerx, rect.top + self.HEAD_H - 6), 110, self.theme)

    def _draw_score_row(self, surf: pygame.Surface, index: int, entry: Optional[Dict[str, Any]]) -> None:
        row = self._local(self.score_row_rect(index))
        seal = pygame.Rect(row.left + 16, 0, 38, 38)
        seal.centery = row.centery
        _seal(surf, seal, ROMAN[index], self.body_font, entry is not None, self.theme)
        date = self.body_font.render(date_text(entry) if entry else NOT_TRACKED, True, INK if entry else _FAINT_INK)
        score = score_text(entry) if entry else NOT_TRACKED
        if index == 0 and entry:
            centre = (seal.right + 80, row.centery - 4)
            draw_laurel(surf, centre, 44, *self.theme.laurel)
            shown = self.best_font.render(score, True, INK)
            surf.blit(shown, shown.get_rect(center=(centre[0], centre[1] - 2)))
            best = self.name_font.render("Your best", True, self.theme.seal[0])
            surf.blit(best, best.get_rect(bottomright=(row.right - 18, row.centery - 2)))
            surf.blit(date, date.get_rect(topright=(row.right - 18, row.centery + 4)))
        else:
            shown = self.score_font.render(score, True, INK if entry else _FAINT_INK)
            surf.blit(shown, shown.get_rect(center=(seal.right + 80, row.centery)))
            surf.blit(date, date.get_rect(midright=(row.right - 18, row.centery)))

    def _draw_scores(self, surf: pygame.Surface) -> None:
        rect = self._local(self.scores_rect)
        _leaf(surf, rect, theme=self.theme)
        self._heading(surf, rect, f"Top {WOODHACKING_TOP_SCORES} scores")
        scores = self._stats.woodhacking_scores
        for index in range(WOODHACKING_TOP_SCORES):
            self._draw_score_row(surf, index, scores[index] if index < len(scores) else None)
            if index:
                top = self._local(self.score_row_rect(index)).top
                pygame.draw.line(surf, self.theme.accent, (rect.left + 14, top), (rect.right - 14, top), 1)

    def _draw_overall(self, surf: pygame.Surface) -> None:
        rect = self._local(self.overall_rect)
        _leaf(surf, rect, theme=self.theme)
        self._heading(surf, rect, "Overall")
        y = rect.top + self.HEAD_H
        for (label, value), kind in zip(overall_lines(self._stats), _OVERALL_ICONS):
            middle = y + self.OVERALL_ROW_H // 2
            _icon(surf, kind, (rect.left + 34, middle), self.theme)
            name = self.body_font.render(label, True, INK)
            surf.blit(name, name.get_rect(midleft=(rect.left + 58, middle)))
            shown = self.score_font.render(value, True, INK if value != NOT_TRACKED else _FAINT_INK)
            right = shown.get_rect(midright=(rect.right - 22, middle))
            surf.blit(shown, right)
            _leader(surf, rect.left + 58 + name.get_width() + 8, right.left - 8, middle + 7, self.theme)
            y += self.OVERALL_ROW_H

    def _draw_woodhacking(self, surf: pygame.Surface) -> None:
        self._draw_scores(surf)
        self._draw_overall(surf)
        hint = self.body_font.render(_HOVER_HINT, True, _FAINT_INK)
        foot = self._local(self.body).bottom + (self.FOOT_H + self.MARGIN - 38) // 2   # between the leaves and the band
        surf.blit(hint, hint.get_rect(center=(self.W // 2, foot)))

    def _draw_score_tooltip(self, surf: pygame.Surface, entry: Dict[str, Any], mouse: Tuple[int, int],
                            off: Tuple[int, int]) -> None:
        details = score_details(entry)
        box = pygame.Rect(0, 0, self.TOOLTIP_W, len(details) * self.TOOLTIP_LINE_H + 2 * self.TOOLTIP_PAD)
        box.topleft = (mouse[0] + 16, mouse[1] + 12)
        box.clamp_ip(self.panel.inflate(-2 * self.FRAME_INSET, -2 * self.FRAME_INSET))
        box.move_ip(*off)
        shadow = pygame.Surface(box.size, pygame.SRCALPHA)
        shadow.fill((0, 0, 0, 80))
        surf.blit(shadow, box.move(4, 5))
        pygame.draw.rect(surf, PARCHMENT, box, border_radius=4)
        pygame.draw.rect(surf, self.theme.accent_dark, box, 2, border_radius=4)
        pygame.draw.rect(surf, self.theme.accent, box.inflate(-6, -6), 1, border_radius=3)
        y = box.top + self.TOOLTIP_PAD
        for (label, value), kind in zip(details, _DETAIL_ICONS):
            middle = y + self.TOOLTIP_LINE_H // 2
            _icon(surf, kind, (box.left + 24, middle), self.theme)
            name = self.body_font.render(label, True, INK)
            surf.blit(name, name.get_rect(midleft=(box.left + 44, middle)))
            shown = self.body_font.render(value, True, INK)
            surf.blit(shown, shown.get_rect(midright=(box.right - self.TOOLTIP_PAD - 2, middle)))
            y += self.TOOLTIP_LINE_H

    # -- what changes from frame to frame ----------------------------------

    def _draw_tabs(self, surf: pygame.Surface, off: Tuple[int, int], mouse: Tuple[int, int]) -> None:
        for page, rect in self.tab_rects.items():
            shown = rect.move(*off)
            _tab(surf, shown, page, self.body_font, page == self.page, rect.collidepoint(mouse), PAGE_THEMES[page])
            if page == PAGE_FISHING:
                glyphs.fish(surf, (shown.left + 26, shown.centery), 26)
            else:
                glyphs.chopping_stump(surf, (shown.left + 26, shown.centery + 2), 28)

    def _draw_close(self, surf: pygame.Surface, off: Tuple[int, int], mouse: Tuple[int, int]) -> None:
        """Closing is a seal inside the frame in the page's colours, with a cross on it."""
        rect = self.close_rect.move(*off)
        fill, edge, _ = self.theme.tab_current
        if self.close_rect.collidepoint(mouse):
            fill = tuple(min(255, c + 28) for c in fill)
        pygame.draw.rect(surf, fill, rect, border_radius=3)
        pygame.draw.rect(surf, edge, rect, 2, border_radius=3)
        inset = 9
        for start, end in (((rect.left + inset, rect.top + inset), (rect.right - inset - 1, rect.bottom - inset - 1)),
                           ((rect.left + inset, rect.bottom - inset - 1), (rect.right - inset - 1, rect.top + inset))):
            pygame.draw.line(surf, self.theme.accent_light, start, end, 3)

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return

        use_temp = alpha_scale < 1.0
        if use_temp:
            surf = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            off = (-self.panel.left, -self.panel.top)
        else:
            surf = self.screen
            off = (0, 0)
            shadow = pygame.Surface(self.panel.size, pygame.SRCALPHA)
            shadow.fill((0, 0, 0, 90))
            surf.blit(shadow, self.panel.move(6, 8))

        if self.page not in self._pages:
            self._pages[self.page] = self._build_page(self.page)
        surf.blit(self._pages[self.page], self.panel.move(*off))

        mouse = pygame.mouse.get_pos()
        self._draw_tabs(surf, off, mouse)
        self._draw_close(surf, off, mouse)

        hovered = self.hovered_score(mouse)
        if hovered is not None:
            row = self.score_row_rect(hovered).move(*off).inflate(-8, 0)
            glow = pygame.Surface(row.size, pygame.SRCALPHA)
            glow.fill((*self.theme.glow, 70))
            surf.blit(glow, row)
            self._draw_score_tooltip(surf, self._stats.woodhacking_scores[hovered], mouse, off)

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, self.panel.topleft)
