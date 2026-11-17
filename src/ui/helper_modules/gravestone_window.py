"""A gravestone's inscription, opened with "Read" in its house menu.

The stone is drawn once when the window opens: a slab with a rounded top in
weathered grey, speckled, with lichen and a little moss at its foot (placed by
a generator seeded with the epitaph's key, so a stone looks the same each time
it is read), a small cross, and the inscription carved in: each letter a dark
stroke with a light edge under it. The texts are models/epitaphs.py. Any click
or Escape puts it away; walking off closes it like a house menu (map_view, by
its `house`).
"""

import os
import random
from typing import TYPE_CHECKING, List, Optional, Tuple

import pygame

from .loan_dialog import _close_dialog
from ...config.constants import FONTS_PATH, SCREEN_HEIGHT, SCREEN_WIDTH, SIDEBAR_WIDTH
from ...models.epitaphs import Epitaph, epitaph, years_line

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.house import House

SLAB_WIDTH = 560
ARCH_HEIGHT = 120          # the rounded top, above the straight sides
MARGIN_X = 64              # from the slab's edge to the widest line of text
TOP_GAP = 46               # from the top of the arch to the cross
BOTTOM_GAP = 70            # under the last line, the moss included
LINE_GAP = 6

NAME_SIZE = 38
YEARS_SIZE = 24
TEXT_SIZE = 25
HINT_SIZE = 18

STONE = (128, 132, 136)
STONE_DARK = (98, 102, 108)
STONE_LIGHT = (156, 160, 162)
OUTLINE = (52, 54, 60)
CARVED = (50, 52, 58)          # the cut of a letter
CARVED_EDGE = (178, 182, 184)  # the light catching the lower edge of the cut
LICHEN = ((168, 164, 112), (150, 152, 98), (186, 178, 128))
MOSS = ((96, 116, 62), (78, 98, 50), (112, 132, 70))
SHADOW = (0, 0, 0, 90)
HINT = (236, 226, 204)
SPECKLES = 700
LICHEN_PATCHES = 7


def open_gravestone(game_state: 'GameState', house: 'House') -> bool:
    """Show what is carved on a gravestone; False if its `Epitaph` names no known inscription."""
    found = epitaph(house.epitaph)
    if found is None:
        game_state.show_warning("The inscription is worn away; nothing can be read.")
        return False
    game_state.info_window = GravestoneWindow(game_state.screen, game_state, house, found)
    game_state.active_house_menu = house
    return True


def _font(size: int) -> pygame.font.Font:
    try:
        return pygame.font.Font(os.path.join(FONTS_PATH, "RomanAntique.ttf"), size)
    except Exception:
        return pygame.font.SysFont("times new roman", size)


def _line_height(font: pygame.font.Font) -> int:
    """How tall a line is: RomanAntique reports far too small a line size, so measure a rendered one."""
    return max(font.get_linesize(), font.size("Mg")[1])


