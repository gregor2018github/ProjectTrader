import pygame
from .config.colors import LIGHT_GRAY, DARK_GRAY, BLACK, WHITE, RED, GREEN, BLUE, YELLOW, ORANGE, PURPLE, PINK

class SettingsWindow:
    def __init__(self, screen, font, game=None):
        self.screen = screen
        self.font = font
        self.game = game
        # Set smaller dimensions than InfoWindow
        self.width = screen.get_width() // 2
        self.height = 300
        self.window_rect = pygame.Rect(0, 0, self.width, self.height)
        self.window_rect.center = (screen.get_width()//2, screen.get_height()//2)
        
        # Create three buttons at the bottom with modified label for reset
        self.buttons = []
        button_width = 140
        button_height = 35
        gap = 30
        total_width = 3 * button_width + 2 * gap
        start_x = self.window_rect.centerx - total_width//2
        y = self.window_rect.bottom - 60
        # Changed "Reset All" to "Reset to Standard"
        for i, label in enumerate(["Save and Close", "Discard", "Default Colors"]):
            btn_rect = pygame.Rect(start_x + i*(button_width+gap), y, button_width, button_height)
            self.buttons.append((btn_rect, label))
            
        # Lorem ipsum text
        self.text = "Colors of Goods in the Charts"
        
        # Predefined allowed colors for goods
        self.allowed_colors = [RED, GREEN, BLUE, YELLOW, ORANGE, PURPLE, PINK, DARK_GRAY, LIGHT_GRAY, BLACK]
        # Build color entries if game and its goods exist using grid layout (max 4 per column)
        self.color_entries = []  # List of tuples: (good, rect)
        if self.game and hasattr(self.game, 'goods'):
            entry_width = 20
            entry_height = 20
            gap_y = 10
            gap_x = 80  # horizontal spacing between columns
            start_y = self.window_rect.top + 100
            start_x = self.window_rect.left + 240
            count = 0
            for good in self.game.goods:
                row = count % 4
                col = count // 4
                x = start_x + col * (entry_width + gap_x)
                y = start_y + row * (entry_height + gap_y)
                entry_rect = pygame.Rect(x, y, entry_width, entry_height)
                self.color_entries.append((good, entry_rect))
                count += 1

    def draw(self):
        # Draw semi-transparent overlay
        overlay = pygame.Surface((self.screen.get_width(), self.screen.get_height()))
        overlay.set_alpha(128)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0,0))
        
        # Draw background (using game frame image if available)
        if self.game and hasattr(self.game, 'pic_info_window'):
            scaled_frame = pygame.transform.scale(self.game.pic_info_window, (self.width, self.height))
            self.screen.blit(scaled_frame, self.window_rect)
        else:
            pygame.draw.rect(self.screen, LIGHT_GRAY, self.window_rect)
            pygame.draw.rect(self.screen, DARK_GRAY, self.window_rect, 2)
            
        # Draw lorem ipsum text (centered in upper part)
        text_surface = self.font.render(self.text, True, BLACK)
        text_rect = text_surface.get_rect(center=(self.window_rect.centerx, self.window_rect.top + 60))
        self.screen.blit(text_surface, text_rect)
        
        # Draw color entries for goods
        for good, rect in self.color_entries:
            pygame.draw.rect(self.screen, good.color_temp, rect)
            pygame.draw.rect(self.screen, DARK_GRAY, rect, 2)
            name_surface = self.font.render(good.name, True, BLACK)
            name_rect = name_surface.get_rect(midleft=(rect.right + 10, rect.centery))
            self.screen.blit(name_surface, name_rect)
        
        # Draw buttons with hover effect
        mouse_pos = pygame.mouse.get_pos()
        for btn_rect, label in self.buttons:
            is_hovered = btn_rect.collidepoint(mouse_pos)
            btn_color = LIGHT_GRAY if is_hovered else WHITE
            text_color = WHITE if is_hovered else BLACK
            pygame.draw.rect(self.screen, btn_color, btn_rect)
            pygame.draw.rect(self.screen, DARK_GRAY, btn_rect, 2)
            label_surface = self.font.render(label, True, text_color)
            label_rect = label_surface.get_rect(center=btn_rect.center)
            self.screen.blit(label_surface, label_rect)

    def handle_click(self, pos):
        # Check clicks on color entries first – update temporary color and sync drawing property.
        for good, rect in self.color_entries:
            if rect.collidepoint(pos):
                try:
                    idx = self.allowed_colors.index(good.color_temp)
                    good.color_temp = self.allowed_colors[(idx + 1) % len(self.allowed_colors)]
                except ValueError:
                    good.color_temp = self.allowed_colors[0]
                good.color = good.color_temp
                return None

        # Check button clicks
        for btn_rect, label in self.buttons:
            if btn_rect.collidepoint(pos):
                if label == "Discard":
                    # Revert temporary changes: restore from saved color_current.
                    for good, _ in self.color_entries:
                        good.color_temp = good.color_current
                        good.color = good.color_temp
                    return label
                elif label == "Default Colors":
                    # Revert all settings to original defaults from color_orig.
                    for good, _ in self.color_entries:
                        good.color_temp = good.color_orig
                        good.color = good.color_temp
                    return None
                elif label == "Save and Close":
                    # Accept changes: copy temporary color into color_current.
                    for good, _ in self.color_entries:
                        good.color_current = good.color_temp
                        good.color = good.color_temp
                    return label
        return None
