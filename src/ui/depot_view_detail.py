import pygame
from ..config.colors import YELLOW, BLACK, DARK_BROWN, TAN, BEIGE, PALE_BROWN, LIGHT_BROWN, WHEAT

class DepotViewDetail:
    def __init__(self, depot_rect, game_state):
        # Place the detail panel just to the right of depot view
        self.rect = pygame.Rect(depot_rect.left + 370, depot_rect.top + 60, 300, depot_rect.height-80)
        self.visible = False
        self.current_statistic = None
        self.game_state = game_state

    def toggle(self):
        self.visible = not self.visible

    def show_for_statistic(self, statistic_label):
        self.current_statistic = statistic_label
        self.visible = True

    def draw(self, screen, font):
        if self.visible:
            pygame.draw.rect(screen, TAN, self.rect) # WHEAT or TAN look good
            pygame.draw.rect(screen, DARK_BROWN, self.rect, 3)
            
            # Access small font from game state (must be passed in game_state)
            small_font = self.game_state.small_font
            if hasattr(font, 'game_state') and hasattr(font.game_state, 'small_font'):
                small_font = font.game_state.small_font
            
            # Draw heading with regular font
            title_text = "Wealth Details"
            if self.current_statistic:
                title_text = f"{self.current_statistic} Details"
                
            title = font.render(title_text, True, BLACK)
            screen.blit(title, (self.rect.x + 20, self.rect.y + 20))
            
            # Draw different content based on which statistic was clicked
            y_pos = self.rect.y + 60
            line_height = 24
            
            # Default lines (you can customize these based on the statistic)
            lines = []
            
            # Add specific content based on statistic
            if self.current_statistic == "Wealth Today":
                lines.extend([
                    "Assets breakdown:",
                    "  Cash: 1,240.00",
                    "  Goods: 850.00",
                    "  Properties: 0.00",
                    "  Total: 2,090.00"
                ])
            elif self.current_statistic == "Wealth Start":
                lines.extend([
                    "Initial investment:",
                    "  Starting Cash: 100.00",
                    "  Loans: 0.00",
                    "  Gifts: 0.00",
                    "  Total: 100.00"
                ])
            elif self.current_statistic == "Buy Actions":
                lines.extend([
                    "Recent purchases:",
                    "  Wood: 24 units",
                    "  Iron: 12 units",
                    "  Beer: 8 units",
                    "  Total spent: 132.00"
                ])
            elif self.current_statistic == "Sell Actions":
                lines.extend([
                    "Recent sales:",
                    "  Wood: 14 units",
                    "  Iron: 8 units",
                    "  Beer: 4 units",
                    "  Total earned: 178.00"
                ])
            elif self.current_statistic == "Total Actions":
                lines.extend([
                    "All transactions:",
                    "  Purchases: 44 units",
                    "  Sales: 26 units",
                    "  Net profit: 46.00",
                    "  Average margin: 18.4%"
                ])
            else:
                lines.extend([
                    "Income: 1,240.00",
                    "Expenses: 450.00",
                    "Profit: 790.00",
                ])
            
            # Render all detail lines with small font
            for line in lines:
                text = small_font.render(line, True, BLACK)
                screen.blit(text, (self.rect.x + 20, y_pos))
                y_pos += line_height
