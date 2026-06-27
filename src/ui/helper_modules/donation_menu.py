import os
import pygame
from typing import Tuple, TYPE_CHECKING
from ...config.colors import SANDY_BROWN, DARK_BROWN, BLACK, WHITE
from ...config.constants import FONTS_PATH
from ..ui_utils import draw_9slice

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.house import House

class DonationMenu:
    """A menu for donating money to an institution using a slider."""

    def __init__(
        self,
        screen: pygame.Surface,
        house: 'House',
        game_state: 'GameState',
        callback,
        category: str = "Donations"
    ):
        self.screen = screen
        self.house = house
        self.game_state = game_state
        self.callback = callback
        self.category = category
        self.font = game_state.font
        try:
            self.title_font = pygame.font.Font(os.path.join(FONTS_PATH, "Medici Text.ttf"), 26)
        except Exception:
            self.title_font = self.font

        # Get max money
        self.max_money = 0
        if hasattr(game_state.game, 'depot'):
            self.max_money = int(game_state.game.depot.money)

        self.current_value = 1 if self.max_money > 0 else 0

        # Layout — centred on screen, large enough to breathe
        self.width = 380
        self.height = 185
        self.padding = 20
        self.header_height = 36
        cb = 24  # close button size

        screen_w, screen_h = screen.get_size()
        self.rect = pygame.Rect(
            (screen_w - self.width) // 2,
            (screen_h - self.height) // 2,
            self.width,
            self.height,
        )

        # Close button — inside panel, top-right corner
        self.close_rect = pygame.Rect(
            self.rect.right - cb - 8,
            self.rect.top + 8,
            cb, cb,
        )

        # Slider
        self.slider_rect = pygame.Rect(
            self.rect.x + self.padding,
            self.rect.y + self.header_height + 18,
            self.width - 2 * self.padding,
            10,
        )
        self.thumb_radius = 10
        self.is_dragging = False

        # Donate button
        self.donate_btn_rect = pygame.Rect(
            self.rect.x + self.padding,
            self.rect.bottom - 50,
            self.width - 2 * self.padding,
            34,
        )

    # ------------------------------------------------------------------
    # Slider helpers
    # ------------------------------------------------------------------

    def _get_thumb_x(self) -> int:
        if self.max_money <= 1:
            return self.slider_rect.x
        ratio = (self.current_value - 1) / (self.max_money - 1)
        return self.slider_rect.x + int(ratio * self.slider_rect.width)

    def _update_value_from_x(self, x: int) -> None:
        if self.max_money <= 1:
            self.current_value = self.max_money
            return
        x = max(self.slider_rect.x, min(x, self.slider_rect.right))
        ratio = (x - self.slider_rect.x) / self.slider_rect.width
        self.current_value = 1 + int(ratio * (self.max_money - 1))

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            thumb_x = self._get_thumb_x()
            thumb_y = self.slider_rect.centery
            thumb_rect = pygame.Rect(
                thumb_x - self.thumb_radius, thumb_y - self.thumb_radius,
                self.thumb_radius * 2, self.thumb_radius * 2,
            )
            hit_rect = self.slider_rect.inflate(0, 20)
            if thumb_rect.collidepoint(event.pos) or hit_rect.collidepoint(event.pos):
                self.is_dragging = True
                self._update_value_from_x(event.pos[0])
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.is_dragging = False
        elif event.type == pygame.MOUSEMOTION:
            if self.is_dragging:
                self._update_value_from_x(event.pos[0])

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.close_rect.collidepoint(pos):
            self._close()
            return True
        if not self.rect.collidepoint(pos):
            self._close()
            return True
        if self.donate_btn_rect.collidepoint(pos):
            if self.current_value > 0 and self.current_value <= self.max_money:
                if self.callback:
                    self.callback(self.current_value)
                else:
                    self._close()
        return True

    def _close(self) -> None:
        self.game_state.menu_fade_window = self
        self.game_state.menu_fade_timer = self.game_state.menu_fade_duration
        self.game_state.info_window = None
        self.game_state.active_house_menu = None

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return

        pw, ph = self.rect.width, self.rect.height
        surf = pygame.Surface((pw, ph), pygame.SRCALPHA)

        # Frame
        game = getattr(self.game_state, 'game', None)
        if game and hasattr(game, 'pic_info_window'):
            draw_9slice(surf, game.pic_info_window, pygame.Rect(0, 0, pw, ph))
        else:
            surf.fill((*SANDY_BROWN, 255))
            pygame.draw.rect(surf, DARK_BROWN, pygame.Rect(0, 0, pw, ph), 3)

        # Title — derived from category so it reads "Town" / "Church" etc.
        institution = self.category.replace(" Donations", "")
        title_surf = self.title_font.render(f"Donate to the {institution}", True, DARK_BROWN)
        surf.blit(title_surf, title_surf.get_rect(centerx=pw // 2, top=12))

        mouse_pos = pygame.mouse.get_pos()

        # Close button (local coords)
        lc = self.close_rect.move(-self.rect.x, -self.rect.y)
        is_close_hovered = alpha_scale >= 1.0 and self.close_rect.collidepoint(mouse_pos)
        pygame.draw.rect(surf, (180, 60, 60) if is_close_hovered else DARK_BROWN, lc)
        m = 5
        pygame.draw.line(surf, WHITE, (lc.left+m, lc.top+m), (lc.right-m, lc.bottom-m), 2)
        pygame.draw.line(surf, WHITE, (lc.left+m, lc.bottom-m), (lc.right-m, lc.top+m), 2)

        # Slider (local coords)
        sx = self.slider_rect.x - self.rect.x
        sy = self.slider_rect.y - self.rect.y
        local_slider = pygame.Rect(sx, sy, self.slider_rect.width, self.slider_rect.height)
        pygame.draw.rect(surf, DARK_BROWN, local_slider, border_radius=5)

        if self.max_money > 1:
            fill_width = self._get_thumb_x() - self.slider_rect.x
            if fill_width > 0:
                pygame.draw.rect(surf, (150, 100, 50), pygame.Rect(sx, sy, fill_width, local_slider.height), border_radius=5)

        thumb_x = self._get_thumb_x() - self.rect.x
        thumb_y = local_slider.centery
        pygame.draw.circle(surf, WHITE, (thumb_x, thumb_y), self.thumb_radius)
        pygame.draw.circle(surf, DARK_BROWN, (thumb_x, thumb_y), self.thumb_radius, 2)

        # Amount label
        val_surf = self.font.render(f"Amount: {self.current_value} / {self.max_money}", True, BLACK)
        surf.blit(val_surf, val_surf.get_rect(centerx=pw // 2, top=local_slider.bottom + 7))

        # Donate button (local coords)
        lbtn = self.donate_btn_rect.move(-self.rect.x, -self.rect.y)
        is_btn_hovered = alpha_scale >= 1.0 and self.donate_btn_rect.collidepoint(mouse_pos)
        pygame.draw.rect(surf, SANDY_BROWN, lbtn)
        pygame.draw.rect(surf, DARK_BROWN, lbtn, 2)
        if is_btn_hovered:
            ov = pygame.Surface((lbtn.width, lbtn.height), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 30))
            surf.blit(ov, lbtn)
        btn_text = self.font.render("Donate", True, BLACK)
        surf.blit(btn_text, btn_text.get_rect(center=lbtn.center))

        if alpha_scale < 1.0:
            surf.set_alpha(int(255 * alpha_scale))
        self.screen.blit(surf, self.rect)
