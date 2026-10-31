"""The settings' weather page, offered only with the debug overlay on: start any kind of weather.

One button per spell of WEATHER_SPELLS starts it (Weather.force), the one
under way marked. Nothing jumps: the weather develops towards it as it would
in play, the clouds gathering before the rain sets in, the fog thickening
over hours, and the spell lasts until it has got there. "Hold" keeps the
spell from running out and its fog from thinning with the hour
(Weather.held, not saved), so it can be looked at as long as needed. The
ground can be soaked or dried at once, for the puddles and the wet ground.
A line at the top shows where the weather stands, live.
"""

from typing import List, Optional, Tuple

import pygame

from ...config.colors import BLACK, DARK_GRAY, LIGHT_GRAY, WHITE
from ...config.constants import WEATHER_SPELLS

ACTIVE_FILL = (196, 218, 186)    # the spell under way, and the options switched on
COLUMNS = 4
BUTTON_SIZE = (128, 38)
GAP = 14


class WeatherDebugPage:
    """The page's buttons inside *rect*, working on *weather* (models/weather.py)."""

    def __init__(self, rect: pygame.Rect, weather, font: pygame.font.Font, small_font: pygame.font.Font) -> None:
        self.rect = rect
        self.weather = weather
        self.font = font
        self.small_font = small_font
        w, h = BUTTON_SIZE
        kinds = list(WEATHER_SPELLS)
        grid_w = COLUMNS * w + (COLUMNS - 1) * GAP
        left = rect.centerx - grid_w // 2
        top = rect.top + 140
        self.spell_buttons: List[Tuple[pygame.Rect, str]] = [
            (pygame.Rect(left + (i % COLUMNS) * (w + GAP), top + (i // COLUMNS) * (h + GAP), w, h), kind)
            for i, kind in enumerate(kinds)]
        rows = (len(kinds) + COLUMNS - 1) // COLUMNS
        y = top + rows * (h + GAP) + 24
        half = (grid_w - GAP) // 2
        self.option_buttons: List[Tuple[pygame.Rect, str]] = [
            (pygame.Rect(left, y, grid_w, h), "hold"),
            (pygame.Rect(left, y + h + GAP, half, h), "soak"),
            (pygame.Rect(left + half + GAP, y + h + GAP, half, h), "dry"),
        ]
        self.back_button = pygame.Rect(0, 0, 160, h)
        self.back_button.midbottom = (rect.centerx, rect.bottom - 28)

    def _label(self, action: str) -> Tuple[str, bool]:
        """An option button's text, and whether it shows as switched on."""
        if action == "hold":
            return ("Hold: on" if self.weather.held else "Hold: off"), self.weather.held
        return ("Soak ground" if action == "soak" else "Dry ground"), False

    def _button(self, screen: pygame.Surface, rect: pygame.Rect, text: str, active: bool, mouse) -> None:
        hovered = rect.collidepoint(mouse)
        fill = ACTIVE_FILL if active else (LIGHT_GRAY if hovered else WHITE)
        pygame.draw.rect(screen, fill, rect)
        pygame.draw.rect(screen, DARK_GRAY, rect, 3 if active else 2)
        label = self.font.render(text, True, BLACK)
        screen.blit(label, label.get_rect(center=rect.center))

    def draw(self, screen: pygame.Surface) -> None:
        weather = self.weather
        mouse = pygame.mouse.get_pos()
        title = self.font.render("Weather (debug)", True, BLACK)
        screen.blit(title, title.get_rect(center=(self.rect.centerx, self.rect.top + 48)))
        hours = "held" if weather.held else f"{weather.hours_left:.1f} h left"
        lines = (f"Now: {weather.kind.capitalize()} ({hours})",
                 f"Rain {weather.rain:.2f}   Clouds {weather.clouds:.2f}   Fog {weather.fog:.2f}"
                 f" (heading for {weather.fog_target():.2f})   Wet {weather.wetness:.2f}")
        for i, line in enumerate(lines):
            text = self.small_font.render(line, True, BLACK)
            screen.blit(text, text.get_rect(center=(self.rect.centerx, self.rect.top + 84 + i * 22)))
        for rect, kind in self.spell_buttons:
            self._button(screen, rect, kind.capitalize(), kind == weather.kind, mouse)
        for rect, action in self.option_buttons:
            self._button(screen, rect, *self._label(action), mouse)
        self._button(screen, self.back_button, "Back", False, mouse)

    def handle_click(self, pos: Tuple[int, int]) -> Optional[str]:
        """Act on a click; "Back" when the page is to close."""
        if self.back_button.collidepoint(pos):
            return "Back"
        for rect, kind in self.spell_buttons:
            if rect.collidepoint(pos):
                self.weather.force(kind)
                return None
        for rect, action in self.option_buttons:
            if rect.collidepoint(pos):
                if action == "hold":
                    self.weather.held = not self.weather.held
                elif action == "soak":
                    self.weather.wetness = 1.0
                else:
                    self.weather.wetness = 0.0
        return None
