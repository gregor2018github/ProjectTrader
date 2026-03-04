"""Main menu screen shown before the game starts."""

import os
import pygame
from typing import Optional, List, Tuple
from ..config.colors import (
    BEIGE, SANDY_BROWN, DARK_BROWN, TAN, PALE_BROWN,
    LIGHT_GRAY, DARK_GRAY, WHITE, DARK_GREEN
)
from ..config.constants import SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH, PICTURES_PATH, FONTS_PATH

_TOTAL_WIDTH = SCREEN_WIDTH + SIDEBAR_WIDTH

# Button dimensions
_BTN_W = 320
_BTN_H = 56
_BTN_SPACING = 14


class MainMenu:
    """Standalone main menu displayed before any game session starts.

    Call ``run()`` to enter the event loop. It blocks until the user makes a
    choice and returns one of: ``"new_game"``, ``"load_game"``,
    ``"settings"``, or ``"exit"``.
    """

    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((_TOTAL_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Merchant's Rise")
        self.clock = pygame.time.Clock()

        try:
            icon = pygame.image.load(os.path.join(PICTURES_PATH, "Icon.png"))
            pygame.display.set_icon(icon)
        except Exception:
            pass

        # Fonts
        try:
            self.title_font = pygame.font.Font(
                os.path.join(FONTS_PATH, "Medici Text.ttf"), 52
            )
            self.subtitle_font = pygame.font.Font(
                os.path.join(FONTS_PATH, "Augusta.ttf"), 22
            )
            self.button_font = pygame.font.Font(
                os.path.join(FONTS_PATH, "RomanAntique.ttf"), 28
            )
        except Exception:
            self.title_font = pygame.font.SysFont("arial", 52, bold=True)
            self.subtitle_font = pygame.font.SysFont("arial", 22)
            self.button_font = pygame.font.SysFont("arial", 28)

        # Game icon displayed inside the panel
        self.icon_surf: Optional[pygame.Surface] = None
        try:
            raw = pygame.image.load(
                os.path.join(PICTURES_PATH, "Icon.png")
            ).convert_alpha()
            self.icon_surf = pygame.transform.smoothscale(raw, (90, 90))
        except Exception:
            pass

        # Panel geometry
        panel_w = 440
        panel_h = 530
        self.panel_rect = pygame.Rect(
            (_TOTAL_WIDTH - panel_w) // 2,
            (SCREEN_HEIGHT - panel_h) // 2,
            panel_w,
            panel_h,
        )

        # Buttons: (rect, label, action, enabled)
        self.buttons: List[Tuple[pygame.Rect, str, str, bool]] = []
        entries = [
            ("Start New Game", "new_game", True),
            ("Load Game",      "load_game", False),
            ("Settings",       "settings",  False),
            ("Exit",           "exit",      True),
        ]
        btn_area_top = self.panel_rect.top + 248
        cx = self.panel_rect.centerx
        for i, (label, action, enabled) in enumerate(entries):
            rect = pygame.Rect(
                cx - _BTN_W // 2,
                btn_area_top + i * (_BTN_H + _BTN_SPACING),
                _BTN_W,
                _BTN_H,
            )
            self.buttons.append((rect, label, action, enabled))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> str:
        """Block until the user selects an option and return the action string."""
        while True:
            self.clock.tick(60)
            mouse_pos = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return "exit"
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for rect, _label, action, enabled in self.buttons:
                        if enabled and rect.collidepoint(mouse_pos):
                            return action

            self._draw(mouse_pos)
            pygame.display.flip()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw(self, mouse_pos: Tuple[int, int]) -> None:
        self.screen.fill(BEIGE)

        # Panel background and border
        pygame.draw.rect(self.screen, SANDY_BROWN, self.panel_rect, border_radius=6)
        pygame.draw.rect(self.screen, DARK_BROWN, self.panel_rect, 3, border_radius=6)

        # --- Icon ---
        cursor_y = self.panel_rect.top + 24
        if self.icon_surf:
            icon_rect = self.icon_surf.get_rect(
                centerx=self.panel_rect.centerx, top=cursor_y
            )
            self.screen.blit(self.icon_surf, icon_rect)
            cursor_y = icon_rect.bottom + 14

        # --- Title ---
        title_surf = self.title_font.render("Merchant's Rise", True, DARK_BROWN)
        title_rect = title_surf.get_rect(
            centerx=self.panel_rect.centerx, top=cursor_y
        )
        self.screen.blit(title_surf, title_rect)
        cursor_y = title_rect.bottom + 6

        # --- Subtitle ---
        sub_surf = self.subtitle_font.render(
            "A Medieval Trading Simulation", True, PALE_BROWN
        )
        sub_rect = sub_surf.get_rect(
            centerx=self.panel_rect.centerx, top=cursor_y
        )
        self.screen.blit(sub_surf, sub_rect)
        cursor_y = sub_rect.bottom + 16

        # --- Divider ---
        pygame.draw.line(
            self.screen, DARK_BROWN,
            (self.panel_rect.left + 30, cursor_y),
            (self.panel_rect.right - 30, cursor_y),
            1,
        )

        # --- Buttons ---
        for rect, label, action, enabled in self.buttons:
            is_hovered = enabled and rect.collidepoint(mouse_pos)

            if not enabled:
                bg = LIGHT_GRAY
                text_color = DARK_GRAY
                border_color = DARK_GRAY
            elif is_hovered:
                bg = PALE_BROWN
                text_color = WHITE
                border_color = DARK_BROWN
            else:
                bg = TAN
                text_color = DARK_BROWN
                border_color = DARK_BROWN

            pygame.draw.rect(self.screen, bg, rect, border_radius=4)
            pygame.draw.rect(self.screen, border_color, rect, 2, border_radius=4)

            text_surf = self.button_font.render(label, True, text_color)
            self.screen.blit(text_surf, text_surf.get_rect(center=rect.center))

