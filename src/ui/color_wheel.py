import math, pygame, colorsys
from typing import Tuple, Optional, Union
from ..config.colors import LIGHT_GRAY, DARK_GRAY, BLACK, WHITE

class ColorWheel:
    """A UI component that allows users to pick a color from a HSV-based wheel.
    
    Includes a preview square and a confirmation button for finalizing the selection.
    """
    
    def __init__(self, center: Tuple[int, int], radius: int, font: pygame.font.Font) -> None:
        """Initialize the color wheel.
        
        Args:
            center: The (x, y) coordinates for the center of the wheel.
            radius: The radius of the color wheel.
            font: The font used for the "Confirm" button.
        """
        self.font: pygame.font.Font = font
        self.center: Tuple[int, int] = center
        self.radius: int = radius
        diameter: int = int(radius * 2)
        self.surface: pygame.Surface = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
        threshold: float = self.radius * 0.7  # inner region: full brightness
        for x in range(diameter):
            for y in range(diameter):
                dx = x - self.radius
                dy = y - self.radius
                distance = math.hypot(dx, dy)
                if distance <= self.radius:
                    hue = (math.degrees(math.atan2(dy, dx)) % 360) / 360.0
                    sat = distance / self.radius
                    if distance <= threshold:
                        val = 1.0  # full brightness in inner disk
                    else:
                        # Linearly decrease brightness from 1.0 at threshold to 0 at radius
                        val = 1.0 - ((distance - threshold) / (self.radius - threshold))
                    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
                    self.surface.set_at((x, y), (int(r*255), int(g*255), int(b*255), 255))
        pygame.draw.circle(self.surface, (0,0,0), (int(self.radius), int(self.radius)), int(self.radius), 2)
        # New property to store the chosen color from the wheel (None until a click in the circle)
        self.selected_color: Optional[Tuple[int, int, int]] = None
        # Define preview square and confirm button sizes and positions relative to the wheel.
        # They will be drawn under the wheel circle.
        self.preview_size: int = 40
        self.gap: int = 10
        self.confirm_width: int = 80
        self.confirm_height: int = 30
        # Compute positions based on the wheel's center and radius.
        self.preview_rect: pygame.Rect = pygame.Rect(
            self.center[0] - self.preview_size//2,
            self.center[1] + self.radius + self.gap,
            self.preview_size,
            self.preview_size)
        self.confirm_rect: pygame.Rect = pygame.Rect(
            self.center[0] - self.confirm_width//2,
            self.preview_rect.bottom + self.gap,
            self.confirm_width,
            self.confirm_height)

    def draw(self, screen: pygame.Surface) -> None:
        """Render the color wheel and associated UI elements.
        
        Args:
            screen: The surface to draw onto.
        """
        x = self.center[0] - self.radius
        y = self.center[1] - self.radius
        screen.blit(self.surface, (x, y))
        pygame.draw.circle(screen, (0,0,0), self.center, int(self.radius), 2)
        # Draw preview square showing the selected color (if any)
        preview_color = self.selected_color if self.selected_color else (200,200,200)
        pygame.draw.rect(screen, preview_color, self.preview_rect)
        pygame.draw.rect(screen, (0,0,0), self.preview_rect, 2)
        # Draw "Confirm" button with standard styling:
        mouse_pos = pygame.mouse.get_pos()
        if self.confirm_rect.collidepoint(mouse_pos):
            btn_color = LIGHT_GRAY
            text_color = WHITE
        else:
            btn_color = WHITE
            text_color = BLACK
        pygame.draw.rect(screen, btn_color, self.confirm_rect)
        pygame.draw.rect(screen, DARK_GRAY, self.confirm_rect, 2)
        
        confirm_text = self.font.render("Confirm", True, text_color)
        text_rect = confirm_text.get_rect(center=self.confirm_rect.center)
        screen.blit(confirm_text, text_rect)

    def handle_click(self, pos: Tuple[int, int]) -> Optional[Union[Tuple[int, int, int], str]]:
        """Handle mouse clicks on the wheel or the confirm button.
        
        Args:
            pos: The (x, y) coordinates of the click.
            
        Returns:
            - Tuple[int, int, int]: The RGB color if confirmed.
            - "cancel": If the user clicked outside or on confirm without selection.
            - None: If the user just updated the current selection in the wheel.
        """
        # If click in wheel circle, update selected_color but do not confirm
        dx = pos[0] - self.center[0]
        dy = pos[1] - self.center[1]
        distance = math.hypot(dx, dy)
        if distance <= self.radius:
            hue = (math.degrees(math.atan2(dy, dx)) % 360) / 360.0
            sat = distance / self.radius
            threshold = self.radius * 0.7
            if distance <= threshold:
                val = 1.0
            else:
                val = 1.0 - ((distance - threshold) / (self.radius - threshold))
            r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
            self.selected_color = (int(r*255), int(g*255), int(b*255))
            return None
        # If click in confirm button and a color is selected, return the color.
        if self.confirm_rect.collidepoint(pos):
            if self.selected_color:
                return self.selected_color
            return "cancel"
        # Click outside both wheel and our extra UI: cancel operation.
        return "cancel"
