"""In-game save/load slot selection dialogs.

Both dialogs follow the InfoWindow pattern: stored in game_state.info_window,
drawn as overlays, and routed through the existing event_handler click mechanism.
"""

import datetime
import pygame
from typing import List, Optional, Tuple, TYPE_CHECKING

from ...config.colors import (
    BLACK, WHITE, DARK_GRAY, LIGHT_GRAY, GRAY,
    DARK_BROWN, TAN, SANDY_BROWN, BEIGE,
)
from ...persistence.save_manager import get_save_slots

if TYPE_CHECKING:
    from ...game import Game

_WINDOW_W = 560
_WINDOW_H = 340
_SLOT_H = 58
_SLOT_SPACING = 10
_SLOT_MARGIN_TOP = 56


def _format_game_date(iso_str: str) -> str:
    try:
        dt = datetime.datetime.fromisoformat(iso_str)
        return dt.strftime("%d %b %Y  %H:%M")
    except Exception:
        return iso_str


def _format_saved_at(iso_str: str) -> str:
    try:
        dt = datetime.datetime.fromisoformat(iso_str)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso_str


class _BaseSlotDialog:
    """Shared geometry and rendering for save/load dialogs."""

    def __init__(
        self,
        screen: pygame.Surface,
        font: pygame.font.Font,
        game: "Game",
        title: str,
    ) -> None:
        self.screen = screen
        self.font = font
        self.game = game
        self.title = title
        self.slots = get_save_slots()

        self.window_rect = pygame.Rect(0, 0, _WINDOW_W, _WINDOW_H)
        self.window_rect.center = (screen.get_width() // 2, screen.get_height() // 2)

        # Slot rects
        self.slot_rects: List[pygame.Rect] = []
        slot_w = _WINDOW_W - 40
        top = self.window_rect.top + _SLOT_MARGIN_TOP
        for i in range(3):
            self.slot_rects.append(
                pygame.Rect(
                    self.window_rect.left + 20,
                    top + i * (_SLOT_H + _SLOT_SPACING),
                    slot_w,
                    _SLOT_H,
                )
            )

        # Cancel button
        cancel_h = 36
        self.cancel_rect = pygame.Rect(
            self.window_rect.centerx - 60,
            self.window_rect.bottom - cancel_h - 12,
            120,
            cancel_h,
        )

    def _draw_background(self) -> None:
        # Dim overlay
        overlay = pygame.Surface(
            (self.screen.get_width(), self.screen.get_height()), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))

        # Window frame (reuse info_window_frame image if available)
        if hasattr(self.game, "pic_info_window"):
            scaled = pygame.transform.scale(
                self.game.pic_info_window, (_WINDOW_W, _WINDOW_H)
            )
            self.screen.blit(scaled, self.window_rect)
        else:
            pygame.draw.rect(self.screen, BEIGE, self.window_rect)
            pygame.draw.rect(self.screen, DARK_BROWN, self.window_rect, 2)

    def _draw_slot(
        self,
        rect: pygame.Rect,
        slot_index: int,
        slot_info: Optional[dict],
        clickable: bool,
        mouse_pos: Tuple[int, int],
    ) -> None:
        hovered = clickable and rect.collidepoint(mouse_pos)
        if not slot_info:
            bg = LIGHT_GRAY
            border = GRAY
        elif hovered:
            bg = SANDY_BROWN
            border = DARK_BROWN
        else:
            bg = TAN
            border = DARK_BROWN
        pygame.draw.rect(self.screen, bg, rect, border_radius=4)
        pygame.draw.rect(self.screen, border, rect, 2, border_radius=4)

        label_color = BLACK if slot_info else DARK_GRAY
        label = self.font.render(f"Slot {slot_index + 1}", True, label_color)
        self.screen.blit(label, (rect.left + 12, rect.top + 8))

        small = getattr(self.game, "small_font", self.font)
        if slot_info:
            info_str = (
                f"{_format_game_date(slot_info['game_date'])}"
                f"   |   {slot_info['money']:.1f} Gold"
                f"   |   Saved {_format_saved_at(slot_info['saved_at'])}"
            )
        else:
            info_str = "Empty"
        info_surf = small.render(info_str, True, DARK_GRAY if not slot_info else BLACK)
        self.screen.blit(info_surf, (rect.left + 12, rect.bottom - 22))

    def _draw_cancel(self, mouse_pos: Tuple[int, int]) -> None:
        hovered = self.cancel_rect.collidepoint(mouse_pos)
        bg = SANDY_BROWN if hovered else TAN
        pygame.draw.rect(self.screen, bg, self.cancel_rect, border_radius=4)
        pygame.draw.rect(self.screen, DARK_BROWN, self.cancel_rect, 2, border_radius=4)
        surf = self.font.render("Cancel", True, BLACK)
        self.screen.blit(surf, surf.get_rect(center=self.cancel_rect.center))

    def _draw_title(self) -> None:
        surf = self.font.render(self.title, True, BLACK)
        self.screen.blit(
            surf,
            surf.get_rect(centerx=self.window_rect.centerx, top=self.window_rect.top + 14),
        )


class SaveDialog(_BaseSlotDialog):
    """Modal dialog for saving to one of 3 fixed slots.

    handle_click() returns "save_slot_1/2/3" or "Cancel".
    """

    def __init__(self, screen: pygame.Surface, font: pygame.font.Font, game: "Game") -> None:
        super().__init__(screen, font, game, "Save Game")

    def draw(self) -> None:
        self._draw_background()
        self._draw_title()
        mouse_pos = pygame.mouse.get_pos()
        for i, rect in enumerate(self.slot_rects):
            self._draw_slot(rect, i, self.slots[i], clickable=True, mouse_pos=mouse_pos)
        self._draw_cancel(mouse_pos)

    def handle_click(self, pos: Tuple[int, int]) -> Optional[str]:
        if self.cancel_rect.collidepoint(pos):
            return "Cancel"
        for i, rect in enumerate(self.slot_rects):
            if rect.collidepoint(pos):
                return f"save_slot_{i + 1}"
        return None


class LoadDialog(_BaseSlotDialog):
    """Modal dialog for loading from one of 3 fixed slots.

    Empty slots are greyed out and non-clickable.
    handle_click() returns "load_slot_1/2/3" or "Cancel".
    """

    def __init__(self, screen: pygame.Surface, font: pygame.font.Font, game: "Game") -> None:
        super().__init__(screen, font, game, "Load Game")

    def draw(self) -> None:
        self._draw_background()
        self._draw_title()
        mouse_pos = pygame.mouse.get_pos()
        for i, rect in enumerate(self.slot_rects):
            clickable = self.slots[i] is not None
            self._draw_slot(rect, i, self.slots[i], clickable=clickable, mouse_pos=mouse_pos)
        self._draw_cancel(mouse_pos)

    def handle_click(self, pos: Tuple[int, int]) -> Optional[str]:
        if self.cancel_rect.collidepoint(pos):
            return "Cancel"
        for i, rect in enumerate(self.slot_rects):
            if rect.collidepoint(pos) and self.slots[i] is not None:
                return f"load_slot_{i + 1}"
        return None
