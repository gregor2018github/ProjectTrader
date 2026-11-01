"""The merchant rank overview, opened from the rank title in the top bar or at the guildhall.

One table: what the player has of each condition, then every rank with what it
asks for, met conditions in green; the rank held is highlighted.
"""

import pygame
from typing import TYPE_CHECKING, Tuple
from .loan_dialog import _BaseDialog, _close_dialog
from ...config.colors import BLACK, DARK_BROWN, DARK_GREEN, DARK_RED, GRAY, GOLD
from ...config.constants import RANK_GRACE_DAYS, REPUTATION_MONTHLY_DECAY
from ...models.merchant_rank import CONDITIONS, CONDITION_LABELS, format_amount

if TYPE_CHECKING:
    from ...game_state import GameState


def open_rank_window(game_state: 'GameState') -> None:
    game_state.info_window = RankWindow(game_state.screen, game_state)


class RankWindow(_BaseDialog):
    W, H = 780, 560
    ROW_H = 30
    NAME_W = 180

    def __init__(self, screen: pygame.Surface, game_state: 'GameState') -> None:
        super().__init__(screen, game_state, self.W, self.H)

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.close_rect.collidepoint(pos) or not self.panel.collidepoint(pos):
            _close_dialog(self.game_state)
        return True

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
        self._draw_title(surf, off, "Merchant Rank")

        merchant_rank = self.game_state.game.merchant_rank
        standing = merchant_rank.standing()
        p = self.panel.move(*off)
        y = p.top + self.HDR + self.PAD

        held = merchant_rank.rank
        y = self._text(surf, f"You are counted a {held.name}.", p.centerx, y, DARK_BROWN, center=True) + 4
        if merchant_rank.highest > merchant_rank.level:
            highest = merchant_rank.ranks[merchant_rank.highest].name
            y = self._text(surf, f"The highest you have risen to: {highest}", p.centerx, y, BLACK, center=True) + 4
        days_left = merchant_rank.grace_days_left(self.game_state.date.date())
        if days_left is not None:
            unmet = ", ".join(CONDITION_LABELS[c] for c in held.unmet(standing))
            y = self._text(surf, f"Slipping ({unmet}): {days_left} of {RANK_GRACE_DAYS} days left to put it right",
                           p.centerx, y, DARK_RED, center=True) + 4

        y += 8
        col_w = (self.W - 2 * self.PAD - self.NAME_W) // len(CONDITIONS)
        left = p.left + self.PAD

        def row(name: str, cells, name_color, top: int) -> None:
            self._text(surf, name, left + 6, top + 4, name_color)
            for i, (text, color) in enumerate(cells):
                cx = left + self.NAME_W + i * col_w + col_w // 2
                self._text(surf, text, cx, top + 4, color, center=True)

        row("", [(CONDITION_LABELS[c], DARK_BROWN) for c in CONDITIONS], DARK_BROWN, y)
        y += self.ROW_H
        row("You have", [(format_amount(c, standing[c]), DARK_BROWN) for c in CONDITIONS], DARK_BROWN, y)
        y += self.ROW_H
        pygame.draw.line(surf, DARK_BROWN, (left, y), (p.right - self.PAD, y), 1)
        y += 4

        for index, rank in enumerate(merchant_rank.ranks):
            if index == merchant_rank.level:
                band = pygame.Surface((self.W - 2 * self.PAD, self.ROW_H), pygame.SRCALPHA)
                band.fill((*GOLD, 90))
                surf.blit(band, (left, y))
            cells = []
            for c in CONDITIONS:
                need = getattr(rank, c)
                met = standing[c] >= need
                cells.append(("–" if need <= 0 else format_amount(c, need), DARK_GREEN if met else GRAY))
            row(rank.name, cells, BLACK if index <= merchant_rank.level else GRAY, y)
            y += self.ROW_H

        y += 8
        notes = [
            "A rank needs all four at once. The town judges you each midnight.",
            f"A rank no longer met is lost after {RANK_GRACE_DAYS} days, one rank at a time.",
            f"Reputation comes from gifts, and fades by {REPUTATION_MONTHLY_DECAY:.0%} each month.",
        ]
        for note in notes:
            y = self._text(surf, note, p.centerx, y, BLACK, center=True) + 2

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, self.panel.topleft)
