"""Small "Game saved" notice in the bottom-right corner of the screen.

Used for autosaves, which should not interrupt play: a quill icon with a
two-line label fades in below the right sidebar and fades out again.
"""

import os
from typing import Optional

import pygame

from ...config.colors import DARK_BROWN
from ...config.constants import (
    PICTURES_PATH, SCREEN_HEIGHT, SCREEN_WIDTH, SIDEBAR_WIDTH,
)

_FADE_IN = 0.3    # seconds
_HOLD = 2.5
_FADE_OUT = 0.8
_ICON_SIZE = (22, 32)
_ICON_GAP = 6
_BOTTOM_BAR_H = 60


class SaveIndicator:
    """Fading quill + "Game saved" label in the empty cell under the sidebar."""

    def __init__(self, font: pygame.font.Font) -> None:
        self.font = font
        self._age: Optional[float] = None  # seconds since show(); None = hidden
        self._surface = self._build_surface()
        # Centre of the grey cell below the sidebar, level with the bottom bar
        self._rect = self._surface.get_rect(center=(
            SCREEN_WIDTH + SIDEBAR_WIDTH // 2,
            SCREEN_HEIGHT - _BOTTOM_BAR_H // 2,
        ))

    def _build_surface(self) -> pygame.Surface:
        icon: Optional[pygame.Surface] = None
        try:
            raw = pygame.image.load(
                os.path.join(PICTURES_PATH, "contracts", "cursor_quill.png")
            ).convert_alpha()
            icon = pygame.transform.smoothscale(raw, _ICON_SIZE)
        except Exception:
            pass

        lines = [self.font.render(text, True, DARK_BROWN) for text in ("Game", "saved")]
        text_w = max(line.get_width() for line in lines)
        text_h = sum(line.get_height() for line in lines)
        icon_w = _ICON_SIZE[0] + _ICON_GAP if icon else 0
        height = max(_ICON_SIZE[1] if icon else 0, text_h)

        surf = pygame.Surface((icon_w + text_w, height), pygame.SRCALPHA)
        if icon:
            surf.blit(icon, (0, (height - _ICON_SIZE[1]) // 2))
        y = (height - text_h) // 2
        for line in lines:
            surf.blit(line, (icon_w, y))
            y += line.get_height()
        return surf

    def show(self) -> None:
        self._age = 0.0

    def update(self, delta_time: float) -> None:
        if self._age is None:
            return
        self._age += delta_time
        if self._age >= _FADE_IN + _HOLD + _FADE_OUT:
            self._age = None

    def draw(self, screen: pygame.Surface) -> None:
        if self._age is None:
            return
        if self._age < _FADE_IN:
            alpha = self._age / _FADE_IN
        elif self._age < _FADE_IN + _HOLD:
            alpha = 1.0
        else:
            alpha = 1.0 - (self._age - _FADE_IN - _HOLD) / _FADE_OUT
        self._surface.set_alpha(int(255 * max(0.0, min(1.0, alpha))))
        screen.blit(self._surface, self._rect)
