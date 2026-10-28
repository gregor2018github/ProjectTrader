"""Inventory overview of an owned warehouse.

Opened from the house menu of a warehouse the player owns: the building's
storage slots, each holding up to its size of one good, with a fill bar
beside every slot (green once it is full), how many slots are in use, and
how much room part-filled slots waste.

Everything but the hover effects is drawn once into a cached panel, which is
only redrawn when what it shows changes, so the open window costs about as
much per frame as two blits.
"""

import os
import pygame
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from ...config.colors import (
    BEIGE, DARK_BROWN, DARK_GRAY, DARK_RED, LIGHT_GRAY, WHEAT, WHITE,
    MUTED_GREEN, MUTED_ORANGE, MUTED_RED, SANDY_BROWN,
)
from ...config.constants import FONTS_PATH, SCREEN_HEIGHT, SCREEN_WIDTH, SIDEBAR_WIDTH
from ..ui_utils import draw_9slice, draw_mouse_tooltip

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.institutions.warehouse import Warehouse


COLS = 5
BOX_W = 104                  # a slot's box, with the good's picture, name and amount
BOX_H = 116
BAR_W = 12                   # the slot's fill bar, right of its box
BAR_GAP = 6
CELL_W = BOX_W + BAR_GAP + BAR_W
COL_GAP = 16
ROW_GAP = 16
TOTAL_BAR_H = 18             # the whole building's fill bar, over the slots
NEARLY_FULL = 0.75           # fill share from which the building's bar turns orange
ICON_SIZE = 56
SIDE_PAD = 36
EMPTY_SLOT = (230, 225, 210)  # the faded placeholder of the license overview
DIM_ALPHA = 120              # how dark the game behind the window gets

# Good pictures at slot size, scaled once per session from the game's
# cut-out goods_icon images (or the 30px icons where a good has none)
_icons: Dict[str, Optional[pygame.Surface]] = {}


def open_warehouse_inventory(game_state: 'GameState', warehouse: 'Warehouse') -> None:
    game_state.info_window = WarehouseInventory(game_state.screen, game_state, warehouse)
    game_state.active_house_menu = warehouse  # walking away closes it, as with the house menu


