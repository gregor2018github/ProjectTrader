import pygame
from typing import List, Tuple, Optional, Any, TYPE_CHECKING
from .config.colors import LIGHT_GRAY, DARK_GRAY, BLACK, WHITE, RED, GREEN, BLUE, YELLOW, ORANGE, PURPLE, PINK
from .ui.helper_modules.color_wheel import ColorWheel
from .ui.ui_utils import draw_9slice
from .ui.controls_overview import ControlsOverview
from .ui.helper_modules.weather_debug import WeatherDebugPage
from .config import settings_store

if TYPE_CHECKING:
    from .game import Game
    from .models.good import Good

class SettingsWindow:
    """A modal window for configuring game settings, such as commodity colors.
    
    Attributes:
        screen: The pygame surface to draw on.
        font: Font used for UI labels.
        game: Reference to the main Game instance.
        width: Width of the settings window.
        height: Height of the settings window.
        window_rect: Rectangular area for the settings window.
        buttons: List of tuples (rect, label) for footer buttons.
        text: Heading text displayed in the window.
        allowed_colors: List of default color constants.
        color_entries: List of tuples (good_object, clickable_rect).
        active_color_wheel: Currently active ColorWheel instance.
        color_wheel_target: The Good object being edited.
    """

    def __init__(self, screen: pygame.Surface, font: pygame.font.Font, game: Optional['Game'] = None) -> None:
        """Initialize the settings window.
        
        Args:
            screen: The surface to draw on.
            font: Font for text rendering.
            game: Optional reference to the Game object.
        """
        self.screen: pygame.Surface = screen
        self.font: pygame.font.Font = font
        self.game: Optional['Game'] = game
        # Set smaller dimensions than InfoWindow
        self.width: int = screen.get_width() // 2
        self.height: int = 300
        self.window_rect: pygame.Rect = pygame.Rect(0, 0, self.width, self.height)
        self.window_rect.center = (screen.get_width()//2, screen.get_height()//2)
        
        # Create three buttons at the bottom with modified label for reset
        self.buttons: List[Tuple[pygame.Rect, str]] = []
        button_width: int = 140
        button_height: int = 35
        gap: int = 30
        labels: List[str] = ["Save and Close", "Discard", "Default Colors"]
        total_width: int = len(labels) * button_width + (len(labels) - 1) * gap
        start_x: int = self.window_rect.centerx - total_width//2
        y: int = self.window_rect.bottom - 60
        # Changed "Reset All" to "Reset to Standard"
        for i, label in enumerate(labels):
            btn_rect = pygame.Rect(start_x + i*(button_width+gap), y, button_width, button_height)
            self.buttons.append((btn_rect, label))
            
        # Lorem ipsum text
        self.text: str = "Colors of Goods in the Charts"
        
        # Predefined allowed colors for goods
        self.allowed_colors: List[Tuple[int, int, int]] = [RED, GREEN, BLUE, YELLOW, ORANGE, PURPLE, PINK, DARK_GRAY, LIGHT_GRAY, BLACK]
        # Build color entries if game and its goods exist using grid layout (max 4 per column)
        self.color_entries: List[Tuple['Good', pygame.Rect]] = []  # List of tuples: (good, rect)
        if self.game and hasattr(self.game, 'goods'):
            entry_width: int = 20
            entry_height: int = 20
            gap_y: int = 10
            gap_x: int = 80  # horizontal spacing between columns
            start_y: int = self.window_rect.top + 100
            start_x: int = self.window_rect.left + 240
            count: int = 0
            for good in self.game.goods:
                row = count % 4
                col = count // 4
                x = start_x + col * (entry_width + gap_x)
                y = start_y + row * (entry_height + gap_y)
                entry_rect = pygame.Rect(x, y, entry_width, entry_height)
                self.color_entries.append((good, entry_rect))
                count += 1
        # New properties for color wheel overlay
        self.active_color_wheel: Optional[ColorWheel] = None  # Instance of ColorWheel if open
        self.color_wheel_target: Optional['Good'] = None    # The good whose color is being changed
        # Overview of all controls, shown over the chooser while open
        self.controls: Optional[ControlsOverview] = None

        # With the debug overlay on, a page to start any kind of weather
        self.weather_page: Optional[WeatherDebugPage] = None
        weather = getattr(self.game, "weather", None)
        if weather is not None and settings_store.get("show_map_debug"):
            page_rect = pygame.Rect(0, 0, 640, 520)
            page_rect.center = self.window_rect.center
            self.weather_page = WeatherDebugPage(page_rect, weather, font,
                                                 getattr(self.game, "small_font", font),
                                                 getattr(self.game, "lightning", None))

        # The chooser shown first: one button per page, and Close
        self.mode: str = "choose"
        labels = ["Chart Colors", "Controls"] + (["Weather"] if self.weather_page else []) + ["Close"]
        self.choose_rect: pygame.Rect = pygame.Rect(0, 0, 420, 95 + len(labels) * 58 + 31)
        self.choose_rect.center = self.window_rect.center
        self.choose_buttons: List[Tuple[pygame.Rect, str]] = []
        for i, label in enumerate(labels):
            btn_rect = pygame.Rect(0, 0, 240, 42)
            btn_rect.midtop = (self.choose_rect.centerx, self.choose_rect.top + 95 + i * 58)
            self.choose_buttons.append((btn_rect, label))

    def _draw_frame(self, rect: pygame.Rect) -> None:
        """Dim the screen and draw the window's background (the game frame if available)."""
        overlay = pygame.Surface((self.screen.get_width(), self.screen.get_height()))
        overlay.set_alpha(128)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0,0))

        if self.game and hasattr(self.game, 'pic_info_window'):
            draw_9slice(self.screen, self.game.pic_info_window, rect)
        else:
            pygame.draw.rect(self.screen, LIGHT_GRAY, rect)
            pygame.draw.rect(self.screen, DARK_GRAY, rect, 2)

    def _draw_buttons(self, buttons: List[Tuple[pygame.Rect, str]]) -> None:
        """Draw buttons with a hover effect."""
        mouse_pos = pygame.mouse.get_pos()
        for btn_rect, label in buttons:
            is_hovered = btn_rect.collidepoint(mouse_pos)
            btn_color = LIGHT_GRAY if is_hovered else WHITE
            text_color = WHITE if is_hovered else BLACK
            pygame.draw.rect(self.screen, btn_color, btn_rect)
            pygame.draw.rect(self.screen, DARK_GRAY, btn_rect, 2)
            label_surface = self.font.render(label, True, text_color)
            label_rect = label_surface.get_rect(center=btn_rect.center)
            self.screen.blit(label_surface, label_rect)

    def draw(self) -> None:
        """Draw the settings window and all its components."""
        if self.mode == "choose":
            self._draw_frame(self.choose_rect)
            title = self.font.render("Settings", True, BLACK)
            self.screen.blit(title, title.get_rect(center=(self.choose_rect.centerx, self.choose_rect.top + 55)))
            self._draw_buttons(self.choose_buttons)
            if self.controls:
                self.controls.draw(self.screen, pygame.mouse.get_pos())
            return
        if self.mode == "weather":
            self._draw_frame(self.weather_page.rect)
            self.weather_page.draw(self.screen)
            return

        self._draw_frame(self.window_rect)

        # Draw lorem ipsum text (centered in upper part)
        text_surface = self.font.render(self.text, True, BLACK)
        text_rect = text_surface.get_rect(center=(self.window_rect.centerx, self.window_rect.top + 60))
        self.screen.blit(text_surface, text_rect)
        
        # Draw color entries for goods
        for good, rect in self.color_entries:
            # Ensure good.color_temp is a valid color (3-tuple)
            color = good.color_temp if isinstance(good.color_temp, (tuple, list)) and len(good.color_temp) >= 3 else (0, 0, 0)
            pygame.draw.rect(self.screen, color, rect)
            pygame.draw.rect(self.screen, DARK_GRAY, rect, 2)
            name_surface = self.font.render(good.name, True, BLACK)
            name_rect = name_surface.get_rect(midleft=(rect.right + 10, rect.centery))
            self.screen.blit(name_surface, name_rect)
        
        self._draw_buttons(self.buttons)
        # If a color wheel is active, draw it as an overlay.
        if self.active_color_wheel:
            self.active_color_wheel.draw(self.screen)

    def _discard_colors(self) -> None:
        """Revert temporary changes: restore from saved color_current."""
        for good, _ in self.color_entries:
            good.color_temp = good.color_current
            good.color = good.color_temp

    def handle_key(self, event: pygame.event.Event) -> Optional[str]:
        """Keep keys from reaching the game while open.

        Escape steps back: out of the controls overview, the weather page or
        the colors page (discarding its changes) to the chooser, and from the
        chooser out of the settings.
        """
        if event.type != pygame.KEYDOWN:
            return None
        if self.controls:
            if self.controls.handle_key(event):
                self.controls = None
        elif event.key == pygame.K_ESCAPE:
            if self.mode == "choose":
                return "Back"
            if self.mode == "weather":
                self.mode = "choose"
            elif not self.active_color_wheel:
                self._discard_colors()
                self.mode = "choose"
        return None

    def handle_click(self, pos: Tuple[int, int]) -> Optional[str]:
        """Process click interactions within the settings window.
        
        Args:
            pos: The (x, y) mouse position of the click.
            
        Returns:
            Optional[str]: Action label if a function button was clicked, or None.
        """
        if self.mode == "choose":
            if self.controls:
                if self.controls.handle_click(pos):
                    self.controls = None
                return None
            for btn_rect, label in self.choose_buttons:
                if btn_rect.collidepoint(pos):
                    if label == "Chart Colors":
                        self.mode = "colors"
                    elif label == "Controls":
                        self.controls = ControlsOverview(self.screen.get_size())
                    elif label == "Weather":
                        self.mode = "weather"
                    else:
                        return "Back"
            return None
        if self.mode == "weather":
            if self.weather_page.handle_click(pos) == "Back":
                self.mode = "choose"
            return None

        # If a color wheel is active, delegate the click to it.
        if self.active_color_wheel:
            result = self.active_color_wheel.handle_click(pos)
            # If result is None, no confirm/cancel action occurred; keep the wheel open.
            if result is None:
                return None
            elif result == "cancel":
                self.active_color_wheel = None
                self.color_wheel_target = None
            else:
                # Only update if a valid color is confirmed.
                if self.color_wheel_target:
                    self.color_wheel_target.color_temp = result
                    self.color_wheel_target.color = result
                self.active_color_wheel = None
                self.color_wheel_target = None
            return None

        # Otherwise, check if a swatch was clicked.
        for good, rect in self.color_entries:
            if rect.collidepoint(pos):
                center = (self.window_rect.centerx, self.window_rect.centery)
                radius = 120  # Increased radius for a bigger color wheel
                # Pass the font when creating the ColorWheel
                self.active_color_wheel = ColorWheel(center, radius, self.font)
                self.color_wheel_target = good
                return None

        # Check button clicks
        for btn_rect, label in self.buttons:
            if btn_rect.collidepoint(pos):
                if label == "Discard":
                    self._discard_colors()
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
