import pygame
from ..config.colors import LIGHT_GRAY, DARK_GRAY, BLACK

class WarningMessage:
    def __init__(self, screen, message, font, game=None):  # added game parameter
        msg_surface = font.render(message, True, BLACK)
        width = msg_surface.get_width() + 80
        height = msg_surface.get_height() + 60
        self.window_rect = pygame.Rect(0, 0, width, height)
        self.window_rect.center = (screen.get_width() // 2, screen.get_height() // 2)
        self.screen = screen
        self.message = message
        self.font = font
        self.timer = 30  # Warning persists for x refreshes
        self.fading = 10  # fade out duration
        self.game = game  # store game reference

    def update(self):
        self.timer -= 1

    def draw(self):
        # Determine dynamic alpha: if timer is within fade-out period, alpha decreases gradually.
        if self.timer < self.fading:
            current_alpha_background = int(128 * (self.timer / self.fading))
            current_alpha_box = int(255 * (self.timer / self.fading))
        else:
            current_alpha_background = 128
            current_alpha_box = 255

        # Draw semi-transparent background overlay with dynamic alpha
        overlay = pygame.Surface((self.screen.get_width(), self.screen.get_height()))
        overlay.set_alpha(current_alpha_background)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))
        
        # Use the info window background frame if available; apply fading to the frame as well.
        if self.game and getattr(self.game, "pic_info_window", None):
            scaled_frame = pygame.transform.scale(self.game.pic_info_window, (self.window_rect.width, self.window_rect.height))
            frame_surface = scaled_frame.copy()
            frame_surface.set_alpha(current_alpha_box)
            self.screen.blit(frame_surface, self.window_rect)
        else:
            # Fallback to drawing a rectangle with fading colors
            temp_surface = pygame.Surface((self.window_rect.width, self.window_rect.height))
            temp_surface.fill(LIGHT_GRAY)
            temp_surface.set_alpha(current_alpha_box)
            self.screen.blit(temp_surface, self.window_rect)
            pygame.draw.rect(self.screen, DARK_GRAY, self.window_rect, 2)
            
        # Draw warning message text with the same fade effect
        text = self.font.render(self.message, True, BLACK)
        text_surface = text.copy()
        text_surface.set_alpha(current_alpha_box)
        text_rect = text.get_rect(center=(self.window_rect.centerx, self.window_rect.top + 40))
        self.screen.blit(text_surface, text_rect)