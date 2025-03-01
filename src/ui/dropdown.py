import pygame
from ..config.colors import *

class Dropdown:
    def __init__(self, x, y, width, height, options, font):
        self.rect = pygame.Rect(x, y, width, height)
        self.options = options
        self.font = font
        self.item_height = 25
        self.is_open = False
        
        # Calculate dropdown dimensions
        self.dropdown_height = len(options) * self.item_height
        # Position above the input field
        self.dropdown_rect = pygame.Rect(x, y - self.dropdown_height, width, self.dropdown_height)
        
    def draw(self, screen):
        if self.is_open:
            # Draw dropdown background
            pygame.draw.rect(screen, WHITE, self.dropdown_rect)

            
            # Draw options
            for i, option in enumerate(self.options):
                item_rect = pygame.Rect(self.dropdown_rect.x, 
                                      self.dropdown_rect.y + (i * self.item_height),
                                      self.dropdown_rect.width,
                                      self.item_height)
                
                # Highlight on hover
                if item_rect.collidepoint(pygame.mouse.get_pos()):
                    pygame.draw.rect(screen, LIGHT_GRAY, item_rect)
                
                # Draw option text
                text = self.font.render(option, True, BLACK)
                screen.blit(text, (item_rect.x + 5, item_rect.y + 2))
                
                # Draw separator line
                if i < len(self.options) - 1:
                    pygame.draw.line(screen, DARK_GRAY, 
                                   (item_rect.left, item_rect.bottom),
                                   (item_rect.right, item_rect.bottom))

            # Draw dropdown border        
            pygame.draw.rect(screen, DARK_BROWN, self.dropdown_rect, 2)
    
    def handle_click(self, pos):
        if not self.is_open:
            return None
            
        # Check if click is inside dropdown
        if self.dropdown_rect.collidepoint(pos):
            clicked_index = (pos[1] - self.dropdown_rect.y) // self.item_height
            if 0 <= clicked_index < len(self.options):
                self.is_open = False
                return self.options[clicked_index]
        
        # Close dropdown if clicked outside
        self.is_open = False
        return None
