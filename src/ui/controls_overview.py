"""Overview of every control, opened from both the main menu's and the in-game settings."""

import os
import pygame
from typing import List, Optional, Tuple
from ..config.colors import SANDY_BROWN, DARK_BROWN, TAN, PALE_BROWN, WHITE, DARK_GRAY
from ..config.constants import FONTS_PATH

# A row's keys are alternatives separated by "/", each a chord of caps joined by "+"
Keys = List[List[str]]
Section = Tuple[str, List[Tuple[Keys, str]]]

# Keep in step with handlers/keyboard_handler.py, handlers/event_handler.py and
# GameMap.handle_movement_keys when a control changes.
LEFT_COLUMN: List[Section] = [
    ("Walking & Map", [
        ([["W A S D"], ["Arrows"]], "Walk"),
        ([["Wheel"], ["+"], ["-"]], "Zoom the map in and out"),
        ([["Ctrl", "Wheel"]], "Zoom out further than usual"),
        ([["Left click"]], "Talk, knock, look at water"),
    ]),
    ("Town Map", [
        ([["Drag"]], "Move the plan around"),
        ([["Wheel"]], "Zoom towards the cursor"),
    ]),
    ("Views", [
        ([["1"]], "Explore"),
        ([["2"]], "Market"),
        ([["3"]], "Depot"),
        ([["4"]], "Politics"),
        ([["5"]], "Trade Routes"),
        ([["6"], ["M"]], "Town Map"),
        ([["Left click"]], "Sidebar picture: whole screen"),
        ([["Left click"]], "Its side buttons: one half"),
    ]),
]

RIGHT_COLUMN: List[Section] = [
    ("Time", [
        ([["Space"]], "Pause / resume"),
        ([["+"], ["-"]], "Faster / slower (map not shown)"),
    ]),
    ("Trading (at the market)", [
        ([["F1"], ["F2"]], "Buy / sell, first row"),
        ([["F3"], ["F4"]], "Buy / sell, second row"),
        ([["F5"], ["F6"]], "Buy / sell, third row"),
        ([["Double click"]], "Select a quantity's text"),
        ([["Enter"], ["Esc"]], "Finish typing a quantity"),
    ]),
    ("Menus & Dialogs", [
        ([["Q"]], "Quit the game"),
        ([["Tab"], ["Shift", "Tab"]], "Move between buttons"),
        ([["Enter"], ["Space"]], "Press the chosen button"),
        ([["Right click"]], "Music button: volume"),
    ]),
    ("Woodhacking", [
        ([["Hold left"]], "Gather power"),
        ([["Release"]], "Swing the axe"),
        ([["Esc"]], "Leave"),
    ]),
    ("Inventory", [
        ([["I"]], "What you carry, open / close"),
        ([["Left click"]], "Warehouse: carry goods and back"),
        ([["Right click"]], "Move one unit of it"),
    ]),
]

_PANEL_W = 1100
_PANEL_H = 840
_ROW_H = 28
_SECTION_GAP = 14
_KEY_COLUMN_W = 190


def _load_font(name: str, size: int) -> pygame.font.Font:
    try:
        return pygame.font.Font(os.path.join(FONTS_PATH, name), size)
    except Exception:
        return pygame.font.SysFont("arial", size)


