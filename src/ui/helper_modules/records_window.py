"""The guild's records of the player's successes, opened at the guildhall.

So far the minigames', a page each. Fishing: a card for every kind of fish with its
portrait, name, how many were landed, their weight together and the biggest one; a
kind never caught is greyed out with a question mark for its name. Woodhacking: the
top scores with their dates, what the player has done over all sessions, and when a
score is hovered what its session made up. Whatever was not tracked yet when a
session was played, as in an older save, shows as ``NOT_TRACKED``.
"""

import datetime
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

import pygame

from .loan_dialog import _BaseDialog
from .statistics_view import _fmt_woodhacking_score
from ...config.colors import BLACK, DARK_BROWN, GOLD, GRAY
from ...config.constants import FONTS_PATH
from ...models.minigames.fishing_pond import SPECIES, Species, format_kg
from ...models.minigames.fishing_scene import fish_sprite
from ...models.statistics import Statistics, WOODHACKING_TOP_SCORES
from ...sim.calendar import format_date

if TYPE_CHECKING:
    from ...game_state import GameState

UNKNOWN_NAME = "?"
NOT_TRACKED = "-"
PORTRAIT_LENGTH = 30             # low pixels long, whatever its kind's size: one drawn small would show nothing
PORTRAIT_SCALE = 4
_GREY_ALPHA = 120                # how faint the portrait of a kind not caught yet is

PAGE_FISHING, PAGE_WOODHACKING = "Fishing", "Woodhacking"
PAGES = (PAGE_FISHING, PAGE_WOODHACKING)

_portraits = {}                  # (species key, caught) -> the portrait


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

    def lines(self) -> List[str]:
        if not self.caught:
            return [f"Caught: {NOT_TRACKED}", f"Total: {NOT_TRACKED}", f"Biggest: {NOT_TRACKED}"]
        biggest = f"{self.biggest_cm:.0f} cm, {format_kg(self.species.kg(self.biggest_cm))}"
        return [f"Caught: {self.count:,}", f"Total: {format_kg(self.kg)}", f"Biggest: {biggest}"]


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
# The window
# ----------------------------------------------------------------------

def open_records_window(game_state: 'GameState') -> None:
    game_state.info_window = RecordsWindow(game_state.screen, game_state)


