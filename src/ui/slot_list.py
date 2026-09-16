"""Scrollable viewport over a vertical list of save slots.

Shared by the in-game save/load dialogs and the main-menu load screen.  The
list scrolls in whole rows so a slot is never drawn half-clipped.
"""

from typing import List, Tuple

import pygame

from ..config.colors import DARK_BROWN, TAN

_SCROLLBAR_W = 8
_SCROLLBAR_GAP = 8


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
