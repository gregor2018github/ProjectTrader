import pygame
from typing import Tuple, Optional, TYPE_CHECKING
from ...config.colors import SANDY_BROWN, DARK_BROWN, BLACK, WHITE

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
        click_pos: Tuple[int, int],
        callback,
        category: str = "Donations"
    ):
        self.screen = screen
        self.house = house
        self.game_state = game_state
        self.callback = callback
        self.category = category
        self.font = game_state.font
        
        # Get max money
        self.max_money = 0
        if hasattr(game_state.game, 'depot'):
            self.max_money = int(game_state.game.depot.money)
            
        self.current_value = 1 if self.max_money > 0 else 0
        
        # Layout metrics
        self.width = 300
        self.height = 180
        self.padding = 15
        self.header_height = 30
        self.close_button_size = 24
        
        # Clamp position to screen
        screen_w, screen_h = screen.get_size()
        self.x = max(0, min(click_pos[0], screen_w - (self.width + self.close_button_size)))
        self.y = max(0, min(click_pos[1], screen_h - self.height))
        
        self.rect = pygame.Rect(self.x, self.y, self.width, self.height)
        
        # Close button rect
        self.close_rect = pygame.Rect(
            self.x + self.width,
            self.y,
            self.close_button_size,
            self.header_height,
        )
        
        # Slider metrics
        self.slider_rect = pygame.Rect(
            self.x + self.padding,
            self.y + self.header_height + 40,
            self.width - 2 * self.padding,
            10
        )
        self.thumb_radius = 10
        self.is_dragging = False
        
        # Donate button
        self.donate_btn_rect = pygame.Rect(
            self.x + self.padding,
            self.y + self.height - 45,
            self.width - 2 * self.padding,
            30
        )

    def _get_thumb_x(self) -> int:
        if self.max_money <= 1:
            return self.slider_rect.x
        ratio = (self.current_value - 1) / (self.max_money - 1)
        return self.slider_rect.x + int(ratio * self.slider_rect.width)

    def _update_value_from_x(self, x: int):
        if self.max_money <= 1:
            self.current_value = self.max_money
            return
            
        x = max(self.slider_rect.x, min(x, self.slider_rect.right))
        ratio = (x - self.slider_rect.x) / self.slider_rect.width
        self.current_value = 1 + int(ratio * (self.max_money - 1))

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Check if clicking on slider track or thumb
            thumb_x = self._get_thumb_x()
            thumb_y = self.slider_rect.centery
            thumb_rect = pygame.Rect(thumb_x - self.thumb_radius, thumb_y - self.thumb_radius, 
                                     self.thumb_radius * 2, self.thumb_radius * 2)
            
            # Expand hit area for slider
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
        """Handle clicks on the menu. Returns True if handled/closed."""
        if self.close_rect.collidepoint(pos):
            self._close()
            return True
            
        if not self.rect.collidepoint(pos) and not self.close_rect.collidepoint(pos):
            self._close()
            return True
            
        if self.donate_btn_rect.collidepoint(pos):
            if self.current_value > 0 and self.current_value <= self.max_money:
                if self.callback:
                    self.callback(self.current_value)
                else:
                    self._close()
            return True
            
        return True

    def _close(self):
        self.game_state.menu_fade_window = self
        self.game_state.menu_fade_timer = self.game_state.menu_fade_duration
        self.game_state.info_window = None
        self.game_state.active_house_menu = None

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return

        bounding_rect = self.rect.union(self.close_rect)
        target_surf = self.screen
        offset_x, offset_y = 0, 0
        
        if alpha_scale < 1.0:
            temp_surf = pygame.Surface((bounding_rect.width, bounding_rect.height), pygame.SRCALPHA)
            target_surf = temp_surf
            offset_x = -bounding_rect.x
            offset_y = -bounding_rect.y
        else:
            temp_surf = None

        # Draw Menu Body
        body_draw_rect = self.rect.move(offset_x, offset_y)
        pygame.draw.rect(target_surf, SANDY_BROWN, body_draw_rect)
        pygame.draw.rect(target_surf, DARK_BROWN, body_draw_rect, 3)
        
        # Draw header
        raw_name = self.house.name or "House"
        display_name = raw_name.split('_')[0]
        title_surf = self.font.render(f"Donate to {display_name}", True, BLACK)
        title_rect = title_surf.get_rect(center=(body_draw_rect.centerx, body_draw_rect.y + self.header_height // 2))
        target_surf.blit(title_surf, title_rect)

        mouse_pos = pygame.mouse.get_pos()

        # Draw Close Button
        close_draw_rect = self.close_rect.move(offset_x, offset_y)
        pygame.draw.rect(target_surf, SANDY_BROWN, close_draw_rect)
        pygame.draw.rect(target_surf, DARK_BROWN, close_draw_rect, 2)
        
        is_close_hovered = alpha_scale >= 1.0 and self.close_rect.collidepoint(mouse_pos)
        if is_close_hovered:
            overlay = pygame.Surface((close_draw_rect.width, close_draw_rect.height), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 30))
            target_surf.blit(overlay, close_draw_rect)

        # Draw X
        margin = 6
        dx, dy = -1, 0
        start1 = (close_draw_rect.left + margin + dx, close_draw_rect.top + margin + dy)
        end1 = (close_draw_rect.right - margin + dx, close_draw_rect.bottom - margin + dy)
        start2 = (close_draw_rect.left + margin + dx, close_draw_rect.bottom - margin + dy)
        end2 = (close_draw_rect.right - margin + dx, close_draw_rect.top + margin + dy)
        
        pygame.draw.line(target_surf, DARK_BROWN, start1, end1, 2)
        pygame.draw.line(target_surf, DARK_BROWN, start2, end2, 2)
        
        # Draw Slider Track
        slider_draw_rect = self.slider_rect.move(offset_x, offset_y)
        pygame.draw.rect(target_surf, DARK_BROWN, slider_draw_rect, border_radius=5)
        
        # Draw Slider Fill
        if self.max_money > 1:
            fill_width = self._get_thumb_x() - self.slider_rect.x
            if fill_width > 0:
                fill_rect = pygame.Rect(slider_draw_rect.x, slider_draw_rect.y, fill_width, slider_draw_rect.height)
                pygame.draw.rect(target_surf, (150, 100, 50), fill_rect, border_radius=5)
        
        # Draw Slider Thumb
        thumb_x = self._get_thumb_x() + offset_x
        thumb_y = slider_draw_rect.centery
        pygame.draw.circle(target_surf, WHITE, (thumb_x, thumb_y), self.thumb_radius)
        pygame.draw.circle(target_surf, DARK_BROWN, (thumb_x, thumb_y), self.thumb_radius, 2)
        
        # Draw Value Text
        val_text = f"Amount: {self.current_value} / {self.max_money}"
        val_surf = self.font.render(val_text, True, BLACK)
        val_rect = val_surf.get_rect(center=(body_draw_rect.centerx, slider_draw_rect.bottom + 20))
        target_surf.blit(val_surf, val_rect)
        
        # Draw Donate Button
        btn_draw_rect = self.donate_btn_rect.move(offset_x, offset_y)
        is_btn_hovered = alpha_scale >= 1.0 and self.donate_btn_rect.collidepoint(mouse_pos)
        
        pygame.draw.rect(target_surf, SANDY_BROWN, btn_draw_rect)
        pygame.draw.rect(target_surf, DARK_BROWN, btn_draw_rect, 2)
        
        if is_btn_hovered:
            overlay = pygame.Surface((btn_draw_rect.width, btn_draw_rect.height), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 30))
            target_surf.blit(overlay, btn_draw_rect)
            
        btn_text = self.font.render("Donate", True, BLACK)
        btn_text_rect = btn_text.get_rect(center=btn_draw_rect.center)
        target_surf.blit(btn_text, btn_text_rect)

        if temp_surf:
            temp_surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(temp_surf, (bounding_rect.x, bounding_rect.y))
