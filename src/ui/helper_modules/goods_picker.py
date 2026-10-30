"""A small panel over an inventory window for picking goods.

Either one good, to reserve a slot for (or "Any good" to lift that), or
several, the goods a warehouse accepts, toggled one by one with All and None.
Choices take effect at once, through the callback; the panel closes on a
single pick, Done, Cancel or a click beside it.
"""

import pygame
from typing import Callable, List, Optional, Set, Tuple, TYPE_CHECKING

from ...config.colors import BEIGE, DARK_BROWN, DARK_GRAY, LIGHT_GRAY, MUTED_GREEN, SANDY_BROWN, WHITE
from ..ui_utils import draw_9slice

if TYPE_CHECKING:
    from .inventory_window import InventoryWindow


COLS = 5
CELL = 78
CELL_GAP = 8
PAD = 16
TITLE_H = 34
BUTTON_H = 30
ICON_SIZE = 40
UNCHOSEN = (230, 225, 210)    # a good left out, as the empty slots look


class GoodsPicker:
    """A goods grid over a window: pick one good, or toggle several."""

    def __init__(self, window: 'InventoryWindow', title: str, goods: List[str],
                 anchor: pygame.Rect, *, chosen: Optional[Set[str]] = None,
                 current: Optional[str] = None,
                 on_pick: Optional[Callable[[Optional[str]], None]] = None,
                 on_change: Optional[Callable[[Optional[Set[str]]], None]] = None) -> None:
        """
        Args:
            window: The window it opens over, for its fonts, icons and frame.
            title: What is being picked.
            goods: The goods to offer, in order.
            anchor: What it opened from, in screen space; it is placed beside it.
            chosen: Several goods: those chosen now (toggling mode).
            current: One good: the one picked now, if any (single mode).
            on_pick: Single mode: called with the good picked, None for any.
            on_change: Toggling mode: called after every change with the goods
                chosen, None when that is all of them.
        """
        self.window = window
        self.title = title
        self.goods = goods
        self.multi = chosen is not None
        self.chosen: Set[str] = set(chosen) if chosen is not None else set()
        self.current = current
        self.on_pick = on_pick
        self.on_change = on_change
        self.closed = False

        rows = -(-len(goods) // COLS)
        width = COLS * CELL + (COLS - 1) * CELL_GAP + 2 * PAD
        height = PAD + TITLE_H + rows * CELL + (rows - 1) * CELL_GAP + PAD + BUTTON_H + PAD
        screen_rect = window.screen.get_rect()
        self.rect = pygame.Rect(0, 0, width, height)
        self.rect.midtop = (anchor.centerx, anchor.bottom + 6)
        if self.rect.bottom > screen_rect.bottom - 10:
            self.rect.bottom = anchor.top - 6
        self.rect.clamp_ip(screen_rect.inflate(-20, -20))

        self.cells: List[Tuple[pygame.Rect, str]] = []
        for i, good in enumerate(goods):
            row, col = divmod(i, COLS)
            self.cells.append((pygame.Rect(
                self.rect.x + PAD + col * (CELL + CELL_GAP),
                self.rect.y + PAD + TITLE_H + row * (CELL + CELL_GAP),
                CELL, CELL), good))

        labels = ["All", "None", "Done"] if self.multi else ["Any good", "Cancel"]
        button_w = (width - 2 * PAD - (len(labels) - 1) * CELL_GAP) // len(labels)
        self.buttons: List[Tuple[pygame.Rect, str]] = [
            (pygame.Rect(self.rect.x + PAD + i * (button_w + CELL_GAP),
                         self.rect.bottom - PAD - BUTTON_H, button_w, BUTTON_H), label)
            for i, label in enumerate(labels)
        ]

        self._surface: Optional[pygame.Surface] = None
        self._shade = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
        self._shade.fill((0, 0, 0, 30))

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def handle_click(self, pos: Tuple[int, int]) -> None:
        if not self.rect.collidepoint(pos):
            self.closed = True
            return
        for rect, good in self.cells:
            if rect.collidepoint(pos):
                if self.multi:
                    self.chosen ^= {good}
                    self._changed()
                else:
                    self.on_pick(good)
                    self.closed = True
                return
        for rect, label in self.buttons:
            if not rect.collidepoint(pos):
                continue
            if label == "All":
                self.chosen = set(self.goods)
                self._changed()
            elif label == "None":
                self.chosen = set()
                self._changed()
            elif label == "Any good":
                self.on_pick(None)
                self.closed = True
            else:  # Done, Cancel
                self.closed = True
            return

    def _changed(self) -> None:
        self._surface = None
        self.on_change(None if self.chosen >= set(self.goods) else set(self.chosen))

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self, screen: pygame.Surface, mouse_pos: Tuple[int, int]) -> None:
        if self._surface is None:
            self._surface = self._render()
        screen.blit(self._surface, self.rect.topleft)
        for rect, _ in self.cells:
            if rect.collidepoint(mouse_pos):
                screen.blit(self._shade, rect.topleft)
        for rect, _ in self.buttons:
            if rect.collidepoint(mouse_pos):
                shade = pygame.Surface(rect.size, pygame.SRCALPHA)
                shade.fill((0, 0, 0, 30))
                screen.blit(shade, rect.topleft)

    def _render(self) -> pygame.Surface:
        window = self.window
        surf = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        local = pygame.Rect(0, 0, *self.rect.size)
        game = window.game_state.game
        if hasattr(game, 'pic_info_window'):
            draw_9slice(surf, game.pic_info_window, local)
        else:
            surf.fill((*SANDY_BROWN, 255))
            pygame.draw.rect(surf, DARK_BROWN, local, 3)

        title = window.body_font.render(self.title, True, DARK_BROWN)
        surf.blit(title, title.get_rect(centerx=local.centerx, top=PAD + 2))

        for rect, good in self.cells:
            cell = rect.move(-self.rect.x, -self.rect.y)
            on = good in self.chosen if self.multi else good == self.current
            pygame.draw.rect(surf, BEIGE if on or not self.multi else UNCHOSEN, cell)
            pygame.draw.rect(surf, DARK_BROWN if on else LIGHT_GRAY, cell, 2 if on else 1)
            icon = window._icon(good, ICON_SIZE)
            if icon:
                if self.multi and not on:
                    icon = icon.copy()
                    icon.set_alpha(90)
                surf.blit(icon, icon.get_rect(center=(cell.centerx, cell.top + 6 + ICON_SIZE // 2)))
            name = window.small_font.render(good, True, DARK_BROWN if on or not self.multi else DARK_GRAY)
            surf.blit(name, name.get_rect(centerx=cell.centerx, bottom=cell.bottom - 4))
            if self.multi and on:
                # A tick in the corner of every good taken
                tick = pygame.Rect(cell.right - 18, cell.top + 4, 14, 14)
                pygame.draw.rect(surf, MUTED_GREEN, tick, border_radius=3)
                pygame.draw.lines(surf, WHITE, False, [
                    (tick.x + 3, tick.centery), (tick.x + 6, tick.bottom - 4), (tick.right - 3, tick.y + 3)], 2)

        for rect, label in self.buttons:
            button = rect.move(-self.rect.x, -self.rect.y)
            pygame.draw.rect(surf, SANDY_BROWN, button)
            pygame.draw.rect(surf, DARK_BROWN, button, 2)
            text = window.body_font.render(label, True, DARK_BROWN)
            surf.blit(text, text.get_rect(center=button.center))

        return surf.convert_alpha()
