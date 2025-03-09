import pygame
from ..config.colors import *

class TimeControl:
    def __init__(self, screen_width, screen_height, font, button_images):
        self.font = font
        self.button_images = button_images
        
        # Set up control panel position and size
        control_width = 340
        control_height = 50
        self.control_rect = pygame.Rect(
            screen_width - control_width -5, # 5 px from right edge
            screen_height - 55,  # Position in bottom bar
            control_width,
            control_height
        )
        
        # Resize button images if they're too large
        self.button_size = 45  # Target size for buttons
        self.resized_buttons = {}
        for name, img in button_images.items():
            if img.get_height() > self.button_size or img.get_width() > self.button_size:
                aspect_ratio = img.get_width() / img.get_height()
                new_height = self.button_size
                new_width = int(new_height * aspect_ratio)
                self.resized_buttons[name] = pygame.transform.scale(img, (new_width, new_height))
            else:
                self.resized_buttons[name] = img
        
        # Define button positions
        self.spacing = 15
        button_x = self.control_rect.x + 163
        button_y = self.control_rect.centery - self.button_size // 2 - 1
        
        # Create button rectangles
        self.buttons = {}
        
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
        self.level_rects = []
        indicator_width = 12
        indicator_height = 12
        indicator_spacing = 5
        total_width = (indicator_width * 5) + (indicator_spacing * 4)
        start_x = self.control_rect.x - (total_width // 2) + 50
        indicator_y = self.control_rect.bottom - 15
        
        for i in range(5):
            self.level_rects.append(
                pygame.Rect(start_x + i * (indicator_width + indicator_spacing), 
                          indicator_y, indicator_width, indicator_height)
            )
        
    def draw(self, screen, current_time_level):
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
                overlay.fill((0, 0, 0, 20))  # Black with 80/255 alpha (more transparent)
                screen.blit(overlay, button_rect)
                
                # Add a highlight border
                pygame.draw.rect(screen, DARK_BROWN, button_rect, 1)
        
        # Draw time level indicators
        for i, rect in enumerate(self.level_rects):
            color = PALE_YELLOW if i < current_time_level else LIGHT_GRAY
            pygame.draw.rect(screen, color, rect)
            pygame.draw.rect(screen, DARK_BROWN, rect, 1)
    
    def handle_click(self, pos, current_time_level):
        for button_name, button_rect in self.buttons.items():
            if button_rect.collidepoint(pos):
                if button_name == "start_stop":
                    return 1 if current_time_level > 1 else 3  # Toggle between pause and normal
                elif button_name == "slower":
                    return max(1, current_time_level - 1)  # Decrease speed by 1
                elif button_name == "faster":
                    return min(5, current_time_level + 1)  # Increase speed by 1
        return None
