import pygame
from typing import List, Optional, Tuple, Any, TYPE_CHECKING
from ..config.colors import *

if TYPE_CHECKING:
    from ..game import Game

class InfoWindow:
    """A pop-up information window with customizable message and buttons.
    
    Attributes:
        screen: The pygame surface to draw on.
        message: The message text to display.
        options: A list of button labels.
        font: The font used for text rendering.
        game: Reference to the main Game instance.
        window_rect: The rectangular area of the info window.
        buttons: A list of tuples containing (button_rect, option_text).
    """

    def __init__(self, screen: pygame.Surface, message: str, options: List[str], font: pygame.font.Font, game: Optional['Game'] = None) -> None:
        """Initialize the info window.
        
        Args:
            screen: The surface to draw on.
            message: The message to show.
            options: List of string labels for the buttons.
            font: Font for text rendering.
            game: Optional reference to the Game object.
        """
        self.screen: pygame.Surface = screen
        self.message: str = message
        self.options: List[str] = options
        self.font: pygame.font.Font = font
        self.game: Optional['Game'] = game  # Store reference to the game object
        
        # Calculate window size based on message and number of options
        msg_surface = self.font.render(message, True, BLACK)
        width: int = max(msg_surface.get_width() + 80, len(options) * 120)  # Made wider for the frame
        height: int = 150 + (len(options) > 2) * 40  # Made taller for the frame
        
        # Create window in center of screen
        screen_center = (screen.get_width() // 2, screen.get_height() // 2)
        self.window_rect: pygame.Rect = pygame.Rect(0, 0, width, height)
        self.window_rect.center = screen_center
        
        # Create buttons
        self.buttons: List[Tuple[pygame.Rect, str]] = []
        button_width: int = 100
        button_height: int = 30
        total_buttons_width: int = len(options) * button_width + (len(options) - 1) * 20
        start_x: int = self.window_rect.centerx - total_buttons_width // 2
        
        for i, option in enumerate(options):
            button_rect = pygame.Rect(start_x + i * (button_width + 20),
                                    self.window_rect.bottom - 70,  # Moved up to fit in frame
                                    button_width, button_height)
            self.buttons.append((button_rect, option))

    def draw(self) -> None:
        """Draw the information window overlay and content."""
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
            # This is a fallback and might fail if GameState isn't initialized correctly
            game = GameState().game  # type: ignore
        
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

    def handle_click(self, pos: Tuple[int, int]) -> Optional[str]:
        """Check if any button was clicked.
        
        Args:
            pos: The (x, y) mouse position of the click.
            
        Returns:
            Optional[str]: The label of the clicked button, or None if no button was clicked.
        """
        for button_rect, option in self.buttons:
            if button_rect.collidepoint(pos):
                return option
        return None