class ControlsOverview:
    """A panel listing all controls, with a Back button; Escape closes it too."""

    def __init__(self, screen_size: Tuple[int, int]) -> None:
        self.title_font = _load_font("Medici Text.ttf", 46)
        self.heading_font = _load_font("RomanAntique.ttf", 26)
        self.text_font = _load_font("Augusta.ttf", 20)
        self.key_font = _load_font("RomanAntique.ttf", 18)

        w, h = screen_size
        self.panel_rect = pygame.Rect(0, 0, min(_PANEL_W, w - 40), min(_PANEL_H, h - 40))
        self.panel_rect.center = (w // 2, h // 2)
        self.back_rect = pygame.Rect(0, 0, 160, 42)
        self.back_rect.midbottom = (self.panel_rect.centerx, self.panel_rect.bottom - 20)

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        """True when the click closes the overview."""
        return self.back_rect.collidepoint(pos)

    def handle_key(self, event: pygame.event.Event) -> bool:
        """True when the key closes the overview."""
        return event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN)

    def draw(self, screen: pygame.Surface, mouse_pos: Tuple[int, int], dim: bool = True) -> None:
        if dim:
            overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 128))
            screen.blit(overlay, (0, 0))

        pygame.draw.rect(screen, SANDY_BROWN, self.panel_rect, border_radius=6)
        pygame.draw.rect(screen, DARK_BROWN, self.panel_rect, 3, border_radius=6)

        title = self.title_font.render("Controls", True, DARK_BROWN)
        title_rect = title.get_rect(centerx=self.panel_rect.centerx, top=self.panel_rect.top + 18)
        screen.blit(title, title_rect)
        divider_y = title_rect.bottom + 8
        pygame.draw.line(screen, DARK_BROWN, (self.panel_rect.left + 30, divider_y),
                         (self.panel_rect.right - 30, divider_y), 1)

        column_w = (self.panel_rect.width - 90) // 2
        top = divider_y + 16
        self._draw_column(screen, LEFT_COLUMN, self.panel_rect.left + 30, top)
        self._draw_column(screen, RIGHT_COLUMN, self.panel_rect.left + 60 + column_w, top)

        hovered = self.back_rect.collidepoint(mouse_pos)
        pygame.draw.rect(screen, PALE_BROWN if hovered else TAN, self.back_rect, border_radius=4)
        pygame.draw.rect(screen, DARK_BROWN, self.back_rect, 2, border_radius=4)
        label = self.heading_font.render("Back", True, WHITE if hovered else DARK_BROWN)
        screen.blit(label, label.get_rect(center=self.back_rect.center))

    def _draw_column(self, screen: pygame.Surface, sections: List[Section], left: int, top: int) -> None:
        y = top
        for heading, rows in sections:
            surf = self.heading_font.render(heading, True, DARK_BROWN)
            screen.blit(surf, (left, y))
            y += surf.get_height() + 4
            for keys, text in rows:
                self._draw_keys(screen, keys, left + 8, y + _ROW_H // 2)
                desc = self.text_font.render(text, True, DARK_BROWN)
                screen.blit(desc, desc.get_rect(midleft=(left + 8 + _KEY_COLUMN_W, y + _ROW_H // 2)))
                y += _ROW_H
            y += _SECTION_GAP

    def _draw_keys(self, screen: pygame.Surface, keys: Keys, left: int, centery: int) -> None:
        x = left
        for i, chord in enumerate(keys):
            if i:
                x = self._draw_joiner(screen, "/", x, centery)
            for j, cap in enumerate(chord):
                if j:
                    x = self._draw_joiner(screen, "+", x, centery)
                x = self._draw_cap(screen, cap, x, centery)

    def _draw_cap(self, screen: pygame.Surface, cap: str, x: int, centery: int) -> int:
        """Draw one key cap from x and return where the next item starts."""
        text = self.key_font.render(cap, True, DARK_BROWN)
        rect = pygame.Rect(0, 0, max(26, text.get_width() + 14), 24)
        rect.midleft = (x, centery)
        pygame.draw.rect(screen, TAN, rect, border_radius=4)
        pygame.draw.line(screen, PALE_BROWN, (rect.left + 3, rect.bottom - 1), (rect.right - 4, rect.bottom - 1), 2)
        pygame.draw.rect(screen, DARK_BROWN, rect, 1, border_radius=4)
        screen.blit(text, text.get_rect(center=rect.center))
        return rect.right + 4

    def _draw_joiner(self, screen: pygame.Surface, mark: str, x: int, centery: int) -> int:
        surf = self.text_font.render(mark, True, DARK_GRAY)
        screen.blit(surf, surf.get_rect(midleft=(x, centery)))
        return x + surf.get_width() + 4
