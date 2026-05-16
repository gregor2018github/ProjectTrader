import pygame
from typing import Tuple, List, Optional, TYPE_CHECKING
from ...config.colors import *

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.good import Good
    from ...models.depot import Depot

class TradeMenu:
    """A menu for trading goods at a market."""
    
    def __init__(
        self,
        screen: pygame.Surface,
        game_state: 'GameState',
        good_name: str,
        click_pos: Tuple[int, int],
    ):
        self.screen = screen
        self.game_state = game_state
        self.good_name = good_name
        self.quantity = 1
        
        # Find the Good object
        self.good: Optional['Good'] = None
        for g in game_state.game.goods:
            if g.name == good_name:
                self.good = g
                break
        
        self.depot = game_state.game.depot
        self.font = game_state.font
        
        # Layout metrics
        self.width = 240
        self.height = 235
        self.padding = 10
        self.header_height = 30
        self.row_height = 40
        
        self.close_button_size = 24
        
        # Clamp position to screen
        screen_w, screen_h = screen.get_size()
        self.x = max(0, min(click_pos[0], screen_w - (self.width + self.close_button_size)))
        self.y = max(0, min(click_pos[1], screen_h - self.height))
        
        self.rect = pygame.Rect(self.x, self.y, self.width, self.height)
        
        # Close button rect (outside, to the right of the header)
        self.close_rect = pygame.Rect(
            self.x + self.width,
            self.y,
            self.close_button_size,
            self.header_height,
        )
        
        # Define buttons
        self.buttons = {}
        self._update_buttons()

    def _update_buttons(self):
        """Update button positions."""
        cx = self.rect.centerx
        x = self.rect.x + self.padding
        y = self.rect.y + self.header_height + self.padding
        width = self.rect.width - 2 * self.padding
        
        # Quantity control row
        qty_center = y + 20
        arrow_size = 20
        
        # Centered Quantity Text Area (conceptually)
        # Minus buttons
        self.buttons['minus10'] = pygame.Rect(cx - 80, qty_center - 10, arrow_size, arrow_size)
        self.buttons['minus'] = pygame.Rect(cx - 50, qty_center - 10, arrow_size, arrow_size)
        # Plus buttons
        self.buttons['plus'] = pygame.Rect(cx + 30, qty_center - 10, arrow_size, arrow_size)
        self.buttons['plus10'] = pygame.Rect(cx + 60, qty_center - 10, arrow_size, arrow_size)
        
        y += 115

        # Buy Button
        self.buttons['buy'] = pygame.Rect(x, y, width, 30)

        y += 40

        # Sell Button
        self.buttons['sell'] = pygame.Rect(x, y, width, 30)

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        """Handle clicks on the menu. Returns True if handled/closed."""
        if self.close_rect.collidepoint(pos) or (not self.rect.collidepoint(pos) and not self.close_rect.collidepoint(pos)):
            self._close()
            return True

        if self.buttons['plus10'].collidepoint(pos):
            self.quantity += 10
            if self.quantity > 999:
                self.quantity = 999
            return True
            
        if self.buttons['plus'].collidepoint(pos):
            self.quantity += 1
            if self.quantity > 999: # Cap quantity
                self.quantity = 999
            return True

        if self.buttons['minus10'].collidepoint(pos):
            self.quantity = max(1, self.quantity - 10)
            return True
            
        if self.buttons['minus'].collidepoint(pos):
            self.quantity = max(1, self.quantity - 1)
            return True
            
        if self.buttons['buy'].collidepoint(pos) and self.good:
            # Replaced show_warning with local handling if needed, but depot has warnings
            self.depot.buy(self.good, self.quantity, self.game_state)
            return True
            
        if self.buttons['sell'].collidepoint(pos) and self.good:
            self.depot.sell(self.good, self.quantity, self.game_state)
            return True
            
        return False

    def _close(self):
        self.game_state.menu_fade_window = self
        self.game_state.menu_fade_timer = self.game_state.menu_fade_duration
        self.game_state.info_window = None
        self.game_state.active_house_menu = None

    def draw(self, alpha_scale: float = 1.0) -> None:
        """Draw the trade menu."""
        if alpha_scale <= 0:
            return

        # Determine bounding area for all parts
        bounding_rect = self.rect.union(self.close_rect)
        
        # Setup target surface
        target_surf = self.screen
        offset_x, offset_y = 0, 0
        
        if alpha_scale < 1.0:
            temp_surf = pygame.Surface((bounding_rect.width, bounding_rect.height), pygame.SRCALPHA)
            target_surf = temp_surf
            offset_x = -bounding_rect.x
            offset_y = -bounding_rect.y
        else:
            temp_surf = None

        # Draw Base Check
        body_draw_rect = self.rect.move(offset_x, offset_y)
        pygame.draw.rect(target_surf, SANDY_BROWN, body_draw_rect)
        pygame.draw.rect(target_surf, DARK_BROWN, body_draw_rect, 3)

        # Draw close button
        close_draw_rect = self.close_rect.move(offset_x, offset_y)
        pygame.draw.rect(target_surf, SANDY_BROWN, close_draw_rect)
        pygame.draw.rect(target_surf, DARK_BROWN, close_draw_rect, 2)
        
        # Close button hover effect
        mouse_pos = pygame.mouse.get_pos()
        if alpha_scale >= 1.0 and self.close_rect.collidepoint(mouse_pos):
            overlay = pygame.Surface((close_draw_rect.width, close_draw_rect.height), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 30))
            target_surf.blit(overlay, close_draw_rect)
        
        # X mark
        margin = 6
        start1 = (close_draw_rect.left + margin, close_draw_rect.top + margin)
        end1 = (close_draw_rect.right - margin, close_draw_rect.bottom - margin)
        start2 = (close_draw_rect.left + margin, close_draw_rect.bottom - margin)
        end2 = (close_draw_rect.right - margin, close_draw_rect.top + margin)
        pygame.draw.line(target_surf, DARK_BROWN, start1, end1, 2)
        pygame.draw.line(target_surf, DARK_BROWN, start2, end2, 2)

        # Header: Good Name
        title_surf = self.font.render(f"Trade {self.good_name}", True, BLACK)
        title_rect = title_surf.get_rect(center=(body_draw_rect.centerx, body_draw_rect.y + 15))
        target_surf.blit(title_surf, title_rect)

        # Quantity Row
        minus10_rect = self.buttons['minus10'].move(offset_x, offset_y)
        minus_rect = self.buttons['minus'].move(offset_x, offset_y)
        plus_rect = self.buttons['plus'].move(offset_x, offset_y)
        plus10_rect = self.buttons['plus10'].move(offset_x, offset_y)
        
        # Hover effects
        for btn_key in ['minus10', 'minus', 'plus', 'plus10']:
            if alpha_scale >= 1.0 and self.buttons[btn_key].collidepoint(mouse_pos):
                 btn_rect = self.buttons[btn_key].move(offset_x, offset_y)
                 overlay = pygame.Surface((btn_rect.width, btn_rect.height), pygame.SRCALPHA)
                 overlay.fill((0, 0, 0, 30))
                 target_surf.blit(overlay, btn_rect)

        # Arrows (Triangles)
        # Minus10 (double point left)
        pygame.draw.polygon(target_surf, DARK_BROWN, [
            (minus10_rect.right, minus10_rect.top),
            (minus10_rect.centerx, minus10_rect.centery),
            (minus10_rect.right, minus10_rect.bottom)
        ])
        pygame.draw.polygon(target_surf, DARK_BROWN, [
            (minus10_rect.centerx, minus10_rect.top),
            (minus10_rect.left, minus10_rect.centery),
            (minus10_rect.centerx, minus10_rect.bottom)
        ])

        # Minus (point left)
        pygame.draw.polygon(target_surf, DARK_BROWN, [
            (minus_rect.right, minus_rect.top),
            (minus_rect.left, minus_rect.centery),
            (minus_rect.right, minus_rect.bottom)
        ])

        # Plus (point right)
        pygame.draw.polygon(target_surf, DARK_BROWN, [
            (plus_rect.left, plus_rect.top),
            (plus_rect.right, plus_rect.centery),
            (plus_rect.left, plus_rect.bottom)
        ])

        # Plus10 (double point right)
        pygame.draw.polygon(target_surf, DARK_BROWN, [
            (plus10_rect.left, plus10_rect.top),
            (plus10_rect.centerx, plus10_rect.centery),
            (plus10_rect.left, plus10_rect.bottom)
        ])
        pygame.draw.polygon(target_surf, DARK_BROWN, [
            (plus10_rect.centerx, plus10_rect.top),
            (plus10_rect.right, plus10_rect.centery),
            (plus10_rect.centerx, plus10_rect.bottom)
        ])
        
        # Quantity Number
        qty_surf = self.font.render(str(self.quantity), True, BLACK)
        qty_rect = qty_surf.get_rect(center=(body_draw_rect.centerx, minus_rect.centery))
        target_surf.blit(qty_surf, qty_rect)

        # Price Info (below Quantity)
        info_y = minus_rect.bottom + 8
        line_gap = 23
        if self.good:
            unit_price = self.good.get_price()
            fee = self.depot.transaction_cost

            price_surf = self.font.render(f"Price per Unit: {unit_price:.1f}", True, DARK_GRAY)
            target_surf.blit(price_surf, price_surf.get_rect(center=(body_draw_rect.centerx, info_y + price_surf.get_height() // 2)))

            fee_surf = self.font.render(f"Trading Fees: {fee:.1f}", True, DARK_GRAY)
            target_surf.blit(fee_surf, fee_surf.get_rect(center=(body_draw_rect.centerx, info_y + line_gap + fee_surf.get_height() // 2)))

            hovering_buy  = alpha_scale >= 1.0 and self.buttons['buy'].collidepoint(mouse_pos)
            hovering_sell = alpha_scale >= 1.0 and self.buttons['sell'].collidepoint(mouse_pos)
            if hovering_buy:
                total = unit_price * self.quantity + fee
                total_surf = self.font.render(f"Total Cost: {total:.1f}", True, DARK_BROWN)
                target_surf.blit(total_surf, total_surf.get_rect(center=(body_draw_rect.centerx, info_y + line_gap * 2 + total_surf.get_height() // 2)))
            elif hovering_sell:
                total = unit_price * self.quantity - fee
                total_surf = self.font.render(f"Total Income: {total:.1f}", True, DARK_BROWN)
                target_surf.blit(total_surf, total_surf.get_rect(center=(body_draw_rect.centerx, info_y + line_gap * 2 + total_surf.get_height() // 2)))

        # Buy Button
        buy_rect = self.buttons['buy'].move(offset_x, offset_y)
        buy_color = BUY_BUTTON
        if alpha_scale >= 1.0 and self.buttons['buy'].collidepoint(mouse_pos):
            buy_color = BUY_BUTTON_HOVER

        pygame.draw.rect(target_surf, buy_color, buy_rect)
        pygame.draw.rect(target_surf, BUY_BUTTON_BORDER, buy_rect, 2)
        buy_text = self.font.render("Buy", True, BUTTON_TEXT)
        buy_text_rect = buy_text.get_rect(center=buy_rect.center)
        target_surf.blit(buy_text, buy_text_rect)

        # Sell Button
        sell_rect = self.buttons['sell'].move(offset_x, offset_y)
        sell_color = SELL_BUTTON
        if alpha_scale >= 1.0 and self.buttons['sell'].collidepoint(mouse_pos):
            sell_color = SELL_BUTTON_HOVER

        pygame.draw.rect(target_surf, sell_color, sell_rect)
        pygame.draw.rect(target_surf, SELL_BUTTON_BORDER, sell_rect, 2)
        sell_text = self.font.render("Sell", True, BUTTON_TEXT)
        sell_text_rect = sell_text.get_rect(center=sell_rect.center)
        target_surf.blit(sell_text, sell_text_rect)

        # Final blit
        if temp_surf:
            temp_surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(temp_surf, (bounding_rect.x, bounding_rect.y))
