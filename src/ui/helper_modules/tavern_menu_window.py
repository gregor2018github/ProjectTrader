"""A tavern's bill of fare for the day, opened from its house menu ("Daily Menu").

The dishes are drawn by `daily_menu()` when the window opens; each course has
a heading, and each dish its name, its price at the right, and a short
description under it.
"""

import os
import pygame
from typing import TYPE_CHECKING, List, Tuple

from .loan_dialog import _BaseDialog, _close_dialog, _load_fonts
from ...config.colors import BLACK, DARK_BROWN, DARK_RED
from ...config.constants import FONTS_PATH, SCREEN_HEIGHT
from ...models.game_calendar import format_long, is_fast_day, is_lent
from ...models.tavern_menu import COURSES, daily_menu

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.house import House

DESCRIPTION_COLOR = (90, 70, 50)
DESCRIPTION_FONT_SIZE = 17
COURSE_GAP = 14
DISH_GAP = 6
PRICE_COLUMN = 70  # room kept at each side for the prices, in pixels


def open_tavern_menu(game_state: 'GameState', house: 'House') -> None:
    game_state.info_window = TavernMenuWindow(game_state.screen, game_state, house)


def _tavern_title(house: 'House') -> str:
    return house.display_name or "The Tavern"


class TavernMenuWindow(_BaseDialog):
    W = 640

    def __init__(self, screen: pygame.Surface, game_state: 'GameState', house: 'House') -> None:
        self.house = house
        self.day = game_state.date.date()
        # The Tiled id would be steadier, but houses keep only their position
        key = f"{house.name}@{round(house.x)},{round(house.y)}"
        self.menu = daily_menu(self.day, house.tavern_class, key)
        # The lines are measured before the panel's size is known
        self.title_font, self.body_font = _load_fonts()
        try:
            self.small_font = pygame.font.Font(os.path.join(FONTS_PATH, "Augusta.ttf"), DESCRIPTION_FONT_SIZE)
        except Exception:
            self.small_font = pygame.font.SysFont("arial", DESCRIPTION_FONT_SIZE - 2)
        self.lines = self._lay_out()
        last, last_top, _ = self.lines[-1]
        height = min(SCREEN_HEIGHT - 40, last_top + last.get_height() + self.PAD + 6)
        super().__init__(screen, game_state, self.W, height)

    def _wrap(self, text: str, font: pygame.font.Font, width: int) -> List[str]:
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

    def _lay_out(self) -> List[Tuple[pygame.Surface, int, bool]]:
        """Each line of the menu rendered, with its top relative to the panel's top
        and whether it goes at the right (a price) rather than in the middle."""
        # The middle column keeps clear of the prices on both sides
        width = self.W - 2 * self.PAD - 2 * PRICE_COLUMN
        lines: List[Tuple[pygame.Surface, int, bool]] = []
        y = self.HDR + self.PAD

        def add(text: str, font: pygame.font.Font, color, gap_after: int = 0) -> None:
            nonlocal y
            for part in self._wrap(text, font, width):
                surface = font.render(part, True, color)
                lines.append((surface, y, False))
                y += surface.get_height()
            y += gap_after

        add(f"Bill of fare for {format_long(self.day)}",
            self.body_font, DARK_BROWN, 2)
        add("All prices in coins", self.small_font, DESCRIPTION_COLOR, 2)
        if is_fast_day(self.day):
            reason = "It is Lent" if is_lent(self.day) else "It is Friday"
            add(f"{reason}, a fast day: no meat is served.", self.small_font, DARK_RED)
        y += COURSE_GAP

        headings = dict(COURSES)
        for course, dishes in self.menu:
            add(f"~ {headings[course]} ~", self.body_font, DARK_BROWN, 4)
            for dish in dishes:
                lines.append((self.body_font.render(f"{dish.price:.2f}", True, DARK_BROWN), y, True))
                add(dish.name, self.body_font, BLACK)
                add(dish.description, self.small_font, DESCRIPTION_COLOR, DISH_GAP)
            y += COURSE_GAP
        if not self.menu:
            add("The kitchen is cold today.", self.body_font, BLACK)
        return lines

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.close_rect.collidepoint(pos) or not self.panel.collidepoint(pos):
            _close_dialog(self.game_state)
        return True

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return

        use_temp = alpha_scale < 1.0
        if use_temp:
            surf = pygame.Surface(self.panel.size, pygame.SRCALPHA)
            off = (-self.panel.left, -self.panel.top)
        else:
            surf = self.screen
            off = (0, 0)

        self._draw_panel(surf, off)
        self._draw_close_btn(surf, off)
        self._draw_title(surf, off, _tavern_title(self.house))

        p = self.panel.move(*off)
        for surface, top, at_right in self.lines:
            if top + surface.get_height() > self.panel.height - self.PAD:
                break
            if at_right:
                surf.blit(surface, surface.get_rect(right=p.right - 2 * self.PAD, top=p.top + top))
            else:
                surf.blit(surface, surface.get_rect(centerx=p.centerx, top=p.top + top))

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, self.panel.topleft)
