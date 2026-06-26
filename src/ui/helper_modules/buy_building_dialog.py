"""Purchase confirmation dialog for buyable buildings (Warehouse etc.)."""

import pygame
from typing import TYPE_CHECKING, Tuple
from .loan_dialog import _BaseDialog, _close_dialog
from ...config.colors import BLACK, DARK_BROWN, DARK_GREEN, DARK_RED, SANDY_BROWN

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.institutions.warehouse import Warehouse


def open_buy_building_dialog(game_state: 'GameState', warehouse: 'Warehouse') -> None:
    game_state.info_window = BuyBuildingDialog(game_state.screen, game_state, warehouse)


class BuyBuildingDialog(_BaseDialog):
    W, H = 400, 248

    def __init__(self, screen: pygame.Surface, game_state: 'GameState',
                 warehouse: 'Warehouse') -> None:
        super().__init__(screen, game_state, self.W, self.H)
        self.warehouse = warehouse
        self.house = game_state.active_house_menu  # enables distance-based close in map_view

        btn_y = self.panel.bottom - self.BTN_H - self.PAD
        half_w = (self.W - 3 * self.PAD) // 2
        self.buy_btn = pygame.Rect(self.panel.left + self.PAD, btn_y, half_w, self.BTN_H)
        self.cancel_btn = pygame.Rect(
            self.panel.left + 2 * self.PAD + half_w, btn_y, half_w, self.BTN_H
        )

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.close_rect.collidepoint(pos) or not self.panel.collidepoint(pos):
            _close_dialog(self.game_state)
            return True
        if self.cancel_btn.collidepoint(pos):
            _close_dialog(self.game_state)
            return True
        if self.buy_btn.collidepoint(pos):
            depot = self.game_state.game.depot
            if depot.money >= self.warehouse.buy_price:
                depot.buy_warehouse(self.warehouse, self.game_state)
                _close_dialog(self.game_state)
            else:
                self.game_state.show_warning("Not enough money to purchase this building.")
        return True

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return

        use_temp = alpha_scale < 1.0
        if use_temp:
            surf = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            off = (-self.panel.left, -self.panel.top)
        else:
            surf = self.screen
            off = (0, 0)

        self._draw_panel(surf, off)
        self._draw_close_btn(surf, off)
        self._draw_title(surf, off, "Purchase Building")

        depot = self.game_state.game.depot
        can_afford = depot.money >= self.warehouse.buy_price

        p = self.panel.move(*off)
        cx = p.centerx
        y = p.top + self.HDR + self.PAD

        lines = [
            (self.warehouse.name, DARK_BROWN),
            (f"Price:  {self.warehouse.buy_price:,} gold", DARK_RED if not can_afford else BLACK),
            (f"Storage gained:  +{self.warehouse.buy_storage}", DARK_GREEN),
            (f"Your money:  {depot.money:,.0f} gold", BLACK),
        ]
        for text, color in lines:
            y = self._text(surf, text, cx, y, color=color, center=True) + 4

        mouse = pygame.mouse.get_pos()
        buy_r = self.buy_btn.move(*off)
        cancel_r = self.cancel_btn.move(*off)

        buy_label = "Buy" if can_afford else "Can't Afford"
        buy_border = DARK_GREEN if can_afford else DARK_RED
        self._draw_btn(surf, buy_r, buy_label, mouse, border=buy_border)
        self._draw_btn(surf, cancel_r, "Cancel", mouse)

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, self.panel.topleft)