class WarehouseInventory:
    """A centred overlay showing the storage slots of one warehouse."""

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
        entry = game.depot.warehouse_entry(warehouse.tmx_id) or {}
        self.slot_size: int = entry.get("slot_size", warehouse.buy_slot_size)
        slot_count = len(entry.get("slots", [])) or warehouse.buy_slots

        rows = max(1, -(-slot_count // COLS))
        grid_w = COLS * CELL_W + (COLS - 1) * COL_GAP
        grid_h = rows * BOX_H + (rows - 1) * ROW_GAP

        # Vertical layout, in panel coordinates
        self.subtitle_y = 62
        self.rule_y = 96
        self.summary_y = 110
        self.total_bar_y = 140
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

        # Slot boxes and their fill bars in screen space, row by row; a short
        # last row (or a warehouse of fewer than COLS slots) is centred
        self.slot_rects: List[Tuple[pygame.Rect, pygame.Rect]] = []
        for i in range(slot_count):
            row, col = divmod(i, COLS)
            in_row = min(COLS, slot_count - row * COLS)
            row_w = in_row * CELL_W + (in_row - 1) * COL_GAP
            x = self.panel_rect.x + (panel_w - row_w) // 2 + col * (CELL_W + COL_GAP)
            y = self.panel_rect.y + self.grid_y + row * (BOX_H + ROW_GAP)
            box = pygame.Rect(x, y, BOX_W, BOX_H)
            bar = pygame.Rect(box.right + BAR_GAP, y, BAR_W, BOX_H)
            self.slot_rects.append((box, bar))

        # The whole building's fill bar spans the first row of slots, bars included
        first_row = self.slot_rects[:COLS]
        if first_row:
            left, right = first_row[0][0].left, first_row[-1][1].right
        else:
            left, right = self.panel_rect.x + SIDE_PAD, self.panel_rect.right - SIDE_PAD
        self.total_bar_rect = pygame.Rect(
            left - self.panel_rect.x, self.total_bar_y, right - left, TOTAL_BAR_H)

        # Made once: the dimming over the game, and the hover shade of a slot
        self._dim = pygame.Surface((total_w, SCREEN_HEIGHT)).convert()
        self._dim.fill((0, 0, 0))
        self._slot_shade = pygame.Surface((BOX_W, BOX_H), pygame.SRCALPHA)
        self._slot_shade.fill((0, 0, 0, 30))

        self._panel: Optional[pygame.Surface] = None
        self._panel_key: Optional[tuple] = None
        self._slots: List[Dict[str, Any]] = []
        self._tooltip: Optional[Tuple[int, str]] = None  # (slot index, text) of the last hover

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

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
        slots = self.game_state.game.depot.warehouse_slots(self.house.tmx_id)
        value = round(sum(self._price(s["good"]) * s["qty"] for s in slots if s["good"]))
        key = (tuple((s["good"], s["qty"]) for s in slots), value)
        if key != self._panel_key:
            self._slots = slots
            self._panel = self._render_panel(slots, value)
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

        for i, (box, bar) in enumerate(self.slot_rects[:len(self._slots)]):
            if box.collidepoint(mouse_pos) or bar.collidepoint(mouse_pos):
                self.screen.blit(self._slot_shade, box.topleft)
                if self._tooltip is None or self._tooltip[0] != i:
                    self._tooltip = (i, self._slot_tooltip(self._slots[i]))
                draw_mouse_tooltip(self.screen, self.body_font, self._tooltip[1], mouse_pos)
                break

    def _slot_tooltip(self, slot: Dict[str, Any]) -> str:
        good_name, qty = slot["good"], slot["qty"]
        if good_name is None:
            return f"Empty slot  ·  holds up to {self.slot_size} of one good"
        room = self.slot_size - qty
        fill = "full" if room <= 0 else f"room for {room} more"
        return f"{qty} of {self.slot_size} {good_name}  ·  worth {self._price(good_name) * qty:,.0f}g  ·  {fill}"

    def _render_panel(self, slots: List[Dict[str, Any]], value: float) -> pygame.Surface:
        """Everything on the window that does not follow the mouse."""
        w, h = self.panel_rect.size
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        game = self.game_state.game
        if hasattr(game, 'pic_info_window'):
            draw_9slice(surf, game.pic_info_window, pygame.Rect(0, 0, w, h))
        else:
            surf.fill((*SANDY_BROWN, 255))
            pygame.draw.rect(surf, DARK_BROWN, pygame.Rect(0, 0, w, h), 4)

        used = [s for s in slots if s["good"] is not None]
        stored = sum(s["qty"] for s in used)
        lost = sum(max(0, self.slot_size - s["qty"]) for s in used)

        # Title and subtitle
        name = self.house.display_name or (self.house.name or "Warehouse").split('_')[0]
        title = self.title_font.render(name, True, DARK_BROWN)
        surf.blit(title, title.get_rect(centerx=w // 2, top=16))
        subtitle = self.heading_font.render("Warehouse Inventory", True, DARK_GRAY)
        surf.blit(subtitle, subtitle.get_rect(centerx=w // 2, top=self.subtitle_y))
        pygame.draw.line(surf, DARK_BROWN, (30, self.rule_y), (w - 30, self.rule_y), 2)
        self._draw_close_button(surf, self.close_rect.move(-self.panel_rect.x, -self.panel_rect.y), hovered=False)

        # How full the building is: in slots, and in units
        slots_surf = self.body_font.render(f"Slots in use:  {len(used)} / {len(slots)}", True, DARK_BROWN)
        surf.blit(slots_surf, (SIDE_PAD, self.summary_y))
        stored_surf = self.body_font.render(
            f"Stored:  {stored} / {len(slots) * self.slot_size} units", True, DARK_BROWN)
        surf.blit(stored_surf, stored_surf.get_rect(right=w - SIDE_PAD, top=self.summary_y))

        bar = self.total_bar_rect
        pygame.draw.rect(surf, WHEAT, bar)
        capacity = len(slots) * self.slot_size
        share = min(1.0, stored / capacity) if capacity else 0.0
        if share > 0:
            color = MUTED_RED if share >= 1.0 else MUTED_ORANGE if share >= NEARLY_FULL else MUTED_GREEN
            pygame.draw.rect(surf, color, pygame.Rect(bar.x, bar.y, max(2, round(bar.width * share)), bar.height))
        pygame.draw.rect(surf, DARK_BROWN, bar, 2)

        # Slots
        for (box, bar), slot in zip(self.slot_rects, slots):
            self._draw_slot(surf, box.move(-self.panel_rect.x, -self.panel_rect.y),
                            bar.move(-self.panel_rect.x, -self.panel_rect.y), slot)

        # Footer: what it is all worth, the room part-filled slots waste, and why
        pygame.draw.line(surf, DARK_BROWN, (30, self.footer_rule_y), (w - 30, self.footer_rule_y), 1)
        value_surf = self.body_font.render(f"Value at market prices:  {value:,.0f}g", True, DARK_BROWN)
        surf.blit(value_surf, (SIDE_PAD, self.footer_y))
        lost_surf = self.body_font.render(
            f"Room lost in part-filled slots:  {lost}", True, DARK_RED if lost else DARK_BROWN)
        surf.blit(lost_surf, lost_surf.get_rect(right=w - SIDE_PAD, top=self.footer_y))
        hint = (f"Each slot holds up to {self.slot_size} of one good; "
                "the room left in a slot holds nothing else.")
        hint_surf = self.small_font.render(hint, True, DARK_GRAY)
        surf.blit(hint_surf, hint_surf.get_rect(centerx=w // 2, top=self.hint_y))

        return surf.convert_alpha()

    @staticmethod
    def _draw_close_button(surf: pygame.Surface, rect: pygame.Rect, hovered: bool) -> None:
        pygame.draw.rect(surf, (180, 60, 60) if hovered else DARK_BROWN, rect)
        m = 5
        pygame.draw.line(surf, WHITE, (rect.left + m, rect.top + m), (rect.right - m, rect.bottom - m), 2)
        pygame.draw.line(surf, WHITE, (rect.left + m, rect.bottom - m), (rect.right - m, rect.top + m), 2)

    def _draw_slot(self, surf: pygame.Surface, box: pygame.Rect, bar: pygame.Rect,
                   slot: Dict[str, Any]) -> None:
        good_name, qty = slot["good"], slot["qty"]

        # Fill bar, filling from the bottom: green once the slot is full
        pygame.draw.rect(surf, WHEAT, bar)
        if good_name is not None and qty > 0:
            share = min(1.0, qty / self.slot_size) if self.slot_size else 1.0
            fill_h = max(2, round(bar.height * share))
            color = MUTED_GREEN if share >= 1.0 else MUTED_ORANGE
            pygame.draw.rect(surf, color, pygame.Rect(bar.x, bar.bottom - fill_h, bar.width, fill_h))
        pygame.draw.rect(surf, DARK_BROWN if good_name else LIGHT_GRAY, bar, 2 if good_name else 1)

        if good_name is None:
            pygame.draw.rect(surf, EMPTY_SLOT, box)
            pygame.draw.rect(surf, LIGHT_GRAY, box, 1)
            empty = self.small_font.render("Empty", True, LIGHT_GRAY)
            surf.blit(empty, empty.get_rect(center=box.center))
            return

        pygame.draw.rect(surf, BEIGE, box)
        pygame.draw.rect(surf, DARK_BROWN, box, 2)
        icon = self._icon(good_name)
        if icon:
            surf.blit(icon, icon.get_rect(center=(box.centerx, box.top + 8 + ICON_SIZE // 2)))
        name = self.small_font.render(good_name, True, DARK_BROWN)
        surf.blit(name, name.get_rect(centerx=box.centerx, bottom=box.bottom - 24))
        amount = self.small_font.render(f"{qty} / {self.slot_size}", True, DARK_GRAY)
        surf.blit(amount, amount.get_rect(centerx=box.centerx, bottom=box.bottom - 6))
