import pygame
from ..config.colors import *

class InfoWindow:
    def __init__(self, screen, message, options, font, game=None):
        self.screen = screen
        self.message = message
        self.options = options
        self.font = font
        self.game = game  # Store reference to the game object
        
        # Calculate window size based on message and number of options
        msg_surface = self.font.render(message, True, BLACK)
        width = max(msg_surface.get_width() + 80, len(options) * 120)  # Made wider for the frame
        height = 150 + (len(options) > 2) * 40  # Made taller for the frame
        
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
                                    self.window_rect.bottom - 70,  # Moved up to fit in frame
                                    button_width, button_height)
            self.buttons.append((button_rect, option))

    def draw(self):
        # Draw semi-transparent background overlay
        s = pygame.Surface((self.screen.get_width(), self.screen.get_height()))
        s.set_alpha(128)
        s.fill((0, 0, 0))
        self.screen.blit(s, (0, 0))
        
        # Get reference to game for the image
        if hasattr(self, 'game') and self.game:
            game = self.game
        else:
            from ..game_state import GameState
            game = GameState().game
        
        # Use the frame image instead of drawing a rectangle
        if hasattr(game, 'pic_info_window'):
            # Scale the frame image to fit the window size
            scaled_frame = pygame.transform.scale(game.pic_info_window, 
                                               (self.window_rect.width, self.window_rect.height))
            self.screen.blit(scaled_frame, self.window_rect)
        else:
            # Fallback to the original rectangle if image not available
            pygame.draw.rect(self.screen, LIGHT_GRAY, self.window_rect)
            pygame.draw.rect(self.screen, DARK_GRAY, self.window_rect, 2)
        
        # Draw message - adjusted positioning
        text = self.font.render(self.message, True, BLACK)
        text_rect = text.get_rect(center=(self.window_rect.centerx, self.window_rect.top + 60))
        self.screen.blit(text, text_rect)
        
        # Get mouse position for hover effects
        mouse_pos = pygame.mouse.get_pos()
        
        # Draw buttons with hover effects
        for button_rect, text in self.buttons:
            # Check if mouse is hovering over this button
            is_hovered = button_rect.collidepoint(mouse_pos)
            button_color = LIGHT_GRAY if is_hovered else WHITE
            text_color = WHITE if is_hovered else BLACK  # Change text color on hover
            
            pygame.draw.rect(self.screen, button_color, button_rect)
            pygame.draw.rect(self.screen, DARK_GRAY, button_rect, 2)
            text_surface = self.font.render(text, True, text_color)
            text_rect = text_surface.get_rect(center=button_rect.center)
            self.screen.blit(text_surface, text_rect)

    def handle_click(self, pos):
        for button_rect, option in self.buttons:
            if button_rect.collidepoint(pos):
                return option
        return None
