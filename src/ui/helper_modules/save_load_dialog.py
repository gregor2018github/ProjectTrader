"""In-game save/load slot selection dialogs.

Both dialogs follow the InfoWindow pattern: stored in game_state.info_window,
drawn as overlays, and routed through the existing event_handler click mechanism.
"""

import datetime
import os
import pygame
from typing import List, Optional, Tuple, TYPE_CHECKING

from ...config.colors import (
    BLACK, WHITE, DARK_GRAY, LIGHT_GRAY, GRAY,
    DARK_BROWN, TAN, SANDY_BROWN, BEIGE, WHEAT,
)
from ...config.constants import FONTS_PATH
from ...persistence.save_manager import get_save_slots

if TYPE_CHECKING:
    from ...game import Game

_WINDOW_W = 580
_SLOT_H = 66
_SLOT_SPACING = 10
_SLOT_MARGIN_TOP = 96    # top padding (~30px) + title + divider gap
_SLOT_TO_CANCEL_GAP = 14 # space between last slot and cancel button
_CANCEL_H = 36
_CANCEL_BOTTOM_PAD = 32  # space below cancel button to window edge
# Window height derived so every gap is explicit
_WINDOW_H = (
    _SLOT_MARGIN_TOP
    + 3 * _SLOT_H + 2 * _SLOT_SPACING
    + _SLOT_TO_CANCEL_GAP
    + _CANCEL_H
    + _CANCEL_BOTTOM_PAD
)  # = 96 + 198 + 20 + 14 + 36 + 32 = 396


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


def _draw_bold(surface: pygame.Surface, font: pygame.font.Font, text: str,
               color: tuple, x: int, y: int) -> None:
    """Render text with a fake-bold effect by drawing offset copies."""
    for dx, dy in ((1, 0), (0, 1), (1, 1)):
        surf = font.render(text, True, color)
        surface.blit(surf, (x + dx, y + dy))
    surf = font.render(text, True, color)
    surface.blit(surf, (x, y))


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

        # Title font — matches main menu "Load Game" heading
        try:
            self.title_font = pygame.font.Font(
                os.path.join(FONTS_PATH, "Medici Text.ttf"), 44
            )
        except Exception:
            self.title_font = font

        self.window_rect = pygame.Rect(0, 0, _WINDOW_W, _WINDOW_H)
        self.window_rect.center = (screen.get_width() // 2, screen.get_height() // 2)

        # Slot rects — 30px margin on each side (+10 vs previous 20)
        self.slot_rects: List[pygame.Rect] = []
        slot_margin = 30
        slot_w = _WINDOW_W - 2 * slot_margin
        slots_top = self.window_rect.top + _SLOT_MARGIN_TOP
        for i in range(3):
            self.slot_rects.append(
                pygame.Rect(
                    self.window_rect.left + slot_margin,
                    slots_top + i * (_SLOT_H + _SLOT_SPACING),
                    slot_w,
                    _SLOT_H,
                )
            )

        # Cancel button — positioned relative to last slot, not window bottom
        cancel_top = self.slot_rects[-1].bottom + _SLOT_TO_CANCEL_GAP
        self.cancel_rect = pygame.Rect(
            self.window_rect.centerx - 60,
            cancel_top,
            120,
            _CANCEL_H,
        )

    def _draw_background(self) -> None:
        overlay = pygame.Surface(
            (self.screen.get_width(), self.screen.get_height()), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))

        if hasattr(self.game, "pic_info_window"):
            scaled = pygame.transform.scale(
                self.game.pic_info_window, (_WINDOW_W, _WINDOW_H)
            )
            self.screen.blit(scaled, self.window_rect)
        else:
            pygame.draw.rect(self.screen, BEIGE, self.window_rect)
            pygame.draw.rect(self.screen, DARK_BROWN, self.window_rect, 2)

    def _draw_title(self) -> None:
        surf = self.title_font.render(self.title, True, DARK_BROWN)
        title_rect = surf.get_rect(
            centerx=self.window_rect.centerx,
            top=self.window_rect.top + 28,
        )
        self.screen.blit(surf, title_rect)

        # Divider line below title
        divider_y = title_rect.bottom + 8
        pygame.draw.line(
            self.screen, DARK_BROWN,
            (self.window_rect.left + 30, divider_y),
            (self.window_rect.right - 30, divider_y),
            1,
        )

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
            if hovered:
                bg, border = WHEAT, DARK_GRAY
            else:
                bg, border = LIGHT_GRAY, GRAY
        elif hovered:
            bg, border = SANDY_BROWN, DARK_BROWN
        else:
            bg, border = TAN, DARK_BROWN
        pygame.draw.rect(self.screen, bg, rect, border_radius=4)
        pygame.draw.rect(self.screen, border, rect, 2, border_radius=4)

        label_color = DARK_BROWN if slot_info else DARK_GRAY
        label = (slot_info.get("save_name") or f"Slot {slot_index + 1}") if slot_info else f"Slot {slot_index + 1}"
        _draw_bold(self.screen, self.font, label, label_color, rect.left + 12, rect.top + 8)

        small = getattr(self.game, "small_font", self.font)
        if slot_info:
            info_str = (
                f"{_format_game_date(slot_info['game_date'])}"
                f"   |   {slot_info['money']:.1f} Gold"
                f"   |   Saved {_format_saved_at(slot_info['saved_at'])}"
            )
            info_color = BLACK
        else:
            info_str = "Empty"
            info_color = DARK_GRAY
        info_surf = small.render(info_str, True, info_color)
        self.screen.blit(info_surf, (rect.left + 12, rect.bottom - 24))

    def _draw_cancel(self, mouse_pos: Tuple[int, int]) -> None:
        hovered = self.cancel_rect.collidepoint(mouse_pos)
        bg = SANDY_BROWN if hovered else TAN
        pygame.draw.rect(self.screen, bg, self.cancel_rect, border_radius=4)
        pygame.draw.rect(self.screen, DARK_BROWN, self.cancel_rect, 2, border_radius=4)
        surf = self.font.render("Cancel", True, BLACK)
        self.screen.blit(surf, surf.get_rect(center=self.cancel_rect.center))