def _wrap(text: str, font: pygame.font.Font, width: int) -> List[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and font.size(trial)[0] > width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def _carve(surface: pygame.Surface, font: pygame.font.Font, text: str, centerx: int, top: int) -> int:
    """Cut a line of text into the stone, centred; returns the y under it."""
    edge = font.render(text, True, CARVED_EDGE)
    cut = font.render(text, True, CARVED)
    rect = cut.get_rect(centerx=centerx, top=top)
    surface.blit(edge, rect.move(1, 2))
    surface.blit(cut, rect)
    return rect.bottom


class GravestoneWindow:
    """The stone with its inscription, in the middle of the screen."""

    def __init__(self, screen: pygame.Surface, game_state: 'GameState', house: Optional['House'],
                 inscription: Epitaph) -> None:
        self.screen = screen
        self.game_state = game_state
        self.house = house                 # closes it when the player walks off (map_view)
        self.epitaph = inscription
        self.stone = self._make_stone()
        self.hint = self._make_hint("Click to step back from the grave.")
        total_w = SCREEN_WIDTH + SIDEBAR_WIDTH
        height = self.stone.get_height() + 12 + self.hint.get_height()
        self.panel = self.stone.get_rect(centerx=total_w // 2, top=max(10, (SCREEN_HEIGHT - height) // 2))

    @staticmethod
    def _make_hint(text: str) -> pygame.Surface:
        """Light words with a dark rim, readable over whatever of the map is behind them."""
        font = _font(HINT_SIZE)
        light, dark = font.render(text, True, HINT), font.render(text, True, (20, 18, 16))
        hint = pygame.Surface((light.get_width() + 4, light.get_height() + 4), pygame.SRCALPHA)
        for dx, dy in ((0, 2), (4, 2), (2, 0), (2, 4), (4, 4)):
            hint.blit(dark, (dx, dy))
        hint.blit(light, (2, 2))
        return hint

    # -- the stone --------------------------------------------------------------

    def text_lines(self) -> List[Tuple[pygame.font.Font, str]]:
        """Every line carved, with its font, the inscription's long lines wrapped to the slab."""
        name_font, years_font, text_font = _font(NAME_SIZE), _font(YEARS_SIZE), _font(TEXT_SIZE)
        width = SLAB_WIDTH - 2 * MARGIN_X
        lines = [(name_font, part) for part in _wrap(self.epitaph.name.upper(), name_font, width)]
        lines.append((years_font, years_line(self.epitaph)))
        lines.append((text_font, ""))      # a gap under the years
        for text in self.epitaph.lines:
            lines += [(text_font, part) for part in _wrap(text, text_font, width)]
        return lines

    def _make_stone(self) -> pygame.Surface:
        lines = self.text_lines()
        text_height = sum(_line_height(font) + LINE_GAP for font, _ in lines)
        cross = 40
        height = TOP_GAP + cross + 18 + text_height + BOTTOM_GAP
        height = max(height, ARCH_HEIGHT + 200)
        w, h = SLAB_WIDTH, height
        stone = pygame.Surface((w, h), pygame.SRCALPHA)

        # The shape: a rounded top over straight sides, as a mask to keep everything on the stone
        shape = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.ellipse(shape, (255, 255, 255, 255), (0, 0, w, 2 * ARCH_HEIGHT))
        pygame.draw.rect(shape, (255, 255, 255, 255), (0, ARCH_HEIGHT, w, h - ARCH_HEIGHT))
        mask = pygame.mask.from_surface(shape)

        face = pygame.Surface((w, h), pygame.SRCALPHA)
        face.fill(STONE)
        rng = random.Random(self.epitaph.key)
        # Weathering: darker and lighter speckles
        for _ in range(SPECKLES):
            colour = rng.choice((STONE_DARK, STONE_LIGHT))
            r = rng.choice((1, 1, 2, 2, 3))
            pygame.draw.circle(face, colour, (rng.randrange(w), rng.randrange(h)), r)
        # Light from the upper left: a lighter band down the left, a darker one down the right
        pygame.draw.rect(face, STONE_LIGHT, (8, ARCH_HEIGHT // 2, 10, h))
        pygame.draw.rect(face, STONE_DARK, (w - 18, ARCH_HEIGHT // 2, 10, h))
        # Lichen in clumps near the edges, moss over the foot
        for _ in range(LICHEN_PATCHES):
            # Clear of the letters: down the edges, or high in the arch beside the cross
            side = rng.random() < 0.6
            x = rng.choice((rng.randrange(14, 34), rng.randrange(w - 34, w - 14))) if side else                 rng.choice((rng.randrange(110, w // 2 - 50), rng.randrange(w // 2 + 50, w - 110)))
            y = rng.randrange(ARCH_HEIGHT, h - 80) if side else rng.randrange(28, TOP_GAP + 20)
            for _ in range(rng.randrange(6, 14)):
                pygame.draw.circle(face, rng.choice(LICHEN),
                                   (x + rng.randrange(-18, 19), y + rng.randrange(-12, 13)), rng.randrange(3, 8))
        for x in range(0, w, 6):
            top = h - 22 - rng.randrange(0, 22)
            pygame.draw.rect(face, rng.choice(MOSS), (x, top, 7, h - top))
        stone.blit(face, (0, 0))
        stone.blit(mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0)), (0, 0),
                   special_flags=pygame.BLEND_RGBA_MIN)   # nothing off the shape
        outline = mask.outline()
        if len(outline) > 2:
            pygame.draw.lines(stone, OUTLINE, True, outline, 4)

        # A small cross, then the inscription
        cx = w // 2
        top = TOP_GAP
        for rect in ((cx - 4, top, 8, cross), (cx - 15, top + 9, 30, 8)):
            pygame.draw.rect(stone, CARVED_EDGE, pygame.Rect(rect).move(1, 2))
        for rect in ((cx - 4, top, 8, cross), (cx - 15, top + 9, 30, 8)):
            pygame.draw.rect(stone, CARVED, rect)
        y = top + cross + 18
        for font, text in lines:
            if text:
                _carve(stone, font, text, cx, y)
            y += _line_height(font) + LINE_GAP
        return stone

    # -- the event interface ------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            _close_dialog(self.game_state)

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        _close_dialog(self.game_state)
        return True

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return
        shadow = pygame.Surface(self.stone.get_size(), pygame.SRCALPHA)
        shadow.fill(SHADOW)
        shadow.blit(self.stone, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)   # the stone's shape, black
        stone, hint = self.stone, self.hint
        if alpha_scale < 1.0:
            alpha = round(255 * alpha_scale)
            stone, hint, shadow = stone.copy(), hint.copy(), shadow.copy()
            for surface in (stone, hint, shadow):
                surface.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
        self.screen.blit(shadow, self.panel.move(10, 12))
        self.screen.blit(stone, self.panel)
        self.screen.blit(hint, hint.get_rect(centerx=self.panel.centerx, top=self.panel.bottom + 12))
