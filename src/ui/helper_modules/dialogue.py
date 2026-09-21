import pygame
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING
from ...config.colors import *
from ..ui_utils import draw_9slice
from ..text_reveal import LetterReveal

if TYPE_CHECKING:
    from ...game import Game

class Dialogue:
    """A UI component that provides a semi-transparent dialogue window with portraits and options.
    
    Handles word-wrapped text rendering, portrait scaling, and interactive button logic.

    The dialogue text is revealed one letter at a time: each glyph fades in
    and drifts up into place, so several neighbouring letters are always
    mid-fade and the line arrives as a soft wave rather than a hard cursor.
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
        
        # Text area inside the dialogue window (also used by the reveal animation)
        self.text_rect: pygame.Rect = pygame.Rect(
            self.dialogue_rect.x + 20,
            self.dialogue_rect.y + 70,
            self.dialogue_rect.width - 40,
            self.dialogue_rect.height - 150
        )

        # Letter-by-letter reveal state
        self._word_positions: List[Tuple[int, int]] = []
        self._layout_text()

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
            draw_9slice(self.screen, self.game.pic_info_window, self.dialogue_rect)
        else:
            # Fallback to drawing a rectangle
            pygame.draw.rect(self.screen, LIGHT_GRAY, self.dialogue_rect)
            pygame.draw.rect(self.screen, DARK_GRAY, self.dialogue_rect, 2)
        
        # Draw NPC name
        name_text = self.font.render(self.npc_name, True, DARK_BROWN)
        self.screen.blit(name_text, (self.dialogue_rect.x + 60, self.dialogue_rect.y + 25))
        
        # Draw dialogue text (word wrapped, revealed letter by letter)
        self._draw_animated_text()
        
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
    
    def _layout_text(self) -> None:
        """Word-wrap the text once and hand the words to the reveal animation.

        Wrapping matches the plain rendering exactly: each word is rendered
        whole and placed at the same position, so the finished text is
        identical to drawing it in one go.
        """
        font = self.font
        rect = self.text_rect
        font_height: int = font.size("Tg")[1]
        space_width: int = font.size(' ')[0]

        # Margins to account for the decorated borders (as before)
        x_margin: float = 0.09 * rect.width
        y_margin: float = 0.12 * rect.height

        left: int = rect.left + int(x_margin / 2)
        x: int = left
        y: int = rect.top + int(y_margin / 2)
        max_x: int = rect.right - int(x_margin / 2)
        max_y: int = rect.bottom - int(y_margin / 2)
        line_spacing: int = int(font_height * 0.2)

        segments: List[Tuple[pygame.Surface, str]] = []
        self._word_positions = []

        for word in self.text.split(' '):
            word_width, word_height = font.size(word)

            # Wrap to the next line
            if x + word_width >= max_x:
                x = left
                y += font_height + line_spacing

            # Out of vertical room: reveal an ellipsis and stop
            if y + word_height > max_y:
                segments.append((font.render("...", True, BLACK).convert_alpha(), "..."))
                self._word_positions.append((x, y))
                break

            segments.append((font.render(word, True, BLACK).convert_alpha(), word))
            self._word_positions.append((x, y))
            x += word_width + space_width

        self._reveal = LetterReveal(segments, font)

    @property
    def is_text_complete(self) -> bool:
        """True once every letter of the dialogue text has appeared."""
        return self._reveal.is_complete

    def skip_text_animation(self) -> None:
        """Show the whole text at once (used when the player clicks early)."""
        self._reveal.skip()

    def _draw_animated_text(self) -> None:
        """Draw the text, each letter fading in and drifting up into place."""
        self._reveal.draw(self.screen, self._word_positions)

    def handle_click(self, pos: Tuple[int, int]) -> Optional[str]:
        """Handle mouse clicks on dialogue options.
        
        Args:
            pos: Mouse coordinates.
            
        Returns:
            Optional[str]: The selected answer text if a button was clicked, else None.
        """
        if not self.active:
            return None

        # While the text is still appearing, a click finishes it rather than
        # picking an answer - otherwise an eager click selects something the
        # player has not finished reading.
        if not self.is_text_complete:
            self.skip_text_animation()
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