_MAX_NAME_LEN = 30


class SaveDialog(_BaseSlotDialog):
    """Modal dialog for saving to one of 3 fixed slots.

    Phase 1 — slot selection: clicking a slot moves to phase 2.
    Phase 2 — name entry: player types a name (max 30 chars), then confirms.

    handle_click() returns "save_slot_1/2/3" (with self.save_name set) or "Cancel".
    handle_event() handles KEYDOWN for text input in phase 2.
    """

    def __init__(self, screen: pygame.Surface, font: pygame.font.Font, game: "Game") -> None:
        super().__init__(screen, font, game, "Save Game")
        self._phase: str = "slot"       # "slot" or "name"
        self._selected_slot: Optional[int] = None
        self._name_text: str = ""
        self.save_name: str = ""        # read by event_handler after confirm

        # Name-entry UI rects (relative to window_rect)
        input_top = self.window_rect.top + 200
        input_h = 44
        btn_top = input_top + input_h + 24
        btn_h = 36
        btn_w = 110
        self._input_rect = pygame.Rect(
            self.window_rect.left + 30,
            input_top,
            _WINDOW_W - 60,
            input_h,
        )
        self._confirm_rect = pygame.Rect(
            self.window_rect.centerx - btn_w - 8,
            btn_top, btn_w, btn_h,
        )
        self._back_name_rect = pygame.Rect(
            self.window_rect.centerx + 8,
            btn_top, btn_w, btn_h,
        )

    def draw(self) -> None:
        self._draw_background()
        self._draw_title()
        mouse_pos = pygame.mouse.get_pos()
        if self._phase == "slot":
            for i, rect in enumerate(self.slot_rects):
                self._draw_slot(rect, i, self.slots[i], clickable=True, mouse_pos=mouse_pos)
            self._draw_cancel(mouse_pos)
        else:
            self._draw_name_entry(mouse_pos)

    def _draw_name_entry(self, mouse_pos: Tuple[int, int]) -> None:
        small = getattr(self.game, "small_font", self.font)

        # Slot subtitle
        slot_label = small.render(f"Slot {self._selected_slot}", True, DARK_GRAY)
        self.screen.blit(slot_label, slot_label.get_rect(
            centerx=self.window_rect.centerx,
            top=self.window_rect.top + 108,
        ))

        # Prompt
        prompt = self.font.render("Enter a name for this save:", True, DARK_BROWN)
        self.screen.blit(prompt, prompt.get_rect(
            centerx=self.window_rect.centerx,
            top=self.window_rect.top + 152,
        ))

        # Text input box
        pygame.draw.rect(self.screen, WHITE, self._input_rect, border_radius=4)
        pygame.draw.rect(self.screen, DARK_BROWN, self._input_rect, 2, border_radius=4)
        cursor = "|" if pygame.time.get_ticks() // 500 % 2 == 0 else " "
        text_surf = self.font.render(self._name_text + cursor, True, BLACK)
        self.screen.blit(text_surf, (
            self._input_rect.left + 10,
            self._input_rect.centery - text_surf.get_height() // 2,
        ))

        # Char counter
        counter = small.render(f"{len(self._name_text)}/{_MAX_NAME_LEN}", True, DARK_GRAY)
        self.screen.blit(counter, counter.get_rect(
            right=self._input_rect.right - 6,
            top=self._input_rect.bottom + 4,
        ))

        # Save button
        hov = self._confirm_rect.collidepoint(mouse_pos)
        pygame.draw.rect(self.screen, SANDY_BROWN if hov else TAN, self._confirm_rect, border_radius=4)
        pygame.draw.rect(self.screen, DARK_BROWN, self._confirm_rect, 2, border_radius=4)
        s = self.font.render("Save", True, BLACK)
        self.screen.blit(s, s.get_rect(center=self._confirm_rect.center))

        # Back button
        hov = self._back_name_rect.collidepoint(mouse_pos)
        pygame.draw.rect(self.screen, SANDY_BROWN if hov else TAN, self._back_name_rect, border_radius=4)
        pygame.draw.rect(self.screen, DARK_BROWN, self._back_name_rect, 2, border_radius=4)
        s = self.font.render("Back", True, BLACK)
        self.screen.blit(s, s.get_rect(center=self._back_name_rect.center))

    def handle_event(self, event: pygame.event.Event) -> None:
        if self._phase != "name" or event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_BACKSPACE:
            self._name_text = self._name_text[:-1]
        elif event.key == pygame.K_RETURN:
            self.save_name = self._name_text.strip()
            # Signal confirm via a pending flag; click handler will pick it up
            # Actually just store — event_handler watches handle_click only.
            # We let Enter act like clicking Save by returning from handle_click next frame.
            # Simpler: set a flag and handle in next draw/click cycle.
            self._enter_pressed = True
        elif len(self._name_text) < _MAX_NAME_LEN and event.unicode.isprintable() and event.unicode:
            self._name_text += event.unicode

    def handle_click(self, pos: Tuple[int, int]) -> Optional[str]:
        # Check Enter-key confirm flag
        if getattr(self, "_enter_pressed", False):
            self._enter_pressed = False
            self.save_name = self._name_text.strip()
            return f"save_slot_{self._selected_slot}"

        if self._phase == "slot":
            if self.cancel_rect.collidepoint(pos):
                return "Cancel"
            for i, rect in enumerate(self.slot_rects):
                if rect.collidepoint(pos):
                    self._phase = "name"
                    self._selected_slot = i + 1
                    existing = self.slots[i]
                    self._name_text = (existing.get("save_name") or "") if existing else ""
                    return None
        else:
            if self._confirm_rect.collidepoint(pos):
                self.save_name = self._name_text.strip()
                return f"save_slot_{self._selected_slot}"
            if self._back_name_rect.collidepoint(pos):
                self._phase = "slot"
                return None
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
