import pygame
from ..config.colors import YELLOW, BLACK, DARK_BROWN, TAN, BEIGE

class DepotViewDetail:
    def __init__(self, depot_rect):
        # Place the detail panel just to the right of depot view
        self.rect = pygame.Rect(depot_rect.left + 370, depot_rect.top + 60, 300, depot_rect.height-80)
        self.visible = False
        print(f"Detail panel initialized at {self.rect}")

    def toggle(self):
        self.visible = not self.visible

    def draw(self, screen, font):
        if self.visible:
            # Draw panel with bright yellow background and border
            pygame.draw.rect(screen, TAN, self.rect)
            pygame.draw.rect(screen, DARK_BROWN, self.rect, 3)
            
            # Draw heading
            title = font.render("Wealth Details", True, BLACK)
            screen.blit(title, (self.rect.x + 20, self.rect.y + 20))
            
            # Draw some sample data
            y_pos = self.rect.y + 60
            line_height = 24
            
            lines = [
                "This is the detail panel",
                "showing wealth statistics:",
                "",
                "Income: 1,240.00",
                "Expenses: 450.00",
                "Profit: 790.00",
                "",
                "Click the + button again",
                "to close this panel."
            ]
            
            for line in lines:
                text = font.render(line, True, BLACK)
                screen.blit(text, (self.rect.x + 20, y_pos))
                y_pos += line_height
