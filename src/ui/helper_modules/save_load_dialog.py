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
from ...persistence.save_manager import get_save_slots, next_free_slot
from ..slot_list import SlotList, rows_height
from ..ui_utils import draw_9slice

if TYPE_CHECKING:
    from ...game import Game

_WINDOW_W = 660
_SLOT_H = 90
_SLOT_SPACING = 10
_SLOT_MARGIN_TOP = 96    # top padding (~30px) + title + divider gap
_SLOT_TO_CANCEL_GAP = 14 # space between last slot and cancel button
_CANCEL_H = 36
_CANCEL_BOTTOM_PAD = 32  # space below cancel button to window edge
_MIN_VISIBLE_SLOTS = 3   # keeps the name-entry phase fitting in the window
_MAX_VISIBLE_SLOTS = 5   # beyond this the slot list scrolls


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
        entries: List[Optional[dict]],
    ) -> None:
        self.screen = screen
        self.font = font
        self.game = game
        self.title = title
        # One row per entry: a slot-info dict from get_save_slots(), or None
        # for the "New Save Game..." row
        self.entries = entries
        self._thumb_cache: dict = {}
        self._thumb_rects: dict = {}       # entry index → Rect of drawn thumbnail
        self._preview_cache: dict = {}     # entry index → full-res Surface
        self._hover_slot: Optional[int] = None
        self._hover_start: int = 0

        # Title font — matches main menu "Load Game" heading
        try:
            self.title_font = pygame.font.Font(
                os.path.join(FONTS_PATH, "Medici Text.ttf"), 44
            )
        except Exception:
            self.title_font = font

        # Window height derived from the visible rows so every gap is explicit
        visible = max(_MIN_VISIBLE_SLOTS, min(_MAX_VISIBLE_SLOTS, len(entries)))
        slots_h = rows_height(visible, _SLOT_H, _SLOT_SPACING)
        window_h = (
            _SLOT_MARGIN_TOP
            + slots_h
            + _SLOT_TO_CANCEL_GAP
            + _CANCEL_H
            + _CANCEL_BOTTOM_PAD
        )
        self.window_rect = pygame.Rect(0, 0, _WINDOW_W, window_h)
        self.window_rect.center = (screen.get_width() // 2, screen.get_height() // 2)

        # Slot list — 30px margin on each side
        slot_margin = 30
        slots_top = self.window_rect.top + _SLOT_MARGIN_TOP
        self.slot_list = SlotList(
            count=len(entries),
            visible=visible,
            left=self.window_rect.left + slot_margin,
            top=slots_top,
            width=_WINDOW_W - 2 * slot_margin,
            row_h=_SLOT_H,
            spacing=_SLOT_SPACING,
        )
        # Tells event_handler the mouse wheel belongs to this dialog (no map zoom)
        self._max_scroll = self.slot_list.max_offset

        # Cancel button — positioned relative to the slot area, not window bottom
        cancel_top = slots_top + slots_h + _SLOT_TO_CANCEL_GAP
        self.cancel_rect = pygame.Rect(
            self.window_rect.centerx - 60,
            cancel_top,
            120,
            _CANCEL_H,
        )

    def _draw_slot_list(self, mouse_pos: Tuple[int, int], readable_only: bool) -> None:
        # Thumbnails of rows scrolled out of view must not trigger the preview
        self._thumb_rects.clear()
        for i, rect in self.slot_list.visible_rows():
            entry = self.entries[i]
            clickable = not (readable_only and entry and entry["corrupted"])
            self._draw_slot(rect, i, entry, clickable=clickable, mouse_pos=mouse_pos)
        self.slot_list.draw_scrollbar(self.screen)

    def _clicked_slot(self, pos: Tuple[int, int]) -> Optional[int]:
        for i, rect in self.slot_list.visible_rows():
            if rect.collidepoint(pos):
                return i
        return None

    def _draw_background(self) -> None:
        overlay = pygame.Surface(
            (self.screen.get_width(), self.screen.get_height()), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))

        if hasattr(self.game, "pic_info_window"):
            draw_9slice(self.screen, self.game.pic_info_window, self.window_rect)
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
        if slot_info is None:
            self._draw_new_save_row(rect, hovered)
            return
        if slot_info["corrupted"]:
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

        # Thumbnail (right side of slot)
        _THUMB_W, _THUMB_H = 92, 56
        thumb_surf = None
        thumb_path = slot_info.get("thumbnail_path") if slot_info else None
        if thumb_path and os.path.exists(thumb_path):
            if slot_index not in self._thumb_cache:
                try:
                    raw = pygame.image.load(thumb_path).convert()
                    self._thumb_cache[slot_index] = pygame.transform.smoothscale(raw, (_THUMB_W, _THUMB_H))
                except Exception:
                    self._thumb_cache[slot_index] = None
            thumb_surf = self._thumb_cache.get(slot_index)
        if thumb_surf is not None:
            thumb_x = rect.right - _THUMB_W - 6
            thumb_y = rect.centery - _THUMB_H // 2
            self._thumb_rects[slot_index] = pygame.Rect(thumb_x, thumb_y, _THUMB_W, _THUMB_H)
            self.screen.blit(thumb_surf, (thumb_x, thumb_y))
            pygame.draw.rect(self.screen, DARK_BROWN,
                             pygame.Rect(thumb_x, thumb_y, _THUMB_W, _THUMB_H), 1)
        else:
            self._thumb_rects.pop(slot_index, None)

        text_right = (rect.right - _THUMB_W - 14) if thumb_surf is not None else rect.right

        corrupted = slot_info["corrupted"]
        label_color = DARK_GRAY if corrupted else DARK_BROWN
        label = slot_info.get("save_name") or f"Slot {slot_info['slot']}"
        _draw_bold(self.screen, self.font, label, label_color, rect.left + 12, rect.top + 8)

        small = getattr(self.game, "small_font", self.font)
        max_w = text_right - rect.left - 12

        def _blit_row(text: str, color: tuple, y: int) -> None:
            surf = small.render(text, True, color)
            if surf.get_width() > max_w:
                clip = pygame.Surface((max_w, surf.get_height()), pygame.SRCALPHA)
                clip.blit(surf, (0, 0))
                surf = clip
            self.screen.blit(surf, (rect.left + 12, y))

        if not corrupted:
            ps = slot_info.get("playtime_seconds", 0.0)
            h, m = int(ps) // 3600, (int(ps) % 3600) // 60
            row2 = (
                f"{_format_game_date(slot_info['game_date'])}"
                f"   |   {slot_info.get('wealth', slot_info['money']):.1f} G wealth"
                f"   |   {slot_info['money']:.1f} G cash"
            )
            row3 = f"{h:02d}h {m:02d}m played   |   Saved {_format_saved_at(slot_info['saved_at'])}"
            _blit_row(row2, BLACK, rect.top + 34)
            _blit_row(row3, BLACK, rect.top + 58)
        else:
            _blit_row("Unreadable save file", DARK_GRAY, rect.top + 34)

    def _draw_new_save_row(self, rect: pygame.Rect, hovered: bool) -> None:
        bg = SANDY_BROWN if hovered else WHEAT
        pygame.draw.rect(self.screen, bg, rect, border_radius=4)
        pygame.draw.rect(self.screen, DARK_BROWN, rect, 2, border_radius=4)
        label = "+  New Save Game..."
        w, h = self.font.size(label)
        _draw_bold(self.screen, self.font, label, DARK_BROWN,
                   rect.centerx - w // 2, rect.centery - h // 2)

    def _draw_empty_message(self, text: str) -> None:
        small = getattr(self.game, "small_font", self.font)
        surf = small.render(text, True, DARK_GRAY)
        area = pygame.Rect(self.window_rect.left, self.window_rect.top + _SLOT_MARGIN_TOP,
                           self.window_rect.width, self.cancel_rect.top - _SLOT_TO_CANCEL_GAP
                           - self.window_rect.top - _SLOT_MARGIN_TOP)
        self.screen.blit(surf, surf.get_rect(center=area.center))

    def _check_hover(self, mouse_pos: Tuple[int, int]) -> None:
        """Track which thumbnail the mouse is hovering over and when it started."""
        for idx, thumb_rect in self._thumb_rects.items():
            if thumb_rect.collidepoint(mouse_pos):
                if self._hover_slot != idx:
                    self._hover_slot = idx
                    self._hover_start = pygame.time.get_ticks()
                return
        self._hover_slot = None

    def _draw_preview(self) -> None:
        """If a thumbnail has been hovered for ≥0.5 s, show it at full saved resolution."""
        if self._hover_slot is None:
            return
        if pygame.time.get_ticks() - self._hover_start < 500:
            return
        slot_info = self.entries[self._hover_slot]
        if not slot_info or slot_info["corrupted"]:
            return
        thumb_path = slot_info.get("thumbnail_path")
        if not thumb_path or not os.path.exists(thumb_path):
            return
        if self._hover_slot not in self._preview_cache:
            try:
                self._preview_cache[self._hover_slot] = pygame.image.load(thumb_path).convert()
            except Exception:
                self._preview_cache[self._hover_slot] = None
        preview = self._preview_cache.get(self._hover_slot)
        if preview is None:
            return
        pw, ph = preview.get_size()
        px = self.screen.get_width() // 2 - pw // 2
        py = self.screen.get_height() // 2 - ph // 2
        pad = 6
        shadow = pygame.Surface((pw + pad * 2, ph + pad * 2), pygame.SRCALPHA)
        shadow.fill((0, 0, 0, 180))
        self.screen.blit(shadow, (px - pad, py - pad))
        self.screen.blit(preview, (px, py))
        pygame.draw.rect(self.screen, DARK_BROWN, pygame.Rect(px, py, pw, ph), 2)

    def _draw_cancel(self, mouse_pos: Tuple[int, int]) -> None:
        hovered = self.cancel_rect.collidepoint(mouse_pos)
        bg = SANDY_BROWN if hovered else TAN
        pygame.draw.rect(self.screen, bg, self.cancel_rect, border_radius=4)
        pygame.draw.rect(self.screen, DARK_BROWN, self.cancel_rect, 2, border_radius=4)
        surf = self.font.render("Cancel", True, BLACK)
        self.screen.blit(surf, surf.get_rect(center=self.cancel_rect.center))


_MAX_NAME_LEN = 30


class SaveDialog(_BaseSlotDialog):
    """Modal dialog for saving to a new slot or overwriting an existing save.

    Phase 1 — slot selection: the first row, "New Save Game...", targets the
              next free slot number; every other row is an existing save.
              Clicking a row moves to phase 2.
    Phase 2 — name entry: player types a name (max 30 chars), then confirms.

    handle_click() returns "save_slot_<n>" (with self.save_name set) or "Cancel".
    handle_event() scrolls the slot list in phase 1 and handles KEYDOWN for
    text input in phase 2.
    """

    def __init__(self, screen: pygame.Surface, font: pygame.font.Font, game: "Game") -> None:
        super().__init__(screen, font, game, "Save Game", [None] + get_save_slots())
        self._phase: str = "slot"       # "slot" or "name"
        self._selected_slot: Optional[int] = None
        self._overwriting: bool = False
        self._name_text: str = ""
        self.save_name: str = ""        # read by event_handler after confirm
        # Capture the game frame before the dialog is drawn (no dialog UI in screenshot)
        self.screenshot: pygame.Surface = pygame.display.get_surface().copy()

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
            self._draw_slot_list(mouse_pos, readable_only=False)
            self._draw_cancel(mouse_pos)
            self._check_hover(mouse_pos)
            self._draw_preview()
        else:
            self._draw_name_entry(mouse_pos)

    def _draw_name_entry(self, mouse_pos: Tuple[int, int]) -> None:
        small = getattr(self.game, "small_font", self.font)

        # Slot subtitle
        subtitle = (f"Overwrite Slot {self._selected_slot}" if self._overwriting
                    else f"New save in Slot {self._selected_slot}")
        slot_label = small.render(subtitle, True, DARK_GRAY)
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
        if self._phase == "slot":
            self.slot_list.handle_wheel(event)
            return
        if event.type != pygame.KEYDOWN:
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
            if self.slot_list.handle_click(pos):
                return None
            i = self._clicked_slot(pos)
            if i is not None:
                existing = self.entries[i]
                self._phase = "name"
                self._overwriting = existing is not None
                if existing is None:
                    self._selected_slot = next_free_slot()
                    self._name_text = ""
                else:
                    self._selected_slot = existing["slot"]
                    self._name_text = existing.get("save_name") or ""
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
    """Modal dialog listing every save file in the saves folder.

    Unreadable saves are greyed out and non-clickable.
    handle_click() returns "load_slot_<n>" or "Cancel".
    """

    def __init__(self, screen: pygame.Surface, font: pygame.font.Font, game: "Game") -> None:
        super().__init__(screen, font, game, "Load Game", get_save_slots())

    def draw(self) -> None:
        self._draw_background()
        self._draw_title()
        mouse_pos = pygame.mouse.get_pos()
        if self.entries:
            self._draw_slot_list(mouse_pos, readable_only=True)
        else:
            self._draw_empty_message("No saved games found.")
        self._draw_cancel(mouse_pos)
        self._check_hover(mouse_pos)
        self._draw_preview()

    def handle_event(self, event: pygame.event.Event) -> None:
        self.slot_list.handle_wheel(event)

    def handle_click(self, pos: Tuple[int, int]) -> Optional[str]:
        if self.cancel_rect.collidepoint(pos):
            return "Cancel"
        if self.slot_list.handle_click(pos):
            return None
        i = self._clicked_slot(pos)
        if i is not None and not self.entries[i]["corrupted"]:
            return f"load_slot_{self.entries[i]['slot']}"
        return None