class RecordsWindow(_BaseDialog):
    COLUMNS = 3
    CARD_W, CARD_H = 350, 128
    GAP = 10
    TAB_W, TAB_H = 170, 32
    TAB_GAP = 12                 # under the tabs, before the page
    SUMMARY_H = 34
    BODY_H = SUMMARY_H + 3 * CARD_H + 2 * GAP
    W = COLUMNS * CARD_W + (COLUMNS - 1) * GAP + 2 * _BaseDialog.PAD
    H = _BaseDialog.HDR + TAB_H + TAB_GAP + BODY_H + 2 * _BaseDialog.PAD

    SCORES_W = 480               # the top scores' panel; the overall figures have the rest
    PANEL_HEAD = 50              # a panel's heading
    SCORE_ROW_H = OVERALL_ROW_H = (BODY_H - PANEL_HEAD) // 5   # they fill their panels, and line up across them
    TOOLTIP_W, TOOLTIP_LINE_H, TOOLTIP_PAD = 240, 28, 10

    def __init__(self, screen: pygame.Surface, game_state: 'GameState') -> None:
        super().__init__(screen, game_state, self.W, self.H)
        try:
            self.name_font = pygame.font.Font(os.path.join(FONTS_PATH, "Medici Text.ttf"), 26)
        except Exception:
            self.name_font = pygame.font.SysFont("arial", 24)
        self.page = PAGE_FISHING
        tabs_w = len(PAGES) * self.TAB_W + (len(PAGES) - 1) * self.GAP
        left = self.panel.centerx - tabs_w // 2
        top = self.panel.top + self.HDR
        self.tab_rects = {page: pygame.Rect(left + i * (self.TAB_W + self.GAP), top, self.TAB_W, self.TAB_H)
                          for i, page in enumerate(PAGES)}
        self.body = pygame.Rect(self.panel.left + self.PAD, top + self.TAB_H + self.TAB_GAP,
                                self.W - 2 * self.PAD, self.BODY_H)
        self.scores_rect = pygame.Rect(self.body.topleft, (self.SCORES_W, self.BODY_H))
        self.overall_rect = pygame.Rect(self.scores_rect.right + self.GAP, self.body.top,
                                        self.body.width - self.SCORES_W - self.GAP, self.BODY_H)

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
        """Where a row of the top scores lies on the screen."""
        return pygame.Rect(self.scores_rect.left, self.scores_rect.top + self.PANEL_HEAD + index * self.SCORE_ROW_H,
                           self.scores_rect.width, self.SCORE_ROW_H)

    def hovered_score(self, pos: Tuple[int, int]) -> Optional[int]:
        """Which of the top scores the pointer is over, if it is on their page and that row holds one."""
        if self.page != PAGE_WOODHACKING:
            return None
        for index in range(len(self._stats.woodhacking_scores)):
            if self.score_row_rect(index).collidepoint(pos):
                return index
        return None

    # -- the fishing page --------------------------------------------------

    def _draw_card(self, surf: pygame.Surface, rect: pygame.Rect, record: FishRecord) -> None:
        self._draw_band(surf, rect, record.caught)
        picture = portrait(record.species, record.caught)
        surf.blit(picture, picture.get_rect(center=(rect.left + 74, rect.centery)))

        x = rect.left + 146
        name = self.name_font.render(record.name, True, DARK_BROWN if record.caught else GRAY)
        surf.blit(name, (x, rect.top + 10))
        y = rect.top + 46
        for line in record.lines():
            y = self._text(surf, line, x, y, BLACK if record.caught else GRAY) + 3

    def _draw_fishing(self, surf: pygame.Surface, body: pygame.Rect) -> None:
        stats = self._stats
        records = fish_records(stats)
        known = sum(record.caught for record in records)
        summary = (f"Fish caught: {stats.fish_caught:,}   |   Kinds: {known} of {len(records)}   |   "
                   f"Best day's fishing: {stats.fishing_highscore:,.2f} coins")
        self._text(surf, summary, body.centerx, body.top, DARK_BROWN, center=True)
        y = body.top + self.SUMMARY_H
        for index, record in enumerate(records):
            row, column = divmod(index, self.COLUMNS)
            rect = pygame.Rect(body.left + column * (self.CARD_W + self.GAP), y + row * (self.CARD_H + self.GAP),
                               self.CARD_W, self.CARD_H)
            self._draw_card(surf, rect, record)

    # -- the woodhacking page ----------------------------------------------

    @staticmethod
    def _draw_band(surf: pygame.Surface, rect: pygame.Rect, lit: bool = True) -> None:
        band = pygame.Surface(rect.size, pygame.SRCALPHA)
        band.fill((255, 245, 215, 90) if lit else (90, 80, 70, 45))
        surf.blit(band, rect)
        pygame.draw.rect(surf, DARK_BROWN if lit else GRAY, rect, 1)

    def _heading(self, surf: pygame.Surface, rect: pygame.Rect, text: str) -> None:
        label = self.name_font.render(text, True, DARK_BROWN)
        surf.blit(label, label.get_rect(midtop=(rect.centerx, rect.top + 12)))

    def _draw_scores(self, surf: pygame.Surface, rect: pygame.Rect, off: Tuple[int, int],
                     hovered: Optional[int]) -> None:
        self._draw_band(surf, rect)
        self._heading(surf, rect, f"Top {WOODHACKING_TOP_SCORES} scores")
        scores = self._stats.woodhacking_scores
        for index in range(WOODHACKING_TOP_SCORES):
            row = self.score_row_rect(index).move(*off)
            if index == hovered:
                glow = pygame.Surface(row.size, pygame.SRCALPHA)
                glow.fill((*GOLD, 90))
                surf.blit(glow, row)
            pygame.draw.line(surf, DARK_BROWN, (row.left + 12, row.top), (row.right - 12, row.top), 1)
            entry = scores[index] if index < len(scores) else None
            colour = BLACK if entry else GRAY
            middle = row.centery
            self._text(surf, f"{index + 1}.", row.left + 18, middle - 12, colour)
            score = self.name_font.render(score_text(entry) if entry else NOT_TRACKED, True,
                                          DARK_BROWN if entry else GRAY)
            surf.blit(score, score.get_rect(midright=(row.left + 130, middle)))
            date = self.body_font.render(date_text(entry) if entry else NOT_TRACKED, True, colour)
            surf.blit(date, date.get_rect(midright=(row.right - 18, middle)))

    def _draw_overall(self, surf: pygame.Surface, rect: pygame.Rect) -> None:
        self._draw_band(surf, rect)
        self._heading(surf, rect, "Overall")
        y = rect.top + self.PANEL_HEAD
        for label, value in overall_lines(self._stats):
            pygame.draw.line(surf, DARK_BROWN, (rect.left + 12, y), (rect.right - 12, y), 1)
            self._text(surf, label, rect.left + 18, y + self.OVERALL_ROW_H // 2 - 12, BLACK)
            shown = self.name_font.render(value, True, DARK_BROWN if value != NOT_TRACKED else GRAY)
            surf.blit(shown, shown.get_rect(midright=(rect.right - 18, y + self.OVERALL_ROW_H // 2)))
            y += self.OVERALL_ROW_H

    def _draw_score_tooltip(self, surf: pygame.Surface, entry: Dict[str, Any], mouse: Tuple[int, int],
                            off: Tuple[int, int]) -> None:
        details = score_details(entry)
        box = pygame.Rect(0, 0, self.TOOLTIP_W, len(details) * self.TOOLTIP_LINE_H + 2 * self.TOOLTIP_PAD)
        box.topleft = (mouse[0] + 16, mouse[1] + 12)
        box.clamp_ip(self.panel.inflate(-2 * self.PAD, -2 * self.PAD))
        box.move_ip(*off)
        pygame.draw.rect(surf, (236, 222, 186), box)
        pygame.draw.rect(surf, DARK_BROWN, box, 2)
        y = box.top + self.TOOLTIP_PAD
        for label, value in details:
            self._text(surf, label, box.left + self.TOOLTIP_PAD, y, BLACK)
            shown = self.body_font.render(value, True, DARK_BROWN)
            surf.blit(shown, shown.get_rect(topright=(box.right - self.TOOLTIP_PAD, y)))
            y += self.TOOLTIP_LINE_H

    def _draw_woodhacking(self, surf: pygame.Surface, off: Tuple[int, int], mouse: Tuple[int, int]) -> None:
        hovered = self.hovered_score(mouse)
        self._draw_scores(surf, self.scores_rect.move(*off), off, hovered)
        self._draw_overall(surf, self.overall_rect.move(*off))
        if hovered is not None:
            self._draw_score_tooltip(surf, self._stats.woodhacking_scores[hovered], mouse, off)

    # -- drawing -----------------------------------------------------------

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

        self._draw_panel(surf, off)
        self._draw_close_btn(surf, off)
        self._draw_title(surf, off, "Records")

        mouse = pygame.mouse.get_pos()
        local_mouse = (mouse[0] + off[0], mouse[1] + off[1])
        for page, rect in self.tab_rects.items():
            self._draw_btn(surf, rect.move(*off), page, local_mouse, active=page == self.page)

        if self.page == PAGE_FISHING:
            self._draw_fishing(surf, self.body.move(*off))
        else:
            self._draw_woodhacking(surf, off, mouse)

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, self.panel.topleft)
