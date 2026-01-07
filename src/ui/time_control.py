import pygame
from typing import Dict, List, Tuple, Any, Optional
from ..config.colors import *

class TimeControl:
    """A UI component for controlling the simulation speed of the game.
    
    Attributes:
        font: The font used for rendering the speed label.
        button_images: Original images for the control buttons.
        control_rect: Rectangular area for the entire control panel.
        button_size: Target size for social media/control buttons.
        resized_buttons: Dictionary of scale-adjusted button images.
        spacing: Pixel spacing between buttons.
        buttons: Dictionary of rects for the slower, start_stop, and faster buttons.
        level_rects: List of rects for the speed level indicator lights.
    """

    def __init__(self, screen_width: int, screen_height: int, font: pygame.font.Font, button_images: Dict[str, pygame.Surface]) -> None:
        """Initialize the time control panel.
        
        Args:
            screen_width: Width of the game screen.
            screen_height: Height of the game screen.
            font: Font for text rendering.
            button_images: Mapping of button names to their source surfaces.
        """
        self.font: pygame.font.Font = font
        self.button_images: Dict[str, pygame.Surface] = button_images
        
        # Set up control panel position and size
        control_width: int = 340
        control_height: int = 50
        self.control_rect: pygame.Rect = pygame.Rect(
            screen_width - control_width -5, # 5 px from right edge
            screen_height - 55,  # Position in bottom bar
            control_width,
            control_height
        )
        
        # Resize button images if they're too large
        self.button_size: int = 45  # Target size for buttons
        self.resized_buttons: Dict[str, pygame.Surface] = {}
        for name, img in button_images.items():
            if img.get_height() > self.button_size or img.get_width() > self.button_size:
                aspect_ratio = img.get_width() / img.get_height()
                new_height = self.button_size
                new_width = int(new_height * aspect_ratio)
                self.resized_buttons[name] = pygame.transform.scale(img, (new_width, new_height))
            else:
                self.resized_buttons[name] = img
        
        # Define button positions
        self.spacing: int = 15
        button_x: int = self.control_rect.x + 163
        button_y: int = self.control_rect.centery - self.button_size // 2 - 1
        
        # Create button rectangles
        self.buttons: Dict[str, pygame.Rect] = {}
        
        # Slower button
        button_img = self.resized_buttons['button_slower_150']
        self.buttons["slower"] = pygame.Rect(
            button_x, button_y, button_img.get_width(), button_img.get_height()
        )
        button_x += button_img.get_width() + self.spacing
        
        # Start/stop button
        button_img = self.resized_buttons['button_start_stop_150']
        self.buttons["start_stop"] = pygame.Rect(
            button_x, button_y, button_img.get_width(), button_img.get_height()
        )
        button_x += button_img.get_width() + self.spacing
        
        # Faster button
        button_img = self.resized_buttons['button_faster_150']
        self.buttons["faster"] = pygame.Rect(
            button_x, button_y, button_img.get_width(), button_img.get_height()
        )
        
        # Time level indicators
        self.level_rects: List[pygame.Rect] = []
        indicator_width: int = 12
        indicator_height: int = 12
        indicator_spacing: int = 5
        total_width: int = (indicator_width * 5) + (indicator_spacing * 4)
        start_x: int = self.control_rect.x - (total_width // 2) + 50
        indicator_y: int = self.control_rect.bottom - 15
        
        for i in range(5):
            self.level_rects.append(
                pygame.Rect(start_x + i * (indicator_width + indicator_spacing), 
                          indicator_y, indicator_width, indicator_height)
            )
        
    def draw(self, screen: pygame.Surface, current_time_level: int) -> None:
        """Draw the time control panel and interactive buttons.
        
        Args:
            screen: The pygame surface to draw on.
            current_time_level: Current speed index (1-5).
        """
        # Draw background panel
        pygame.draw.rect(screen, TAN, self.control_rect)
        pygame.draw.rect(screen, DARK_BROWN, self.control_rect, 2)
        
        # Draw current speed label
        speed_names = {
            1: "Paused",
            2: "Slow",
            3: "Normal",
            4: "Fast",
            5: "Very Fast"
        }
        speed_label = self.font.render(f"Speed: {speed_names[current_time_level]}", True, DARK_BROWN)
        screen.blit(speed_label, (self.control_rect.x + 10, self.control_rect.y + 5))
        
        # Get mouse position for hover effects
        mouse_pos = pygame.mouse.get_pos()
        
        # Draw buttons with hover effects
        for button_name, button_rect in self.buttons.items():
            # Determine if button is being hovered over
            is_hovered = button_rect.collidepoint(mouse_pos)
            
            # Draw the button image
            screen.blit(self.resized_buttons[f'button_{button_name}_150'], button_rect)
            
            # If hovered, draw a semi-transparent dark overlay
            if is_hovered:
                # Create a dark overlay surface with transparency
                overlay = pygame.Surface((button_rect.width, button_rect.height), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 20))  # Black with 20/255 alpha
                screen.blit(overlay, button_rect)
                
                # Add a highlight border
                pygame.draw.rect(screen, DARK_BROWN, button_rect, 1)
        
        # Draw time level indicators
        for i, rect in enumerate(self.level_rects):
            color = PALE_YELLOW if i < current_time_level else LIGHT_GRAY
            pygame.draw.rect(screen, color, rect)
            pygame.draw.rect(screen, DARK_BROWN, rect, 1)
    
    def handle_click(self, pos: Tuple[int, int], current_time_level: int) -> Optional[int]:
        """Handle mouse clicks on the speed control buttons.
        
        Args:
            pos: The (x, y) mouse position of the click.
            current_time_level: The current time level before the click.
            
        Returns:
            Optional[int]: The new time level if a button was clicked, or None.
        """
        for button_name, button_rect in self.buttons.items():
            if button_rect.collidepoint(pos):
                if button_name == "start_stop":
                    return 1 if current_time_level > 1 else 3  # Toggle between pause and normal
                elif button_name == "slower":
                    return max(1, current_time_level - 1)  # Decrease speed by 1
                elif button_name == "faster":
                    return min(5, current_time_level + 1)  # Increase speed by 1
        return None
