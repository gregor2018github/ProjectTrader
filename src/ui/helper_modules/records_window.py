"""The guild's records of the player's successes, opened at the guildhall.

So far the minigames', a page each, on a sheet like the minigames' how-to pages and
their certificate: browned parchment in a gold frame with flourishes in its corners,
leaves ruled in brass, seals in red ink, brass plaques.

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
from ..paper import draw_paper
from ...config.colors import GOLD, GRAY, PARCHMENT
from ...config.constants import FONTS_PATH
from ...models.minigames.fishing_pond import SPECIES, Species, format_kg
from ...models.minigames.fishing_scene import fish_sprite
from ...models.minigames.tutorial_sheet import BRASS, BRASS_DARK, BRASS_LIGHT, INK, RUBRIC, draw_tab, plaque
from ...models.minigames.woodhacking import draw_divider, draw_flourish, draw_laurel
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

def _leaf(surf: pygame.Surface, rect: pygame.Rect, lit: bool = True) -> None:
    """A paler leaf ruled in brass, as the how-to pages' cards; a duller one for what is still to come."""
    leaf = pygame.Surface(rect.size, pygame.SRCALPHA)
    leaf.fill((255, 248, 226, 110) if lit else (120, 104, 84, 38))
    surf.blit(leaf, rect)
    pygame.draw.rect(surf, BRASS_DARK if lit else _FAINT_INK, rect, 2, border_radius=4)
    pygame.draw.rect(surf, BRASS if lit else (168, 150, 120), rect.inflate(-6, -6), 1, border_radius=3)


def _picture_frame(surf: pygame.Surface, picture: pygame.Rect, lit: bool = True) -> None:
    """The frame round a picture, as on the how-to pages."""
    pygame.draw.rect(surf, INK if lit else _FAINT_INK, picture.inflate(8, 8), border_radius=3)
    pygame.draw.rect(surf, BRASS if lit else (168, 150, 120), picture.inflate(6, 6), 2, border_radius=3)
    pygame.draw.rect(surf, BRASS_DARK if lit else _FAINT_INK, picture.inflate(2, 2), 1)


def _seal(surf: pygame.Surface, rect: pygame.Rect, text: str, font: pygame.font.Font, lit: bool = True) -> None:
    """A red seal with a gold edge and a numeral on it; a pale one for a place not taken yet."""
    pygame.draw.rect(surf, RUBRIC if lit else (206, 190, 156), rect, border_radius=3)
    pygame.draw.rect(surf, GOLD if lit else (168, 150, 120), rect, 2, border_radius=3)
    label = font.render(text, True, BRASS_LIGHT if lit else _FAINT_INK)
    surf.blit(label, label.get_rect(center=rect.center))


def _leader(surf: pygame.Surface, x0: int, x1: int, y: int) -> None:
    """A ledger's dotted line from a label to its value."""
    for x in range(x0, x1, 7):
        surf.fill(BRASS, (x, y, 2, 2))


