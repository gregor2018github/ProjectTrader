from __future__ import annotations
import os
import pygame
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..game_state import GameState

from ..config.constants import PICTURES_PATH, FONTS_PATH
from ..config.colors import DARK_RED, DARK_GREEN

_coin_img: Optional[pygame.Surface] = None
_popup_font: Optional[pygame.font.Font] = None

_COIN_W = 36
_FONT_SIZE = 28
_DURATION = 1.5   # seconds
_RISE_PX = 90     # pixels risen by end of animation
_PAD = 7          # padding around content inside the background pill
_BG_COLOR = (255, 255, 255, 160)  # white, semi-transparent


def _load_assets() -> tuple[pygame.Surface, pygame.font.Font]:
    global _coin_img, _popup_font
    if _coin_img is None:
        raw = pygame.image.load(os.path.join(PICTURES_PATH, "coins_120.png")).convert_alpha()
        aspect = raw.get_height() / raw.get_width()
        _coin_img = pygame.transform.smoothscale(raw, (_COIN_W, int(_COIN_W * aspect)))
    if _popup_font is None:
        _popup_font = pygame.font.Font(os.path.join(FONTS_PATH, "MorrisRomanBlack.ttf"), _FONT_SIZE)
    return _coin_img, _popup_font


class CoinPopup:
    """A floating coin-pile + amount label that rises and fades above the cursor."""

    def __init__(self, screen: pygame.Surface, pos: tuple[int, int], amount: float, is_spent: bool) -> None:
        coin_img, font = _load_assets()
        self.screen = screen
        self.timer: float = _DURATION

        sign = "-" if is_spent else "+"
        color = DARK_RED if is_spent else DARK_GREEN
        label = f"{sign}{amount:.1f} G"

        text_surf = font.render(label, True, color)
        gap = 8
        content_w = coin_img.get_width() + gap + text_surf.get_width()
        content_h = max(coin_img.get_height(), text_surf.get_height())

        # Full surface includes padding for the background pill
        w = content_w + _PAD * 2
        h = content_h + _PAD * 2

        self._surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(self._surf, _BG_COLOR, (0, 0, w, h), border_radius=8)
        coin_y = _PAD + (content_h - coin_img.get_height()) // 2
        self._surf.blit(coin_img, (_PAD, coin_y))
        text_y = _PAD + (content_h - text_surf.get_height()) // 2
        self._surf.blit(text_surf, (_PAD + coin_img.get_width() + gap, text_y))

        # Spawn centered horizontally above the cursor tip
        self._x = pos[0] - w // 2
        self._y = pos[1] - h - 8

    @property
    def alive(self) -> bool:
        return self.timer > 0.0

    def update(self, delta_time: float) -> None:
        self.timer -= delta_time

    def draw(self) -> None:
        t = max(0.0, self.timer / _DURATION)  # 1.0 → 0.0
        alpha = int(255 * t)
        y = self._y - int(_RISE_PX * (1.0 - t))

        frame = self._surf.copy()
        frame.set_alpha(alpha)
        self.screen.blit(frame, (self._x, y))


def on_money_spent(game_state: "GameState", amount: float = 0.0) -> None:
    """Trigger feedback when the player spends money (buy, donate, etc.)."""
    if game_state.game:
        game_state.game.play_sound("falling_coins_buy")
    _spawn(game_state, amount, is_spent=True)


def on_money_received(game_state: "GameState", amount: float = 0.0) -> None:
    """Trigger feedback when the player receives money (sell, loan, etc.)."""
    if game_state.game:
        game_state.game.play_sound("falling_coins_sell")
    _spawn(game_state, amount, is_spent=False)


def _spawn(game_state: "GameState", amount: float, is_spent: bool) -> None:
    pos = pygame.mouse.get_pos()
    game_state.coin_popups.append(CoinPopup(game_state.screen, pos, amount, is_spent))
