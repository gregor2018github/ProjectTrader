import pygame
from ..config.colors import *

class InfoWindow:
    def __init__(self, screen, message, options, font):
        self.screen = screen
        self.message = message
        self.options = options
        self.font = font
        
        # Calculate window size based on message and number of options
        msg_surface = self.font.render(message, True, BLACK)
        width = max(msg_surface.get_width() + 40, len(options) * 120)
        height = 120 + (len(options) > 2) * 40
        
        # Create window in center of screen
        screen_center = (screen.get_width() // 2, screen.get_height() // 2)
        self.window_rect = pygame.Rect(0, 0, width, height)
        self.window_rect.center = screen_center
        
        # Create buttons
        self.buttons = []
        button_width = 100
        button_height = 30
        total_buttons_width = len(options) * button_width + (len(options) - 1) * 20
        start_x = self.window_rect.centerx - total_buttons_width // 2
        
        for i, option in enumerate(options):
            button_rect = pygame.Rect(start_x + i * (button_width + 20),
                                    self.window_rect.bottom - 50,
                                    button_width, button_height)
            self.buttons.append((button_rect, option))

    def draw(self):
        # Draw semi-transparent background
        s = pygame.Surface((self.screen.get_width(), self.screen.get_height()))
        s.set_alpha(128)
        s.fill((0, 0, 0))
        self.screen.blit(s, (0, 0))
        
        # Draw window
        pygame.draw.rect(self.screen, LIGHT_GRAY, self.window_rect)
        pygame.draw.rect(self.screen, DARK_GRAY, self.window_rect, 2)
        
        # Draw message
        text = self.font.render(self.message, True, BLACK)
        text_rect = text.get_rect(center=(self.window_rect.centerx, self.window_rect.top + 40))
        self.screen.blit(text, text_rect)
        
        # Draw buttons
        for button_rect, text in self.buttons:
            pygame.draw.rect(self.screen, WHITE, button_rect)
            pygame.draw.rect(self.screen, DARK_GRAY, button_rect, 2)
            text_surface = self.font.render(text, True, BLACK)
            text_rect = text_surface.get_rect(center=button_rect.center)
            self.screen.blit(text_surface, text_rect)

    def handle_click(self, pos):
        for button_rect, option in self.buttons:
            if button_rect.collidepoint(pos):
                return option
        return None
