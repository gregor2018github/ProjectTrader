"""The sheet announcing a rise in rank, opened the moment it happens (`Game._show_next_notice`).

A certificate like the minigames': the rank's numeral in a laurel wreath, its name, where it
stands on the ladder, what it opens, and how far the player already is along the road to the
next one. It shows the standing at the moment it opens, while the game waits behind it, so the
sheet is drawn once; only the sparkles round the wreath and the button are drawn every frame.

The player may well be clicking away at the market when it opens, so for its first moments
(`INPUT_DELAY_S`) it takes no input and shows no button: a click meant for something else
does not close it unread.
"""

import math
import os
from typing import List, NamedTuple, Optional, Tuple, TYPE_CHECKING

import pygame

from .info_window import _dim_overlay
from .loan_dialog import _BaseDialog
from .records_window import _leaf
from ...config.colors import DARK_GREEN, GOLD
from ...config.constants import FONTS_PATH
from ...models.merchant_rank import CONDITIONS, CONDITION_LABELS, Rank, RankRise, format_amount
from ...models.minigames.tutorial_sheet import (
    BRASS, BRASS_DARK, BUTTON_SIZE, INK, RUBRIC, draw_button, framed_sheet, inked, plaque,
)
from ...models.minigames.woodhacking import draw_divider, draw_laurel

if TYPE_CHECKING:
    from ...game_state import GameState

BUTTON_LABEL = "Onward"
INPUT_DELAY_S = 0.5              # how long it ignores input after opening
ENTRANCE_S = 0.3                 # how long it takes to settle into place
ENTRANCE_DROP = 26               # pixels it comes down by

ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")
RANK_WORDS = {                   # a line for each rank that can be risen to
    "Hawker": "The market has learned your voice, and the stallholders nod as you pass.",
    "Chapman": "You keep a proper store now, and folk come looking for your wares.",
    "Trader": "Your word carries weight at the booths, and your goods go where you send them.",
    "Merchant": "The town's traders seek your counsel, and your ledgers are thick with their names.",
    "Burgher": "You are a citizen of standing, and the town's doors open at your knock.",
    "Guildmaster": "The guild's seal is in your keeping, and the town's trade answers to you.",
    "Patrician": "Your house stands among the first of the town, and your name will outlast you.",
}
TOP_OF_THE_LADDER = "No rank stands higher. All that is left is to keep it."

_LETTER_W = {"I": 10, "V": 24, "X": 24}
_LETTER_GAP = 4
_NUMERAL_H = 34

_FAINT_INK = (120, 104, 84)
_TRACK = (120, 104, 84, 70)      # a progress bar's empty part

# The sheet's layout, top to bottom
W = 820
MARGIN = 44
TITLE_Y, DIVIDER_Y = 50, 84
WREATH_Y, WREATH_R = 168, 58
SPOKEN_Y = 258                   # "The town now speaks of you as"
NAME_Y = 304
WORDS_Y = 350
LADDER_Y = 398
LADDER_END = 448                 # under the ladder's names
PLAQUE_H = 46                    # what it opens, if anything
HEAD_H = 50                      # the heading of the road's leaf
ROW_H = 33
WORDS_LEAF_H = 62                # the leaf at the top of the ladder
BUTTON_GAP, FOOT = 14, 34


class RoadRow(NamedTuple):
    """One condition of the next rank against what the player has of it."""
    label: str
    have: str
    need: str
    share: float                 # 0 to 1, how far along
    met: bool


def road_rows(next_rank: Rank, standing: dict) -> List[RoadRow]:
    rows = []
    for condition in CONDITIONS:
        have, need = standing[condition], getattr(next_rank, condition)
        share = 1.0 if need <= 0 else max(0.0, min(1.0, have / need))
        rows.append(RoadRow(CONDITION_LABELS[condition], format_amount(condition, have),
                            format_amount(condition, need), share, have >= need))
    return rows


