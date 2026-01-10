import pygame
from typing import Optional, TYPE_CHECKING
from ...config.colors import LIGHT_GRAY, DARK_GRAY, BLACK

if TYPE_CHECKING:
    from ...game import Game

class WarningMessage:
    """A transient pop-up message that fades out over time.
    
    Attributes:
        screen: The pygame surface to draw on.
        message: The warning text to display.
        font: The font used for text rendering.
        timer: Time remaining in seconds before the message disappears.
        fade_time: Duration of the fade-out effect in seconds.
        game: Optional reference to the Game instance for frame styling.
        window_rect: The rectangular area for the warning box.
    """

    def __init__(self, screen: pygame.Surface, message: str, font: pygame.font.Font, game: Optional['Game'] = None) -> None:
        """Initialize the warning message.
        
        Args:
            screen: The surface to draw on.
            message: The warning text.
            font: Font for text rendering.
            game: Optional reference to the Game object.
        """
        msg_surface = font.render(message, True, BLACK)
        width: int = msg_surface.get_width() + 80
        height: int = msg_surface.get_height() + 60
        self.window_rect: pygame.Rect = pygame.Rect(0, 0, width, height)
        self.window_rect.center = (screen.get_width() // 2, screen.get_height() // 2)
        self.screen: pygame.Surface = screen
        self.message: str = message
        self.font: pygame.font.Font = font
        self.timer: float = 2.0  # Warning persists for 2 seconds (time-based)
        self.fade_time: float = 0.5  # Fade out during the last 0.5 seconds
        self.game: Optional['Game'] = game  # store game reference

    def update(self, delta_time: float = 0.016) -> None:
        """Update the message timer.
        
        Args:
            delta_time: Time elapsed since the last update in seconds.
        """
        self.timer -= delta_time

    def draw(self) -> None:
        """Draw the warning message with transparency and fade-out effect."""
        # Determine dynamic alpha: if timer is within fade-out period, alpha decreases gradually.
        if self.timer < self.fade_time:
            current_alpha_background = int(128 * (self.timer / self.fade_time))
            current_alpha_box = int(255 * (self.timer / self.fade_time))
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