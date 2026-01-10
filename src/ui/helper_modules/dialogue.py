import pygame
from typing import List, Optional, Tuple, Any, TYPE_CHECKING
from ...config.colors import *

if TYPE_CHECKING:
    from ...game import Game

class Dialogue:
    """A UI component that provides a semi-transparent dialogue window with portraits and options.
    
    Handles word-wrapped text rendering, portrait scaling, and interactive button logic.
    """
    
    def __init__(self, screen: pygame.Surface, game: 'Game', picture: str, npc_name: str, text: str, answers: Optional[List[str]] = None, sound: Optional[str] = None) -> None:
        """
        Initialize a dialogue with an NPC
        
        Args:
            screen: pygame surface to draw on.
            game: reference to main game object.
            picture: string key for the portrait image in game.pic_portraits.
            npc_name: name of the NPC to display.
            text: string of dialogue text.
            answers: list of string answers (default: ["Continue", "Leave"]).
            sound: name of sound file to play (default: None).
        """
        self.screen: pygame.Surface = screen
        self.game: 'Game' = game
        self.picture: str = picture
        self.npc_name: str = npc_name
        self.text: str = text
        self.answers: List[str] = answers or ["Continue", "Leave"]
        self.font: pygame.font.Font = game.font
        self.active: bool = True
        self.result: Optional[str] = None  # Will store the selected answer

        # first stop all sounds that are still running
        pygame.mixer.stop()
        
        # Play sound if specified
        if sound and hasattr(game, 'play_sound'):
            game.play_sound(sound)
        
        # Calculate portrait dimensions (70% of screen height)
        screen_width, screen_height = screen.get_size()
        portrait_height = int(screen_height * 0.7)
        
        # Get original portrait aspect ratio to maintain proportions
        original_portrait = game.pic_portraits.get(picture, None)
        if original_portrait:
            orig_width, orig_height = original_portrait.get_size()
            aspect_ratio: float = orig_width / orig_height
            portrait_width: int = int(portrait_height * aspect_ratio)
            
            # Scale the portrait preserving aspect ratio
            self.portrait: Optional[pygame.Surface] = pygame.transform.scale(
                original_portrait,
                (portrait_width, portrait_height)
            )
            
            # Position portrait in bottom left
            self.portrait_rect: pygame.Rect = pygame.Rect(
                0,  # Left margin
                screen_height - portrait_height,  # Bottom position
                portrait_width,
                portrait_height
            )
        else:
            # Fallback if portrait not found
            self.portrait = None
            self.portrait_rect = pygame.Rect(20, screen_height - 300, 200, 280)
        
        # Create dialogue window in the middle-right of the screen
        dialogue_width: int = screen_width - self.portrait_rect.right - 60
        dialogue_height: int = min(400, int(screen_height * 0.6))
        
        self.dialogue_rect: pygame.Rect = pygame.Rect(
            self.portrait_rect.right + 30,
            (screen_height // 2) - (dialogue_height // 2),  # Center vertically
            dialogue_width,
            dialogue_height
        )
        
        # Create buttons for answers
        self.buttons: List[Tuple[pygame.Rect, str]] = []
        button_width: int = min(dialogue_width - 40, 200)
        button_height: int = 40
        spacing: int = 20
        
        # If we have multiple answers, arrange them side by side
        if len(self.answers) > 1:
            total_width: int = (button_width * len(self.answers)) + (spacing * (len(self.answers) - 1))
            start_x: int = self.dialogue_rect.centerx - (total_width // 2)
            
            for i, answer in enumerate(self.answers):
                button_rect = pygame.Rect(
                    start_x + (i * (button_width + spacing)),
                    self.dialogue_rect.bottom - button_height - 35,
                    button_width,
                    button_height
                )
                self.buttons.append((button_rect, answer))
        else:
            # Single answer centered
            button_rect = pygame.Rect(
                self.dialogue_rect.centerx - (button_width // 2),
                self.dialogue_rect.bottom - button_height - 35,
                button_width,
                button_height
            )
            self.buttons.append((button_rect, self.answers[0]))
    
    def draw(self) -> None:
        """Draw the dialogue UI."""
        if not self.active:
            return
            
        # Draw semi-transparent background overlay
        overlay = pygame.Surface((self.screen.get_width(), self.screen.get_height()))
        overlay.set_alpha(160)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))
        
        # Draw portrait if available
        if self.portrait:
            self.screen.blit(self.portrait, self.portrait_rect)
        
        # Draw dialogue window with background image if available
        if hasattr(self.game, 'pic_info_window'):
            # Scale the image to fit the dialogue window
            scaled_frame = pygame.transform.scale(
                self.game.pic_info_window,
                (self.dialogue_rect.width, self.dialogue_rect.height)
            )
            self.screen.blit(scaled_frame, self.dialogue_rect)
        else:
            # Fallback to drawing a rectangle
            pygame.draw.rect(self.screen, LIGHT_GRAY, self.dialogue_rect)
            pygame.draw.rect(self.screen, DARK_GRAY, self.dialogue_rect, 2)
        
        # Draw NPC name
        name_text = self.font.render(self.npc_name, True, DARK_BROWN)
        self.screen.blit(name_text, (self.dialogue_rect.x + 60, self.dialogue_rect.y + 25))
        
        # Draw dialogue text (with word wrapping)
        self._draw_wrapped_text(
            self.text,
            pygame.Rect(
                self.dialogue_rect.x + 20,
                self.dialogue_rect.y + 70,
                self.dialogue_rect.width - 40,
                self.dialogue_rect.height - 150
            )
        )
        
        # Get mouse position for hover effects
        mouse_pos = pygame.mouse.get_pos()
        
        # Draw answer buttons with hover effects
        for button_rect, text in self.buttons:
            # Check for hover state
            is_hovered = button_rect.collidepoint(mouse_pos)
            button_color = SANDY_BROWN if is_hovered else TAN
            text_color = WHITE if is_hovered else BLACK
            
            pygame.draw.rect(self.screen, button_color, button_rect)
            pygame.draw.rect(self.screen, DARK_BROWN, button_rect, 2)
            
            text_surface = self.font.render(text, True, text_color)
            text_rect = text_surface.get_rect(center=button_rect.center)
            self.screen.blit(text_surface, text_rect)
    
    def _draw_wrapped_text(self, text: str, rect: pygame.Rect) -> None:
        """Draw text that automatically wraps within the given rectangle.
        
        Ensures that text does not overlap decorated borders.
        
        Args:
            text: The text to render.
            rect: Target rectangle for text area.
        """
        font = self.font
        font_height: int = font.size("Tg")[1]
        
        words: List[str] = text.split(' ')
        space_width: int = font.size(' ')[0]
        
        # Define margins to account for decorative borders
        x_margin: float = 0.09 * rect.width    # 9% margin necessary for the width
        y_margin: float = 0.12 * rect.height   # 12% margin necessary for the height
        
        # Starting position WITH margin offsets
        x: int = rect.left + int(x_margin/2)  # Add left margin
        y: int = rect.top + int(y_margin/2)   # Add top margin
        
        # Calculate available space for text
        max_x: int = rect.right - int(x_margin/2)  # Right boundary
        max_y: int = rect.bottom - int(y_margin/2)  # Bottom boundary
        
        line_spacing: int = int(font_height * 0.2)  # Add 20% of font height as line spacing
        
        for word in words:
            word_surface = font.render(word, True, BLACK)
            word_width, word_height = word_surface.get_size()
            
            # Check if we need to wrap to the next line
            if x + word_width >= max_x:
                x = rect.left + int(x_margin/2)  # Reset to left margin, not left edge
                y += font_height + line_spacing
                
            # Check if we've exceeded the height and need to stop
            if y + word_height > max_y:
                # Add ellipsis to indicate truncated text
                ellipsis = font.render("...", True, BLACK)
                self.screen.blit(ellipsis, (x, y))
                break
                
            self.screen.blit(word_surface, (x, y))
            x += word_width + space_width
    
    def handle_click(self, pos: Tuple[int, int]) -> Optional[str]:
        """Handle mouse clicks on dialogue options.
        
        Args:
            pos: Mouse coordinates.
            
        Returns:
            Optional[str]: The selected answer text if a button was clicked, else None.
        """
        if not self.active:
            return None
            
        for button_rect, answer in self.buttons:
            if button_rect.collidepoint(pos):
                self.result = answer
                self.active = False
                return answer
        
        return None


# Helper function to create and show a dialogue
def show_dialogue(screen: pygame.Surface, game: 'Game', picture: str = "portrait_merchant", npc_name: str = "Merchant", text: str = "Greetings, traveler!", answers: Optional[List[str]] = None, sound: Optional[str] = None) -> Dialogue:
    """Show a dialogue with an NPC.
    
    Args:
        screen: pygame surface to draw on.
        game: reference to game object.
        picture: string key for portrait image.
        npc_name: name of the NPC to display.
        text: dialogue text.
        answers: list of possible answers.
        sound: name of sound file to play.
        
    Returns:
        Dialogue: The dialogue instance.
    """
    dialogue = Dialogue(screen, game, picture, npc_name, text, answers, sound)
    return dialogue