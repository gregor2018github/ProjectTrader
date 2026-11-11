from __future__ import annotations
import os
import random
import pygame
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..game_state import GameState

from ..config.constants import PICTURES_PATH, FONTS_PATH
from ..config.colors import DARK_RED, DARK_GREEN

_coin_img: Optional[pygame.Surface] = None
_popup_font: Optional[pygame.font.Font] = None
_good_icons: dict[tuple[str, int], pygame.Surface] = {}

_COIN_W = 36
_GOOD_ICON_SIZE = 36
_FONT_SIZE = 28
_DURATION = 1.5   # seconds
_RISE_PX = 90     # pixels risen by end of animation
_PAD = 7          # padding around content inside the background pill
_BG_COLOR = (255, 255, 255, 160)  # white, semi-transparent
_SINGLE_COIN_SOUNDS = ("coin_flip", "coin_flip", "coin_single_1", "coin_single_2")  # flip or single, half each


def _load_assets() -> tuple[pygame.Surface, pygame.font.Font]:
    global _coin_img, _popup_font
    if _coin_img is None:
        raw = pygame.image.load(os.path.join(PICTURES_PATH, "coins_120.png")).convert_alpha()
        aspect = raw.get_height() / raw.get_width()
        _coin_img = pygame.transform.smoothscale(raw, (_COIN_W, int(_COIN_W * aspect)))
    if _popup_font is None:
        _popup_font = pygame.font.Font(os.path.join(FONTS_PATH, "MorrisRomanBlack.ttf"), _FONT_SIZE)
    return _coin_img, _popup_font


def good_icon(good_name: str, size: int) -> pygame.Surface:
    """A good's picture fitted into a square of `size`: its cut-out icon, or its 30px one
    (an empty square for a good with neither), kept once made."""
    key = (good_name, size)
    if key not in _good_icons:
        image = None
        for name in (f"{good_name.lower()}_icon.png", f"{good_name.lower()}_30.png"):
            path = os.path.join(PICTURES_PATH, name)
            if os.path.isfile(path):
                image = pygame.image.load(path)
                break
        if image is None:
            image = pygame.Surface((size, size), pygame.SRCALPHA)
        w, h = image.get_size()
        scale = size / max(w, h)
        _good_icons[key] = pygame.transform.smoothscale(
            image, (max(1, round(w * scale)), max(1, round(h * scale))))
    return _good_icons[key]


class FloatingPopup:
    """A picture and a label on a pale pill, rising and fading above a point of the screen."""

    def __init__(self, screen: pygame.Surface, pos: tuple[int, int], icon: pygame.Surface,
                 label: str, color: tuple[int, int, int], icon_first: bool = True) -> None:
        font = _load_assets()[1]
        self.screen = screen
        self.timer: float = _DURATION

        text_surf = font.render(label, True, color)
        gap = 8
        content_w = icon.get_width() + gap + text_surf.get_width()
        content_h = max(icon.get_height(), text_surf.get_height())

        # Full surface includes padding for the background pill
        w = content_w + _PAD * 2
        h = content_h + _PAD * 2

        self._surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(self._surf, _BG_COLOR, (0, 0, w, h), border_radius=8)
        icon_y = _PAD + (content_h - icon.get_height()) // 2
        text_y = _PAD + (content_h - text_surf.get_height()) // 2
        if icon_first:
            self._surf.blit(icon, (_PAD, icon_y))
            self._surf.blit(text_surf, (_PAD + icon.get_width() + gap, text_y))
        else:
            self._surf.blit(text_surf, (_PAD, text_y))
            self._surf.blit(icon, (_PAD + text_surf.get_width() + gap, icon_y))

        # Spawn centered horizontally above the point
        self._x = pos[0] - w // 2
        self._y = pos[1] - h - 8

    @property
    def height(self) -> int:
        return self._surf.get_height()

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


class CoinPopup(FloatingPopup):
    """A floating coin-pile + amount label that rises and fades above the cursor."""

    def __init__(self, screen: pygame.Surface, pos: tuple[int, int], amount: float, is_spent: bool) -> None:
        sign = "-" if is_spent else "+"
        color = DARK_RED if is_spent else DARK_GREEN
        super().__init__(screen, pos, _load_assets()[0], f"{sign}{amount:.1f} G", color)


class GoodsPopup(FloatingPopup):
    """A good received for nothing (a gift, a reward): "+3" and the good's picture, rising
    and fading like the coins."""

    def __init__(self, screen: pygame.Surface, pos: tuple[int, int], good_name: str, quantity: int) -> None:
        super().__init__(screen, pos, good_icon(good_name, _GOOD_ICON_SIZE), f"+{quantity}", DARK_GREEN,
                         icon_first=False)


def on_money_spent(game_state: "GameState", amount: float = 0.0) -> None:
    """Trigger feedback when the player spends money (buy, donate, etc.)."""
    if game_state.game:
        game_state.game.play_sound("falling_coins_buy")
    _spawn(game_state, amount, is_spent=True)


def on_money_donated(game_state: "GameState", amount: float = 0.0) -> None:
    """Feedback for a gift (alms, church, town): a single coin is heard flipped or dropped
    (coin_flip, or one of the coin_single variants, by even odds); more is the usual falling coins."""
    if amount != 1:
        on_money_spent(game_state, amount)
        return
    if game_state.game:
        game_state.game.play_sound(random.choice(_SINGLE_COIN_SOUNDS))
    _spawn(game_state, amount, is_spent=True)


def on_money_received(game_state: "GameState", amount: float = 0.0) -> None:
    """Trigger feedback when the player receives money (sell, loan, etc.)."""
    if game_state.game:
        game_state.game.play_sound("falling_coins_sell")
    _spawn(game_state, amount, is_spent=False)


def on_goods_received(game_state: "GameState", goods: dict[str, int]) -> None:
    """Feedback for goods the player is given with no money changing hands (a gift, a
    quest's reward): "+3" and each good's picture rising over the cursor, one above the
    other. Not for trades, whose coins are what matters and have their own popup."""
    pos = pygame.mouse.get_pos()
    y = pos[1]
    for good_name, quantity in goods.items():
        if quantity <= 0:
            continue
        popup = GoodsPopup(game_state.screen, (pos[0], y), good_name, quantity)
        game_state.coin_popups.append(popup)
        y -= popup.height + 4


def show_coin_popup(game_state: "GameState", amount: float, is_spent: bool) -> None:
    """Spawn only the visual popup, without playing any sound."""
    _spawn(game_state, amount, is_spent)


def _spawn(game_state: "GameState", amount: float, is_spent: bool) -> None:
    pos = pygame.mouse.get_pos()
    game_state.coin_popups.append(CoinPopup(game_state.screen, pos, amount, is_spent))
