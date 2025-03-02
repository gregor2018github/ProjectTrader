import pygame
from ..config.colors import *

class Menu:
    def __init__(self, screen_width, font):
        self.font = font
        self.is_open = False
        self.items = ["Quit", "Balance", "Map", "Settings", "Demo"]
        
        # Menu button dimensions and position
        self.button_width = 100
        self.button_height = 40
        self.button_rect = pygame.Rect(
            screen_width - self.button_width - 10,  # 10px from right edge
            10,  # 10px from top
            self.button_width,
            self.button_height
        )
        
        # Dropdown dimensions
        self.item_height = 40
        self.dropdown_rect = pygame.Rect(
            self.button_rect.x,
            self.button_rect.bottom,
            self.button_width,
            self.item_height * len(self.items)
        )

    def draw(self, screen):
        # Get mouse position for hover effect
        mouse_pos = pygame.mouse.get_pos()
        is_hovered = self.button_rect.collidepoint(mouse_pos)
        
        # Draw menu button with hover effects
        button_color = SANDY_BROWN if is_hovered else TAN
        text_color = WHITE if is_hovered else BLACK
        
        pygame.draw.rect(screen, button_color, self.button_rect)
        pygame.draw.rect(screen, DARK_BROWN, self.button_rect, 2)
        
        # Draw "Menu" text with appropriate color based on hover state
        text = self.font.render("Menu", True, text_color)
        text_rect = text.get_rect(center=self.button_rect.center)
        screen.blit(text, text_rect)
        
        # Draw dropdown if open
        if self.is_open:
            pygame.draw.rect(screen, WHITE, self.dropdown_rect)
            
            for i, item in enumerate(self.items):
                item_rect = pygame.Rect(
                    self.dropdown_rect.x,
                    self.dropdown_rect.y + (i * self.item_height),
                    self.dropdown_rect.width,
                    self.item_height
                )
                
                # Highlight on hover
                if item_rect.collidepoint(pygame.mouse.get_pos()):
                    pygame.draw.rect(screen, LIGHT_GRAY, item_rect)
                
                # Draw item text
                text = self.font.render(item, True, BLACK)
                text_rect = text.get_rect(center=item_rect.center)
                screen.blit(text, text_rect)
                
                # Draw separator line
                if i < len(self.items) - 1:
                    pygame.draw.line(screen, DARK_GRAY,
                                   (item_rect.left, item_rect.bottom),
                                   (item_rect.right, item_rect.bottom))
                # Draw dropdown border    
                pygame.draw.rect(screen, DARK_GRAY, self.dropdown_rect, 2)
        

    def handle_click(self, pos):
        if self.button_rect.collidepoint(pos):
            self.is_open = not self.is_open
            return None
            
        if self.is_open and self.dropdown_rect.collidepoint(pos):
            clicked_index = (pos[1] - self.dropdown_rect.y) // self.item_height
            if 0 <= clicked_index < len(self.items):
                self.is_open = False
                return self.items[clicked_index]
        
        self.is_open = False
        return None
