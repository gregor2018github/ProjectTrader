"""Inventory overview of an owned warehouse.

Opened from the house menu of a warehouse the player owns: a grid of slots,
one per good stored there, with how full the building is and what its
contents are worth at today's prices.

Everything but the hover effects is drawn once into a cached panel, which is
only redrawn when what it shows changes, so the open window costs about as
much per frame as two blits.
"""

import os
import pygame
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from ...config.colors import (
    BEIGE, DARK_BROWN, DARK_GRAY, LIGHT_GRAY, WHEAT, WHITE,
    MUTED_GREEN, MUTED_ORANGE, MUTED_RED, SANDY_BROWN,
)
from ...config.constants import FONTS_PATH, SCREEN_HEIGHT, SCREEN_WIDTH, SIDEBAR_WIDTH
from ..ui_utils import draw_9slice, draw_mouse_tooltip

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.institutions.warehouse import Warehouse


COLS = 5
MIN_ROWS = 3                 # a fresh warehouse still shows its empty shelves
SLOT_SIZE = 104
SLOT_GAP = 12
ICON_SIZE = 56
SIDE_PAD = 36
BAR_HEIGHT = 18
EMPTY_SLOT = (230, 225, 210)  # the faded placeholder of the license overview
NEARLY_FULL = 0.75           # fill share from which the capacity bar turns orange
DIM_ALPHA = 120              # how dark the game behind the window gets

# Good pictures at slot size, scaled once per session from the game's
# cut-out goods_icon images (or the 30px icons where a good has none)
_icons: Dict[str, Optional[pygame.Surface]] = {}


def open_warehouse_inventory(game_state: 'GameState', warehouse: 'Warehouse') -> None:
    game_state.info_window = WarehouseInventory(game_state.screen, game_state, warehouse)
    game_state.active_house_menu = warehouse  # walking away closes it, as with the house menu