def numeral_width(numeral: str) -> int:
    return sum(_LETTER_W[letter] for letter in numeral) + _LETTER_GAP * (len(numeral) - 1)


def draw_numeral(surf: pygame.Surface, numeral: str, centre: Tuple[int, int]) -> None:
    """A Roman numeral in plain strokes, as cut in stone: the blackletter's I reads as a J."""
    x = centre[0] - numeral_width(numeral) // 2
    top, bottom = centre[1] - _NUMERAL_H // 2, centre[1] + _NUMERAL_H // 2
    for letter in numeral:
        width = _LETTER_W[letter]
        if letter == "I":
            pygame.draw.line(surf, RUBRIC, (x + width // 2, top), (x + width // 2, bottom), 4)
        elif letter == "V":
            pygame.draw.line(surf, RUBRIC, (x + 2, top), (x + width // 2, bottom), 4)
            pygame.draw.line(surf, RUBRIC, (x + width - 2, top), (x + width // 2, bottom), 3)
        else:
            pygame.draw.line(surf, RUBRIC, (x + 2, top), (x + width - 2, bottom), 4)
            pygame.draw.line(surf, RUBRIC, (x + width - 2, top), (x + 2, bottom), 3)
        for y in (top, bottom):      # the little feet closing each stroke
            if letter == "I":
                pygame.draw.line(surf, RUBRIC, (x, y), (x + width - 1, y), 2)
            elif y == top or letter == "X":
                pygame.draw.line(surf, RUBRIC, (x - 2, y), (x + 6, y), 2)
                pygame.draw.line(surf, RUBRIC, (x + width - 6, y), (x + width + 1, y), 2)
        x += width + _LETTER_GAP


def _opened_text(opened: Tuple[str, ...]) -> str:
    return f"You may now {' and '.join(opened)}"


class RankUpWindow(_BaseDialog):
    def __init__(self, screen: pygame.Surface, game_state: 'GameState', rise: RankRise) -> None:
        merchant_rank = game_state.game.merchant_rank
        self.rise = rise
        self.ranks: List[Rank] = merchant_rank.ranks
        self.next_rank: Optional[Rank] = (self.ranks[rise.level + 1] if rise.level + 1 < len(self.ranks) else None)
        self.rows = road_rows(self.next_rank, merchant_rank.standing()) if self.next_rank else []

        self.plaque_y = LADDER_END + PLAQUE_H // 2 - 6
        self.leaf_top = LADDER_END + (PLAQUE_H if rise.opened else 0) + 2
        leaf_h = HEAD_H + len(self.rows) * ROW_H + 10 if self.rows else WORDS_LEAF_H
        self.leaf_h = leaf_h
        height = self.leaf_top + leaf_h + BUTTON_GAP + BUTTON_SIZE[1] + FOOT
        super().__init__(screen, game_state, W, height)

        self.h1_font = self._medici(46, 36)
        self.name_font = self._medici(58, 44)
        self.heading_font = self._medici(26, 24)
        self.small_font = self._augusta(17, 15)
        self.button_rect = pygame.Rect((0, 0), BUTTON_SIZE)
        self.button_rect.midtop = (self.panel.centerx, self.panel.top + self.leaf_top + leaf_h + BUTTON_GAP)
        self._sheet: Optional[pygame.Surface] = None
        self._opened_at: Optional[int] = None

    @staticmethod
    def _medici(size: int, fallback: int) -> pygame.font.Font:
        try:
            return pygame.font.Font(os.path.join(FONTS_PATH, "Medici Text.ttf"), size)
        except Exception:
            return pygame.font.SysFont("arial", fallback)

    @staticmethod
    def _augusta(size: int, fallback: int) -> pygame.font.Font:
        try:
            return pygame.font.Font(os.path.join(FONTS_PATH, "Augusta.ttf"), size)
        except Exception:
            return pygame.font.SysFont("arial", fallback)

    # -- input -------------------------------------------------------------

    def _seconds_open(self) -> float:
        if self._opened_at is None:
            return 0.0
        return (pygame.time.get_ticks() - self._opened_at) / 1000.0

    @property
    def takes_input(self) -> bool:
        return self._seconds_open() >= INPUT_DELAY_S

    def handle_click(self, pos: Tuple[int, int]) -> Optional[str]:
        if self.takes_input and self.button_rect.collidepoint(pos):
            return "OK"
        return None

    def handle_key(self, event: pygame.event.Event) -> Optional[str]:
        if self.takes_input and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_ESCAPE):
            return "OK"
        return None

    # -- the sheet ---------------------------------------------------------

    def _centred(self, sheet: pygame.Surface, label: pygame.Surface, y: int) -> None:
        sheet.blit(label, label.get_rect(center=(W // 2, y)))

    def _draw_ladder(self, sheet: pygame.Surface) -> None:
        """Every rank in a line, those reached in gold and the one risen to in red."""
        step = (W - 2 * MARGIN) / len(self.ranks)
        xs = [round(MARGIN + step * (i + 0.5)) for i in range(len(self.ranks))]
        for i in range(len(xs) - 1):
            reached = i < self.rise.level
            pygame.draw.line(sheet, GOLD if reached else (168, 150, 120), (xs[i], LADDER_Y), (xs[i + 1], LADDER_Y),
                             3 if reached else 1)
        for i, (x, rank) in enumerate(zip(xs, self.ranks)):
            size = 10 if i == self.rise.level else 6
            points = [(x, LADDER_Y - size), (x + size, LADDER_Y), (x, LADDER_Y + size), (x - size, LADDER_Y)]
            if i == self.rise.level:
                pygame.draw.polygon(sheet, RUBRIC, points)
                pygame.draw.polygon(sheet, GOLD, points, 2)
            elif i < self.rise.level:
                pygame.draw.polygon(sheet, GOLD, points)
                pygame.draw.polygon(sheet, BRASS_DARK, points, 1)
            else:
                pygame.draw.polygon(sheet, (206, 190, 156), points)
                pygame.draw.polygon(sheet, (168, 150, 120), points, 1)
            colour = RUBRIC if i == self.rise.level else INK if i < self.rise.level else _FAINT_INK
            name = self.small_font.render(rank.name, True, colour)
            sheet.blit(name, name.get_rect(midtop=(x, LADDER_Y + 16)))

    def _draw_road(self, sheet: pygame.Surface) -> None:
        """How far the player already is along the road to the next rank."""
        leaf = pygame.Rect(MARGIN, self.leaf_top, W - 2 * MARGIN, self.leaf_h)
        _leaf(sheet, leaf)
        if not self.rows:
            self._centred(sheet, self.body_font.render(TOP_OF_THE_LADDER, True, INK), leaf.centery)
            return
        heading = self.heading_font.render(f"The road to {self.next_rank.name}", True, INK)
        sheet.blit(heading, heading.get_rect(center=(leaf.centerx, leaf.top + 23)))
        draw_divider(sheet, (leaf.centerx, leaf.top + HEAD_H - 6), 110)

        bar_left, bar_w = leaf.left + 206, 270
        y = leaf.top + HEAD_H
        for row in self.rows:
            middle = y + ROW_H // 2
            self._draw_mark(sheet, (leaf.left + 26, middle), row.met)
            label = self.body_font.render(row.label, True, INK)
            sheet.blit(label, label.get_rect(midleft=(leaf.left + 46, middle)))

            bar = pygame.Rect(bar_left, middle - 6, bar_w, 12)
            track = pygame.Surface(bar.size, pygame.SRCALPHA)
            pygame.draw.rect(track, _TRACK, track.get_rect(), border_radius=3)
            sheet.blit(track, bar)
            if row.share > 0:
                filled = pygame.Rect(bar.topleft, (max(4, round(bar.width * row.share)), bar.height))
                pygame.draw.rect(sheet, DARK_GREEN if row.met else BRASS, filled, border_radius=3)
            pygame.draw.rect(sheet, BRASS_DARK, bar, 1, border_radius=3)

            value = self.body_font.render(f"{row.have} of {row.need}", True, DARK_GREEN if row.met else INK)
            sheet.blit(value, value.get_rect(midright=(leaf.right - 22, middle)))
            y += ROW_H

    @staticmethod
    def _draw_mark(sheet: pygame.Surface, centre: Tuple[int, int], met: bool) -> None:
        """A green tick for a condition already met, an empty ring for one still to come."""
        x, y = centre
        if met:
            pygame.draw.lines(sheet, DARK_GREEN, False, [(x - 7, y), (x - 2, y + 6), (x + 8, y - 7)], 3)
        else:
            pygame.draw.circle(sheet, BRASS_DARK, centre, 6, 2)

    def _build_sheet(self) -> pygame.Surface:
        sheet = framed_sheet((W, self.panel.height))
        rise = self.rise
        self._centred(sheet, inked("Rank Restored" if rise.again else "Risen in Rank", self.h1_font, GOLD), TITLE_Y)
        draw_divider(sheet, (W // 2, DIVIDER_Y), 170)

        draw_laurel(sheet, (W // 2, WREATH_Y), WREATH_R)
        draw_numeral(sheet, ROMAN[rise.level], (W // 2, WREATH_Y - 2))

        spoken = "The town speaks of you again as" if rise.again else "The town now speaks of you as"
        self._centred(sheet, self.body_font.render(spoken, True, INK), SPOKEN_Y)
        self._centred(sheet, inked(rise.name, self.name_font, GOLD), NAME_Y)
        words = RANK_WORDS.get(rise.name)
        if words:
            self._centred(sheet, self.body_font.render(words, True, _FAINT_INK), WORDS_Y)

        self._draw_ladder(sheet)
        if rise.opened:
            plaque(sheet, self.body_font, _opened_text(rise.opened), (W // 2, self.plaque_y))
        self._draw_road(sheet)
        return sheet

    # -- what changes from frame to frame ----------------------------------

    def _draw_sparkles(self, surf: pygame.Surface, centre: Tuple[int, int], seconds: float) -> None:
        """Gold glints coming and going round the wreath, each at its own place and pace."""
        for i in range(12):
            angle = i * 2.4
            distance = WREATH_R + 22 + (i * 37) % 44
            glow = math.sin(seconds * (1.1 + (i % 5) * 0.23) + i * 1.7)
            if glow <= 0.25:
                continue
            x = round(centre[0] + distance * 1.5 * math.cos(angle))
            y = round(centre[1] + distance * 0.62 * math.sin(angle))
            size = 3 + round(5 * glow)
            star = [(x, y - size), (x + 2, y - 2), (x + size, y), (x + 2, y + 2),
                    (x, y + size), (x - 2, y + 2), (x - size, y), (x - 2, y - 2)]
            pygame.draw.polygon(surf, GOLD, star)
            pygame.draw.polygon(surf, BRASS_DARK, star, 1)

    def draw(self, alpha_scale: float = 1.0) -> None:
        if self._sheet is None:
            self._sheet = self._build_sheet()
        if self._opened_at is None:
            self._opened_at = pygame.time.get_ticks()

        seconds = self._seconds_open()
        settled = min(1.0, seconds / ENTRANCE_S)
        eased = 1.0 - (1.0 - settled) ** 3
        self.screen.blit(_dim_overlay(self.screen.get_size()), (0, 0))

        self._sheet.set_alpha(round(255 * eased * alpha_scale))
        self.screen.blit(self._sheet, self.panel.move(0, -round(ENTRANCE_DROP * (1.0 - eased))))
        if settled < 1.0:
            return

        self._draw_sparkles(self.screen, (self.panel.centerx, self.panel.top + WREATH_Y), seconds)
        if self.takes_input:
            hovered = self.button_rect.collidepoint(pygame.mouse.get_pos())
            draw_button(self.screen, self.button_rect, BUTTON_LABEL, self.body_font, hovered)
