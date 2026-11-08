"""The guild's records of the player's successes, opened at the guildhall.

So far the minigames': a card for every kind of fish with its portrait, name, how
many were landed, their weight together and the biggest one; a kind never caught
is greyed out with a question mark for its name. Over them the sessions' bests.
"""

import os
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

import pygame

from .loan_dialog import _BaseDialog
from .statistics_view import _fmt_woodhacking_score
from ...config.colors import BLACK, DARK_BROWN, GRAY
from ...config.constants import FONTS_PATH
from ...models.minigames.fishing_pond import SPECIES, Species, format_kg
from ...models.minigames.fishing_scene import fish_sprite
from ...models.statistics import Statistics

if TYPE_CHECKING:
    from ...game_state import GameState

UNKNOWN_NAME = "?"
PORTRAIT_LENGTH = 30             # low pixels long, whatever its kind's size: one drawn small would show nothing
PORTRAIT_SCALE = 4
_GREY_ALPHA = 120                # how faint the portrait of a kind not caught yet is

_portraits = {}                  # (species key, caught) -> the portrait


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
            return ["Caught: –", "Total: –", "Biggest: –"]
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


def open_records_window(game_state: 'GameState') -> None:
    game_state.info_window = RecordsWindow(game_state.screen, game_state)


class RecordsWindow(_BaseDialog):
    COLUMNS = 3
    CARD_W, CARD_H = 350, 128
    GAP = 10
    SUMMARY_H = 34
    W = COLUMNS * CARD_W + (COLUMNS - 1) * GAP + 2 * _BaseDialog.PAD
    H = _BaseDialog.HDR + _BaseDialog.PAD + SUMMARY_H + 3 * CARD_H + 2 * GAP + 2 * _BaseDialog.PAD

    def __init__(self, screen: pygame.Surface, game_state: 'GameState') -> None:
        super().__init__(screen, game_state, self.W, self.H)
        try:
            self.name_font = pygame.font.Font(os.path.join(FONTS_PATH, "Medici Text.ttf"), 26)
        except Exception:
            self.name_font = pygame.font.SysFont("arial", 24)

    def _draw_card(self, surf: pygame.Surface, rect: pygame.Rect, record: FishRecord) -> None:
        band = pygame.Surface(rect.size, pygame.SRCALPHA)
        band.fill((255, 245, 215, 90) if record.caught else (90, 80, 70, 45))
        surf.blit(band, rect)
        pygame.draw.rect(surf, DARK_BROWN if record.caught else GRAY, rect, 1)

        picture = portrait(record.species, record.caught)
        surf.blit(picture, picture.get_rect(center=(rect.left + 74, rect.centery)))

        x = rect.left + 146
        name = self.name_font.render(record.name, True, DARK_BROWN if record.caught else GRAY)
        surf.blit(name, (x, rect.top + 10))
        y = rect.top + 46
        for line in record.lines():
            y = self._text(surf, line, x, y, BLACK if record.caught else GRAY) + 3

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

        stats = self.game_state.game.depot.stats
        records = fish_records(stats)
        p = self.panel.move(*off)
        y = p.top + self.HDR + self.PAD

        known = sum(record.caught for record in records)
        summary = (f"Fish caught: {stats.fish_caught:,}   |   Kinds: {known} of {len(records)}   |   "
                   f"Best day's fishing: {stats.fishing_highscore:,.2f} coins   |   "
                   f"Best woodhacking: {_fmt_woodhacking_score(stats.woodhacking_highscore)}")
        self._text(surf, summary, p.centerx, y, DARK_BROWN, center=True)
        y += self.SUMMARY_H

        for index, record in enumerate(records):
            row, column = divmod(index, self.COLUMNS)
            rect = pygame.Rect(p.left + self.PAD + column * (self.CARD_W + self.GAP),
                               y + row * (self.CARD_H + self.GAP), self.CARD_W, self.CARD_H)
            self._draw_card(surf, rect, record)

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, self.panel.topleft)