def _icon(surf: pygame.Surface, kind: str, center: Tuple[int, int]) -> None:
    """A streak's brass notches, a perfect hit's gold lozenge, or a sawn log's end."""
    x, y = center
    if kind == STREAK:
        for i, height in enumerate((8, 13, 18)):
            rect = pygame.Rect(x - 10 + i * 8, y + 9 - height, 5, height)
            pygame.draw.rect(surf, BRASS, rect, border_radius=1)
            pygame.draw.rect(surf, BRASS_DARK, rect, 1, border_radius=1)
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
    MARGIN = 44                  # the page's sides and foot, clear of the frame's flourishes
    FRAME_INSET = 13
    TITLE_Y, DIVIDER_Y = 46, 80
    TAB_TOP = 94
    TAB_W, TAB_H = 200, 38
    BODY_TOP = 146
    PLAQUES_H = 46               # the fishing page's plaques, over the cards
    BODY_H = PLAQUES_H + 3 * CARD_H + 2 * GAP
    W = COLUMNS * CARD_W + (COLUMNS - 1) * GAP + 2 * MARGIN
    H = BODY_TOP + BODY_H + MARGIN

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
        self.close_rect.center = (self.panel.right - 19, self.panel.top + 19)

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

    def _local(self, rect: pygame.Rect) -> pygame.Rect:
        """A rect on the screen, as it lies on the page's own sheet."""
        return rect.move(-self.panel.left, -self.panel.top)

    def _inked(self, text: str, font: pygame.font.Font, colour) -> pygame.Surface:
        """Text with a dark edge, so gold reads on the paper."""
        edge = font.render(text, True, INK)
        label = pygame.Surface((edge.get_width() + 2, edge.get_height() + 2), pygame.SRCALPHA)
        for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
            label.blit(edge, (dx, dy))
        label.blit(font.render(text, True, colour), (1, 1))
        return label

    # -- the sheet ---------------------------------------------------------

    def _build_sheet(self) -> pygame.Surface:
        """What every page has: the paper, the gold frame, its flourishes and the title."""
        sheet = pygame.Surface((self.W, self.H))
        whole = sheet.get_rect()
        draw_paper(sheet, whole, whole.topleft)
        pygame.draw.rect(sheet, _GOLD_DARK, whole, 6)
        pygame.draw.rect(sheet, GOLD, whole.inflate(-4, -4), 3)
        inner = whole.inflate(-2 * self.FRAME_INSET, -2 * self.FRAME_INSET)
        pygame.draw.rect(sheet, _GOLD_DARK, inner, 1)
        for sx, sy, corner in ((1, 1, inner.topleft), (-1, 1, inner.topright),
                               (1, -1, inner.bottomleft), (-1, -1, inner.bottomright)):
            draw_flourish(sheet, corner, sx, sy)
        title = self._inked("Records", self.sheet_title_font, GOLD)
        sheet.blit(title, title.get_rect(center=(whole.centerx, self.TITLE_Y)))
        draw_divider(sheet, (whole.centerx, self.DIVIDER_Y), 170)
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
            _leader(surf, x0 + name.get_width() + 6, right.left - 5, y + name.get_height() - 7)
            y += step

    # -- the fishing page --------------------------------------------------

    def _draw_card(self, surf: pygame.Surface, rect: pygame.Rect, record: FishRecord) -> None:
        _leaf(surf, rect, record.caught)
        picture = pygame.Rect(rect.left + 12, 0, self.PICTURE_W, self.PICTURE_H)
        picture.centery = rect.centery
        _picture_frame(surf, picture, record.caught)
        surf.blit(_water(picture.size, record.caught), picture)
        fish = portrait(record.species, record.caught)
        surf.blit(fish, fish.get_rect(center=picture.center))

        x0, x1 = picture.right + 16, rect.right - 14
        font = self.name_font if record.caught else self.score_font   # a lone question mark is small
        name = font.render(record.name, True, INK if record.caught else _FAINT_INK)
        surf.blit(name, name.get_rect(midleft=(x0, rect.top + 26)))
        pygame.draw.line(surf, BRASS if record.caught else (168, 150, 120), (x0, rect.top + 44), (x1, rect.top + 44), 1)
        self._rows(surf, record.rows(), x0, x1, rect.top + 50, 25, record.caught)

    def _draw_fishing(self, surf: pygame.Surface) -> None:
        stats = self._stats
        records = fish_records(stats)
        known = sum(record.caught for record in records)
        body = self._local(self.body)
        for dx, text in ((-320, f"Fish caught: {stats.fish_caught:,}"),
                         (0, f"Kinds found: {known} of {len(records)}"),
                         (320, f"Best day's fishing: {stats.fishing_highscore:,.2f} coins")):
            plaque(surf, self.body_font, text, (body.centerx + dx, body.top + 16))
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
        draw_divider(surf, (rect.centerx, rect.top + self.HEAD_H - 6), 110)

    def _draw_score_row(self, surf: pygame.Surface, index: int, entry: Optional[Dict[str, Any]]) -> None:
        row = self._local(self.score_row_rect(index))
        seal = pygame.Rect(row.left + 16, 0, 38, 38)
        seal.centery = row.centery
        _seal(surf, seal, ROMAN[index], self.body_font, entry is not None)
        date = self.body_font.render(date_text(entry) if entry else NOT_TRACKED, True, INK if entry else _FAINT_INK)
        score = score_text(entry) if entry else NOT_TRACKED
        if index == 0 and entry:
            centre = (seal.right + 80, row.centery - 4)
            draw_laurel(surf, centre, 44)
            shown = self.best_font.render(score, True, INK)
            surf.blit(shown, shown.get_rect(center=(centre[0], centre[1] - 2)))
            best = self.name_font.render("Your best", True, RUBRIC)
            surf.blit(best, best.get_rect(bottomright=(row.right - 18, row.centery - 2)))
            surf.blit(date, date.get_rect(topright=(row.right - 18, row.centery + 4)))
        else:
            shown = self.score_font.render(score, True, INK if entry else _FAINT_INK)
            surf.blit(shown, shown.get_rect(center=(seal.right + 80, row.centery)))
            surf.blit(date, date.get_rect(midright=(row.right - 18, row.centery)))

    def _draw_scores(self, surf: pygame.Surface) -> None:
        rect = self._local(self.scores_rect)
        _leaf(surf, rect)
        self._heading(surf, rect, f"Top {WOODHACKING_TOP_SCORES} scores")
        scores = self._stats.woodhacking_scores
        for index in range(WOODHACKING_TOP_SCORES):
            self._draw_score_row(surf, index, scores[index] if index < len(scores) else None)
            if index:
                top = self._local(self.score_row_rect(index)).top
                pygame.draw.line(surf, BRASS, (rect.left + 14, top), (rect.right - 14, top), 1)

    def _draw_overall(self, surf: pygame.Surface) -> None:
        rect = self._local(self.overall_rect)
        _leaf(surf, rect)
        self._heading(surf, rect, "Overall")
        y = rect.top + self.HEAD_H
        for (label, value), kind in zip(overall_lines(self._stats), _OVERALL_ICONS):
            middle = y + self.OVERALL_ROW_H // 2
            _icon(surf, kind, (rect.left + 34, middle))
            name = self.body_font.render(label, True, INK)
            surf.blit(name, name.get_rect(midleft=(rect.left + 58, middle)))
            shown = self.score_font.render(value, True, INK if value != NOT_TRACKED else _FAINT_INK)
            right = shown.get_rect(midright=(rect.right - 22, middle))
            surf.blit(shown, right)
            _leader(surf, rect.left + 58 + name.get_width() + 8, right.left - 8, middle + 7)
            y += self.OVERALL_ROW_H

    def _draw_woodhacking(self, surf: pygame.Surface) -> None:
        self._draw_scores(surf)
        self._draw_overall(surf)
        hint = self.body_font.render(_HOVER_HINT, True, _FAINT_INK)
        surf.blit(hint, hint.get_rect(center=(self.W // 2, self.H - self.MARGIN // 2 - 5)))

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
        pygame.draw.rect(surf, BRASS_DARK, box, 2, border_radius=4)
        pygame.draw.rect(surf, BRASS, box.inflate(-6, -6), 1, border_radius=3)
        y = box.top + self.TOOLTIP_PAD
        for (label, value), kind in zip(details, _DETAIL_ICONS):
            middle = y + self.TOOLTIP_LINE_H // 2
            _icon(surf, kind, (box.left + 24, middle))
            name = self.body_font.render(label, True, INK)
            surf.blit(name, name.get_rect(midleft=(box.left + 44, middle)))
            shown = self.body_font.render(value, True, INK)
            surf.blit(shown, shown.get_rect(midright=(box.right - self.TOOLTIP_PAD - 2, middle)))
            y += self.TOOLTIP_LINE_H

    # -- what changes from frame to frame ----------------------------------

    def _draw_tabs(self, surf: pygame.Surface, off: Tuple[int, int], mouse: Tuple[int, int]) -> None:
        for page, rect in self.tab_rects.items():
            shown = rect.move(*off)
            draw_tab(surf, shown, page, self.body_font, page == self.page, False, rect.collidepoint(mouse))
            if page == PAGE_FISHING:
                glyphs.fish(surf, (shown.left + 26, shown.centery), 26)
            else:
                glyphs.chopping_stump(surf, (shown.left + 26, shown.centery + 2), 28)

    def _draw_close(self, surf: pygame.Surface, off: Tuple[int, int], mouse: Tuple[int, int]) -> None:
        """Closing is a seal over the frame's corner, with a cross on it."""
        rect = self.close_rect.move(*off)
        pygame.draw.rect(surf, (168, 52, 44) if self.close_rect.collidepoint(mouse) else RUBRIC, rect, border_radius=3)
        pygame.draw.rect(surf, GOLD, rect, 2, border_radius=3)
        inset = 9
        for start, end in (((rect.left + inset, rect.top + inset), (rect.right - inset - 1, rect.bottom - inset - 1)),
                           ((rect.left + inset, rect.bottom - inset - 1), (rect.right - inset - 1, rect.top + inset))):
            pygame.draw.line(surf, BRASS_LIGHT, start, end, 3)

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
            glow.fill((*GOLD, 70))
            surf.blit(glow, row)
            self._draw_score_tooltip(surf, self._stats.woodhacking_scores[hovered], mouse, off)

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, self.panel.topleft)