class WarehouseInventory:
    """A centred overlay listing the goods stored in one warehouse."""

    def __init__(self, screen: pygame.Surface, game_state: 'GameState',
                 warehouse: 'Warehouse') -> None:
        self.screen = screen
        self.game_state = game_state
        self.house = warehouse  # map_view closes the window once the player walks off

        try:
            self.title_font = pygame.font.Font(os.path.join(FONTS_PATH, "Medici Text.ttf"), 36)
            self.heading_font = pygame.font.Font(os.path.join(FONTS_PATH, "Augusta.ttf"), 24)
            self.body_font = pygame.font.Font(os.path.join(FONTS_PATH, "Augusta.ttf"), 18)
            self.small_font = pygame.font.Font(os.path.join(FONTS_PATH, "Augusta.ttf"), 16)
        except Exception:
            self.title_font = pygame.font.SysFont("arial", 30)
            self.heading_font = pygame.font.SysFont("arial", 20)
            self.body_font = pygame.font.SysFont("arial", 15)
            self.small_font = pygame.font.SysFont("arial", 13)

        game = game_state.game
        self.goods_by_name = {good.name: good for good in game.goods}
        slot_count = len(game.depot.good_stock)
        self.rows = max(MIN_ROWS, -(-slot_count // COLS))
        grid_w = COLS * SLOT_SIZE + (COLS - 1) * SLOT_GAP
        grid_h = self.rows * SLOT_SIZE + (self.rows - 1) * SLOT_GAP

        # Vertical layout, in panel coordinates
        self.subtitle_y = 62
        self.rule_y = 96
        self.capacity_y = 110
        self.bar_y = 140
        self.grid_y = 178
        self.footer_rule_y = self.grid_y + grid_h + 18
        self.footer_y = self.footer_rule_y + 12
        self.hint_y = self.footer_y + 32
        panel_w = grid_w + 2 * SIDE_PAD
        panel_h = self.hint_y + 44

        total_w = SCREEN_WIDTH + SIDEBAR_WIDTH
        self.panel_rect = pygame.Rect(
            (total_w - panel_w) // 2, (SCREEN_HEIGHT - panel_h) // 2, panel_w, panel_h
        )
        cb_size = 28
        self.close_rect = pygame.Rect(
            self.panel_rect.right - cb_size - 8, self.panel_rect.top + 8, cb_size, cb_size
        )

        # Slot rects in screen space, filled row by row
        self.slot_rects: List[pygame.Rect] = []
        for i in range(self.rows * COLS):
            row, col = divmod(i, COLS)
            self.slot_rects.append(pygame.Rect(
                self.panel_rect.x + SIDE_PAD + col * (SLOT_SIZE + SLOT_GAP),
                self.panel_rect.y + self.grid_y + row * (SLOT_SIZE + SLOT_GAP),
                SLOT_SIZE, SLOT_SIZE,
            ))

        # Made once: the dimming over the game, and the hover shade of a slot
        self._dim = pygame.Surface((total_w, SCREEN_HEIGHT)).convert()
        self._dim.fill((0, 0, 0))
        self._slot_shade = pygame.Surface((SLOT_SIZE, SLOT_SIZE), pygame.SRCALPHA)
        self._slot_shade.fill((0, 0, 0, 30))

        self._panel: Optional[pygame.Surface] = None
        self._panel_key: Optional[tuple] = None
        self._stock: List[Tuple[str, int]] = []
        self._tooltip: Optional[Tuple[int, str]] = None  # (slot index, text) of the last hover

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _read_stock(self) -> List[Tuple[str, int]]:
        """The goods stored here, most plentiful first."""
        stock = self.game_state.game.depot.warehouse_stock(self.house.tmx_id)
        return sorted(((g, q) for g, q in stock.items() if q > 0), key=lambda item: (-item[1], item[0]))

    def _price(self, good_name: str) -> float:
        good = self.goods_by_name.get(good_name)
        return good.get_price() if good else 0.0

    def _icon(self, good_name: str) -> Optional[pygame.Surface]:
        if good_name not in _icons:
            images = self.game_state.game.images
            large = images.get('goods_icon', {}).get(good_name)
            if large is not None:
                scale = ICON_SIZE / max(large.get_size())
                size = (max(1, round(large.get_width() * scale)), max(1, round(large.get_height() * scale)))
                _icons[good_name] = pygame.transform.smoothscale(large, size).convert_alpha()
            else:
                small = images['goods_30'].get(good_name)
                _icons[good_name] = (
                    pygame.transform.smoothscale(small, (ICON_SIZE, ICON_SIZE)) if small else None
                )
        return _icons[good_name]

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._close()

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.close_rect.collidepoint(pos) or not self.panel_rect.collidepoint(pos):
            self._close()
        return True

    def _close(self) -> None:
        gs = self.game_state
        gs.menu_fade_window = self
        gs.menu_fade_timer = gs.menu_fade_duration
        gs.info_window = None
        gs.active_house_menu = None

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return

        # Redraw the panel only when something on it changed
        stock = self._read_stock()
        value = round(sum(self._price(g) * q for g, q in stock))
        starting_capacity = self.game_state.game.depot.starting_storage_capacity()
        key = (tuple(stock), value, self.house.buy_storage, starting_capacity)
        if key != self._panel_key:
            self._stock = stock
            self._panel = self._render_panel(stock, value, starting_capacity)
            self._panel_key = key
            self._tooltip = None

        self._dim.set_alpha(int(DIM_ALPHA * alpha_scale))
        self.screen.blit(self._dim, (0, 0))
        self._panel.set_alpha(None if alpha_scale >= 1.0 else int(255 * alpha_scale))
        self.screen.blit(self._panel, self.panel_rect.topleft)
        if alpha_scale < 1.0:
            return  # fading out: no hover effects

        mouse_pos = pygame.mouse.get_pos()
        if self.close_rect.collidepoint(mouse_pos):
            self._draw_close_button(self.screen, self.close_rect, hovered=True)
            return

        for i, (good_name, qty) in enumerate(self._stock):
            rect = self.slot_rects[i]
            if rect.collidepoint(mouse_pos):
                self.screen.blit(self._slot_shade, rect.topleft)
                if self._tooltip is None or self._tooltip[0] != i:
                    capacity = self.house.buy_storage
                    share = qty / capacity * 100 if capacity else 0
                    text = (f"{qty} {good_name}  ·  worth {self._price(good_name) * qty:,.0f}g"
                            f"  ·  {share:.0f}% of the space")
                    self._tooltip = (i, text)
                draw_mouse_tooltip(self.screen, self.body_font, self._tooltip[1], mouse_pos)
                break

    def _render_panel(self, stock: List[Tuple[str, int]], value: float,
                      starting_capacity: int) -> pygame.Surface:
        """Everything on the window that does not follow the mouse."""
        w, h = self.panel_rect.size
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        game = self.game_state.game
        if hasattr(game, 'pic_info_window'):
            draw_9slice(surf, game.pic_info_window, pygame.Rect(0, 0, w, h))
        else:
            surf.fill((*SANDY_BROWN, 255))
            pygame.draw.rect(surf, DARK_BROWN, pygame.Rect(0, 0, w, h), 4)

        stored = sum(q for _, q in stock)
        capacity = self.house.buy_storage

        # Title and subtitle
        name = self.house.display_name or (self.house.name or "Warehouse").split('_')[0]
        title = self.title_font.render(name, True, DARK_BROWN)
        surf.blit(title, title.get_rect(centerx=w // 2, top=16))
        subtitle = self.heading_font.render("Warehouse Inventory", True, DARK_GRAY)
        surf.blit(subtitle, subtitle.get_rect(centerx=w // 2, top=self.subtitle_y))
        pygame.draw.line(surf, DARK_BROWN, (30, self.rule_y), (w - 30, self.rule_y), 2)

        self._draw_close_button(surf, self.close_rect.move(-self.panel_rect.x, -self.panel_rect.y), hovered=False)
        self._draw_capacity(surf, stored, capacity)

        # Slots
        for i, rect in enumerate(self.slot_rects):
            local = rect.move(-self.panel_rect.x, -self.panel_rect.y)
            if i < len(stock):
                self._draw_slot(surf, local, *stock[i])
            else:
                pygame.draw.rect(surf, EMPTY_SLOT, local)
                pygame.draw.rect(surf, LIGHT_GRAY, local, 1)

        if not stock:
            grid_rect = self.slot_rects[0].union(self.slot_rects[-1]).move(-self.panel_rect.x, -self.panel_rect.y)
            empty = self.heading_font.render("These shelves stand empty", True, DARK_GRAY)
            surf.blit(empty, empty.get_rect(center=grid_rect.center))

        # Footer: what it is all worth, and how the storage fills
        pygame.draw.line(surf, DARK_BROWN, (30, self.footer_rule_y), (w - 30, self.footer_rule_y), 1)
        value_surf = self.body_font.render(f"Value at market prices:  {value:,.0f}g", True, DARK_BROWN)
        surf.blit(value_surf, (SIDE_PAD, self.footer_y))
        free_surf = self.body_font.render(f"Free space:  {max(0, capacity - stored)}", True, DARK_BROWN)
        surf.blit(free_surf, free_surf.get_rect(right=w - SIDE_PAD, top=self.footer_y))
        hint = (f"Purchases fill your starting storage ({starting_capacity}) first, "
                "then your warehouses in the order bought.")
        hint_surf = self.small_font.render(hint, True, DARK_GRAY)
        surf.blit(hint_surf, hint_surf.get_rect(centerx=w // 2, top=self.hint_y))

        return surf.convert_alpha()

    @staticmethod
    def _draw_close_button(surf: pygame.Surface, rect: pygame.Rect, hovered: bool) -> None:
        pygame.draw.rect(surf, (180, 60, 60) if hovered else DARK_BROWN, rect)
        m = 5
        pygame.draw.line(surf, WHITE, (rect.left + m, rect.top + m), (rect.right - m, rect.bottom - m), 2)
        pygame.draw.line(surf, WHITE, (rect.left + m, rect.bottom - m), (rect.right - m, rect.top + m), 2)

    def _draw_capacity(self, surf: pygame.Surface, stored: int, capacity: int) -> None:
        """The 'Stored' line and a bar showing how full the building is."""
        w = self.panel_rect.width
        label = self.body_font.render("Stored", True, DARK_BROWN)
        surf.blit(label, (SIDE_PAD, self.capacity_y))
        amount = self.body_font.render(f"{stored} / {capacity} units", True, DARK_BROWN)
        surf.blit(amount, amount.get_rect(right=w - SIDE_PAD, top=self.capacity_y))

        bar = pygame.Rect(SIDE_PAD, self.bar_y, w - 2 * SIDE_PAD, BAR_HEIGHT)
        pygame.draw.rect(surf, WHEAT, bar)
        share = min(1.0, stored / capacity) if capacity else 0.0
        if share > 0:
            color = MUTED_RED if share >= 1.0 else MUTED_ORANGE if share >= NEARLY_FULL else MUTED_GREEN
            pygame.draw.rect(surf, color, pygame.Rect(bar.x, bar.y, max(2, round(bar.width * share)), bar.height))
        pygame.draw.rect(surf, DARK_BROWN, bar, 2)

    def _draw_slot(self, surf: pygame.Surface, rect: pygame.Rect, good_name: str, qty: int) -> None:
        pygame.draw.rect(surf, BEIGE, rect)
        pygame.draw.rect(surf, DARK_BROWN, rect, 2)

        icon = self._icon(good_name)
        if icon:
            surf.blit(icon, icon.get_rect(center=(rect.centerx, rect.top + 8 + ICON_SIZE // 2)))
        name = self.small_font.render(good_name, True, DARK_BROWN)
        surf.blit(name, name.get_rect(centerx=rect.centerx, bottom=rect.bottom - 6))

        # Quantity badge in the top-right corner, like a stack count
        count = self.small_font.render(str(qty), True, WHITE)
        badge = count.get_rect().inflate(10, 2)
        badge.topright = (rect.right - 4, rect.top + 4)
        pygame.draw.rect(surf, DARK_BROWN, badge, border_radius=4)
        surf.blit(count, count.get_rect(center=badge.center))
