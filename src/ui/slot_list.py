"""Scrollable viewport over a vertical list of save slots.

Shared by the in-game save/load dialogs and the main-menu load screen.  The
list scrolls in whole rows so a slot is never drawn half-clipped.
"""

from typing import Any, Dict, List, Optional, Tuple

import pygame

from ..config.colors import (
    BEIGE, BLACK, DARK_BROWN, MUTED_DARK_RED, MUTED_RED, SANDY_BROWN, TAN, WHITE,
)

_SCROLLBAR_W = 8
_SCROLLBAR_GAP = 8

_CROSS_SIZE = 22
# Width a save row reserves on its right edge for the delete cross
CROSS_COLUMN_W = _CROSS_SIZE + 14
DELETE_TOOLTIP = "Delete Save File"
_CURSOR_W = 30  # width of the custom cursor image drawn at the mouse position


def rows_height(rows: int, row_h: int, spacing: int) -> int:
    """Pixel height of ``rows`` stacked rows (0 for none)."""
    return max(0, rows * row_h + (rows - 1) * spacing)


class SlotList:
    """Geometry and scroll state for ``count`` rows shown ``visible`` at a time."""

    def __init__(self, count: int, visible: int, left: int, top: int,
                 width: int, row_h: int, spacing: int) -> None:
        self.count = count
        self.visible = max(0, min(visible, count))
        self.row_h = row_h
        self.spacing = spacing
        self.offset = 0
        self.scrollable = count > self.visible
        # Reserve room for the scrollbar only when it is actually shown
        row_w = width - (_SCROLLBAR_W + _SCROLLBAR_GAP if self.scrollable else 0)
        self.rows_rect = pygame.Rect(left, top, row_w, self.height)
        self.track_rect = pygame.Rect(
            left + width - _SCROLLBAR_W, top, _SCROLLBAR_W, self.height
        )

    @property
    def height(self) -> int:
        return rows_height(self.visible, self.row_h, self.spacing)

    @property
    def bottom(self) -> int:
        return self.rows_rect.top + self.height

    @property
    def max_offset(self) -> int:
        return self.count - self.visible

    def visible_rows(self) -> List[Tuple[int, pygame.Rect]]:
        """Return ``(slot_index, rect)`` for every row currently on screen."""
        rows = []
        for pos in range(self.visible):
            index = self.offset + pos
            rows.append((index, pygame.Rect(
                self.rows_rect.left,
                self.rows_rect.top + pos * (self.row_h + self.spacing),
                self.rows_rect.width,
                self.row_h,
            )))
        return rows

    def scroll(self, rows: int) -> None:
        self.offset = max(0, min(self.max_offset, self.offset + rows))

    def handle_wheel(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEWHEEL:
            self.scroll(-event.y)

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        """Jump the list to the clicked track position. Returns True if consumed."""
        if not self.scrollable or not self.track_rect.inflate(8, 0).collidepoint(pos):
            return False
        thumb = self._thumb_rect()
        if thumb.collidepoint(pos):
            return True
        # Page towards the click
        self.scroll(self.visible if pos[1] > thumb.centery else -self.visible)
        return True

    def _thumb_rect(self) -> pygame.Rect:
        track = self.track_rect
        thumb_h = max(24, track.height * self.visible // self.count)
        thumb_y = track.top + (track.height - thumb_h) * self.offset // self.max_offset
        return pygame.Rect(track.left, thumb_y, track.width, thumb_h)

    def draw_scrollbar(self, surface: pygame.Surface) -> None:
        if not self.scrollable:
            return
        pygame.draw.rect(surface, TAN, self.track_rect, border_radius=4)
        pygame.draw.rect(surface, DARK_BROWN, self._thumb_rect(), border_radius=4)


# ---------------------------------------------------------------------------
# Delete button, tooltip and confirmation box
# ---------------------------------------------------------------------------

def delete_cross_rect(row: pygame.Rect) -> pygame.Rect:
    """Hit box of the delete cross at the right edge of a save row."""
    return pygame.Rect(
        row.right - _CROSS_SIZE - 8,
        row.centery - _CROSS_SIZE // 2,
        _CROSS_SIZE,
        _CROSS_SIZE,
    )


def draw_delete_cross(surface: pygame.Surface, row: pygame.Rect,
                      mouse_pos: Tuple[int, int]) -> bool:
    """Draw the delete cross for ``row``. Returns True if the mouse is over it."""
    rect = delete_cross_rect(row)
    hovered = rect.collidepoint(mouse_pos)
    if hovered:
        pygame.draw.rect(surface, MUTED_RED, rect, border_radius=4)
        pygame.draw.rect(surface, MUTED_DARK_RED, rect, 1, border_radius=4)
    color = WHITE if hovered else MUTED_DARK_RED
    inset = 6
    left, top = rect.left + inset, rect.top + inset
    right, bottom = rect.right - inset - 1, rect.bottom - inset - 1
    pygame.draw.line(surface, color, (left, top), (right, bottom), 3)
    pygame.draw.line(surface, color, (left, bottom), (right, top), 3)
    return hovered


def draw_tooltip(surface: pygame.Surface, font: pygame.font.Font, text: str,
                 pos: Tuple[int, int]) -> None:
    """Draw a small text box beside ``pos``, clear of the custom cursor image."""
    text_surf = font.render(text, True, BLACK)
    box = text_surf.get_rect().inflate(14, 8)
    # The cursor image (30x41) hangs right/down from pos: start right of it,
    # or flip to the left of pos when there is no room on the right
    box.midleft = (pos[0] + _CURSOR_W + 6, pos[1] + 12)
    if box.right > surface.get_width():
        box.right = pos[0] - 6
    box.clamp_ip(surface.get_rect())
    pygame.draw.rect(surface, BEIGE, box, border_radius=3)
    pygame.draw.rect(surface, DARK_BROWN, box, 1, border_radius=3)
    surface.blit(text_surf, text_surf.get_rect(center=box.center))


class DeleteConfirm:
    """"Are you sure?" box shown over a save list before a save is deleted."""

    _W, _H = 460, 180
    _BTN_W, _BTN_H = 130, 38

    def __init__(self, entry: Dict[str, Any], center: Tuple[int, int],
                 font: pygame.font.Font, small_font: pygame.font.Font) -> None:
        self.entry = entry
        self.font = font
        self.small_font = small_font
        self.rect = pygame.Rect(0, 0, self._W, self._H)
        self.rect.center = center
        btn_y = self.rect.bottom - self._BTN_H - 22
        self.delete_rect = pygame.Rect(
            self.rect.centerx - self._BTN_W - 10, btn_y, self._BTN_W, self._BTN_H
        )
        self.cancel_rect = pygame.Rect(
            self.rect.centerx + 10, btn_y, self._BTN_W, self._BTN_H
        )

    @property
    def slot(self) -> int:
        return self.entry["slot"]

    def draw(self, surface: pygame.Surface, mouse_pos: Tuple[int, int]) -> None:
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 110))
        surface.blit(overlay, (0, 0))

        pygame.draw.rect(surface, BEIGE, self.rect, border_radius=6)
        pygame.draw.rect(surface, DARK_BROWN, self.rect, 3, border_radius=6)

        title = self.font.render("Delete Save File?", True, DARK_BROWN)
        surface.blit(title, title.get_rect(centerx=self.rect.centerx, top=self.rect.top + 20))

        name = self.entry.get("save_name") or f"Slot {self.slot}"
        max_name = 28
        if len(name) > max_name:
            name = name[:max_name - 1] + "…"
        detail = self.small_font.render(
            f'"{name}" will be deleted permanently.', True, BLACK
        )
        surface.blit(detail, detail.get_rect(centerx=self.rect.centerx, top=self.rect.top + 64))

        for rect, label, base, hover, text_color in (
            (self.delete_rect, "Delete", MUTED_RED, MUTED_DARK_RED, WHITE),
            (self.cancel_rect, "Cancel", TAN, SANDY_BROWN, BLACK),
        ):
            bg = hover if rect.collidepoint(mouse_pos) else base
            pygame.draw.rect(surface, bg, rect, border_radius=4)
            pygame.draw.rect(surface, DARK_BROWN, rect, 2, border_radius=4)
            label_surf = self.font.render(label, True, text_color)
            surface.blit(label_surf, label_surf.get_rect(center=rect.center))

    def handle_click(self, pos: Tuple[int, int]) -> Optional[bool]:
        """True = delete confirmed, False = cancelled, None = click ignored."""
        if self.delete_rect.collidepoint(pos):
            return True
        if self.cancel_rect.collidepoint(pos) or not self.rect.collidepoint(pos):
            return False
        return None
