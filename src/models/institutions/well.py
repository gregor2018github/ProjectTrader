import datetime
import os
import random
import pygame
from typing import List, Optional, Tuple, TYPE_CHECKING

from ..house import House
from ...config.constants import (
    SPLASH_VOLUME, COIN_THROW_COST,
    WELL_WISH_PROBABILITY, FONTS_PATH,
)
from ...config.colors import SANDY_BROWN, DARK_BROWN, BLACK, WHITE, PALE_BROWN

if TYPE_CHECKING:
    from ...game_state import GameState

_COOLDOWN_MIN_DAYS = 1
_COOLDOWN_MAX_DAYS = 7


class Well(House):
    """Represents a well on the map where the player can throw coins or rocks."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._wish_cooldown_until: Optional[datetime.datetime] = None

    def throw_coin(self, game_state: 'GameState') -> None:
        """Deduct a coin from the player's money and play a splash sound.

        If the well is not on cooldown and the random wish check passes, opens
        the WishMenu afterward.  Shows a warning if the player cannot afford it.
        """
        depot = game_state.game.depot if game_state.game else None
        if depot is None:
            return

        if not depot.book_miscellaneous(COIN_THROW_COST):
            game_state.show_warning("Not enough money!")
            return

        self._play_splash(game_state)

        on_cooldown = (
            self._wish_cooldown_until is not None
            and game_state.date < self._wish_cooldown_until
        )
        if not on_cooldown and random.random() < WELL_WISH_PROBABILITY:
            self._open_wish_menu(game_state)
        else:
            game_state.info_window = None
            game_state.active_house_menu = None

    def throw_rock(self, game_state: 'GameState') -> None:
        """Play a splash sound without any cost."""
        self._play_splash(game_state)
        game_state.info_window = None
        game_state.active_house_menu = None

    def _play_splash(self, game_state: 'GameState') -> None:
        """Play a random splash sound."""
        if not game_state.game:
            return
        splash_num = random.randint(1, 4)
        channel = game_state.game.play_sound(f"splash_{splash_num}")
        if channel:
            channel.set_volume(SPLASH_VOLUME)

    def _open_wish_menu(self, game_state: 'GameState') -> None:
        """Replace the current info_window with the WishMenu."""
        if not game_state.game:
            return
        goods_names = [g.name for g in game_state.game.goods]
        click_pos = pygame.mouse.get_pos()

        def wish_callback(good_name: str, direction: str) -> None:
            if game_state.game:
                for good in game_state.game.goods:
                    if good.name == good_name:
                        good.apply_well_shock(direction)
                        break
                game_state.game.play_sound("wish_granted")
            cooldown_days = random.randint(_COOLDOWN_MIN_DAYS, _COOLDOWN_MAX_DAYS)
            self._wish_cooldown_until = game_state.date + datetime.timedelta(days=cooldown_days)
            game_state.info_window = None
            game_state.active_house_menu = None

        game_state.info_window = WishMenu(
            game_state.screen,
            goods_names,
            game_state,
            click_pos,
            wish_callback,
        )


class WishMenu:
    """Pop-up menu for making a well wish — choosing a good and price direction.

    Styled identically to HouseMenu.  Two inline dropdowns let the player pick
    a good and whether its price should go up or down.
    """

    _ITEM_H = 25          # Height of each dropdown list row
    _DIRECTION_OPTIONS = ["Price goes up", "Price goes down"]

    def __init__(
        self,
        screen: pygame.Surface,
        goods_names: List[str],
        game_state: 'GameState',
        click_pos: Tuple[int, int],
        callback,
    ) -> None:
        self.screen = screen
        self.goods_names = goods_names
        self.game_state = game_state
        self.callback = callback

        self.selected_good = goods_names[0] if goods_names else ""
        self.selected_direction = "Price goes up"
        self.good_dropdown_open = False
        self.dir_dropdown_open = False

        try:
            self.title_font = pygame.font.Font(
                os.path.join(FONTS_PATH, "Medici Text.ttf"), 26
            )
        except Exception:
            self.title_font = game_state.font

        # ── Layout constants ──────────────────────────────────────────────
        self.width = 240
        self.header_height = 44
        self.padding = 10
        self._label_h = 18
        self._btn_h = 34
        self._gap = 12
        self._action_h = 40
        self._close_size = 20

        body_h = (
            self.padding
            + self._label_h + 4 + self._btn_h + self._gap   # good row
            + self._label_h + 4 + self._btn_h + self._gap   # direction row
            + self._action_h
            + self.padding
        )
        self.total_height = self.header_height + body_h

        screen_w, screen_h = screen.get_size()
        self.x = max(0, min(click_pos[0], screen_w - self.width))
        self.y = max(0, min(click_pos[1], screen_h - self.total_height))
        self.rect = pygame.Rect(self.x, self.y, self.width, self.total_height)

        # Close button (inside header, top-right)
        close_pad = (self.header_height - self._close_size) // 2
        self.close_rect = pygame.Rect(
            self.x + self.width - self._close_size - close_pad,
            self.y + close_pad,
            self._close_size, self._close_size,
        )

        # Row rects
        y = self.y + self.header_height + self.padding
        inner_w = self.width - 2 * self.padding

        self._good_label_rect = pygame.Rect(self.x + self.padding, y, inner_w, self._label_h)
        y += self._label_h + 4
        self._good_btn_rect = pygame.Rect(self.x + self.padding, y, inner_w, self._btn_h)
        y += self._btn_h + self._gap

        self._dir_label_rect = pygame.Rect(self.x + self.padding, y, inner_w, self._label_h)
        y += self._label_h + 4
        self._dir_btn_rect = pygame.Rect(self.x + self.padding, y, inner_w, self._btn_h)
        y += self._btn_h + self._gap

        self._wish_btn_rect = pygame.Rect(self.x + self.padding, y, inner_w, self._action_h)

        # Pre-compute dropdown list rects (open downward, clamp to screen)
        good_list_h = len(self.goods_names) * self._ITEM_H
        good_list_y = self._good_btn_rect.bottom
        if good_list_y + good_list_h > screen_h:
            good_list_y = self._good_btn_rect.top - good_list_h
        self._good_list_rect = pygame.Rect(
            self._good_btn_rect.x, good_list_y,
            self._good_btn_rect.width, good_list_h,
        )

        dir_list_h = len(self._DIRECTION_OPTIONS) * self._ITEM_H
        dir_list_y = self._dir_btn_rect.bottom
        if dir_list_y + dir_list_h > screen_h:
            dir_list_y = self._dir_btn_rect.top - dir_list_h
        self._dir_list_rect = pygame.Rect(
            self._dir_btn_rect.x, dir_list_y,
            self._dir_btn_rect.width, dir_list_h,
        )

    # ── Public interface ──────────────────────────────────────────────────

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        """Handle a mouse click.  Returns True if the event was consumed."""

        # 1. Good dropdown list is open — handle it first
        if self.good_dropdown_open:
            if self._good_list_rect.collidepoint(pos):
                idx = (pos[1] - self._good_list_rect.y) // self._ITEM_H
                if 0 <= idx < len(self.goods_names):
                    self.selected_good = self.goods_names[idx]
            self.good_dropdown_open = False
            return True

        # 2. Direction dropdown list is open
        if self.dir_dropdown_open:
            if self._dir_list_rect.collidepoint(pos):
                idx = (pos[1] - self._dir_list_rect.y) // self._ITEM_H
                if 0 <= idx < len(self._DIRECTION_OPTIONS):
                    self.selected_direction = self._DIRECTION_OPTIONS[idx]
            self.dir_dropdown_open = False
            return True

        # 3. Close button
        if self.close_rect.collidepoint(pos):
            self._close()
            return True

        # 4. Click outside the menu
        if not self.rect.collidepoint(pos):
            self._close()
            return True

        # 5. Good selector button
        if self._good_btn_rect.collidepoint(pos):
            self.good_dropdown_open = not self.good_dropdown_open
            self.dir_dropdown_open = False
            return True

        # 6. Direction selector button
        if self._dir_btn_rect.collidepoint(pos):
            self.dir_dropdown_open = not self.dir_dropdown_open
            self.good_dropdown_open = False
            return True

        # 7. Make Wish button
        if self._wish_btn_rect.collidepoint(pos):
            self.callback(self.selected_good, self.selected_direction)
            return True

        return False

    def draw(self, alpha_scale: float = 1.0) -> None:
        """Draw the wish menu.

        Args:
            alpha_scale: Fade factor 0.0–1.0 (used during menu-fade animations).
        """
        if alpha_scale <= 0:
            return

        font = self.game_state.font
        mouse = pygame.mouse.get_pos()

        # Use an off-screen surface when fading so we can set a global alpha
        if alpha_scale < 1.0:
            surf = pygame.Surface(
                (self.rect.width, self.rect.height), pygame.SRCALPHA
            )
            ox, oy = -self.rect.x, -self.rect.y
        else:
            surf = self.screen
            ox, oy = 0, 0

        # ── Main panel ────────────────────────────────────────────────────
        panel = self.rect.move(ox, oy)
        pygame.draw.rect(surf, SANDY_BROWN, panel)
        pygame.draw.rect(surf, DARK_BROWN, panel, 3)

        # Title
        title_surf = self.title_font.render("Well", True, DARK_BROWN)
        title_rect = title_surf.get_rect(
            center=(panel.centerx, panel.y + self.header_height // 2)
        )
        surf.blit(title_surf, title_rect)

        # Close button
        cr = self.close_rect.move(ox, oy)
        pygame.draw.rect(surf, DARK_BROWN, cr)
        if alpha_scale >= 1.0 and self.close_rect.collidepoint(mouse):
            ov = pygame.Surface(cr.size, pygame.SRCALPHA)
            ov.fill((255, 255, 255, 40))
            surf.blit(ov, cr)
        mg = 5
        pygame.draw.line(surf, WHITE, (cr.left + mg, cr.top + mg), (cr.right - mg, cr.bottom - mg), 2)
        pygame.draw.line(surf, WHITE, (cr.left + mg, cr.bottom - mg), (cr.right - mg, cr.top + mg), 2)

        # ── Good selector ─────────────────────────────────────────────────
        self._draw_label(surf, font, "Good:", self._good_label_rect.move(ox, oy))
        self._draw_selector_btn(
            surf, font, mouse, ox, oy,
            self._good_btn_rect, self.selected_good, self.good_dropdown_open,
            alpha_scale,
        )

        # ── Direction selector ────────────────────────────────────────────
        self._draw_label(surf, font, "Direction:", self._dir_label_rect.move(ox, oy))
        self._draw_selector_btn(
            surf, font, mouse, ox, oy,
            self._dir_btn_rect, self.selected_direction, self.dir_dropdown_open,
            alpha_scale,
        )

        # ── Make Wish button ──────────────────────────────────────────────
        wb = self._wish_btn_rect.move(ox, oy)
        pygame.draw.rect(surf, SANDY_BROWN, wb)
        pygame.draw.rect(surf, DARK_BROWN, wb, 2)
        if alpha_scale >= 1.0 and self._wish_btn_rect.collidepoint(mouse):
            ov = pygame.Surface(wb.size, pygame.SRCALPHA)
            ov.fill((0, 0, 0, 30))
            surf.blit(ov, wb)
        wish_text = font.render("Make a Wish", True, BLACK)
        surf.blit(wish_text, wish_text.get_rect(center=wb.center))

        # Blit faded surface to screen
        if alpha_scale < 1.0:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, (self.rect.x, self.rect.y))

        # ── Dropdown lists (always drawn on top, directly onto screen) ────
        if alpha_scale >= 1.0:
            if self.good_dropdown_open:
                self._draw_dropdown_list(
                    self.screen, font, mouse,
                    self._good_list_rect, self.goods_names, self.selected_good,
                )
            if self.dir_dropdown_open:
                self._draw_dropdown_list(
                    self.screen, font, mouse,
                    self._dir_list_rect, self._DIRECTION_OPTIONS, self.selected_direction,
                )

    # ── Private helpers ───────────────────────────────────────────────────

    def _close(self) -> None:
        self.game_state.menu_fade_window = self
        self.game_state.menu_fade_timer = self.game_state.menu_fade_duration
        self.game_state.info_window = None
        self.game_state.active_house_menu = None

    def _draw_label(
        self,
        surf: pygame.Surface,
        font: pygame.font.Font,
        text: str,
        rect: pygame.Rect,
    ) -> None:
        label = font.render(text, True, DARK_BROWN)
        surf.blit(label, (rect.x, rect.y))

    def _draw_selector_btn(
        self,
        surf: pygame.Surface,
        font: pygame.font.Font,
        mouse: Tuple[int, int],
        ox: int,
        oy: int,
        btn_rect: pygame.Rect,
        current_value: str,
        is_open: bool,
        alpha_scale: float,
    ) -> None:
        r = btn_rect.move(ox, oy)
        bg = PALE_BROWN if is_open else SANDY_BROWN
        pygame.draw.rect(surf, bg, r)
        pygame.draw.rect(surf, DARK_BROWN, r, 2)
        if alpha_scale >= 1.0 and btn_rect.collidepoint(mouse) and not is_open:
            ov = pygame.Surface(r.size, pygame.SRCALPHA)
            ov.fill((0, 0, 0, 20))
            surf.blit(ov, r)
        text_surf = font.render(current_value, True, BLACK)
        surf.blit(text_surf, text_surf.get_rect(midleft=(r.x + 8, r.centery)))
        # Small drawn triangle as arrow indicator
        ax = r.right - 14
        ay = r.centery
        half = 5
        if is_open:
            pts = [(ax - half, ay + 2), (ax + half, ay + 2), (ax, ay - half + 2)]
        else:
            pts = [(ax - half, ay - 2), (ax + half, ay - 2), (ax, ay + half - 2)]
        pygame.draw.polygon(surf, DARK_BROWN, pts)

    def _draw_dropdown_list(
        self,
        surf: pygame.Surface,
        font: pygame.font.Font,
        mouse: Tuple[int, int],
        list_rect: pygame.Rect,
        options: List[str],
        selected: str,
    ) -> None:
        pygame.draw.rect(surf, SANDY_BROWN, list_rect)
        pygame.draw.rect(surf, DARK_BROWN, list_rect, 2)
        for i, option in enumerate(options):
            item_rect = pygame.Rect(
                list_rect.x, list_rect.y + i * self._ITEM_H,
                list_rect.width, self._ITEM_H,
            )
            if option == selected:
                pygame.draw.rect(surf, PALE_BROWN, item_rect)
            elif item_rect.collidepoint(mouse):
                ov = pygame.Surface(item_rect.size, pygame.SRCALPHA)
                ov.fill((0, 0, 0, 20))
                surf.blit(ov, item_rect)
            text_surf = font.render(option, True, BLACK)
            surf.blit(text_surf, text_surf.get_rect(midleft=(item_rect.x + 8, item_rect.centery)))
            if i < len(options) - 1:
                pygame.draw.line(
                    surf, PALE_BROWN,
                    (item_rect.left + 4, item_rect.bottom),
                    (item_rect.right - 4, item_rect.bottom), 1,
                )
